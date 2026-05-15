"""Main window of the native desktop GUI.

Layout
------
::

    +------------------+--------------------+--------------------+
    | system + params  |  3D viewport       |  LaTeX equations   |
    | (left dock)      |  (PyVista QtInter) |  (right dock)      |
    +------------------+--------------------+--------------------+

The left panel exposes:
  - a combo box of available systems (read from the registry),
  - one labeled parameter widget per system parameter, auto-generated
    from the system's parameter schema. Each widget is a ``QDoubleSpinBox``
    paired with a horizontal slider; parameters that span multiple orders
    of magnitude can opt into a log scale (see :class:`_ParamWidget`).
  - an integrator combo box (populated from the integrator registry),
  - "Run" and "Export video" buttons, plus a "Reset view" button and a
    Cancel button shown while a simulation/export is running,
  - a status-bar progress widget driven by the worker thread.

The center is a ``pyvistaqt.QtInteractor`` driven by :class:`Renderer3D`.
If construction fails (e.g. no OpenGL context) we drop in a placeholder
label so the rest of the GUI stays usable.

The right panel renders the system's ODE LaTeX (and Lagrangian, if any)
via matplotlib mathtext, with hi-DPI awareness.

The window is fully usable even before the registry exists: it falls
back to a built-in Lorenz placeholder so the GUI can be exercised in
isolation. The fallback signature mirrors the real backend exactly.

Keyboard shortcuts
------------------
- Ctrl-R: Run simulation
- Ctrl-E: Export video
- R:      Reset camera
- Esc:    Cancel the running simulation / export
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

from chaotic_systems.visualization.contract import (
    ParameterSpec,
    SystemLike,
    _coerce_parameter,
    default_params,
    list_systems_safe,
)
from chaotic_systems.visualization.latex import latex_to_qimage
from chaotic_systems.visualization.renderer import Renderer3D

__all__ = [
    "MainWindow",  # noqa: F822 - exported lazily via __getattr__ (it's a Qt class)
    "build_application",
    "run",
]


# ---------------------------------------------------------------------------
# Fallback system used when the registry is missing or empty.
# This is intentionally NOT a "real" implementation — it just keeps the GUI
# launchable in isolation and gives the tests something concrete to render.
# Its `simulate` signature mirrors `DynamicalSystem.simulate` (positional
# `t_span`, optional `y0`/`params`, keyword `integrator`/`dt`) so swapping
# in a real system never changes call sites.
# ---------------------------------------------------------------------------


class _FallbackLorenz:
    """Tiny in-GUI Lorenz attractor so the window is always exercise-able."""

    name = "Lorenz (fallback)"
    latex = (
        r"\begin{aligned}"
        r"\dot{x} &= \sigma (y - x) \\"
        r"\dot{y} &= x (\rho - z) - y \\"
        r"\dot{z} &= x y - \beta z"
        r"\end{aligned}"
    )
    lagrangian_latex: str | None = None
    state_dim = 3
    parameters: dict[str, ParameterSpec] = {
        "sigma": ParameterSpec("sigma", default=10.0, min=0.0, max=30.0, description="Prandtl"),
        "rho": ParameterSpec("rho", default=28.0, min=0.0, max=60.0, description="Rayleigh"),
        "beta": ParameterSpec("beta", default=8.0 / 3.0, min=0.0, max=10.0, description="geom."),
    }
    initial_state = np.array([1.0, 1.0, 1.0])

    def rhs(self, t: float, y: np.ndarray, **params: float) -> np.ndarray:
        s = params.get("sigma", 10.0)
        r = params.get("rho", 28.0)
        b = params.get("beta", 8.0 / 3.0)
        x1, x2, x3 = y
        return np.array([s * (x2 - x1), x1 * (r - x3) - x2, x1 * x2 - b * x3])

    def simulate(
        self,
        t_span: tuple[float, float],
        y0: np.ndarray | None = None,
        params: dict[str, float] | None = None,
        *,
        integrator: str = "RK45",
        dt: float | None = 0.01,
        **_kwargs: Any,
    ) -> Any:
        from scipy.integrate import solve_ivp

        merged = {"sigma": 10.0, "rho": 28.0, "beta": 8.0 / 3.0}
        if params:
            merged.update({k: float(v) for k, v in params.items() if k in merged})
        if y0 is None:
            y0 = self.initial_state.copy()
        t0, t1 = t_span
        step = float(dt) if dt else 0.01
        n = max(2, int(round((t1 - t0) / step)) + 1)
        t_eval = np.linspace(t0, t1, n)
        sol = solve_ivp(
            lambda t, y: self.rhs(t, y, **merged),
            (t0, t1),
            y0,
            method=integrator,
            t_eval=t_eval,
            rtol=1e-7,
            atol=1e-9,
        )

        class _Traj:
            state_dim = 3

        traj = _Traj()
        traj.t = sol.t  # type: ignore[attr-defined]
        traj.y = sol.y.T  # type: ignore[attr-defined]
        return traj


def _systems() -> list[SystemLike]:
    """Return the registry's systems, or a single fallback if empty."""

    found = list_systems_safe()
    if found:
        return found
    return [_FallbackLorenz()]  # type: ignore[list-item]


