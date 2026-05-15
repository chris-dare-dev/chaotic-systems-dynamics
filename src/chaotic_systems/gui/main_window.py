"""Main window of the native desktop GUI.

Layout
------
::

    +------------------+--------------------+--------------------+
    | system + params  |  3D viewport       |  LaTeX equations   |
    | (left dock)      |  (PyVista QtInter) |  (right dock)      |
    +------------------+--------------------+--------------------+

The left panel exposes:
  - a combo box of available systems (read from the math-agent registry),
  - one labeled spinbox per system parameter, auto-generated from the
    system's parameter schema,
  - an integrator combo box,
  - "Run" and "Export video" buttons.

The center is a ``pyvistaqt.QtInteractor`` driven by :class:`Renderer3D`.
The right panel renders the system's ODE LaTeX (and Lagrangian, if any)
via matplotlib mathtext.

The window is fully usable even before the math agent's registry exists:
it falls back to a built-in Lorenz placeholder so the GUI can be exercised
in isolation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from chaotic_systems.visualization.contract import (
    Parameter,
    SystemLike,
    _coerce_parameter,
    default_params,
    list_systems_safe,
)
from chaotic_systems.visualization.latex import latex_to_qimage
from chaotic_systems.visualization.renderer import Renderer3D

__all__ = ["build_application", "run"]  # ``MainWindow`` is exported lazily via __getattr__


# ---------------------------------------------------------------------------
# Fallback system used when the math-agent registry is missing or empty.
# This is intentionally NOT a "real" implementation — it just keeps the GUI
# launchable in isolation and gives the tests something concrete to render.
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
    parameters: dict[str, Parameter] = {
        "sigma": Parameter("sigma", default=10.0, min=0.0, max=30.0, description="Prandtl"),
        "rho": Parameter("rho", default=28.0, min=0.0, max=60.0, description="Rayleigh"),
        "beta": Parameter("beta", default=8.0 / 3.0, min=0.0, max=10.0, description="geom."),
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
        y0: np.ndarray,
        params: dict[str, float],
        integrator: str = "RK45",
        dt: float = 0.01,
    ) -> Any:
        from scipy.integrate import solve_ivp

        t0, t1 = t_span
        n = max(2, int(round((t1 - t0) / dt)) + 1)
        t_eval = np.linspace(t0, t1, n)
        sol = solve_ivp(
            lambda t, y: self.rhs(t, y, **params),
            (t0, t1),
            y0,
            method=integrator,
            t_eval=t_eval,
            rtol=1e-7,
            atol=1e-9,
        )

        class _Traj:
            pass

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


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


def _build_window_class() -> type:
    """Build the MainWindow class lazily so PySide6 is only imported on demand."""

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import (
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QScrollArea,
        QSplitter,
        QVBoxLayout,
        QWidget,
    )
    from pyvistaqt import QtInteractor

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
            self._integrators: list[str] = list(integrators or ["RK45", "RK23", "DOP853", "LSODA"])
            self._current_renderer: Renderer3D | None = None
            self._param_widgets: dict[str, QDoubleSpinBox] = {}
            self._last_trajectory: Any = None

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
            button_row.addWidget(self.run_button)
            button_row.addWidget(self.export_button)
            left_layout.addLayout(button_row)
            left_layout.addStretch(1)

            # --- center: 3D viewport ---------------------------------------
            self.viewer = QtInteractor(self)
            self.viewer.set_background("white")

            # --- right panel: LaTeX ----------------------------------------
            right = QWidget(self)
            right_layout = QVBoxLayout(right)
            right_layout.setContentsMargins(8, 8, 8, 8)

            right_layout.addWidget(QLabel("Equations of motion:", right))
            self.ode_label = QLabel(right)
            self.ode_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            self.ode_label.setWordWrap(True)
            self.ode_scroll = QScrollArea(right)
            self.ode_scroll.setWidget(self.ode_label)
            self.ode_scroll.setWidgetResizable(True)
            right_layout.addWidget(self.ode_scroll, 1)

            right_layout.addWidget(QLabel("Lagrangian / Hamiltonian:", right))
            self.lagr_label = QLabel(right)
            self.lagr_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            self.lagr_label.setWordWrap(True)
            self.lagr_scroll = QScrollArea(right)
            self.lagr_scroll.setWidget(self.lagr_label)
            self.lagr_scroll.setWidgetResizable(True)
            right_layout.addWidget(self.lagr_scroll, 1)

            # --- assemble ---------------------------------------------------
            splitter = QSplitter(Qt.Orientation.Horizontal, self)
            splitter.addWidget(left)
            splitter.addWidget(self.viewer.interactor)
            splitter.addWidget(right)
            splitter.setStretchFactor(0, 0)
            splitter.setStretchFactor(1, 3)
            splitter.setStretchFactor(2, 1)
            splitter.setSizes([280, 800, 320])
            self.setCentralWidget(splitter)

            self._rebuild_for_current_system()

        # ------------------------------------------------------------------

        @property
        def current_system(self) -> SystemLike:
            """Return the currently selected backend system."""

            idx = max(0, self.system_box.currentIndex())
            return self._systems[idx]

        # ----------------------------------------------------- internal slots

        def _on_system_changed(self, _idx: int) -> None:
            self._rebuild_for_current_system()

        def _rebuild_for_current_system(self) -> None:
            system = self.current_system

            # Clear existing parameter widgets.
            while self._param_form_layout.rowCount() > 0:
                self._param_form_layout.removeRow(0)
            self._param_widgets = {}
            raw_params = getattr(system, "parameters", {}) or {}
            for key, raw in raw_params.items():
                p = _coerce_parameter(key, raw)
                spin = QDoubleSpinBox(self._param_form_host)
                spin.setRange(float(p.min), float(p.max))
                spin.setDecimals(6)
                spin.setSingleStep((float(p.max) - float(p.min)) / 100.0 or 0.01)
                spin.setValue(float(p.default))
                if p.description:
                    spin.setToolTip(p.description)
                self._param_form_layout.addRow(QLabel(f"{p.name}:"), spin)
                self._param_widgets[key] = spin

            # Update LaTeX panels.
            self._render_latex_into(self.ode_label, getattr(system, "latex", "") or "")
            lagr = getattr(system, "lagrangian_latex", None)
            self._render_latex_into(self.lagr_label, lagr or r"\text{(not derived from a Lagrangian)}")

        def _render_latex_into(self, label: Any, latex: str) -> None:
            try:
                image = latex_to_qimage(latex, fontsize=18, dpi=180)
            except Exception as exc:
                label.setText(f"<LaTeX render failed: {exc}>")
                return
            pixmap = QPixmap.fromImage(image)
            label.setPixmap(pixmap)
            label.setFixedSize(pixmap.size())

        def _params(self) -> dict[str, float]:
            return {key: float(spin.value()) for key, spin in self._param_widgets.items()}

        def _simulate(self) -> Any:
            system = self.current_system
            params = self._params() or default_params(system)
            y0 = np.asarray(getattr(system, "initial_state"), dtype=float).copy()
            sim = getattr(system, "simulate", None)
            if sim is None:
                raise RuntimeError(
                    f"System {getattr(system, 'name', system)!r} has no .simulate(); "
                    "the backend may not be installed yet."
                )
            traj = sim(
                (0.0, float(self.t_end.value())),
                y0,
                params,
                integrator=self.integrator_box.currentText(),
                dt=float(self.dt.value()),
            )
            self._last_trajectory = traj
            return traj

        def _on_run(self) -> None:
            try:
                traj = self._simulate()
            except Exception as exc:
                QMessageBox.critical(self, "Simulation failed", str(exc))
                return
            # Replace the viewport content.
            try:
                self.viewer.clear()
            except Exception:
                pass
            renderer = Renderer3D(
                traj,
                title=getattr(self.current_system, "name", "trajectory"),
            )
            renderer.attach(self.viewer)
            self._current_renderer = renderer

        def _on_export(self) -> None:
            traj = self._last_trajectory
            if traj is None:
                try:
                    traj = self._simulate()
                except Exception as exc:
                    QMessageBox.critical(self, "Simulation failed", str(exc))
                    return
            path_str, _ = QFileDialog.getSaveFileName(
                self,
                "Export video",
                str(Path.home() / "trajectory.mp4"),
                "MP4 Video (*.mp4)",
            )
            if not path_str:
                return
            renderer = Renderer3D(
                traj,
                title=getattr(self.current_system, "name", "trajectory"),
            )
            try:
                renderer.render_to_video(path_str, fps=30, duration_seconds=10.0)
            except Exception as exc:
                QMessageBox.critical(self, "Export failed", str(exc))
                return
            QMessageBox.information(self, "Export complete", f"Wrote {path_str}")

        def closeEvent(self, event: Any) -> None:  # type: ignore[override]
            try:
                self.viewer.close()
            except Exception:
                pass
            super().closeEvent(event)

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
# subclasses ``QMainWindow`` (a PySide6 type).
def _make_attr(name: str) -> Any:  # pragma: no cover - trivial
    if name == "MainWindow":
        return _build_window_class()
    raise AttributeError(name)


def __getattr__(name: str) -> Any:  # pragma: no cover - trivial
    return _make_attr(name)
