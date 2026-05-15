"""Main window of the native desktop GUI.

Layout
------
::

    +-------------------------------------------------------------+
    |  QToolBar:  Run | Pause | Stop | Jump-to-end | Export ...   |
    +------------------+--------------------+---------------------+
    |  System          |  3D viewport       |  Mathematics        |
    |  Parameters      |  (PyVista          |    Equations of     |
    |  Integrator      |   QtInteractor)    |     motion          |
    |  Time range      |   + transport      |    Lagrangian /     |
    |  Export          |     scrubber       |     Hamiltonian     |
    +------------------+--------------------+---------------------+
    |  QStatusBar: state | frame i / N | t = ... | lambda1 = ...  |
    +-------------------------------------------------------------+

The left panel groups controls into card-style ``QGroupBox`` widgets
(see ``docs/ui_design.md``). The center is a ``pyvistaqt.QtInteractor``
driven by :class:`Renderer3D` with a bottom transport strip
(play/pause/stop/jump-to-end/speed/scrubber). If construction fails
(e.g. no OpenGL context) we drop in a placeholder label so the rest of
the GUI stays usable. The right panel renders the system's ODE LaTeX
(and Lagrangian, if any) via matplotlib mathtext.

Theming
-------
The dark Tokyo Night Storm QSS is applied in :func:`build_application`
via :func:`chaotic_systems.gui.theme.apply_theme`. Renderer colors and
LaTeX glyph color both read from the palette so they stay coherent if
the theme switches.

Transport actions
-----------------
The toolbar exposes ``QAction``s with stable object names so the same
control surface is available to scripts and external agents:

    transport_run, transport_pause, transport_stop, transport_jump_end,
    action_export, action_reset_view, action_toggle_theme

Use :meth:`MainWindow.transport_actions` to fetch the dict at runtime.
The bottom transport strip below the viewport remains the primary user
control surface; the toolbar is a parallel binding for shortcuts and
discoverability.

The window is fully usable even before the registry exists: it falls
back to a built-in Lorenz placeholder so the GUI can be exercised in
isolation. The fallback signature mirrors the real backend exactly.

Keyboard shortcuts
------------------
- Ctrl-R: Run simulation
- Ctrl-E: Export video
- R:      Reset camera
- Esc:    Cancel the running simulation / export
- Space:  Play / Pause
- Ctrl-.: Stop and rewind
- End:    Jump to last frame
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
        QSize,
        Qt,
        QThread,
        QTimer,
        Signal,
    )
    from PySide6.QtGui import (
        QAction,
        QImage,
        QKeySequence,
        QPalette,
        QPixmap,
        QShortcut,
    )
    from PySide6.QtWidgets import (
        QApplication,
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QFrame,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QSlider,
        QSplitter,
        QStatusBar,
        QStyle,
        QToolBar,
        QVBoxLayout,
        QWidget,
    )

    try:
        from pyvistaqt import QtInteractor
    except ImportError:  # pragma: no cover - pyvistaqt is a hard runtime dep
        QtInteractor = None  # type: ignore[assignment]

    def _palette_text_color_hex(widget: QWidget) -> str:
        """Return the active palette's foreground text color as a hex string.

        Used to keep LaTeX glyphs legible on whatever theme Qt is using —
        dark on light, light on dark. Falls back to a neutral mid-gray if
        the palette query fails for any reason.
        """

        try:
            color = widget.palette().color(QPalette.ColorRole.WindowText)
            return color.name()  # "#RRGGBB"
        except Exception:  # pragma: no cover - defensive
            return "#cccccc"

    # -----------------------------------------------------------------------
    # LaTeX flowing widget — scales rendered pixmaps to fit the available
    # width, never overflows horizontally. Multi-row aligned environments
    # are stacked into per-row labels so each row scales independently.
    # -----------------------------------------------------------------------

    class _LatexRow(QLabel):
        """A single LaTeX row label that scales its cached pixmap to fit width.

        The high-DPI source pixmap is rendered once (in the renderer thread,
        via matplotlib) and cached on the instance. Resizes only trigger a
        cheap ``Qt.SmoothTransformation`` scale of the already-rasterized
        pixmap — never a re-render through matplotlib.
        """

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            # `setScaledContents` would distort the aspect ratio; we do the
            # scaling ourselves to preserve it.
            self.setScaledContents(False)
            self._source_pixmap: QPixmap | None = None
            self._dpr: float = 1.0
            self.setMinimumHeight(1)

        def set_source(self, pixmap: QPixmap, dpr: float) -> None:
            """Install a fresh high-DPI source pixmap and reflow."""

            self._source_pixmap = pixmap
            self._dpr = max(float(dpr), 1.0)
            self._reflow()

        def clear_source(self) -> None:
            self._source_pixmap = None
            self.clear()

        def _logical_source_width(self) -> int:
            if self._source_pixmap is None or self._source_pixmap.isNull():
                return 0
            return int(self._source_pixmap.width() / self._dpr)

        def _logical_source_height(self) -> int:
            if self._source_pixmap is None or self._source_pixmap.isNull():
                return 0
            return int(self._source_pixmap.height() / self._dpr)

        def _reflow(self) -> None:
            if self._source_pixmap is None or self._source_pixmap.isNull():
                return
            avail = max(1, self.width())
            src_w = self._logical_source_width()
            src_h = self._logical_source_height()
            if src_w <= 0 or src_h <= 0:
                return
            if src_w <= avail:
                # Pixmap already fits — show at native size.
                display = self._source_pixmap
                logical_w = src_w
                logical_h = src_h
            else:
                # Scale down proportionally. We scale to the device-pixel size
                # the smooth transform expects, then set the DPR so Qt draws
                # the correct logical size.
                target_logical_w = avail
                ratio = target_logical_w / src_w
                target_logical_h = max(1, int(src_h * ratio))
                target_device_w = int(target_logical_w * self._dpr)
                target_device_h = int(target_logical_h * self._dpr)
                display = self._source_pixmap.scaled(
                    target_device_w,
                    target_device_h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                display.setDevicePixelRatio(self._dpr)
                logical_w = target_logical_w
                logical_h = target_logical_h
            self.setPixmap(display)
            self.setFixedHeight(logical_h)
            # We are allowed to shrink horizontally; only the height is fixed.
            self.setMinimumWidth(0)
            self.setMaximumWidth(16777215)
            _ = logical_w  # used implicitly by the layout

        def resizeEvent(self, event: Any) -> None:  # type: ignore[override]
            super().resizeEvent(event)
            self._reflow()

    class _FlowingLatex(QWidget):
        """A widget that lays out one or more rendered LaTeX rows vertically.

        Each row is an independent ``_LatexRow``. The widget never produces
        horizontal overflow: rows wider than the available width are scaled
        down proportionally. If the panel shrinks below a sane minimum
        (``min_width`` px), the parent scroll area can still scroll
        *vertically* but horizontal overflow is suppressed.

        Re-rendering through matplotlib happens only inside :meth:`set_latex`.
        Resizes only trigger ``QPixmap.scaled``.
        """

        # Minimum logical width at which the widget will still try to scale
        # the equation. Below this the rows display at this width and the
        # parent QScrollArea (if any) takes over.
        MIN_WIDTH_PX = 120

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self._layout = QVBoxLayout(self)
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._layout.setSpacing(4)
            self._layout.addStretch(1)
            self._rows: list[_LatexRow] = []
            self._fallback_label: QLabel | None = None
            self.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
            self.setMinimumWidth(self.MIN_WIDTH_PX)
            # Track the latest render config so callers can re-render on
            # palette / DPI change without re-passing all the arguments.
            self._last_latex: str = ""
            self._last_color: str = "#000000"
            self._last_dpi: int = 120
            self._last_fontsize: int = 13
            self._last_dpr: float = 1.0

        # -- public API ---------------------------------------------------

        def set_latex(
            self,
            latex: str,
            *,
            color: str,
            fontsize: int = 13,
            dpi: int = 120,
            dpr: float = 1.0,
        ) -> None:
            """Render ``latex`` into the widget. One row per equation line."""

            from chaotic_systems.visualization.latex import _strip_alignment_env

            self._last_latex = latex
            self._last_color = color
            self._last_dpi = dpi
            self._last_fontsize = fontsize
            self._last_dpr = max(float(dpr), 1.0)

            self._clear_rows()
            self._clear_fallback()
            if not latex:
                return

            rows = _strip_alignment_env(latex)
            target_dpi = int(self._last_dpi * self._last_dpr)
            try:
                for row_latex in rows:
                    image = self._render_one(row_latex, color, fontsize, target_dpi)
                    if image is None:
                        continue
                    pixmap = QPixmap.fromImage(image)
                    pixmap.setDevicePixelRatio(self._last_dpr)
                    row_widget = _LatexRow(self)
                    row_widget.set_source(pixmap, self._last_dpr)
                    # Insert *before* the trailing stretch so rows pack from
                    # the top.
                    insert_at = max(0, self._layout.count() - 1)
                    self._layout.insertWidget(insert_at, row_widget)
                    self._rows.append(row_widget)
            except Exception as exc:  # noqa: BLE001 — surfaced as a fallback label
                self._install_fallback(f"<LaTeX render failed: {exc}>")
                return

            if not self._rows:
                self._install_fallback("<LaTeX produced no rows>")

        def rerender_at(self, *, color: str, dpr: float) -> None:
            """Re-render with the previously-set LaTeX but a new color/DPI ratio."""

            if not self._last_latex:
                return
            self.set_latex(
                self._last_latex,
                color=color,
                fontsize=self._last_fontsize,
                dpi=self._last_dpi,
                dpr=dpr,
            )

        # -- internals ----------------------------------------------------

        def _render_one(
            self,
            latex: str,
            color: str,
            fontsize: int,
            dpi: int,
        ) -> QImage | None:
            from chaotic_systems.visualization.latex import _render_with_matplotlib

            # We bypass the public mathtext entry point so we can render *one
            # row* and avoid double-stripping aligned environments.
            arr = _render_with_matplotlib(
                latex,
                fontsize=fontsize,
                dpi=dpi,
                color=color,
                background=None,
            )
            if arr.size == 0:
                return None
            h, w, _ = arr.shape
            contiguous = np.ascontiguousarray(arr)
            image = QImage(
                contiguous.data, w, h, 4 * w, QImage.Format.Format_RGBA8888
            ).copy()
            return image

        def _clear_rows(self) -> None:
            for row in self._rows:
                row.setParent(None)
                row.deleteLater()
            self._rows = []

        def _clear_fallback(self) -> None:
            if self._fallback_label is not None:
                self._fallback_label.setParent(None)
                self._fallback_label.deleteLater()
                self._fallback_label = None

        def _install_fallback(self, text: str) -> None:
            self._clear_rows()
            self._clear_fallback()
            lab = QLabel(text, self)
            lab.setWordWrap(True)
            insert_at = max(0, self._layout.count() - 1)
            self._layout.insertWidget(insert_at, lab)
            self._fallback_label = lab

        def has_pixmap_rows(self) -> bool:
            """Test hook: returns True iff at least one row carries a pixmap."""

            return any(
                r.pixmap() is not None and not r.pixmap().isNull() for r in self._rows
            )

        def pixmap(self) -> QPixmap | None:  # type: ignore[override]
            """Back-compat: return the first row's pixmap (or ``None``).

            Mirrors the ``QLabel.pixmap()`` accessor used by the original
            non-flowing implementation so existing smoke tests still work.
            """

            for r in self._rows:
                pm = r.pixmap()
                if pm is not None and not pm.isNull():
                    return pm
            return None

        def text(self) -> str:  # type: ignore[override]
            """Back-compat: return fallback text if any row failed to render."""

            if self._fallback_label is not None:
                return self._fallback_label.text()
            return ""

        def max_row_pixmap_width(self) -> int:
            """Test hook: largest *displayed* pixmap width (in device px)."""

            best = 0
            for r in self._rows:
                pm = r.pixmap()
                if pm is None or pm.isNull():
                    continue
                best = max(best, int(pm.width() / max(1.0, pm.devicePixelRatio())))
            return best

    # -----------------------------------------------------------------------
    # Card-style group box helper. A `QGroupBox` with `variant="card"` so
    # the QSS theme can target it without leaking onto plain group boxes
    # that other code might add later.
    # -----------------------------------------------------------------------

    def _make_card(title: str, parent: QWidget) -> tuple[QGroupBox, QVBoxLayout]:
        """Return a (groupbox, inner_layout) pair pre-styled as a card."""

        box = QGroupBox(title, parent)
        box.setProperty("variant", "card")
        inner = QVBoxLayout(box)
        inner.setContentsMargins(12, 16, 12, 12)
        inner.setSpacing(8)
        return box, inner

    # -----------------------------------------------------------------------
    # Collapsible section — a header button with a chevron that toggles
    # the visibility of a body widget. Used in the right ("Mathematics")
    # panel to fold the Lagrangian section when not relevant.
    # -----------------------------------------------------------------------

    class _CollapsibleSection(QWidget):
        """A foldable section: clickable header reveals/hides the body widget."""

        def __init__(
            self,
            title: str,
            body: QWidget,
            parent: QWidget | None = None,
            *,
            expanded: bool = True,
        ) -> None:
            super().__init__(parent)
            self._body = body
            self._toggle = QPushButton(self)
            self._toggle.setCheckable(True)
            self._toggle.setFlat(True)
            self._toggle.setProperty("variant", "section-toggle")
            self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
            # Layout-friendly: align text to left + add minimal padding. The
            # color / hover state lives in the QSS so theme switches "just
            # work".
            self._toggle.setStyleSheet(
                "QPushButton[variant=\"section-toggle\"] {"
                " text-align: left; padding: 4px 6px;"
                " font-weight: 600; border: none; background: transparent; }"
            )
            self._toggle.toggled.connect(self._on_toggled)
            self._title = title

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)
            layout.addWidget(self._toggle)
            layout.addWidget(self._body, 1)
            self._toggle.setChecked(expanded)
            self._refresh_label(expanded)

        def _refresh_label(self, expanded: bool) -> None:
            arrow = "v" if expanded else ">"
            self._toggle.setText(f"  {arrow}  {self._title}")

        def _on_toggled(self, checked: bool) -> None:
            self._body.setVisible(checked)
            self._refresh_label(checked)

        def setExpanded(self, expanded: bool) -> None:  # noqa: N802 - Qt-style
            self._toggle.setChecked(expanded)

    # -----------------------------------------------------------------------
    # Viewport title overlay — a translucent QLabel pinned to the top-left
    # of the QtInteractor showing the current system's display name.
    # -----------------------------------------------------------------------

    class _ViewportOverlay(QLabel):
        """Semi-transparent overlay label, positioned by the parent on resize."""

        def __init__(self, parent: QWidget) -> None:
            super().__init__(parent)
            self.setProperty("role", "overlay")
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setMargin(0)
            self.hide()

        def set_system_name(self, name: str) -> None:
            if not name:
                self.hide()
                return
            self.setText(name)
            self.adjustSize()
            self.show()

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
            self._spin.setMinimumWidth(88)
            # Tooltip pulls `description` and (if present) `units` from the
            # backend Parameter via duck-typing. The visualization-side
            # ParameterSpec doesn't currently carry units; the real core
            # Parameter does, so we try both.
            units = getattr(p, "units", None) or ""
            tip_parts: list[str] = []
            if p.description:
                tip_parts.append(p.description)
            if units:
                tip_parts.append(f"units: {units}")
            tip_parts.append(f"range: [{lo:g}, {hi:g}]")
            self._spin.setToolTip("\n".join(tip_parts))

            self._slider = QSlider(Qt.Orientation.Horizontal, self)
            self._slider.setRange(0, 1000)
            self._slider.setValue(self._to_slider(default))
            self._slider.setToolTip(self._spin.toolTip())

            self._spin.valueChanged.connect(self._on_spin_changed)
            self._slider.valueChanged.connect(self._on_slider_changed)

            layout = QHBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
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

            # Transport / animation state. The animation timer ticks on the
            # GUI thread; each tick advances the renderer's visible polyline
            # by ``_frames_per_tick`` samples. Pause / Stop just stop the
            # timer — the trajectory data stays in memory.
            self._anim_timer: QTimer = QTimer(self)
            self._anim_timer.setTimerType(Qt.TimerType.PreciseTimer)
            self._anim_timer.timeout.connect(self._on_anim_tick)
            self._is_playing: bool = False
            self._speed_multiplier: float = 1.0
            # Sensible wall-clock playback duration at 1× speed for the
            # default Lorenz trajectory. Configurable by callers via the
            # ``target_playback_seconds`` attribute before pressing Run.
            self.target_playback_seconds: float = 10.0
            self._base_tick_ms: int = 33  # ~30 Hz refresh
            self._frames_per_tick_base: int = 1
            self._scrubber_dragging: bool = False
            self._current_frame_index: int = 0

            # --- left panel (card-style group boxes) -----------------------
            left = QWidget(self)
            left.setMinimumWidth(300)
            left_outer = QVBoxLayout(left)
            left_outer.setContentsMargins(16, 16, 16, 16)
            left_outer.setSpacing(16)

            # We wrap the cards in a QScrollArea so narrow windows still
            # surface all controls (just scrollable).
            left_scroll = QScrollArea(left)
            left_scroll.setWidgetResizable(True)
            left_scroll.setFrameShape(QFrame.Shape.NoFrame)
            left_scroll.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            left_inner = QWidget(left_scroll)
            cards_layout = QVBoxLayout(left_inner)
            cards_layout.setContentsMargins(0, 0, 0, 0)
            cards_layout.setSpacing(16)

            # --- card: System ---
            system_card, system_layout = _make_card("System", left_inner)
            self.system_box = QComboBox(system_card)
            self.system_box.setToolTip("Switch to a different dynamical system")
            for sys_obj in self._systems:
                self.system_box.addItem(getattr(sys_obj, "name", repr(sys_obj)))
            if preselect is not None:
                idx = self.system_box.findText(preselect)
                if idx >= 0:
                    self.system_box.setCurrentIndex(idx)
            self.system_box.currentIndexChanged.connect(self._on_system_changed)
            system_layout.addWidget(self.system_box)
            cards_layout.addWidget(system_card)

            # --- card: Parameters ---
            params_card, params_layout = _make_card("Parameters", left_inner)
            self._param_form_host = QWidget(params_card)
            self._param_form_layout = QFormLayout(self._param_form_host)
            self._param_form_layout.setContentsMargins(0, 0, 0, 0)
            self._param_form_layout.setHorizontalSpacing(8)
            self._param_form_layout.setVerticalSpacing(8)
            self._param_form_layout.setLabelAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            params_layout.addWidget(self._param_form_host)
            cards_layout.addWidget(params_card)

            # --- card: Integrator ---
            integrator_card, integrator_layout = _make_card("Integrator", left_inner)
            self.integrator_box = QComboBox(integrator_card)
            self.integrator_box.setToolTip(
                "ODE solver. RK45 is the default; pick LSODA/DOP853 for stiffer problems."
            )
            for name in self._integrators:
                self.integrator_box.addItem(name)
            # Default to RK45 if present.
            default_idx = self.integrator_box.findText("RK45")
            if default_idx >= 0:
                self.integrator_box.setCurrentIndex(default_idx)
            integrator_layout.addWidget(self.integrator_box)
            cards_layout.addWidget(integrator_card)

            # --- card: Time range ---
            time_card, time_layout = _make_card("Time range", left_inner)
            time_form = QFormLayout()
            time_form.setContentsMargins(0, 0, 0, 0)
            time_form.setHorizontalSpacing(8)
            time_form.setVerticalSpacing(8)
            time_form.setLabelAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.t_end = QDoubleSpinBox(time_card)
            self.t_end.setRange(0.1, 1e4)
            self.t_end.setDecimals(2)
            self.t_end.setValue(40.0)
            self.t_end.setToolTip("Final simulation time (seconds)")
            self.dt = QDoubleSpinBox(time_card)
            self.dt.setRange(1e-5, 1.0)
            self.dt.setDecimals(5)
            self.dt.setValue(0.01)
            self.dt.setToolTip("Integration step (seconds). Smaller = more accurate, slower.")
            time_form.addRow(QLabel("t_end (s)", time_card), self.t_end)
            time_form.addRow(QLabel("dt (s)", time_card), self.dt)
            time_layout.addLayout(time_form)

            # Run / Reset live inside the Time range card so they're the
            # last things the user sees scrolling top-to-bottom.
            run_row = QHBoxLayout()
            run_row.setContentsMargins(0, 0, 0, 0)
            run_row.setSpacing(8)
            self.run_button = QPushButton("Run", time_card)
            self.run_button.setProperty("variant", "primary")
            self.run_button.setToolTip("Integrate the system (Ctrl-R)")
            self.run_button.setObjectName("button_run")
            self.run_button.clicked.connect(self._on_run)
            self.reset_view_button = QPushButton("Reset view", time_card)
            self.reset_view_button.setToolTip("Re-center the 3D camera (R)")
            self.reset_view_button.setObjectName("button_reset_view")
            self.reset_view_button.clicked.connect(self._on_reset_view)
            run_row.addWidget(self.run_button, 1)
            run_row.addWidget(self.reset_view_button, 1)
            time_layout.addLayout(run_row)
            cards_layout.addWidget(time_card)

            # --- card: Export ---
            export_card, export_layout = _make_card("Export", left_inner)
            export_row = QHBoxLayout()
            export_row.setContentsMargins(0, 0, 0, 0)
            export_row.setSpacing(8)
            self.export_button = QPushButton("Export MP4", export_card)
            self.export_button.setObjectName("button_export")
            self.export_button.setToolTip("Render the current trajectory to an MP4 file (Ctrl-E)")
            self.export_button.clicked.connect(self._on_export)
            self.cancel_button = QPushButton("Cancel", export_card)
            self.cancel_button.setProperty("variant", "danger")
            self.cancel_button.setObjectName("button_cancel")
            self.cancel_button.setToolTip("Cancel an in-flight export (Esc)")
            self.cancel_button.clicked.connect(self._on_cancel)
            self.cancel_button.setEnabled(False)
            export_row.addWidget(self.export_button, 1)
            export_row.addWidget(self.cancel_button, 1)
            export_layout.addLayout(export_row)
            self.progress_bar = QProgressBar(export_card)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(False)
            self.progress_bar.setTextVisible(False)
            export_layout.addWidget(self.progress_bar)
            cards_layout.addWidget(export_card)

            # Inline status line (kept for back-compat; the real status
            # surface is the QStatusBar at the bottom of the window).
            self.status_label = QLabel("", left_inner)
            self.status_label.setWordWrap(True)
            self.status_label.setProperty("role", "caption")
            cards_layout.addWidget(self.status_label)

            # Current state readout.
            self.state_label = QLabel("y(t_end) = (no simulation yet)", left_inner)
            self.state_label.setWordWrap(True)
            self.state_label.setProperty("role", "caption")
            cards_layout.addWidget(self.state_label)

            cards_layout.addStretch(1)
            left_scroll.setWidget(left_inner)
            left_outer.addWidget(left_scroll, 1)

            # --- center: 3D viewport + transport controls -----------------
            from chaotic_systems.gui.theme import viewport_background

            self.viewer: Any = None
            inner_viewer_widget: QWidget
            if QtInteractor is None:
                inner_viewer_widget = QLabel(
                    "3D viewport unavailable: pyvistaqt is not installed."
                )
                inner_viewer_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            else:
                try:
                    self.viewer = QtInteractor(self)
                    self.viewer.set_background(viewport_background())
                    inner_viewer_widget = self.viewer.interactor
                except Exception as exc:  # pragma: no cover - depends on display
                    label = QLabel(
                        "3D viewport unavailable on this display\n"
                        f"({type(exc).__name__}: {exc})"
                    )
                    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    inner_viewer_widget = label
                    self.viewer = None

            # Frame around the viewport. QFrame[role="viewport-frame"] gets
            # the thin border + radius from the QSS, so the PyVista canvas
            # visually sits in a card matching the rest of the chrome.
            viewport_frame = QFrame(self)
            viewport_frame.setProperty("role", "viewport-frame")
            viewport_frame.setFrameShape(QFrame.Shape.NoFrame)
            viewport_frame.setMinimumWidth(480)
            vframe_layout = QVBoxLayout(viewport_frame)
            vframe_layout.setContentsMargins(1, 1, 1, 1)
            vframe_layout.setSpacing(0)
            vframe_layout.addWidget(inner_viewer_widget, 1)

            # Wrap the framed viewer + transport row in a vertical container
            # so the transport docks directly under the viewport.
            center = QWidget(self)
            center.setMinimumWidth(480)
            center_layout = QVBoxLayout(center)
            center_layout.setContentsMargins(8, 16, 8, 8)
            center_layout.setSpacing(8)
            center_layout.addWidget(viewport_frame, 1)

            transport = self._build_transport_panel(center)
            center_layout.addWidget(transport, 0)
            viewer_widget = center

            # Overlay label (semi-transparent system-name chip, top-left).
            # Lives as a child of the viewport frame so it draws on top of
            # the QtInteractor without affecting layout.
            self.viewport_overlay = _ViewportOverlay(viewport_frame)
            self._viewport_frame = viewport_frame
            viewport_frame.installEventFilter(self)

            # --- right panel: Mathematics ----------------------------------
            right = QWidget(self)
            right.setMinimumWidth(340)
            right_layout = QVBoxLayout(right)
            right_layout.setContentsMargins(16, 16, 16, 16)
            right_layout.setSpacing(16)

            math_card, math_layout = _make_card("Mathematics", right)
            math_layout.setSpacing(8)

            # Flowing LaTeX widgets — scale rendered pixmaps to the panel's
            # current width and avoid horizontal overflow. Wrapped in a
            # QScrollArea that allows *vertical* scrolling only.
            self.ode_widget = _FlowingLatex(math_card)
            self.ode_label = self.ode_widget  # back-compat alias for tests
            self.ode_scroll = QScrollArea(math_card)
            self.ode_scroll.setWidget(self.ode_widget)
            self.ode_scroll.setWidgetResizable(True)
            self.ode_scroll.setFrameShape(QFrame.Shape.NoFrame)
            self.ode_scroll.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )

            self.lagr_widget = _FlowingLatex(math_card)
            self.lagr_label = self.lagr_widget  # back-compat alias for tests
            self.lagr_scroll = QScrollArea(math_card)
            self.lagr_scroll.setWidget(self.lagr_widget)
            self.lagr_scroll.setWidgetResizable(True)
            self.lagr_scroll.setFrameShape(QFrame.Shape.NoFrame)
            self.lagr_scroll.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )

            self._ode_section = _CollapsibleSection(
                "Equations of motion", self.ode_scroll, math_card, expanded=True
            )
            self._lagr_section = _CollapsibleSection(
                "Lagrangian / Hamiltonian",
                self.lagr_scroll,
                math_card,
                expanded=True,
            )
            math_layout.addWidget(self._ode_section, 1)
            math_layout.addWidget(self._lagr_section, 1)
            right_layout.addWidget(math_card, 1)

            # --- assemble ---------------------------------------------------
            splitter = QSplitter(Qt.Orientation.Horizontal, self)
            splitter.setHandleWidth(1)
            splitter.setChildrenCollapsible(False)
            splitter.addWidget(left)
            splitter.addWidget(viewer_widget)
            splitter.addWidget(right)
            splitter.setStretchFactor(0, 0)
            splitter.setStretchFactor(1, 3)
            splitter.setStretchFactor(2, 1)
            splitter.setSizes([320, 800, 340])
            self.setCentralWidget(splitter)

            # Toolbar + status bar — built after the central widget so the
            # window-level placements know their parent.
            self._transport_actions: dict[str, QAction] = {}
            self._build_toolbar()
            self._build_status_bar()

            # Keyboard shortcuts.
            QShortcut(QKeySequence("Ctrl+R"), self, activated=self._on_run)
            QShortcut(QKeySequence("Ctrl+E"), self, activated=self._on_export)
            QShortcut(QKeySequence("R"), self, activated=self._on_reset_view)
            QShortcut(QKeySequence("Esc"), self, activated=self._on_cancel)
            QShortcut(QKeySequence(Qt.Key.Key_Space), self, activated=self._on_toggle_play)
            QShortcut(QKeySequence("Ctrl+."), self, activated=self._on_stop)
            QShortcut(QKeySequence("End"), self, activated=self._on_jump_to_end)

            self._set_transport_enabled(False)
            self._rebuild_for_current_system()
            self._sync_overlay_to_current_system()

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
            self._sync_overlay_to_current_system()

        def _clear_param_form(self) -> None:
            """Empty the parameter form.

            ``QFormLayout.removeRow(int)`` already deletes the row's widgets
            (since Qt 5.8). Calling ``deleteLater()`` on the same widgets
            afterwards raises ``RuntimeError: Internal C++ object already
            deleted``. We just drop our Python-side references.
            """

            while self._param_form_layout.rowCount() > 0:
                self._param_form_layout.removeRow(0)
            self._param_widgets = {}

        def _rebuild_for_current_system(self) -> None:
            system = self.current_system
            self._clear_param_form()
            raw_params = getattr(system, "parameters", {}) or {}
            for key, raw in raw_params.items():
                p = _coerce_parameter(key, raw)
                w = _ParamWidget(p, self._param_form_host)
                label_text = f"{p.name}"
                label = QLabel(label_text)
                label.setProperty("role", "caption")
                self._param_form_layout.addRow(label, w)
                self._param_widgets[key] = w

            # Collapse the Lagrangian section automatically when the
            # current system isn't derived from one — the body still
            # renders the "not derived" placeholder so users can expand
            # to confirm.
            lagr = getattr(system, "lagrangian_latex", None)
            if hasattr(self, "_lagr_section"):
                self._lagr_section.setExpanded(bool(lagr))

            # Update LaTeX panels.
            self._render_latex_into(self.ode_label, getattr(system, "latex", "") or "")
            self._render_latex_into(
                self.lagr_label,
                lagr or r"\text{(not derived from a Lagrangian)}",
            )

            # Refresh status-bar lyapunov chip — clear when system changes.
            if hasattr(self, "lyapunov_chip"):
                self.lyapunov_chip.setText("lambda1 = -")

        def _render_latex_into(self, widget: Any, latex: str) -> None:
            """Render ``latex`` into a flowing widget (or fall back to QLabel).

            For ``_FlowingLatex`` widgets we delegate to the widget's own
            cache-aware render path so resizes don't trigger re-rasterization.
            For raw ``QLabel`` widgets (legacy callers, custom subclasses) we
            fall back to the original ``latex_to_qimage`` -> ``setPixmap``
            path.
            """

            # Hi-DPI: render at dpi * device-pixel-ratio for crisp output.
            try:
                screen = self.screen()
                dpr = float(screen.devicePixelRatio()) if screen is not None else 1.0
            except (AttributeError, RuntimeError):  # pragma: no cover
                dpr = 1.0
            color = _palette_text_color_hex(widget)
            if isinstance(widget, _FlowingLatex):
                widget.set_latex(latex, color=color, fontsize=13, dpi=120, dpr=dpr)
                return
            # Fallback: legacy QLabel rendering path.
            try:
                image = latex_to_qimage(
                    latex, fontsize=13, dpi=int(120 * dpr), color=color
                )
                image.setDevicePixelRatio(dpr)
            except Exception as exc:
                widget.setText(f"<LaTeX render failed: {exc}>")
                return
            pixmap = QPixmap.fromImage(image)
            pixmap.setDevicePixelRatio(dpr)
            widget.setPixmap(pixmap)
            widget.setFixedSize(int(pixmap.width() / dpr), int(pixmap.height() / dpr))

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
            # Always pause / drop any prior playback before attaching a new
            # renderer — the old renderer's actors are about to go away.
            self._pause()
            self._current_renderer = None
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
            # Wire up the transport controls for the new trajectory.
            n = self._renderer_total_frames()
            if n > 1:
                self._recompute_tick_cadence()
                self.frame_scrubber.setRange(0, n - 1)
                self._set_transport_enabled(True)
                self._seek_to(0)
                # Run starts at 1× from frame 0 per the spec.
                self._play()
            else:
                self._set_transport_enabled(False)
            self._set_status("Simulation complete.", state="done")
            # Light up the toolbar transport actions that depend on having
            # a trajectory loaded.
            for key in ("transport_pause", "transport_stop", "transport_jump_end",
                        "action_export"):
                act = self._transport_actions.get(key)
                if act is not None:
                    act.setEnabled(True)

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

            self._set_status(f"Exporting to {path_str}...", busy=True, state="exporting")
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
            self._set_status(f"Wrote {path}", state="done")
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

        # ------------------------------------------------------------ toolbar

        # Toolbar action specs: (object_name, label, QStyle pixmap enum,
        # tooltip, slot, starts_enabled). Kept as data so the structure is
        # readable and external agents can introspect it via
        # ``MainWindow.transport_actions()``.
        def _toolbar_action_specs(self) -> list[tuple[str, str, Any, str, Any, bool]]:
            sp = QStyle.StandardPixmap
            return [
                (
                    "transport_run",
                    "Run",
                    sp.SP_MediaPlay,
                    "Integrate and start animated playback (Ctrl-R)",
                    self._on_run,
                    True,
                ),
                (
                    "transport_pause",
                    "Pause",
                    sp.SP_MediaPause,
                    "Pause / resume playback (Space)",
                    self._on_toggle_play,
                    False,
                ),
                (
                    "transport_stop",
                    "Stop",
                    sp.SP_MediaStop,
                    "Stop playback and rewind to start (Ctrl-.)",
                    self._on_stop,
                    False,
                ),
                (
                    "transport_jump_end",
                    "Jump to end",
                    sp.SP_MediaSkipForward,
                    "Jump to the last frame of the trajectory (End)",
                    self._on_jump_to_end,
                    False,
                ),
                (
                    "action_export",
                    "Export MP4",
                    sp.SP_DialogSaveButton,
                    "Render the current trajectory to an MP4 file (Ctrl-E)",
                    self._on_export,
                    False,
                ),
                (
                    "action_reset_view",
                    "Reset view",
                    sp.SP_BrowserReload,
                    "Re-center the 3D camera (R)",
                    self._on_reset_view,
                    True,
                ),
                (
                    "action_toggle_theme",
                    "Toggle theme",
                    sp.SP_DesktopIcon,
                    "Switch between dark and light themes",
                    self._on_toggle_theme,
                    True,
                ),
            ]

        def _build_toolbar(self) -> None:
            """Build the top toolbar with media-style transport actions.

            The actions live as ``QAction``s on the toolbar with stable
            ``objectName``s so they're addressable by name; parallel agents
            wiring animation hooks can look them up without re-creating
            anything.
            """

            toolbar = QToolBar("main", self)
            toolbar.setObjectName("toolbar_main")
            toolbar.setMovable(False)
            toolbar.setFloatable(False)
            toolbar.setIconSize(QSize(18, 18))
            toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

            style = self.style()
            for i, spec in enumerate(self._toolbar_action_specs()):
                obj_name, label, pix_enum, tip, slot, enabled = spec
                # Separators before Export and Toggle-theme group related
                # actions visually.
                if obj_name in {"action_export", "action_toggle_theme"} and i > 0:
                    toolbar.addSeparator()
                action = QAction(label, self)
                action.setObjectName(obj_name)
                action.setToolTip(tip)
                action.setIcon(style.standardIcon(pix_enum))
                action.setEnabled(enabled)
                action.triggered.connect(slot)
                if obj_name == "transport_run":
                    # Mark "Run" as the primary action via QSS variant.
                    toolbar.addAction(action)
                    btn = toolbar.widgetForAction(action)
                    if btn is not None:
                        btn.setProperty("variant", "primary")
                        btn.style().unpolish(btn)
                        btn.style().polish(btn)
                else:
                    toolbar.addAction(action)
                self._transport_actions[obj_name] = action

            self._toolbar = toolbar

        def transport_actions(self) -> dict[str, QAction]:
            """Return the toolbar's transport ``QAction``s keyed by object name.

            Stable keys: ``transport_run``, ``transport_pause``,
            ``transport_stop``, ``transport_jump_end``, ``action_export``,
            ``action_reset_view``, ``action_toggle_theme``.

            External agents wiring playback hooks should prefer this entry
            point over reaching into ``self._transport_actions`` directly.
            """

            return dict(self._transport_actions)

        def _register_transport_actions(self) -> dict[str, QAction]:
            """Compatibility alias for the registration hook documented in the
            integration plan with the animation agent."""

            return self.transport_actions()

        def _on_toggle_theme(self) -> None:
            """Flip between dark and light QSS themes."""

            from chaotic_systems.gui.theme import (
                apply_theme,
                current_theme,
                viewport_background,
            )

            app = QApplication.instance()
            if app is None:
                return
            new_mode = "light" if current_theme() == "dark" else "dark"
            apply_theme(app, new_mode)
            # Re-render LaTeX so glyph color tracks the new palette.
            self._rebuild_for_current_system()
            # Keep the PyVista background in sync.
            if self.viewer is not None:
                try:
                    self.viewer.set_background(viewport_background())
                except (AttributeError, RuntimeError):
                    pass

        # ------------------------------------------------------------ status bar

        def _build_status_bar(self) -> None:
            """Build the bottom status bar with state + frame/time/lyapunov chips."""

            bar = QStatusBar(self)
            self.setStatusBar(bar)

            # State chip — Idle / Running / Exporting / Error.
            self.state_chip = QLabel("Idle", bar)
            self.state_chip.setProperty("role", "chip")
            self.state_chip.setProperty("state", "idle")
            self.state_chip.setToolTip("Current run state")

            # Frame chip — i / N.
            self.frame_chip = QLabel("frame 0 / 0", bar)
            self.frame_chip.setProperty("role", "chip")
            self.frame_chip.setToolTip("Animated frame index / total frames")

            # Time chip — t = ...
            self.time_chip = QLabel("t = 0.000", bar)
            self.time_chip.setProperty("role", "chip")
            self.time_chip.setToolTip("Current simulation time")

            # Lyapunov chip — lambda1 = ... when computed.
            self.lyapunov_chip = QLabel("lambda1 = -", bar)
            self.lyapunov_chip.setProperty("role", "chip")
            self.lyapunov_chip.setProperty("highlight", "lyapunov")
            self.lyapunov_chip.setToolTip(
                "Largest Lyapunov exponent (positive = chaotic)"
            )

            bar.addWidget(self.state_chip)
            bar.addPermanentWidget(self.frame_chip)
            bar.addPermanentWidget(self.time_chip)
            bar.addPermanentWidget(self.lyapunov_chip)

        def _set_state_chip(self, text: str, state: str) -> None:
            """Update the state chip text and the QSS ``state`` property.

            ``state`` should be one of ``"idle"``, ``"running"``,
            ``"exporting"``, ``"error"``. The QSS theme styles the chip
            accordingly via the attribute selector.
            """

            self.state_chip.setText(text)
            self.state_chip.setProperty("state", state)
            self.state_chip.style().unpolish(self.state_chip)
            self.state_chip.style().polish(self.state_chip)

        def _update_status_frame(self, frame_index: int) -> None:
            n = self._renderer_total_frames()
            self.frame_chip.setText(f"frame {max(0, frame_index)} / {max(0, n - 1)}")
            t_now = self._trajectory_t_value(frame_index)
            if t_now is None:
                self.time_chip.setText("t = 0.000")
            else:
                self.time_chip.setText(f"t = {t_now:.3f}")

        # ------------------------------------------------------------ overlay

        def _sync_overlay_to_current_system(self) -> None:
            """Refresh the viewport overlay to show the current system's name."""

            try:
                name = getattr(self.current_system, "name", "")
            except IndexError:
                name = ""
            if hasattr(self, "viewport_overlay") and self.viewport_overlay is not None:
                self.viewport_overlay.set_system_name(name)
                self._reposition_overlay()

        def _reposition_overlay(self) -> None:
            """Pin the overlay to the top-left of the viewport frame."""

            if (
                not hasattr(self, "viewport_overlay")
                or self.viewport_overlay is None
                or not hasattr(self, "_viewport_frame")
            ):
                return
            margin = 12
            self.viewport_overlay.move(margin, margin)
            self.viewport_overlay.raise_()

        def eventFilter(self, watched: Any, event: Any) -> bool:  # type: ignore[override]
            # Re-anchor the overlay whenever the viewport frame resizes so it
            # never drifts under the LaTeX panel.
            from PySide6.QtCore import QEvent

            if (
                hasattr(self, "_viewport_frame")
                and watched is self._viewport_frame
                and event.type() == QEvent.Type.Resize
            ):
                self._reposition_overlay()
            return super().eventFilter(watched, event)

        # ------------------------------------------------------------ transport

        # Discrete playback-speed presets — chosen to match what users get in
        # video tools (VLC / QuickTime). The "1×" preset is calibrated so the
        # full trajectory plays back over ``target_playback_seconds`` of
        # wall-clock time at the default tick cadence.
        _SPEED_PRESETS: tuple[float, ...] = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0)

        def _build_transport_panel(self, parent: QWidget) -> QWidget:
            """Build the bottom transport-control strip under the viewport.

            Layout::

                [Play] [Stop] [End]  Speed: [1× v]   [=====O==========] t = 12.3 / 40.0
            """

            host = QWidget(parent)
            row = QHBoxLayout(host)
            row.setContentsMargins(6, 2, 6, 2)
            row.setSpacing(6)

            self.play_button = QPushButton("Play", host)
            self.play_button.setToolTip("Play / Pause (Space)")
            self.play_button.setCheckable(True)
            self.play_button.clicked.connect(self._on_toggle_play)

            self.stop_button = QPushButton("Stop", host)
            self.stop_button.setToolTip("Stop and rewind to start (Ctrl-.)")
            self.stop_button.clicked.connect(self._on_stop)

            self.jump_end_button = QPushButton("End", host)
            self.jump_end_button.setToolTip("Jump to the end of the trajectory (End)")
            self.jump_end_button.clicked.connect(self._on_jump_to_end)

            self.speed_box = QComboBox(host)
            for s in self._SPEED_PRESETS:
                label = f"{s:g}×"  # narrow space + multiplication sign
                self.speed_box.addItem(label, s)
            default_idx = self.speed_box.findData(1.0)
            if default_idx >= 0:
                self.speed_box.setCurrentIndex(default_idx)
            self.speed_box.currentIndexChanged.connect(self._on_speed_changed)

            self.frame_scrubber = QSlider(Qt.Orientation.Horizontal, host)
            self.frame_scrubber.setRange(0, 0)
            self.frame_scrubber.setSingleStep(1)
            self.frame_scrubber.setPageStep(10)
            self.frame_scrubber.setTracking(True)
            self.frame_scrubber.sliderPressed.connect(self._on_scrubber_press)
            self.frame_scrubber.sliderReleased.connect(self._on_scrubber_release)
            self.frame_scrubber.valueChanged.connect(self._on_scrubber_value)

            self.time_label = QLabel("t = 0.000 / 0.000", host)
            self.time_label.setMinimumWidth(140)

            row.addWidget(self.play_button)
            row.addWidget(self.stop_button)
            row.addWidget(self.jump_end_button)
            row.addWidget(QLabel("Speed:", host))
            row.addWidget(self.speed_box)
            row.addWidget(self.frame_scrubber, 1)
            row.addWidget(self.time_label)
            return host

        def _set_transport_enabled(self, enabled: bool) -> None:
            for w in (
                self.play_button,
                self.stop_button,
                self.jump_end_button,
                self.speed_box,
                self.frame_scrubber,
            ):
                w.setEnabled(enabled)
            if not enabled:
                self.play_button.setChecked(False)

        def _recompute_tick_cadence(self) -> None:
            """Pick a ``_frames_per_tick_base`` so 1× plays over the target wall time.

            At 1×, the polyline should grow from frame 0 to frame ``n-1`` over
            ``target_playback_seconds``. We fix the timer period at
            ``_base_tick_ms`` (~30 Hz) and pick the per-tick stride
            accordingly. At higher speeds we multiply the stride; we never
            shrink the timer period below the base because Qt timers below
            10-15 ms behave badly across platforms.
            """

            n = self._renderer_total_frames()
            if n <= 0:
                self._frames_per_tick_base = 1
                return
            target_ms = max(50.0, float(self.target_playback_seconds) * 1000.0)
            ticks = max(1.0, target_ms / float(self._base_tick_ms))
            self._frames_per_tick_base = max(1, int(round(n / ticks)))

        def _renderer_total_frames(self) -> int:
            r = self._current_renderer
            if r is None:
                return 0
            return int(r.n_frames)

        def _trajectory_t_value(self, frame_index: int) -> float | None:
            traj = self._last_trajectory
            if traj is None:
                return None
            try:
                t = np.asarray(traj.t, dtype=float)
            except (AttributeError, ValueError):
                return None
            if t.ndim != 1 or t.size == 0:
                return None
            idx = int(np.clip(frame_index, 0, t.size - 1))
            return float(t[idx])

        def _update_time_label(self, frame_index: int) -> None:
            t_now = self._trajectory_t_value(frame_index)
            t_end = self._trajectory_t_value(self._renderer_total_frames() - 1)
            if t_now is None or t_end is None:
                self.time_label.setText("t = 0.000 / 0.000")
                return
            self.time_label.setText(f"t = {t_now:.3f} / {t_end:.3f}")

        def _on_speed_changed(self, _idx: int) -> None:
            data = self.speed_box.currentData()
            try:
                self._speed_multiplier = float(data)
            except (TypeError, ValueError):
                self._speed_multiplier = 1.0
            if self._is_playing:
                # Re-arm the timer with the new cadence; we only change the
                # per-tick stride, not the timer period, so high speeds stay
                # smooth (4 frames per 33 ms tick at 4×, 8 at 8×).
                pass  # _on_anim_tick reads the multiplier each tick

        def _on_toggle_play(self) -> None:
            if self._current_renderer is None:
                return
            if self._is_playing:
                self._pause()
            else:
                self._play()

        def _play(self) -> None:
            if self._current_renderer is None:
                return
            n = self._renderer_total_frames()
            if n <= 1:
                return
            # If we're at the end, rewind to start so Play is meaningful.
            if self._current_frame_index >= n - 1:
                self._seek_to(0)
            self._is_playing = True
            self.play_button.setChecked(True)
            self.play_button.setText("Pause")
            self._anim_timer.start(self._base_tick_ms)

        def _pause(self) -> None:
            self._is_playing = False
            self.play_button.setChecked(False)
            self.play_button.setText("Play")
            self._anim_timer.stop()

        def _on_stop(self) -> None:
            if self._current_renderer is None:
                return
            self._pause()
            self._seek_to(0)

        def _on_jump_to_end(self) -> None:
            if self._current_renderer is None:
                return
            self._pause()
            self._seek_to(self._renderer_total_frames() - 1)

        def _seek_to(self, frame_index: int) -> None:
            r = self._current_renderer
            if r is None:
                return
            n = r.n_frames
            if n <= 1:
                return
            idx = int(np.clip(int(frame_index), 0, n - 1))
            self._current_frame_index = idx
            r.seek(idx)
            # Keep the scrubber in sync without re-entering the drag handler.
            block = self.frame_scrubber.blockSignals(True)
            try:
                self.frame_scrubber.setValue(idx)
            finally:
                self.frame_scrubber.blockSignals(block)
            self._update_time_label(idx)
            self._update_status_frame(idx)

        def _on_anim_tick(self) -> None:
            r = self._current_renderer
            if r is None or not self._is_playing:
                return
            n = r.n_frames
            stride = max(
                1, int(round(self._frames_per_tick_base * self._speed_multiplier))
            )
            next_idx = self._current_frame_index + stride
            if next_idx >= n - 1:
                # Snap to the last frame and stop.
                self._seek_to(n - 1)
                self._pause()
                return
            self._seek_to(next_idx)

        def _on_scrubber_press(self) -> None:
            self._scrubber_dragging = True
            if self._is_playing:
                self._pause()

        def _on_scrubber_release(self) -> None:
            self._scrubber_dragging = False

        def _on_scrubber_value(self, value: int) -> None:
            # Pause during interactive drags; idle programmatic updates are
            # already filtered out via blockSignals in :meth:`_seek_to`.
            if self._scrubber_dragging and self._is_playing:
                self._pause()
            self._seek_to(int(value))

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

        def _set_status(
            self,
            text: str,
            *,
            busy: bool = False,
            state: str | None = None,
        ) -> None:
            self.status_label.setText(text)
            self.setCursor(Qt.CursorShape.WaitCursor if busy else Qt.CursorShape.ArrowCursor)
            # Mirror the message into the status-bar's permanent state chip.
            if state is None:
                inferred = "running" if busy else "idle"
            else:
                inferred = state
            label_map = {
                "idle": "Idle",
                "running": "Running",
                "exporting": "Exporting",
                "error": "Error",
                "done": "Done",
            }
            chip_label = label_map.get(inferred, inferred.capitalize())
            chip_state = inferred if inferred != "done" else "idle"
            self._set_state_chip(chip_label, chip_state)

        def _show_error(self, title: str, message: str) -> None:
            self._set_status(message, state="error")
            QMessageBox.critical(self, title, message)

        # ------------------------------------------------------------------

        def closeEvent(self, event: Any) -> None:  # type: ignore[override]
            # Stop the animation first — its timer fires on the GUI thread
            # and can otherwise keep the event loop alive briefly while the
            # window is tearing down.
            try:
                self._anim_timer.stop()
            except RuntimeError:  # pragma: no cover - already cleaned up
                pass
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


def build_application(
    argv: list[str] | None = None, *, theme: str = "dark"
) -> tuple[Any, Any]:
    """Construct ``QApplication`` and :class:`MainWindow`.

    Returns ``(app, window)`` without calling ``app.exec()`` — useful for
    tests and for callers that want to customize the window before showing it.

    The Tokyo Night Storm dark QSS theme is applied to the ``QApplication``
    by default; pass ``theme="light"`` for the (currently stub) light
    variant.
    """

    import sys

    from PySide6.QtWidgets import QApplication

    from chaotic_systems.gui.theme import apply_theme

    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    apply_theme(app, theme)
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