def _integrator_names() -> list[str]:
    """Return the integrator registry's names, with a static fallback."""

    try:
        from chaotic_systems.integrators import list_integrators

        return list_integrators()
    except ImportError:  # pragma: no cover - integrators always ship today
        return ["RK45", "RK23", "DOP853", "LSODA"]


# ---------------------------------------------------------------------------
# Module-level window-class cache so isinstance checks across import paths
# match. Without this, `__getattr__("MainWindow")` in this module and the one
# in `chaotic_systems.gui.__init__` would each build a fresh class.
# ---------------------------------------------------------------------------


_window_class_cache: type | None = None


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


def _build_window_class() -> type:
    """Build the MainWindow class lazily so PySide6 is only imported on demand.

    The result is cached so callers across both ``chaotic_systems.gui`` and
    ``chaotic_systems.gui.main_window`` see the same class object — important
    for ``isinstance(window, MainWindow)`` checks.
    """

    global _window_class_cache
    if _window_class_cache is not None:
        return _window_class_cache

    from PySide6.QtCore import (
        QObject,
        Qt,
        QThread,
        Signal,
    )
    from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
    from PySide6.QtWidgets import (
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QScrollArea,
        QSlider,
        QSplitter,
        QVBoxLayout,
        QWidget,
    )

    try:
        from pyvistaqt import QtInteractor
    except ImportError:  # pragma: no cover - pyvistaqt is a hard runtime dep
        QtInteractor = None  # type: ignore[assignment]

    # -----------------------------------------------------------------------
    # Parameter widget — spinbox + slider, optional log scale.
    # -----------------------------------------------------------------------

    class _ParamWidget(QWidget):
        """A composite (spinbox + slider) widget for a single parameter.

        Step / decimals are derived from the parameter's magnitude. Parameters
        whose range spans >= 3 decades or whose default value is positive and
        many orders of magnitude away from min/max are rendered on a log
        scale.
        """

        def __init__(self, p: ParameterSpec, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self._spec = p

            lo = float(p.min)
            hi = float(p.max)
            default = float(p.default)
            if lo > hi:
                lo, hi = hi, lo

            # Decide on log scale.
            use_log = (
                lo > 0.0
                and hi > 0.0
                and (math.log10(max(hi, 1e-30)) - math.log10(max(lo, 1e-30))) >= 3.0
            )
            self._use_log = use_log

            # Pick a step + decimals that don't waste typing time. Default
            # to 1% of |default| (well-resolved knob) and at least 6 decimals
            # for tiny parameters.
            magnitude = max(abs(default), abs(hi - lo) * 0.01, 1e-6)
            step = magnitude * 0.01 if magnitude > 0 else (hi - lo) / 200.0
            if step <= 0:
                step = 1e-3
            decimals = max(3, int(round(-math.log10(step))) + 2) if step < 1 else 3

            self._spin = QDoubleSpinBox(self)
            self._spin.setRange(lo, hi)
            self._spin.setDecimals(decimals)
            self._spin.setSingleStep(step)
            self._spin.setValue(default)
            if p.description:
                self._spin.setToolTip(p.description)

            self._slider = QSlider(Qt.Orientation.Horizontal, self)
            self._slider.setRange(0, 1000)
            self._slider.setValue(self._to_slider(default))

            self._spin.valueChanged.connect(self._on_spin_changed)
            self._slider.valueChanged.connect(self._on_slider_changed)

            layout = QHBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._spin, 0)
            layout.addWidget(self._slider, 1)

            self._syncing = False

        @property
        def spec(self) -> ParameterSpec:
            return self._spec

        def value(self) -> float:
            return float(self._spin.value())

        # --- internal mapping spinbox <-> slider ---

        def _to_slider(self, val: float) -> int:
            lo = self._spin.minimum()
            hi = self._spin.maximum()
            if hi == lo:
                return 0
            if self._use_log:
                v = math.log10(max(val, 1e-30))
                a = math.log10(max(lo, 1e-30))
                b = math.log10(max(hi, 1e-30))
                frac = (v - a) / (b - a)
            else:
                frac = (val - lo) / (hi - lo)
            frac = max(0.0, min(1.0, frac))
            return int(round(frac * 1000))

        def _from_slider(self, pos: int) -> float:
            lo = self._spin.minimum()
            hi = self._spin.maximum()
            frac = pos / 1000.0
            if self._use_log:
                a = math.log10(max(lo, 1e-30))
                b = math.log10(max(hi, 1e-30))
                return 10.0 ** (a + frac * (b - a))
            return lo + frac * (hi - lo)

        def _on_spin_changed(self, val: float) -> None:
            if self._syncing:
                return
            self._syncing = True
            try:
                self._slider.setValue(self._to_slider(val))
            finally:
                self._syncing = False

        def _on_slider_changed(self, pos: int) -> None:
            if self._syncing:
                return
            self._syncing = True
            try:
                self._spin.setValue(self._from_slider(pos))
            finally:
                self._syncing = False

    # -----------------------------------------------------------------------
    # Worker objects — run sim and export on QThreads off the Qt main loop.
    # -----------------------------------------------------------------------

    class _SimulateWorker(QObject):
        """Run `system.simulate(...)` on a worker thread."""

        finished = Signal(object)  # Trajectory-like
        error = Signal(str, str)  # (kind, message)

        def __init__(
            self,
            system: SystemLike,
            t_span: tuple[float, float],
            y0: np.ndarray,
            params: dict[str, float],
            integrator: str,
            dt: float,
        ) -> None:
            super().__init__()
            self._system = system
            self._t_span = t_span
            self._y0 = y0
            self._params = params
            self._integrator = integrator
            self._dt = dt

        def run(self) -> None:
            try:
                traj = self._system.simulate(
                    self._t_span,
                    self._y0,
                    self._params,
                    integrator=self._integrator,
                    dt=self._dt,
                )
            except KeyError as exc:
                self.error.emit("KeyError", str(exc))
                return
            except RuntimeError as exc:
                self.error.emit("RuntimeError", str(exc))
                return
            except ValueError as exc:
                self.error.emit("ValueError", str(exc))
                return
            except ImportError as exc:
                self.error.emit("ImportError", str(exc))
                return
            except Exception as exc:  # pragma: no cover - last-resort guard
                self.error.emit("Exception", f"{type(exc).__name__}: {exc}")
                return
            self.finished.emit(traj)

    class _ExportWorker(QObject):
        """Render the trajectory to MP4 on a worker thread, with progress."""

        finished = Signal(str)  # path
        error = Signal(str, str)
        progress = Signal(int, int)  # (current, total)

        def __init__(
            self,
            trajectory: Any,
            title: str,
            path: str,
            fps: int = 30,
            duration_seconds: float = 10.0,
            size: tuple[int, int] = (1280, 720),
        ) -> None:
            super().__init__()
            self._traj = trajectory
            self._title = title
            self._path = path
            self._fps = fps
            self._duration = duration_seconds
            self._size = size
            self._cancelled = False

        def cancel(self) -> None:
            self._cancelled = True

        def _is_cancelled(self) -> bool:
            return self._cancelled

        def _emit_progress(self, i: int, n: int) -> None:
            self.progress.emit(i, n)

        def run(self) -> None:
            try:
                renderer = Renderer3D(self._traj, title=self._title)
                renderer.render_to_video(
                    self._path,
                    fps=self._fps,
                    duration_seconds=self._duration,
                    size=self._size,
                    progress=self._emit_progress,
                    cancel=self._is_cancelled,
                )
            except ImportError as exc:
                self.error.emit("ImportError", str(exc))
                return
            except (RuntimeError, ValueError) as exc:
                self.error.emit(type(exc).__name__, str(exc))
                return
            except Exception as exc:  # pragma: no cover - last-resort guard
                self.error.emit("Exception", f"{type(exc).__name__}: {exc}")
                return
            self.finished.emit(self._path)

    # -----------------------------------------------------------------------
    # The actual main window.
    # -----------------------------------------------------------------------

    class _MainWindow(QMainWindow):
        """Top-level window for the chaotic-systems-dynamics GUI."""

        def __init__(
            self,
            systems: list[SystemLike] | None = None,
            *,
            integrators: list[str] | None = None,
            preselect: str | None = None,
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            self.setWindowTitle("chaotic-systems-dynamics")
            self.resize(1400, 800)

            self._systems: list[SystemLike] = list(systems) if systems else _systems()
            self._integrators: list[str] = list(integrators or _integrator_names())
            self._current_renderer: Renderer3D | None = None
            self._param_widgets: dict[str, _ParamWidget] = {}
            self._last_trajectory: Any = None

            # Worker-thread state.
            self._sim_thread: QThread | None = None
            self._sim_worker: _SimulateWorker | None = None
            self._export_thread: QThread | None = None
            self._export_worker: _ExportWorker | None = None

            # --- left panel -------------------------------------------------
            left = QWidget(self)
            left_layout = QVBoxLayout(left)
            left_layout.setContentsMargins(8, 8, 8, 8)

            self.system_box = QComboBox(left)
            for sys_obj in self._systems:
                self.system_box.addItem(getattr(sys_obj, "name", repr(sys_obj)))
            if preselect is not None:
                idx = self.system_box.findText(preselect)
                if idx >= 0:
                    self.system_box.setCurrentIndex(idx)
            self.system_box.currentIndexChanged.connect(self._on_system_changed)
            left_layout.addWidget(QLabel("System:", left))
            left_layout.addWidget(self.system_box)

            self._param_form_host = QWidget(left)
            self._param_form_layout = QFormLayout(self._param_form_host)
            self._param_form_layout.setContentsMargins(0, 0, 0, 0)
            left_layout.addWidget(QLabel("Parameters:", left))
            left_layout.addWidget(self._param_form_host)

            self.integrator_box = QComboBox(left)
            for name in self._integrators:
                self.integrator_box.addItem(name)
            # Default to RK45 if present.
            default_idx = self.integrator_box.findText("RK45")
            if default_idx >= 0:
                self.integrator_box.setCurrentIndex(default_idx)
            left_layout.addWidget(QLabel("Integrator:", left))
            left_layout.addWidget(self.integrator_box)

            self.t_end = QDoubleSpinBox(left)
            self.t_end.setRange(0.1, 1e4)
            self.t_end.setDecimals(2)
            self.t_end.setValue(40.0)
            self.dt = QDoubleSpinBox(left)
            self.dt.setRange(1e-5, 1.0)
            self.dt.setDecimals(5)
            self.dt.setValue(0.01)
            left_layout.addWidget(QLabel("t_end (s):", left))
            left_layout.addWidget(self.t_end)
            left_layout.addWidget(QLabel("dt (s):", left))
            left_layout.addWidget(self.dt)

            button_row = QHBoxLayout()
            self.run_button = QPushButton("Run", left)
            self.run_button.clicked.connect(self._on_run)
            self.export_button = QPushButton("Export video", left)
            self.export_button.clicked.connect(self._on_export)
            self.cancel_button = QPushButton("Cancel", left)
            self.cancel_button.clicked.connect(self._on_cancel)
            self.cancel_button.setEnabled(False)
            self.reset_view_button = QPushButton("Reset view", left)
            self.reset_view_button.clicked.connect(self._on_reset_view)
            button_row.addWidget(self.run_button)
            button_row.addWidget(self.export_button)
            button_row.addWidget(self.cancel_button)
            button_row.addWidget(self.reset_view_button)
            left_layout.addLayout(button_row)

            # Progress + status.
            self.progress_bar = QProgressBar(left)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(False)
            left_layout.addWidget(self.progress_bar)
            self.status_label = QLabel("", left)
            self.status_label.setWordWrap(True)
            left_layout.addWidget(self.status_label)

            # Current state readout.
            self.state_label = QLabel("y(t_end) = (no simulation yet)", left)
            self.state_label.setWordWrap(True)
            left_layout.addWidget(QLabel("Current state:", left))
            left_layout.addWidget(self.state_label)

            left_layout.addStretch(1)

            # --- center: 3D viewport ---------------------------------------
            self.viewer: Any = None
            viewer_widget: QWidget
            if QtInteractor is None:
                viewer_widget = QLabel(
                    "3D viewport unavailable: pyvistaqt is not installed."
                )
                viewer_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            else:
                try:
                    self.viewer = QtInteractor(self)
                    self.viewer.set_background("white")
                    viewer_widget = self.viewer.interactor
                except Exception as exc:  # pragma: no cover - depends on display
                    label = QLabel(
                        "3D viewport unavailable on this display\n"
                        f"({type(exc).__name__}: {exc})"
                    )
                    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    viewer_widget = label
                    self.viewer = None

            # --- right panel: LaTeX ----------------------------------------
            right = QWidget(self)
            right_layout = QVBoxLayout(right)
            right_layout.setContentsMargins(8, 8, 8, 8)

            right_layout.addWidget(QLabel("Equations of motion:", right))
            self.ode_label = QLabel(right)
            self.ode_label.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
            )
            self.ode_label.setWordWrap(True)
            self.ode_scroll = QScrollArea(right)
            self.ode_scroll.setWidget(self.ode_label)
            self.ode_scroll.setWidgetResizable(True)
            right_layout.addWidget(self.ode_scroll, 1)

            right_layout.addWidget(QLabel("Lagrangian / Hamiltonian:", right))
            self.lagr_label = QLabel(right)
            self.lagr_label.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
            )
            self.lagr_label.setWordWrap(True)
            self.lagr_scroll = QScrollArea(right)
            self.lagr_scroll.setWidget(self.lagr_label)
            self.lagr_scroll.setWidgetResizable(True)
            right_layout.addWidget(self.lagr_scroll, 1)

            # --- assemble ---------------------------------------------------
            splitter = QSplitter(Qt.Orientation.Horizontal, self)
            splitter.addWidget(left)
            splitter.addWidget(viewer_widget)
            splitter.addWidget(right)
            splitter.setStretchFactor(0, 0)
            splitter.setStretchFactor(1, 3)
            splitter.setStretchFactor(2, 1)
            splitter.setSizes([320, 800, 320])
            self.setCentralWidget(splitter)

            # Keyboard shortcuts.
            QShortcut(QKeySequence("Ctrl+R"), self, activated=self._on_run)
            QShortcut(QKeySequence("Ctrl+E"), self, activated=self._on_export)
            QShortcut(QKeySequence("R"), self, activated=self._on_reset_view)
            QShortcut(QKeySequence("Esc"), self, activated=self._on_cancel)

            self._rebuild_for_current_system()

        # ------------------------------------------------------------------

        @property
        def current_system(self) -> SystemLike:
            """Return the currently selected backend system."""

            idx = self.system_box.currentIndex()
            if idx < 0 or idx >= len(self._systems):
                raise IndexError("no system is currently selected")
            return self._systems[idx]

        # ----------------------------------------------------- internal slots

        def _on_system_changed(self, _idx: int) -> None:
            self._rebuild_for_current_system()

        def _clear_param_form(self) -> None:
            """Empty the parameter form, scheduling widget deletion."""

            while self._param_form_layout.rowCount() > 0:
                self._param_form_layout.removeRow(0)
            for widget in self._param_widgets.values():
                widget.deleteLater()
            self._param_widgets = {}

        def _rebuild_for_current_system(self) -> None:
            system = self.current_system
            self._clear_param_form()
            raw_params = getattr(system, "parameters", {}) or {}
            for key, raw in raw_params.items():
                p = _coerce_parameter(key, raw)
                w = _ParamWidget(p, self._param_form_host)
                label_text = f"{p.name}:"
                self._param_form_layout.addRow(QLabel(label_text), w)
                self._param_widgets[key] = w

            # Update LaTeX panels.
            self._render_latex_into(self.ode_label, getattr(system, "latex", "") or "")
            lagr = getattr(system, "lagrangian_latex", None)
            self._render_latex_into(
                self.lagr_label,
                lagr or r"\text{(not derived from a Lagrangian)}",
            )

        def _render_latex_into(self, label: Any, latex: str) -> None:
            # Hi-DPI: render at dpi * device-pixel-ratio for crisp output.
            try:
                screen = self.screen()
                dpr = float(screen.devicePixelRatio()) if screen is not None else 1.0
            except (AttributeError, RuntimeError):  # pragma: no cover
                dpr = 1.0
            try:
                image = latex_to_qimage(latex, fontsize=18, dpi=int(180 * dpr))
                image.setDevicePixelRatio(dpr)
            except Exception as exc:
                label.setText(f"<LaTeX render failed: {exc}>")
                return
            pixmap = QPixmap.fromImage(image)
            pixmap.setDevicePixelRatio(dpr)
            label.setPixmap(pixmap)
            label.setFixedSize(int(pixmap.width() / dpr), int(pixmap.height() / dpr))

        def _params(self) -> dict[str, float]:
            return {key: w.value() for key, w in self._param_widgets.items()}

        # ----------------------------------------------------- run pipeline

        def _on_run(self) -> None:
            if self._sim_thread is not None:
                self._set_status("Simulation already running.")
                return
            try:
                system = self.current_system
                params = self._params() or default_params(system)
                y0 = np.asarray(system.initial_state, dtype=float).copy()
                if not np.isfinite(y0).all():
                    raise ValueError("system initial state has non-finite entries")
                t_end = float(self.t_end.value())
                if t_end <= 0.0:
                    raise ValueError("t_end must be positive")
                if "simulate" not in dir(system):
                    raise RuntimeError(
                        f"system {getattr(system, 'name', system)!r} has no .simulate() method"
                    )
                integrator = self.integrator_box.currentText()
                # Probe the integrator name early so an unknown choice fails
                # cleanly rather than blowing up inside the worker.
                try:
                    from chaotic_systems.integrators import get_integrator

                    get_integrator(integrator)
                except (ImportError, KeyError):
                    pass  # unknown integrators are surfaced by the worker
            except (KeyError, ValueError, RuntimeError) as exc:
                self._show_error("Invalid run configuration", str(exc))
                return

            self._set_status(f"Running {system.name} with {integrator}...", busy=True)
            self.run_button.setEnabled(False)
            self.export_button.setEnabled(False)
            self.cancel_button.setEnabled(True)
            self.progress_bar.setVisible(True)
            # Indeterminate progress for live sim.
            self.progress_bar.setRange(0, 0)

            worker = _SimulateWorker(
                system=system,
                t_span=(0.0, t_end),
                y0=y0,
                params=params,
                integrator=integrator,
                dt=float(self.dt.value()),
            )
            thread = QThread(self)
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.finished.connect(self._on_sim_finished)
            worker.error.connect(self._on_sim_error)
            worker.finished.connect(thread.quit)
            worker.error.connect(thread.quit)
            thread.finished.connect(self._cleanup_sim_thread)
            self._sim_thread = thread
            self._sim_worker = worker
            thread.start()

        def _on_sim_finished(self, traj: Any) -> None:
            self._last_trajectory = traj
            self._update_state_label(traj)
            if self.viewer is not None:
                try:
                    self.viewer.clear()
                except (AttributeError, RuntimeError):
                    pass
                try:
                    system = self.current_system
                    axes_labels = self._axes_labels_for(system)
                    renderer = Renderer3D(
                        traj,
                        title=getattr(system, "name", "trajectory"),
                        axes_labels=axes_labels,
                    )
                    renderer.attach(self.viewer)
                    self._current_renderer = renderer
                except (ValueError, RuntimeError) as exc:
                    self._show_error("Render failed", str(exc))
            self._set_status("Simulation complete.")

        def _on_sim_error(self, kind: str, message: str) -> None:
            self._show_error(f"Simulation failed ({kind})", self._hinted(kind, message))

        def _cleanup_sim_thread(self) -> None:
            if self._sim_worker is not None:
                self._sim_worker.deleteLater()
            if self._sim_thread is not None:
                self._sim_thread.deleteLater()
            self._sim_thread = None
            self._sim_worker = None
            self.run_button.setEnabled(True)
            self.export_button.setEnabled(True)
            self.cancel_button.setEnabled(self._export_thread is not None)
            self.progress_bar.setVisible(self._export_thread is not None)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)

        # ----------------------------------------------------- export pipeline

        def _on_export(self) -> None:
            if self._export_thread is not None:
                self._set_status("Export already running.")
                return
            traj = self._last_trajectory
            if traj is None:
                self._set_status("Run a simulation before exporting.")
                return
            path_str, _ = QFileDialog.getSaveFileName(
                self,
                "Export video",
                str(Path.home() / "trajectory.mp4"),
                "MP4 Video (*.mp4)",
            )
            if not path_str:
                return

            self._set_status(f"Exporting to {path_str}...", busy=True)
            self.run_button.setEnabled(False)
            self.export_button.setEnabled(False)
            self.cancel_button.setEnabled(True)
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)

            worker = _ExportWorker(
                trajectory=traj,
                title=getattr(self.current_system, "name", "trajectory"),
                path=path_str,
                fps=30,
                duration_seconds=10.0,
            )
            thread = QThread(self)
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.progress.connect(self._on_export_progress)
            worker.finished.connect(self._on_export_finished)
            worker.error.connect(self._on_export_error)
            worker.finished.connect(thread.quit)
            worker.error.connect(thread.quit)
            thread.finished.connect(self._cleanup_export_thread)
            self._export_thread = thread
            self._export_worker = worker
            thread.start()

        def _on_export_progress(self, current: int, total: int) -> None:
            if total <= 0:
                return
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)

        def _on_export_finished(self, path: str) -> None:
            self._set_status(f"Wrote {path}")
            QMessageBox.information(self, "Export complete", f"Wrote {path}")

        def _on_export_error(self, kind: str, message: str) -> None:
            self._show_error(f"Export failed ({kind})", self._hinted(kind, message))

        def _cleanup_export_thread(self) -> None:
            if self._export_worker is not None:
                self._export_worker.deleteLater()
            if self._export_thread is not None:
                self._export_thread.deleteLater()
            self._export_thread = None
            self._export_worker = None
            self.run_button.setEnabled(True)
            self.export_button.setEnabled(True)
            self.cancel_button.setEnabled(False)
            self.progress_bar.setVisible(False)
            self.progress_bar.setValue(0)

        def _on_cancel(self) -> None:
            cancelled = False
            if self._export_worker is not None:
                self._export_worker.cancel()
                cancelled = True
                self._set_status("Cancelling export...")
            # Sim cancellation isn't well-defined for scipy/internal integrators
            # without intrusive callbacks; the cancel button is wired up so the
            # user can clear an in-flight export. For sim, we just acknowledge.
            if self._sim_thread is not None and not cancelled:
                self._set_status(
                    "Simulation cannot be cancelled mid-step; it will finish soon."
                )

        # ------------------------------------------------------------------

        def _on_reset_view(self) -> None:
            if self._current_renderer is not None:
                self._current_renderer.reset_camera()

        def _axes_labels_for(self, system: SystemLike) -> tuple[str, str, str] | None:
            name = getattr(system, "name", "")
            if name == "HenonHeiles":
                return ("x", "y", "p_x")
            if name == "DoublePendulum":
                return ("theta1", "theta2", "theta1_dot")
            state_dim = int(getattr(system, "state_dim", 3) or 3)
            if state_dim >= 3:
                return ("x", "y", "z")
            return None

        def _update_state_label(self, traj: Any) -> None:
            try:
                y = np.asarray(traj.y)
                last = y[-1]
                t_last = float(np.asarray(traj.t)[-1])
                # Trim long state vectors for readability.
                pretty = ", ".join(f"{v:+.4g}" for v in last[:8])
                if last.shape[0] > 8:
                    pretty += ", ..."
                self.state_label.setText(f"y(t={t_last:.3f}) = [{pretty}]")
            except (AttributeError, IndexError, ValueError):
                self.state_label.setText("y(t_end) = <unavailable>")

        # ----------------------------------------------------- diagnostics

        @staticmethod
        def _hinted(kind: str, message: str) -> str:
            if kind == "RuntimeError" and "solve_ivp" in message.lower():
                return (
                    message
                    + "\n\nHint: the integrator failed. Try a smaller dt, a "
                    "tighter tolerance, or switch to LSODA / DOP853 for stiffer "
                    "problems."
                )
            if kind == "ImportError":
                return (
                    message
                    + "\n\nHint: a dependency is missing. Re-install with "
                    "`pip install -e .[dev]`."
                )
            if kind == "KeyError":
                return (
                    message
                    + "\n\nHint: an unknown parameter or system name was passed in."
                )
            return message

        def _set_status(self, text: str, *, busy: bool = False) -> None:
            self.status_label.setText(text)
            self.setCursor(Qt.CursorShape.WaitCursor if busy else Qt.CursorShape.ArrowCursor)

        def _show_error(self, title: str, message: str) -> None:
            self._set_status(message)
            QMessageBox.critical(self, title, message)

        # ------------------------------------------------------------------

        def closeEvent(self, event: Any) -> None:  # type: ignore[override]
            # Best-effort cleanup so we don't leave background threads dangling.
            for thread in (self._sim_thread, self._export_thread):
                if thread is not None:
                    thread.quit()
                    thread.wait(2000)
            if self.viewer is not None:
                try:
                    self.viewer.close()
                except (AttributeError, RuntimeError):
                    pass
            super().closeEvent(event)

    # Side-attach the inner widget class for testing.
    _MainWindow._ParamWidget = _ParamWidget  # type: ignore[attr-defined]
    _window_class_cache = _MainWindow
    return _MainWindow


def build_application(argv: list[str] | None = None) -> tuple[Any, Any]:
    """Construct ``QApplication`` and :class:`MainWindow`.

    Returns ``(app, window)`` without calling ``app.exec()`` — useful for
    tests and for callers that want to customize the window before showing it.
    """

    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    window_cls = _build_window_class()
    window = window_cls()
    return app, window


def run(argv: list[str] | None = None) -> int:
    """Build the application, show the window, and run the Qt event loop."""

    app, window = build_application(argv)
    window.show()
    return int(app.exec())


# ``MainWindow`` is a public name; the actual class is built lazily because it
# subclasses ``QMainWindow`` (a PySide6 type) and the build is cached so
# isinstance checks across import paths match.
def __getattr__(name: str) -> Any:  # pragma: no cover - trivial
    if name == "MainWindow":
        return _build_window_class()
    raise AttributeError(name)
