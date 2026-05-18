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
        n_points: int | None = None,
        **_kwargs: Any,
    ) -> Any:
        from scipy.integrate import solve_ivp

        merged = {"sigma": 10.0, "rho": 28.0, "beta": 8.0 / 3.0}
        if params:
            merged.update({k: float(v) for k, v in params.items() if k in merged})
        if y0 is None:
            y0 = self.initial_state.copy()
        t0, t1 = t_span
        # Honor an explicit ``n_points`` request (the GUI wants dense
        # uniform sampling for smooth playback); otherwise derive from
        # ``dt`` for headless / scripted use.
        if n_points is not None and int(n_points) >= 2:
            n = int(n_points)
        else:
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


# Classification tolerance: |lambda| <= this is treated as "zero" in the
# regime classifier below. Continuous-flow systems always have at least
# one near-zero exponent (the trivial flow-direction mode), but real
# hyperchaotic systems can have small-but-real positive exponents (4D
# Rossler's lambda_2 ~ 0.03-0.05 per Stankevich & Wilczak 2015), so the
# tolerance has to stay below that range. 1e-2 is the practical floor
# for the Benettin/QR estimator at typical (t_total=500, dt=1) settings.
_LYAPUNOV_ZERO_TOL: float = 1e-2


def _format_lyapunov_spectrum(spectrum: np.ndarray) -> tuple[str, float]:
    """Format a Lyapunov spectrum for the GUI Diagnostics card.

    Returns ``(display_text, leading_exponent)``. The display text lists
    every exponent with two decimal places of precision, plus a regime
    classification (``Regular`` / ``Chaotic`` / ``Hyperchaotic``) and
    the sum-of-positive-exponents Kaplan-Yorke proxy.
    """

    arr = np.asarray(spectrum, dtype=float)
    if arr.size == 0:
        return ("(empty spectrum)", 0.0)
    sorted_desc = np.sort(arr)[::-1]
    n_positive = int(np.sum(sorted_desc > _LYAPUNOV_ZERO_TOL))
    if n_positive == 0:
        regime = "Regular (no positive exponent)"
    elif n_positive == 1:
        regime = "Chaotic (1 positive exponent)"
    else:
        regime = f"Hyperchaotic ({n_positive} positive exponents)"
    exponent_lines = "\n".join(
        f"  λ{i + 1} = {lam:+.4f}" for i, lam in enumerate(sorted_desc)
    )
    return (f"{regime}\n{exponent_lines}", float(sorted_desc[0]))


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
        QIcon,
        QImage,
        QKeySequence,
        QPalette,
        QPixmap,
        QShortcut,
    )
    from PySide6.QtWidgets import (
        QApplication,
        QColorDialog,
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QFrame,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QMenu,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QSlider,
        QSplitter,
        QStatusBar,
        QTextBrowser,
        QToolBar,
        QToolButton,
        QVBoxLayout,
        QWidget,
        QWidgetAction,
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
            except Exception:  # noqa: BLE001 — surfaced as a clean fallback label
                # The mathtext layer already attempts a sanitised retry and
                # a fallback message before raising. Reaching this branch
                # means the renderer itself is broken (no fonts, etc.).
                self._install_fallback(
                    "renderer cannot display this expression — see docs"
                )
                return

            if not self._rows:
                self._install_fallback(
                    "renderer cannot display this expression — see docs"
                )

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
                " font-weight: 600; border: none; background: transparent;"
                " color: #c0caf5; font-size: 12pt; }"
            )
            self._toggle.toggled.connect(self._on_toggled)
            self._title = title

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)
            layout.addWidget(self._toggle)
            layout.addWidget(self._body, 1)
            # Expanded sections fill their parent; collapsed sections shrink
            # to the header's natural height so a collapsed Lagrangian
            # doesn't leave a void in the Mathematics panel.
            self.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            self._toggle.setChecked(expanded)
            self._refresh_label(expanded)
            self._apply_collapsed_policy(expanded)

        def _refresh_label(self, expanded: bool) -> None:
            # Unicode chevrons render in the system font on every modern
            # platform and avoid the bare lowercase ``v`` that earlier
            # builds shipped. The visual weight matches the SVG chevron
            # the QComboBox dropdown uses.
            arrow = "▾" if expanded else "▸"  # ▾ / ▸
            self._toggle.setText(f"  {arrow}  {self._title}")

        def _on_toggled(self, checked: bool) -> None:
            self._body.setVisible(checked)
            self._refresh_label(checked)
            self._apply_collapsed_policy(checked)

        def _apply_collapsed_policy(self, expanded: bool) -> None:
            """Shrink the section when collapsed so siblings can claim the space."""

            if expanded:
                self.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Expanding,
                )
                self.setMaximumHeight(16777215)
            else:
                self.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Fixed,
                )
                # Force the layout to recompute the header-only height.
                self.setMaximumHeight(self._toggle.sizeHint().height() + 8)

        def setExpanded(self, expanded: bool) -> None:  # noqa: N802 - Qt-style
            self._toggle.setChecked(expanded)
            # ``setChecked`` only emits ``toggled`` when the state actually
            # changes; force the policy refresh in case we set it to the
            # current value.
            self._apply_collapsed_policy(expanded)

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
            # Belt-and-braces defence against the "LorenzPendulum" overlap
            # in the critique:
            #   1. Resize self to 0×0 first so QLabel discards its cached
            #      glyph bitmap.
            #   2. Hide so the parent can reclaim the previous rectangle.
            #   3. Force the parent to repaint the previously-occupied
            #      rectangle so a wider name shrinking to a shorter one
            #      doesn't leave stale glyphs behind.
            #   4. Set the new text, size, and re-show.
            previous_geometry = self.geometry()
            self.resize(0, 0)
            self.hide()
            parent = self.parentWidget()
            if parent is not None and previous_geometry.isValid():
                parent.repaint(previous_geometry)
            self.clear()
            if not name:
                return
            self.setText(name)
            self.adjustSize()
            self.show()
            self.raise_()
            self.update()

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
            n_points: int | None = None,
        ) -> None:
            super().__init__()
            self._system = system
            self._t_span = t_span
            self._y0 = y0
            self._params = params
            self._integrator = integrator
            self._dt = dt
            self._n_points = n_points

        def run(self) -> None:
            # Local import so this module stays import-safe even if the
            # integrators package fails to load (the generic ImportError
            # path below handles that).
            try:
                from chaotic_systems.integrators import IntegratorDivergedError
            except ImportError:  # pragma: no cover - integrators always ship
                IntegratorDivergedError = ()  # type: ignore[assignment, misc]
            try:
                # Pass ``n_points`` only when the system accepts it — the
                # GUI's fallback Lorenz takes ``**kwargs`` but real
                # backend systems take ``n_points`` explicitly. Passing
                # the keyword is harmless either way.
                kwargs: dict[str, Any] = {
                    "integrator": self._integrator,
                    "dt": self._dt,
                }
                if self._n_points is not None:
                    kwargs["n_points"] = int(self._n_points)
                traj = self._system.simulate(
                    self._t_span,
                    self._y0,
                    self._params,
                    **kwargs,
                )
            except IntegratorDivergedError as exc:
                # Distinct kind so the GUI can show a targeted hint
                # instead of the generic "RuntimeError" path. Must come
                # before the RuntimeError branch (it subclasses it).
                self.error.emit("IntegratorDivergedError", str(exc))
                return
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

    class _PrerenderWorker(QObject):
        """Warm the renderer's prerender cache on a worker thread.

        Calls ``Renderer3D.build_prerender_cache`` with progress and
        cancel callbacks bridged to Qt signals. The worker is short-lived
        (typically 80-200 ms for a 4000-sample Lorenz on M1) but matters
        perceptually: it eliminates the cold-start jank during the first
        few seconds of playback. See ``docs/prerender_design.md`` for
        the full design.

        Important: the renderer owns VTK objects on the GUI thread.
        Calling ``build_prerender_cache`` from a worker thread *does*
        issue ``Render()`` against those VTK objects, which is generally
        thread-unsafe — but the calls happen against a plotter that is
        idle (no other code is touching it while the worker is running)
        and the GUI's event loop is not pumping VTK during this window.
        This matches the established pattern in
        ``Renderer3D.render_to_video`` which also runs on a QThread.
        """

        finished = Signal()
        error = Signal(str, str)
        progress = Signal(int, int)  # (current, total)
        cancelled = Signal()

        def __init__(self, renderer: Renderer3D) -> None:
            super().__init__()
            self._renderer = renderer
            self._cancelled = False

        def cancel(self) -> None:
            self._cancelled = True

        def _is_cancelled(self) -> bool:
            return self._cancelled

        def _emit_progress(self, i: int, n: int) -> None:
            self.progress.emit(i, n)

        def run(self) -> None:
            try:
                ok = self._renderer.build_prerender_cache(
                    progress_cb=self._emit_progress,
                    cancel_cb=self._is_cancelled,
                )
            except (RuntimeError, ValueError) as exc:
                self.error.emit(type(exc).__name__, str(exc))
                return
            except Exception as exc:  # pragma: no cover - last-resort guard
                self.error.emit("Exception", f"{type(exc).__name__}: {exc}")
                return
            if not ok:
                self.cancelled.emit()
                return
            self.finished.emit()

    # -----------------------------------------------------------------------
    # Lyapunov worker — computes the full spectrum off the GUI thread.
    # The compute uses the variational equations + continuous QR
    # re-orthonormalization (Benettin et al., Meccanica 15, 1980),
    # already implemented in ``core/lyapunov.py``. Typical wall-clock
    # for default Lorenz at canonical settings is ~5 s on Apple Silicon
    # — too long for the GUI thread, hence the worker.
    # -----------------------------------------------------------------------

    class _LyapunovWorker(QObject):
        """Run ``lyapunov_spectrum(system, ...)`` on a worker thread.

        The Benettin / continuous-QR algorithm integrates the variational
        equations over ``t_total - t_transient`` time units, periodically
        QR-decomposing the perturbation matrix to extract local stretch
        rates. Default settings (``t_transient=50``, ``t_total=500``,
        ``dt=1.0``) match the canonical reference and yield ~0.7% error
        on Lorenz's largest exponent (0.9072 vs canonical 0.9056).
        """

        finished = Signal(object)  # ndarray of exponents, sorted descending
        error = Signal(str, str)  # (kind, message)

        def __init__(
            self,
            system: SystemLike,
            params: dict[str, float],
            y0: np.ndarray,
            t_transient: float = 50.0,
            t_total: float = 500.0,
            dt: float = 1.0,
        ) -> None:
            super().__init__()
            self._system = system
            self._params = params
            self._y0 = y0
            self._t_transient = t_transient
            self._t_total = t_total
            self._dt = dt

        def run(self) -> None:
            try:
                from chaotic_systems.core.lyapunov import lyapunov_spectrum
            except ImportError as exc:  # pragma: no cover - core always ships
                self.error.emit("ImportError", str(exc))
                return
            try:
                spectrum = lyapunov_spectrum(
                    self._system,
                    y0=self._y0,
                    params=self._params,
                    t_transient=self._t_transient,
                    t_total=self._t_total,
                    dt=self._dt,
                )
            except (RuntimeError, ValueError) as exc:
                self.error.emit(type(exc).__name__, str(exc))
                return
            except Exception as exc:  # pragma: no cover - last-resort guard
                self.error.emit("Exception", f"{type(exc).__name__}: {exc}")
                return
            # Sort descending so λ_1 is the leading entry — the compute
            # routine returns them in array order; visually we want the
            # largest first.
            spectrum_sorted = np.sort(np.asarray(spectrum, dtype=float))[::-1]
            self.finished.emit(spectrum_sorted)

    # -----------------------------------------------------------------------
    # Busy spinner — a tiny rotating-arc widget for indeterminate work.
    # Mounted in the bottom status bar; visible during simulation or during
    # export warm-up. Once the export emits its first determinate progress
    # tick, the spinner stops and the bevelled bar takes over.
    # -----------------------------------------------------------------------

    class _BusySpinner(QWidget):
        """A small Apple-style rotating arc, palette accent color.

        The widget paints a 270-degree arc and spins it at ~60 FPS by
        updating an angle offset on a ``QTimer``. ``start()`` shows the
        widget and arms the timer; ``stop()`` hides it and disarms.
        Drawing is fully QPainter-based, so the widget needs nothing
        beyond a parent widget.
        """

        DEFAULT_SIZE_PX = 16

        def __init__(
            self,
            parent: QWidget | None = None,
            *,
            diameter: int = DEFAULT_SIZE_PX,
            color: str = "#7aa2f7",
        ) -> None:
            super().__init__(parent)
            self._diameter = int(diameter)
            self._color_hex = color
            self._angle = 0
            self.setFixedSize(self._diameter + 4, self._diameter + 4)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self._timer = QTimer(self)
            self._timer.setTimerType(Qt.TimerType.PreciseTimer)
            self._timer.timeout.connect(self._advance)
            self.hide()

        # -- public API -----------------------------------------------------

        def start(self) -> None:
            self.show()
            # 60 FPS rotation — visually smooth, costs us a few microseconds
            # per frame against an offscreen Qt buffer.
            self._timer.start(16)

        def stop(self) -> None:
            self._timer.stop()
            self.hide()

        # -- internals ------------------------------------------------------

        def _advance(self) -> None:
            # 6 deg per tick × 60 Hz = 360 deg/s full revolution. Smooth.
            self._angle = (self._angle + 6) % 360
            self.update()

        def paintEvent(self, event: Any) -> None:  # type: ignore[override]
            from PySide6.QtCore import QRectF
            from PySide6.QtGui import QColor, QPainter, QPen

            painter = QPainter(self)
            try:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                pen_width = max(2.0, self._diameter / 8.0)
                # Faint track ring under the spinning arc — Apple-style.
                track_color = QColor(self._color_hex)
                track_color.setAlpha(60)
                pen_track = QPen(track_color)
                pen_track.setWidthF(pen_width)
                pen_track.setCapStyle(Qt.PenCapStyle.RoundCap)
                arc_rect = QRectF(
                    pen_width / 2.0 + 1,
                    pen_width / 2.0 + 1,
                    self._diameter - 1,
                    self._diameter - 1,
                )
                painter.setPen(pen_track)
                painter.drawArc(arc_rect, 0, 360 * 16)
                # The leading arc — 270 deg sweep, rotating.
                pen = QPen(QColor(self._color_hex))
                pen.setWidthF(pen_width)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                start_angle = int(-self._angle * 16)
                painter.drawArc(arc_rect, start_angle, 270 * 16)
            finally:
                painter.end()
            _ = event  # unused; required signature

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
            # Prerender worker — runs ``Renderer3D.build_prerender_cache``
            # off the GUI thread after every successful simulation
            # (provided the trajectory is long enough to benefit; see
            # ``_PRERENDER_MIN_FRAMES``). See ``docs/prerender_design.md``.
            self._prerender_thread: QThread | None = None
            self._prerender_worker: _PrerenderWorker | None = None
            # Lyapunov worker — computes the full spectrum off the GUI
            # thread when the user clicks the Diagnostics card's
            # "Compute Lyapunov spectrum" button. See
            # ``docs/proposals/capability-roadmap-2026-05-17.md`` D1.
            self._lyapunov_thread: QThread | None = None
            self._lyapunov_worker: _LyapunovWorker | None = None

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
            # 15 s gives a calmer perceptual feel than the original 10 s
            # without crossing into "too slow" territory.
            self.target_playback_seconds: float = 15.0
            # ~60 Hz refresh — modern Qt + macOS handles 16 ms timers
            # cleanly. The old 33 ms (~30 Hz) cadence forced a high stride
            # which made the head sphere teleport visibly between phase
            # points; halving the period lets us advance ~6 frames/tick
            # for the default 4000-sample Lorenz, in line with the
            # ``_MAX_STRIDE`` cap below.
            self._base_tick_ms: int = 16
            # Hard ceiling on the per-tick stride. With sub-frame
            # interpolation on both the polyline tail and the head
            # sphere, advancing more than ~one trajectory sample per
            # rendered frame loses visual continuity (the polyline
            # appears to "ratchet" past samples). A cap of 2 keeps
            # the per-frame jump bounded; if the trajectory is so
            # dense that the wall-clock playback target can't be met
            # without exceeding this, playback simply runs longer.
            self._MAX_STRIDE: int = 2
            self._frames_per_tick_base: float = 1.0
            # Fractional playback position, in samples. The displayed
            # frame index is ``floor`` of this; the renderer interpolates
            # the head sphere's position to the fractional remainder.
            self._anim_position: float = 0.0
            # Arc-length parameter for the prerender-driven playback
            # path. Only consulted when the current renderer has
            # ``has_prerender_cache`` set — otherwise the integer-frame
            # ``_anim_position`` carries the playhead. See
            # ``docs/prerender_design.md`` for the motivation.
            self._anim_arc_position: float = 0.0
            # Wall-clock anchors. The animation loop computes the
            # target playhead from wall-clock elapsed time rather than
            # accumulating per-tick increments — that way a missed
            # frame causes the head to *catch up* on the next render
            # instead of falling behind. Set by :meth:`_play` and
            # rebased whenever the speed changes mid-playback or the
            # user scrubs.
            self._play_wall_start: float = 0.0
            self._play_arc_start: float = 0.0
            self._play_position_start: float = 0.0
            self._scrubber_dragging: bool = False
            self._current_frame_index: int = 0
            # Optional per-render trace. When non-None, every animation
            # tick appends a ``(wall_time, head_x, head_y, head_z)``
            # row. Used by ``tools/validate_smoothness.py`` and the
            # unit tests to measure max per-frame head displacement.
            self._anim_trace: list[tuple[float, float, float, float]] | None = (
                None
            )

            # --- Settings state (session-scoped) -------------------------
            # Defaults match what the renderer / preview path already
            # does. Each toggle below is wired to a ``_set_setting_*``
            # method; future ``QSettings`` integration plugs in here.
            self._setting_show_axes: bool = True
            self._setting_show_grid: bool = True
            # Off by default — for systems like Lorenz the RHS magnitudes
            # vary wildly across phase space, so the magnitude-scaled arrow
            # glyphs collapse into a visually noisy blob that doesn't read
            # as a vector field. Users who want it can opt in via Settings.
            self._setting_show_vector_preview: bool = False
            self._setting_trajectory_width: float = 3.5
            from chaotic_systems.gui.theme import viewport_background
            self._setting_bg_color: str = viewport_background()

            # V2 — perturbed-IC comparison.
            #
            # When ``_setting_compare_perturbed_ic`` is True, every Run
            # chains a second simulation with ``y0[0] += epsilon`` and
            # overlays its trajectory in a distinct color. Epsilon is
            # held as a per-window setting (defaults to 1e-3 which is
            # large enough to be visually obvious on Lorenz within
            # ~20 time units but small enough that early-time orbits
            # are visually indistinguishable). The bookkeeping state
            # for the in-flight secondary sim lives in
            # ``_compare_thread`` / ``_compare_worker``.
            self._setting_compare_perturbed_ic: bool = False
            self._setting_compare_epsilon: float = 1e-3
            self._compare_thread: QThread | None = None
            self._compare_worker: _SimulateWorker | None = None
            # Snapshot the most recent Run's primary configuration so
            # the secondary sim (fired in ``_on_sim_finished``) uses
            # identical params + integrator + dt + t_end.
            self._compare_primary_config: dict[str, Any] | None = None

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

            # The System picker lives in the toolbar (a top-level mode
            # switch, not a side-panel form field). We allocate the
            # combobox here, before the toolbar build, so other cards can
            # depend on it; the toolbar builder takes ownership of layout.
            self.system_box = QComboBox(self)
            self.system_box.setObjectName("system_picker")
            self.system_box.setToolTip("Switch to a different dynamical system")
            for sys_obj in self._systems:
                self.system_box.addItem(getattr(sys_obj, "name", repr(sys_obj)))
            if preselect is not None:
                idx = self.system_box.findText(preselect)
                if idx >= 0:
                    self.system_box.setCurrentIndex(idx)
            self.system_box.currentIndexChanged.connect(self._on_system_changed)

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
            # Per-item tooltips highlight integrators with known stability
            # caveats. Euler is a 1st-order baseline and reliably blows
            # up on chaotic / stiff systems (Lorenz at dt=0.01 is the
            # canonical example) — flag it at the point of selection
            # rather than letting users hit the divergence error first.
            _per_item_tooltips = {
                "Euler": (
                    "Euler — 1st-order baseline. Unstable on chaotic / "
                    "stiff systems: Lorenz at dt=0.01 diverges. Use only "
                    "for very small dt (≲ 1e-3) or as a pedagogical "
                    "reference. Prefer RK4 / RK45 for real runs."
                ),
            }
            for name in self._integrators:
                self.integrator_box.addItem(name)
                tip = _per_item_tooltips.get(name)
                if tip is not None:
                    self.integrator_box.setItemData(
                        self.integrator_box.count() - 1,
                        tip,
                        Qt.ItemDataRole.ToolTipRole,
                    )
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

            cards_layout.addWidget(time_card)

            # --- card: Diagnostics (Lyapunov spectrum) ---
            # The full Lyapunov spectrum has been computable since the
            # initial implementation (see ``core/lyapunov.py``), but was
            # never surfaced in the GUI — this card closes that gap per
            # docs/proposals/capability-roadmap-2026-05-17.md (D1).
            diag_card, diag_layout = _make_card("Diagnostics", left_inner)
            self.lyapunov_button = QPushButton(
                "Compute Lyapunov spectrum", diag_card
            )
            self.lyapunov_button.setObjectName("button_lyapunov")
            self.lyapunov_button.setToolTip(
                "Compute the full Lyapunov spectrum (Benettin / continuous "
                "QR). Takes ~5 seconds for default Lorenz on a modern "
                "laptop. Runs on a worker thread; the GUI stays responsive."
            )
            self.lyapunov_button.clicked.connect(self._on_compute_lyapunov)
            diag_layout.addWidget(self.lyapunov_button)
            self.lyapunov_result_label = QLabel(
                "Click to compute. λ₁ > 0 ⇒ chaos; two positive exponents "
                "⇒ hyperchaos.",
                diag_card,
            )
            self.lyapunov_result_label.setWordWrap(True)
            self.lyapunov_result_label.setProperty("role", "caption")
            diag_layout.addWidget(self.lyapunov_result_label)
            cards_layout.addWidget(diag_card)

            # Run / Export / Cancel buttons all live in the toolbar now,
            # but we keep hidden Q* widgets here so internal slots can
            # depend on a stable surface (button enable/disable mirrors
            # the toolbar QActions). These are never shown in the UI.
            self.run_button = QPushButton("Run", left_inner)
            self.run_button.setProperty("variant", "primary")
            self.run_button.setObjectName("button_run")
            self.run_button.clicked.connect(self._on_run)
            self.run_button.setVisible(False)
            self.reset_view_button = QPushButton("Reset view", left_inner)
            self.reset_view_button.setObjectName("button_reset_view")
            self.reset_view_button.clicked.connect(self._on_reset_view)
            self.reset_view_button.setVisible(False)
            self.export_button = QPushButton("Export MP4", left_inner)
            self.export_button.setObjectName("button_export")
            self.export_button.clicked.connect(self._on_export)
            self.export_button.setVisible(False)
            self.cancel_button = QPushButton("Cancel", left_inner)
            self.cancel_button.setProperty("variant", "danger")
            self.cancel_button.setObjectName("button_cancel")
            self.cancel_button.clicked.connect(self._on_cancel)
            self.cancel_button.setEnabled(False)
            self.cancel_button.setVisible(False)
            # The legacy left-panel ``progress_bar`` is gone — progress lives
            # exclusively on the bottom status bar via ``status_progress``
            # (Apple-style bevelled pill) and ``status_spinner``. We keep a
            # ``progress_bar`` attribute as a back-compat alias resolved via
            # ``__getattr__`` below; legacy callers see the status-bar
            # widget instead of a separate top-left bar.

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
                    # Force a render on resize so the QOpenGLWidget never
                    # leaves stale-framebuffer streaks. We hook the
                    # interactor's ``resizeEvent`` non-invasively via a
                    # QTimer single-shot to keep VTK happy across versions.
                    original_resize = inner_viewer_widget.resizeEvent

                    def _resize_with_repaint(event: Any) -> None:
                        original_resize(event)
                        try:
                            self.viewer.GetRenderWindow().Render()
                        except (AttributeError, RuntimeError):
                            pass
                        inner_viewer_widget.update()
                        QTimer.singleShot(0, lambda: self._force_viewport_render())

                    inner_viewer_widget.resizeEvent = (  # type: ignore[method-assign]
                        _resize_with_repaint
                    )
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
            self.viewport_hint = QLabel(
                "Press Ctrl-R to simulate", viewport_frame
            )
            self.viewport_hint.setProperty("role", "hint")
            self.viewport_hint.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
            )
            self.viewport_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.viewport_hint.show()
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
            # E1 — educational notes panel.
            #
            # A ``QTextBrowser`` renders the markdown blob each system
            # exposes via ``educational_notes``. We wrap it in the same
            # ``_CollapsibleSection`` widget the LaTeX panels use so the
            # user can fold it away when not needed. Qt 5.14+ /
            # PySide6 ships ``setMarkdown`` natively, so no extra
            # dependency is needed. See
            # ``docs/proposals/capability-roadmap-2026-05-17.md`` E1.
            self.notes_widget = QTextBrowser(math_card)
            self.notes_widget.setObjectName("educational_notes")
            self.notes_widget.setOpenExternalLinks(True)
            self.notes_widget.setReadOnly(True)
            self.notes_widget.setFrameShape(QFrame.Shape.NoFrame)
            # Match the rest of the dark theme; the QSS sets a base
            # background, but the document-side stylesheet controls
            # link / heading colors so they stay legible.
            self.notes_widget.document().setDefaultStyleSheet(
                "h1,h2,h3{color:#c0caf5;margin:6px 0 4px 0;}"
                "p{color:#a9b1d6;line-height:1.4;}"
                "li{color:#a9b1d6;}"
                "code{color:#9ece6a;background:#1a1b26;"
                "padding:1px 4px;border-radius:3px;}"
                "strong{color:#e0af68;}"
                "em{color:#bb9af7;}"
                "a{color:#7aa2f7;}"
            )
            self._notes_section = _CollapsibleSection(
                "Notes",
                self.notes_widget,
                math_card,
                expanded=True,
            )
            math_layout.addWidget(self._ode_section, 1)
            math_layout.addWidget(self._lagr_section, 1)
            math_layout.addWidget(self._notes_section, 2)
            right_layout.addWidget(math_card, 1)

            # --- assemble ---------------------------------------------------
            splitter = QSplitter(Qt.Orientation.Horizontal, self)
            splitter.setHandleWidth(4)
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
            # Initialize export tooltip to the "Run a simulation first"
            # state before any trajectory exists.
            self._refresh_export_estimate()
            self._rebuild_for_current_system()
            self._sync_overlay_to_current_system()
            # Position the hint at bottom-center of the viewport as soon
            # as the frame's geometry settles. ``_reposition_overlay`` is
            # also called from the viewport-frame ``resizeEvent`` filter
            # for subsequent layout changes.
            QTimer.singleShot(0, self._reposition_overlay)
            # Draw the welcome state once the viewer's OpenGL context is up.
            # Deferring to the event loop avoids racing the QtInteractor's
            # first paint on macOS.
            QTimer.singleShot(50, self._render_vector_field_preview)

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
            self._render_vector_field_preview()

        # --- viewport welcome state ----------------------------------------

        def _force_viewport_render(self) -> None:
            """Force a fresh repaint of the QtInteractor viewport.

            Wraps the VTK render-window call with the defensive try/except
            shape we use everywhere PyVista is consumed so a transient
            teardown error never propagates to the GUI thread.
            """

            if self.viewer is None:
                return
            try:
                self.viewer.GetRenderWindow().Render()
            except (AttributeError, RuntimeError):
                pass
            try:
                self.viewer.update()
            except (AttributeError, RuntimeError):
                pass

        def _render_vector_field_preview(self) -> None:
            """Sketch a sparse vector-field preview of the current system.

            Sampled on a 12³ grid for 3D systems (20² for 2D). The preview is
            cleared the moment a real trajectory lands via ``_on_sim_finished``.
            Failures are swallowed silently — the welcome state is a "nice
            to have", not load-bearing.
            """

            if self.viewer is None:
                return
            if not getattr(self, "_setting_show_vector_preview", True):
                # User has hidden the preview — just clear and leave the
                # bg color in place.
                try:
                    self.viewer.clear()
                    self.viewer.set_background(self._setting_bg_color)
                except (AttributeError, RuntimeError):
                    pass
                self._force_viewport_render()
                return
            try:
                import pyvista as pv

                from chaotic_systems.gui.theme import (
                    PALETTE,
                )

                # Discard whatever was previously drawn (last trajectory
                # or last preview).
                self.viewer.clear()
                self.viewer.set_background(self._setting_bg_color)
                system = self.current_system
                params = default_params(system) or {}
                rhs = getattr(system, "rhs", None)
                if rhs is None:
                    return
                state_dim = int(getattr(system, "state_dim", 3) or 3)

                # Sample around the system's initial state so the preview
                # lives in a region that's actually visited by the dynamics.
                y0 = np.asarray(
                    getattr(system, "initial_state", np.zeros(state_dim)),
                    dtype=float,
                ).copy()
                if y0.size < 3:
                    y0 = np.concatenate(
                        [y0, np.zeros(3 - y0.size)]
                    )

                # Spatial extent — generous enough to look interesting.
                radius = 2.0 + 0.5 * float(np.linalg.norm(y0[:3]))
                if state_dim >= 3:
                    n = 6
                    xs = np.linspace(y0[0] - radius, y0[0] + radius, n)
                    ys = np.linspace(y0[1] - radius, y0[1] + radius, n)
                    zs = np.linspace(y0[2] - radius, y0[2] + radius, n)
                    XX, YY, ZZ = np.meshgrid(xs, ys, zs, indexing="ij")
                    pts = np.column_stack(
                        [XX.ravel(), YY.ravel(), ZZ.ravel()]
                    )
                else:
                    n = 12
                    xs = np.linspace(y0[0] - radius, y0[0] + radius, n)
                    ys = np.linspace(y0[1] - radius, y0[1] + radius, n)
                    XX, YY = np.meshgrid(xs, ys, indexing="ij")
                    pts = np.column_stack(
                        [XX.ravel(), YY.ravel(), np.zeros(XX.size)]
                    )

                # Evaluate the RHS at each sample. Use the system's own
                # state_dim — pad/truncate to feed into rhs and project the
                # vector to 3D for visualization.
                vecs = np.zeros((pts.shape[0], 3), dtype=float)
                for i, p in enumerate(pts):
                    y = np.zeros(max(state_dim, 3), dtype=float)
                    y[: min(3, state_dim)] = p[: min(3, state_dim)]
                    try:
                        v = np.asarray(rhs(0.0, y, **params), dtype=float)
                    except Exception:  # noqa: BLE001 - preview is best-effort
                        continue
                    vecs[i, : min(3, v.size)] = v[: min(3, v.size)]

                magnitudes = np.linalg.norm(vecs, axis=1)
                m = float(magnitudes.max()) if magnitudes.size else 0.0
                if m <= 0:
                    return
                # Normalize so the arrows are all visually present.
                scale = float(radius) / max(8.0, float(m))

                cloud = pv.PolyData(pts)
                cloud["vectors"] = vecs * scale
                cloud["magnitude"] = magnitudes
                glyphs = cloud.glyph(
                    orient="vectors",
                    scale="magnitude",
                    factor=0.7,
                    geom=pv.Arrow(),
                )
                self.viewer.add_mesh(
                    glyphs,
                    color=PALETTE.text_secondary,
                    opacity=0.25,
                    show_scalar_bar=False,
                )
                self.viewer.reset_camera()
                self._force_viewport_render()
            except Exception:  # noqa: BLE001 - preview never blocks the GUI
                return

        # ------------------------------------------------------------------

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

            # E1: refresh the educational-notes panel. If the system
            # didn't author any notes, fall back to a brief placeholder
            # so the panel never goes empty in a way the user could read
            # as broken.
            self._set_educational_notes(
                getattr(system, "educational_notes", "") or ""
            )

            # Refresh status-bar lyapunov chip + Diagnostics card —
            # hide / reset on system change until/unless a value is
            # computed for the new system.
            if hasattr(self, "lyapunov_chip"):
                self.lyapunov_chip.setText("λ₁ = —")
                self.lyapunov_chip.setVisible(False)
            if hasattr(self, "lyapunov_result_label"):
                self.lyapunov_result_label.setText(
                    "Click to compute. λ₁ > 0 ⇒ chaos; two positive "
                    "exponents ⇒ hyperchaos."
                )
            # The pre-export estimate is trajectory-derived; clear it
            # when the system flips so we never show a stale value.
            if hasattr(self, "export_estimate_chip"):
                self._last_trajectory = None
                self._refresh_export_estimate()

            # Gate symplectic integrators against the current system.
            # leapfrog / velocity_verlet / yoshida4 only apply to
            # separable Hamiltonian systems; for everything else
            # (Lorenz, Rossler, Chua, Duffing, double pendulum, ...)
            # they would raise a cryptic "grad_t_fn missing" error
            # mid-Run. Disable + tooltip them instead.
            self._update_integrator_availability(system)

        def _update_integrator_availability(self, system: SystemLike) -> None:
            """Disable symplectic integrators when the system isn't Hamiltonian.

            Hamiltonian systems advertise a separable ``.hamiltonian``
            (an instance of ``HamiltonianSystem`` with ``.separable``
            true). For those, every integrator stays enabled. For
            anything else, we mark the symplectic options as disabled
            via the combo's underlying model so the user can see the
            option exists but can't pick it. If the currently-selected
            integrator just got disabled, fall back to ``RK45``.
            """

            try:
                from chaotic_systems.integrators import SYMPLECTIC_INTEGRATORS
            except ImportError:  # pragma: no cover - integrators always present
                return

            ham = getattr(system, "hamiltonian", None)
            is_hamiltonian = ham is not None and bool(
                getattr(ham, "separable", False)
            )

            model = self.integrator_box.model()
            disabled_tip = (
                "Disabled — "
                + getattr(system, "name", "this system")
                + " is not a separable Hamiltonian system. Symplectic "
                "integrators (leapfrog / velocity_verlet / yoshida4) "
                "only apply when H(q, p) = T(p) + V(q). Pick RK45 / "
                "DOP853 / LSODA instead."
            )
            current_disabled = False
            current_text = self.integrator_box.currentText()
            for row in range(self.integrator_box.count()):
                name = self.integrator_box.itemText(row)
                if name not in SYMPLECTIC_INTEGRATORS:
                    continue
                item = model.item(row) if hasattr(model, "item") else None
                if item is None:
                    continue
                flags = item.flags()
                if is_hamiltonian:
                    item.setFlags(flags | Qt.ItemFlag.ItemIsEnabled)
                    # Restore the default tooltip for symplectic items
                    # — short and informative on a Hamiltonian system.
                    item.setData(
                        "Symplectic — exactly preserves the symplectic "
                        "2-form; pair with a separable Hamiltonian.",
                        Qt.ItemDataRole.ToolTipRole,
                    )
                else:
                    item.setFlags(flags & ~Qt.ItemFlag.ItemIsEnabled)
                    item.setData(disabled_tip, Qt.ItemDataRole.ToolTipRole)
                    if name == current_text:
                        current_disabled = True

            if current_disabled:
                # Fall back to RK45 (or the first non-symplectic option).
                fallback_idx = self.integrator_box.findText("RK45")
                if fallback_idx < 0:
                    for row in range(self.integrator_box.count()):
                        if (
                            self.integrator_box.itemText(row)
                            not in SYMPLECTIC_INTEGRATORS
                        ):
                            fallback_idx = row
                            break
                if fallback_idx >= 0:
                    self.integrator_box.setCurrentIndex(fallback_idx)
                    self._set_status(
                        "Switched to RK45 — "
                        + getattr(system, "name", "this system")
                        + " is not a Hamiltonian system."
                    )

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

        def _set_educational_notes(self, notes: str) -> None:
            """Render ``notes`` (markdown) into the notes panel.

            Empty strings fall back to a brief placeholder so the panel
            never reads as broken; non-empty strings are passed through
            :meth:`QTextBrowser.setMarkdown` (Qt 5.14+ — no external
            markdown dependency required).
            """
            if not hasattr(self, "notes_widget") or self.notes_widget is None:
                return
            stripped = (notes or "").strip()
            if not stripped:
                # Friendly placeholder so it's obvious the panel isn't
                # broken — just no notes have been authored yet for the
                # current system.
                self.notes_widget.setMarkdown(
                    "_No educational notes for this system yet._"
                )
                return
            self.notes_widget.setMarkdown(stripped)
            # Scroll to top in case the previous system's notes had been
            # scrolled down.
            self.notes_widget.verticalScrollBar().setValue(0)

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
            # The status bar's spinner + bevelled progress chunk are wired
            # by ``_set_status``; indeterminate while the integrator runs.
            self._show_busy(True)
            # Welcome-state cleanup — the viewport is about to hold a real
            # trajectory; the hint and the vector-field preview are done.
            if hasattr(self, "viewport_hint") and self.viewport_hint is not None:
                self.viewport_hint.hide()
            # Mirror the toolbar QAction state for run.
            run_action = self._transport_actions.get("transport_run")
            if run_action is not None:
                run_action.setEnabled(False)

            n_points = int(min(4000, max(800, round(60.0 * t_end))))
            # V2: snapshot the primary config so a chained comparison
            # sim (fired from _on_sim_finished if the compare setting
            # is on) hits exactly the same integrator / dt / n_points.
            # ``_compare_primary_config`` is consumed once per Run and
            # cleared after the secondary sim is launched (or skipped).
            if self._setting_compare_perturbed_ic and system.state_dim >= 1:
                # Perturbing component 0 by epsilon is the canonical
                # demo — the orbit pair stays on the same attractor
                # but spreads exponentially. For pathological systems
                # where component 0 should never be perturbed (none in
                # the v1 catalog), a future iteration can surface the
                # perturbed component as a setting.
                perturbed_y0 = y0.copy()
                perturbed_y0[0] += float(self._setting_compare_epsilon)
                self._compare_primary_config = {
                    "system": system,
                    "t_span": (0.0, t_end),
                    "y0": perturbed_y0,
                    "params": params,
                    "integrator": integrator,
                    "dt": float(self.dt.value()),
                    "n_points": n_points,
                }
            else:
                self._compare_primary_config = None

            worker = _SimulateWorker(
                system=system,
                t_span=(0.0, t_end),
                y0=y0,
                params=params,
                integrator=integrator,
                dt=float(self.dt.value()),
                # Request a dense uniform sampling so the playback is
                # smooth regardless of integrator step size. ~60
                # samples per simulated second targets stride ≈ 1 at
                # 15 s playback × 60 Hz GUI tick, which keeps the head
                # advancing roughly one trajectory sample per rendered
                # frame at 1× speed (the visually-smoothest case). Cap
                # at 4000 so a very long t_end doesn't blow memory.
                n_points=n_points,
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
                    # Apply the persisted trajectory-width setting before
                    # the scene builds so the polyline uses the right
                    # tube width from frame 1.
                    renderer._line_width = self._setting_trajectory_width  # noqa: SLF001
                    renderer.attach(self.viewer)
                    self._current_renderer = renderer
                    # Re-apply axes / grid / background settings since the
                    # plotter's clear() in the build path wiped them.
                    self._apply_axes_grid()
                    self._apply_bg_color()
                except (ValueError, RuntimeError) as exc:
                    self._show_error("Render failed", str(exc))
            # Wire up the transport controls for the new trajectory.
            n = self._renderer_total_frames()
            if n > 1:
                self._recompute_tick_cadence()
                self.frame_scrubber.setRange(0, n - 1)
                self._set_transport_enabled(True)
                self._seek_to(0)
            else:
                self._set_transport_enabled(False)
            # Light up the toolbar transport actions that depend on having
            # a trajectory loaded.
            for key in ("transport_pause", "transport_stop", "transport_jump_end",
                        "action_export"):
                act = self._transport_actions.get(key)
                if act is not None:
                    act.setEnabled(True)
            # V1: enable the phase-portrait action iff the trajectory has
            # at least 2 state components (the phase-plot routine requires
            # two distinct axes). 1-D maps wouldn't have a meaningful
            # portrait; 2-D-and-up always do.
            phase_act = self._transport_actions.get("action_phase_portrait")
            if phase_act is not None:
                try:
                    state_dim = int(getattr(traj, "state_dim", 0)) or int(
                        np.asarray(traj.y).shape[1]
                    )
                except (AttributeError, IndexError, ValueError):
                    state_dim = 0
                phase_act.setEnabled(state_dim >= 2)
            # D5: the recurrence plot works on any-dimensional trajectory
            # (the plot is in *time* space, not state space), so we
            # gate it only on having a trajectory at all.
            recurrence_act = self._transport_actions.get("action_recurrence")
            if recurrence_act is not None:
                recurrence_act.setEnabled(True)
            # Surface the pre-export size estimate now that a trajectory
            # exists. The chip + Export tooltip both update.
            self._refresh_export_estimate()
            # Branch: dense trajectories run the prerender worker (warm
            # the VTK pipeline, build the arc-length table, animate a
            # determinate progress pill); short trajectories skip
            # straight to playback. The threshold lives on
            # ``_PRERENDER_MIN_FRAMES`` and is documented in
            # ``docs/prerender_design.md``.
            if n >= self._PRERENDER_MIN_FRAMES and self._current_renderer is not None:
                self._start_prerender(self._current_renderer)
            else:
                self._set_status("Simulation complete.", state="done")
                if n > 1:
                    # Run starts at 1× from frame 0 per the spec.
                    self._play()

            # V2 — kick off the perturbed-IC secondary sim if the
            # compare setting was on when Run was pressed. The config
            # was snapshotted in ``_on_run``; consume + clear it here
            # so a subsequent Run with the toggle off doesn't fire a
            # leftover comparison.
            if self._compare_primary_config is not None:
                self._launch_comparison_sim(self._compare_primary_config)
                self._compare_primary_config = None

        def _on_sim_error(self, kind: str, message: str) -> None:
            self._show_error(f"Simulation failed ({kind})", self._hinted(kind, message))

        # -- V2 perturbed-IC comparison ----------------------------------

        def _on_setting_compare_perturbed_ic(self, checked: bool) -> None:
            """Toggle the V2 perturbed-IC comparison setting.

            Takes effect on the *next* Run, not retroactively — the
            current trajectory's existing overlay stays put until a
            fresh Run rebuilds the scene.
            """
            self._setting_compare_perturbed_ic = bool(checked)
            if checked:
                self._set_status(
                    "Comparison armed: next Run will overlay a perturbed-IC orbit "
                    f"(epsilon = {self._setting_compare_epsilon:g}).",
                )
            else:
                self._set_status("Comparison disarmed.")

        def _launch_comparison_sim(self, config: dict[str, Any]) -> None:
            """Kick off the V2 perturbed-IC sim on a dedicated thread.

            The config dict carries the perturbed ``y0`` already; see
            the construction site in :meth:`_on_run`. On finish the
            secondary trajectory is overlaid on the primary's renderer
            via :meth:`Renderer3D.add_overlay_trajectory`.
            """
            if self._compare_thread is not None:
                # Should be rare — the primary just finished, but defend.
                self._set_status(
                    "Comparison sim already in flight; skipping new one."
                )
                return
            try:
                worker = _SimulateWorker(
                    system=config["system"],
                    t_span=config["t_span"],
                    y0=config["y0"],
                    params=config["params"],
                    integrator=config["integrator"],
                    dt=config["dt"],
                    n_points=config["n_points"],
                )
            except (ValueError, KeyError, RuntimeError) as exc:
                self._set_status(
                    f"Comparison sim setup failed: {exc}", state="error"
                )
                return
            thread = QThread(self)
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.finished.connect(self._on_compare_finished)
            worker.error.connect(self._on_compare_error)
            worker.finished.connect(thread.quit)
            worker.error.connect(thread.quit)
            thread.finished.connect(self._cleanup_compare_thread)
            self._compare_thread = thread
            self._compare_worker = worker
            thread.start()

        def _on_compare_finished(self, traj: Any) -> None:
            """Overlay the secondary trajectory on the current renderer.

            Picks the Tokyo-Night "red-pink" accent (``#f7768e``) so
            the overlay reads against the primary's viridis colormap.
            Failure is non-fatal — the primary trajectory's playback
            continues normally and the user sees a status message.
            """
            if self._current_renderer is None:
                self._set_status(
                    "Comparison done, but the primary renderer was torn down.",
                )
                return
            try:
                self._current_renderer.add_overlay_trajectory(
                    traj,
                    color="#f7768e",
                    opacity=0.85,
                )
            except (RuntimeError, ValueError) as exc:
                self._set_status(
                    f"Comparison overlay failed: {exc}", state="error"
                )
                return
            # Compute the late-time separation as a quick numerical
            # readout — small now, but a teachable number on chaotic
            # systems. Falls back silently if shapes don't match.
            sep_msg = ""
            try:
                primary_y = np.asarray(self._last_trajectory.y, dtype=float)
                secondary_y = np.asarray(traj.y, dtype=float)
                if (
                    primary_y.ndim == 2
                    and secondary_y.ndim == 2
                    and primary_y.shape == secondary_y.shape
                ):
                    sep = float(
                        np.linalg.norm(primary_y[-1] - secondary_y[-1])
                    )
                    sep_msg = f" Final separation: {sep:.4g}."
            except (AttributeError, ValueError, IndexError):
                pass
            self._set_status(
                f"Comparison overlay added (epsilon = "
                f"{self._setting_compare_epsilon:g}).{sep_msg}",
                state="done",
            )

        def _on_compare_error(self, kind: str, message: str) -> None:
            self._set_status(
                f"Comparison sim failed ({kind}): {message}", state="error"
            )

        def _cleanup_compare_thread(self) -> None:
            if self._compare_worker is not None:
                self._compare_worker.deleteLater()
            if self._compare_thread is not None:
                self._compare_thread.deleteLater()
            self._compare_thread = None
            self._compare_worker = None

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
            if self._export_thread is None:
                self._show_busy(False)
            run_action = self._transport_actions.get("transport_run")
            if run_action is not None:
                run_action.setEnabled(True)

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
            # Spinner shows during the export warm-up; the determinate
            # progress chunk takes over once the first frame ships.
            self._show_busy(True)
            self.status_progress.setRange(0, 100)
            self.status_progress.setValue(0)
            self.status_progress.setVisible(True)

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
            # The first determinate update hides the spinner; the bevelled
            # progress chunk now carries the signal.
            if self.status_spinner.isVisible():
                self.status_spinner.stop()
            self.status_progress.setRange(0, int(total))
            self.status_progress.setValue(int(current))
            self.status_progress.setVisible(True)

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
            self._show_busy(False)

        # --------------------------------------------------- prerender pipeline

        def _start_prerender(self, renderer: Renderer3D) -> None:
            """Kick off ``Renderer3D.build_prerender_cache`` on a worker thread.

            Called from :meth:`_on_sim_finished` once a fresh trajectory
            is in the renderer. Shows a determinate progress pill in the
            status bar ("Preparing animation... X%") and only fires
            playback when the worker's ``finished`` signal lands.
            """

            # Defensive — don't pile a second prerender on top of a
            # still-running one.
            if self._prerender_thread is not None:
                return
            self._set_status(
                "Preparing animation...", busy=True, state="running"
            )
            # Status-bar prep: spinner runs (rotating arc), and the
            # determinate progress chunk is primed for the worker's
            # progress signal. ``_show_busy(True)`` already arms the
            # spinner; we *also* want the pill visible from frame zero
            # so the user sees the determinate progress from the first
            # tick instead of an indeterminate spinner-only phase.
            self._show_busy(True)
            self.status_progress.setRange(0, 100)
            self.status_progress.setValue(0)
            self.status_progress.setVisible(True)
            # The Cancel toolbar action handles prerender cancellation.
            self.cancel_button.setEnabled(True)

            worker = _PrerenderWorker(renderer)
            thread = QThread(self)
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.progress.connect(self._on_prerender_progress)
            worker.finished.connect(self._on_prerender_finished)
            worker.cancelled.connect(self._on_prerender_cancelled)
            worker.error.connect(self._on_prerender_error)
            worker.finished.connect(thread.quit)
            worker.cancelled.connect(thread.quit)
            worker.error.connect(thread.quit)
            thread.finished.connect(self._cleanup_prerender_thread)
            self._prerender_thread = thread
            self._prerender_worker = worker
            thread.start()

        def _on_prerender_progress(self, current: int, total: int) -> None:
            if total <= 0:
                return
            self.status_progress.setRange(0, int(total))
            self.status_progress.setValue(int(current))
            self.status_progress.setVisible(True)
            pct = int(round(100.0 * current / max(1, total)))
            self._set_status(
                f"Preparing animation... {pct}%",
                busy=True,
                state="running",
            )

        def _on_prerender_finished(self) -> None:
            self._set_status("Simulation complete.", state="done")
            # Spinner stops; the pill animates the last frame and
            # disappears at the end of the next status update.
            self._show_busy(False)
            self.cancel_button.setEnabled(False)
            # Now that the renderer is warm, start playback.
            if self._current_renderer is not None and self._renderer_total_frames() > 1:
                self._play()

        def _on_prerender_cancelled(self) -> None:
            self._set_status(
                "Animation prep cancelled — scrub or press Run to retry.",
                state="idle",
            )
            self._show_busy(False)
            self.cancel_button.setEnabled(False)
            # Leave the transport controls enabled — the trajectory is
            # still loaded, the user can scrub manually or trigger Run
            # again to retry.

        def _on_prerender_error(self, kind: str, message: str) -> None:
            self._show_error(
                f"Animation prep failed ({kind})",
                self._hinted(kind, message),
            )
            self._show_busy(False)
            self.cancel_button.setEnabled(False)

        def _cleanup_prerender_thread(self) -> None:
            if self._prerender_worker is not None:
                self._prerender_worker.deleteLater()
            if self._prerender_thread is not None:
                self._prerender_thread.deleteLater()
            self._prerender_thread = None
            self._prerender_worker = None

        # ------------------------------------------------------------------ Lyapunov

        def _on_compute_lyapunov(self) -> None:
            """Kick off the Lyapunov-spectrum worker for the current system.

            Reads parameters and initial state from the current widget
            state so users see the spectrum of whatever they have
            dialled in, not just the system defaults. Disables the
            button while the worker runs and re-enables on
            finished / error.
            """

            if self._lyapunov_thread is not None:
                # Already computing.
                return
            try:
                system = self.current_system
            except IndexError:
                return
            params = self._params() or default_params(system)
            try:
                y0 = np.asarray(system.initial_state, dtype=float).copy()
            except (AttributeError, ValueError):
                self.lyapunov_result_label.setText(
                    "Could not read initial state from the system."
                )
                return
            if not np.isfinite(y0).all():
                self.lyapunov_result_label.setText(
                    "Initial state has non-finite entries; cannot compute spectrum."
                )
                return

            self.lyapunov_button.setEnabled(False)
            self.lyapunov_result_label.setText("Computing spectrum…")
            self._set_status(
                "Computing Lyapunov spectrum (~5 s)…", busy=True
            )

            worker = _LyapunovWorker(system, params, y0)
            thread = QThread(self)
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.finished.connect(self._on_lyapunov_finished)
            worker.error.connect(self._on_lyapunov_error)
            worker.finished.connect(thread.quit)
            worker.error.connect(thread.quit)
            thread.finished.connect(self._cleanup_lyapunov_thread)
            self._lyapunov_thread = thread
            self._lyapunov_worker = worker
            thread.start()

        def _on_lyapunov_finished(self, spectrum: np.ndarray) -> None:
            text, leading = _format_lyapunov_spectrum(spectrum)
            self.lyapunov_result_label.setText(text)
            self.lyapunov_button.setEnabled(True)
            self._set_status("Lyapunov spectrum ready.", state="done")
            if hasattr(self, "lyapunov_chip"):
                self.lyapunov_chip.setText(f"λ₁ = {leading:+.4f}")
                self.lyapunov_chip.setVisible(True)

        def _on_lyapunov_error(self, kind: str, message: str) -> None:
            self.lyapunov_result_label.setText(
                f"{kind}: {message}"
            )
            self.lyapunov_button.setEnabled(True)
            self._set_status("Lyapunov compute failed.", state="error")

        def _cleanup_lyapunov_thread(self) -> None:
            if self._lyapunov_worker is not None:
                self._lyapunov_worker.deleteLater()
            if self._lyapunov_thread is not None:
                self._lyapunov_thread.deleteLater()
            self._lyapunov_thread = None
            self._lyapunov_worker = None

        # ------------------------------------------------------------------

        def _on_cancel(self) -> None:
            cancelled = False
            # Cancellation precedence: export → prerender → sim. Export
            # takes priority because it's the most expensive
            # user-initiated operation; prerender is short but visible;
            # sim is treated as best-effort acknowledgement.
            if self._export_worker is not None:
                self._export_worker.cancel()
                cancelled = True
                self._set_status("Cancelling export...")
            if not cancelled and self._prerender_worker is not None:
                self._prerender_worker.cancel()
                cancelled = True
                self._set_status("Cancelling animation prep...")
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

        def _on_open_bifurcation(self) -> None:
            """Open the bifurcation-diagram explorer in a top-level window.

            The dialog has its own picker over the registered discrete
            maps (Logistic / HenonMap / Ikeda / StandardMap) so it
            does not depend on the main window's ODE-only system picker.
            See ``docs/proposals/capability-roadmap-2026-05-17.md`` D2.
            """
            try:
                from chaotic_systems.gui.bifurcation_panel import (
                    build_bifurcation_dialog,
                )
            except ImportError as exc:  # pragma: no cover
                self._set_status(
                    f"Bifurcation explorer unavailable: {exc}",
                    state="error",
                )
                return
            try:
                dialog = build_bifurcation_dialog(parent=self)
            except ValueError as exc:
                self._set_status(
                    f"No discrete maps registered: {exc}", state="error"
                )
                return
            # Hold a reference so the window isn't GC'd before it's shown;
            # WA_DeleteOnClose handles cleanup once the user closes it.
            self._bifurcation_window = dialog
            dialog.show()

        def _on_open_recurrence(self) -> None:
            """Open the recurrence-plot / RQA explorer on the most recent trajectory.

            See ``docs/proposals/capability-roadmap-2026-05-17.md`` D5.
            """
            traj = self._last_trajectory
            if traj is None:
                self._set_status(
                    "Run a simulation first — the recurrence plot reads "
                    "the most recent trajectory.",
                    state="error",
                )
                return
            try:
                from chaotic_systems.gui.recurrence_panel import (
                    build_recurrence_dialog,
                )
            except ImportError as exc:  # pragma: no cover
                self._set_status(
                    f"Recurrence explorer unavailable: {exc}", state="error"
                )
                return
            system = None
            try:
                system = self.current_system
            except (AttributeError, IndexError):
                pass
            try:
                dialog = build_recurrence_dialog(
                    traj,
                    system_name=getattr(system, "name", None),
                    parent=self,
                )
            except (TypeError, ValueError) as exc:
                self._set_status(
                    f"Recurrence plot failed: {exc}", state="error"
                )
                return
            self._recurrence_window = dialog
            dialog.show()

        def _on_open_basins(self) -> None:
            """Open the basin-of-attraction explorer in a top-level window.

            The dialog ships with the canonical undriven double-well
            Duffing demo preloaded; future iterations can surface
            arbitrary system + attractor selection. See
            ``docs/proposals/capability-roadmap-2026-05-17.md`` D4.
            """
            try:
                from chaotic_systems.gui.basin_panel import build_basin_dialog
            except ImportError as exc:  # pragma: no cover
                self._set_status(
                    f"Basin explorer unavailable: {exc}", state="error"
                )
                return
            try:
                dialog = build_basin_dialog(parent=self)
            except (ValueError, RuntimeError) as exc:
                self._set_status(
                    f"Basin explorer failed: {exc}", state="error"
                )
                return
            self._basin_window = dialog
            dialog.show()

        def _on_open_phase_portrait(self) -> None:
            """Open the 2D phase-portrait explorer on the most recent trajectory.

            The dialog is a single-trajectory snapshot — to refresh
            against a newer simulation, the user re-opens it after
            re-running. See
            ``docs/proposals/capability-roadmap-2026-05-17.md`` V1.
            """
            traj = self._last_trajectory
            if traj is None:
                self._set_status(
                    "Run a simulation first — the phase portrait reads the "
                    "most recent trajectory.",
                    state="error",
                )
                return
            state_dim = int(
                getattr(traj, "state_dim", 0)
                or getattr(traj, "y", np.zeros((1, 0))).shape[1]
            )
            if state_dim < 2:
                self._set_status(
                    "Phase portrait requires a system with state_dim >= 2.",
                    state="error",
                )
                return
            try:
                from chaotic_systems.gui.phase_panel import build_phase_dialog
            except ImportError as exc:  # pragma: no cover
                self._set_status(
                    f"Phase-portrait explorer unavailable: {exc}",
                    state="error",
                )
                return
            from chaotic_systems.gui.theme import viewport_background

            system = None
            try:
                system = self.current_system
            except (AttributeError, IndexError):
                pass
            axes_labels = (
                self._axes_labels_for(system) if system is not None else None
            )
            try:
                dialog = build_phase_dialog(
                    traj,
                    axes_labels=axes_labels,
                    system_name=getattr(system, "name", None),
                    facecolor=viewport_background(),
                    parent=self,
                )
            except (TypeError, ValueError) as exc:
                self._set_status(
                    f"Phase portrait failed: {exc}", state="error"
                )
                return
            self._phase_window = dialog
            dialog.show()

        # ------------------------------------------------------------ toolbar

        # Toolbar action specs: (object_name, label, icon-stem, tooltip,
        # slot, starts_enabled). ``icon_stem`` resolves to
        # ``assets/icons/<stem>.svg``. Kept as data so the structure is
        # readable and external agents can introspect it via
        # ``MainWindow.transport_actions()``.
        def _toolbar_action_specs(self) -> list[tuple[str, str, str, str, Any, bool]]:
            return [
                (
                    "transport_run",
                    "Run",
                    "run",
                    "Integrate and start animated playback (Ctrl-R)",
                    self._on_run,
                    True,
                ),
                (
                    "transport_pause",
                    "Pause",
                    "pause",
                    "Pause / resume playback (Space)",
                    self._on_toggle_play,
                    False,
                ),
                (
                    "transport_stop",
                    "Stop",
                    "stop",
                    "Stop playback and rewind to start (Ctrl-.)",
                    self._on_stop,
                    False,
                ),
                (
                    "transport_jump_end",
                    "Jump to end",
                    "jump-end",
                    "Jump to the last frame of the trajectory (End)",
                    self._on_jump_to_end,
                    False,
                ),
                (
                    "action_export",
                    "Export MP4",
                    "export",
                    "Render the current trajectory to an MP4 file (Ctrl-E)",
                    self._on_export,
                    False,
                ),
                (
                    "action_reset_view",
                    "Reset view",
                    "reset-view",
                    "Re-center the 3D camera (R)",
                    self._on_reset_view,
                    True,
                ),
                (
                    "action_bifurcation",
                    "Bifurcation…",
                    "bifurcation",
                    "Open the bifurcation-diagram explorer for the registered "
                    "discrete maps (logistic / Hénon / Ikeda / standard map). "
                    "See docs/proposals/capability-roadmap-2026-05-17.md D2.",
                    self._on_open_bifurcation,
                    True,
                ),
                (
                    "action_phase_portrait",
                    "Phase portrait…",
                    "phase-portrait",
                    "Open the 2D phase-portrait explorer on the most recent "
                    "trajectory. Pick any two state-vector components to plot "
                    "y[i] vs y[j]. Disabled until you've run a simulation. "
                    "See docs/proposals/capability-roadmap-2026-05-17.md V1.",
                    self._on_open_phase_portrait,
                    False,
                ),
                (
                    "action_recurrence",
                    "Recurrence plot…",
                    "recurrence",
                    "Open the recurrence-plot + RQA explorer on the most "
                    "recent trajectory. Reveals periodic / chaotic / laminar "
                    "structure that the 3D render alone doesn't expose. "
                    "Disabled until you've run a simulation. See "
                    "docs/proposals/capability-roadmap-2026-05-17.md D5.",
                    self._on_open_recurrence,
                    False,
                ),
                (
                    "action_basins",
                    "Basins…",
                    "basins",
                    "Open the basin-of-attraction explorer (undriven "
                    "double-well Duffing demo). Map the (x, v) plane "
                    "by which fixed point each initial condition flows to. "
                    "See docs/proposals/capability-roadmap-2026-05-17.md D4.",
                    self._on_open_basins,
                    True,
                ),
                (
                    "action_toggle_theme",
                    "Toggle theme",
                    "theme",
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

            Toolbar layout (left to right):

                [System ▾]  Run  Pause  Stop  Jump-to-end  |  Export  |  Reset view  Theme
            """

            toolbar = QToolBar("main", self)
            toolbar.setObjectName("toolbar_main")
            toolbar.setMovable(False)
            toolbar.setFloatable(False)
            toolbar.setIconSize(QSize(18, 18))
            toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

            # System picker first — the most common "pick a system, then
            # hit Run" flow is now a two-click motion in the same row.
            self.system_box.setMinimumWidth(160)
            toolbar.addWidget(self.system_box)
            toolbar.addSeparator()

            icons_dir = (
                Path(__file__).resolve().parent / "assets" / "icons"
            )

            for i, spec in enumerate(self._toolbar_action_specs()):
                obj_name, label, icon_stem, tip, slot, enabled = spec
                # Separators before Export and Toggle-theme group related
                # actions visually.
                if obj_name in {"action_export", "action_reset_view"} and i > 0:
                    toolbar.addSeparator()
                action = QAction(label, self)
                action.setObjectName(obj_name)
                action.setToolTip(tip)
                icon_path = icons_dir / f"{icon_stem}.svg"
                if icon_path.exists():
                    action.setIcon(QIcon(str(icon_path)))
                action.setEnabled(enabled)
                action.triggered.connect(slot)
                toolbar.addAction(action)
                if obj_name == "transport_run":
                    # Mark "Run" as the primary action via QSS variant.
                    btn = toolbar.widgetForAction(action)
                    if btn is not None:
                        btn.setProperty("variant", "primary")
                        btn.style().unpolish(btn)
                        btn.style().polish(btn)
                self._transport_actions[obj_name] = action

            # --- Settings dropdown ----------------------------------------
            # Separator + gear button with a popup QMenu. Holds toggles for
            # axes, grid, background color, trajectory width, and the
            # vector-field preview. QSettings persistence is stubbed.
            toolbar.addSeparator()
            self._settings_button = self._build_settings_button(toolbar, icons_dir)
            toolbar.addWidget(self._settings_button)

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

        # ------------------------------------------------------------ settings

        # Background-color presets surfaced in the Settings dropdown.
        # Each entry is ``(label, hex)``. The user can also open a full
        # ``QColorDialog`` for an arbitrary color.
        _BG_PRESETS: tuple[tuple[str, str], ...] = (
            ("Tokyo Night", "#24283b"),
            ("Deep Night", "#1a1b26"),
            ("Pure Black", "#000000"),
            ("Paper Cream", "#f5f1e8"),
        )

        def _build_settings_button(self, toolbar: QToolBar, icons_dir: Path) -> QToolButton:
            """Build the gear button with a popup ``QMenu`` of toggles."""

            btn = QToolButton(toolbar)
            btn.setObjectName("button_settings")
            btn.setToolTip("Display settings")
            btn.setText("Settings")
            icon_path = icons_dir / "gear.svg"
            if icon_path.exists():
                btn.setIcon(QIcon(str(icon_path)))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

            menu = QMenu(btn)
            menu.setObjectName("menu_settings")

            # Show axes ----------------------------------------------------
            self.action_show_axes = QAction("Show axes", self)
            self.action_show_axes.setCheckable(True)
            self.action_show_axes.setChecked(self._setting_show_axes)
            self.action_show_axes.toggled.connect(self._on_setting_show_axes)
            menu.addAction(self.action_show_axes)

            # Show grid ----------------------------------------------------
            self.action_show_grid = QAction("Show grid", self)
            self.action_show_grid.setCheckable(True)
            self.action_show_grid.setChecked(self._setting_show_grid)
            self.action_show_grid.toggled.connect(self._on_setting_show_grid)
            menu.addAction(self.action_show_grid)

            # Show vector field preview -----------------------------------
            self.action_show_vector_preview = QAction(
                "Show vector field preview", self
            )
            self.action_show_vector_preview.setCheckable(True)
            self.action_show_vector_preview.setChecked(
                self._setting_show_vector_preview
            )
            self.action_show_vector_preview.toggled.connect(
                self._on_setting_show_vector_preview
            )
            menu.addAction(self.action_show_vector_preview)

            # V2 — compare with perturbed IC -------------------------------
            # Toggling this on makes Run launch the primary trajectory as
            # usual, then immediately fire a *secondary* sim with the same
            # parameters but ``y0[0] += epsilon``. The secondary loads into
            # the same viewport as a static red overlay via
            # ``Renderer3D.add_overlay_trajectory`` — making "sensitive
            # dependence on initial conditions" a single-click demo
            # (Strogatz section 9). Epsilon is fixed at ``1e-3`` for v1;
            # a slider is the natural follow-up.
            self.action_compare_perturbed_ic = QAction(
                "Compare: perturbed initial condition", self
            )
            self.action_compare_perturbed_ic.setObjectName(
                "action_compare_perturbed_ic"
            )
            self.action_compare_perturbed_ic.setCheckable(True)
            self.action_compare_perturbed_ic.setChecked(
                self._setting_compare_perturbed_ic
            )
            self.action_compare_perturbed_ic.setToolTip(
                "On the next Run, also integrate the same system with "
                f"y0[0] += {self._setting_compare_epsilon:g}. The "
                "perturbed orbit overlays the primary in a distinct "
                "color so you can watch them diverge. The butterfly "
                "effect in one click. See "
                "docs/proposals/capability-roadmap-2026-05-17.md V2."
            )
            self.action_compare_perturbed_ic.toggled.connect(
                self._on_setting_compare_perturbed_ic
            )
            menu.addAction(self.action_compare_perturbed_ic)

            menu.addSeparator()

            # Background submenu ------------------------------------------
            bg_menu = menu.addMenu("Background")
            bg_menu.setObjectName("menu_settings_background")
            self._bg_actions: dict[str, QAction] = {}
            for label, hex_color in self._BG_PRESETS:
                act = QAction(f"  {label}  ({hex_color})", self)
                act.setCheckable(True)
                act.setChecked(hex_color.lower() == self._setting_bg_color.lower())
                act.triggered.connect(
                    lambda _checked=False, color=hex_color: self._on_setting_bg_color(color)
                )
                bg_menu.addAction(act)
                self._bg_actions[hex_color.lower()] = act
            bg_menu.addSeparator()
            pick_act = QAction("Open color picker...", self)
            pick_act.triggered.connect(self._on_setting_bg_color_pick)
            bg_menu.addAction(pick_act)

            # Trajectory width — a slider in a QWidgetAction. -------------
            width_holder = QWidget(menu)
            wh_layout = QHBoxLayout(width_holder)
            wh_layout.setContentsMargins(8, 4, 8, 4)
            wh_layout.setSpacing(8)
            wh_layout.addWidget(QLabel("Trajectory width", width_holder))
            self.trajectory_width_slider = QSlider(
                Qt.Orientation.Horizontal, width_holder
            )
            self.trajectory_width_slider.setObjectName("trajectory_width_slider")
            # Slider integer range maps to 1.0..6.0 px in 0.1 increments.
            self.trajectory_width_slider.setRange(10, 60)
            self.trajectory_width_slider.setValue(
                int(round(self._setting_trajectory_width * 10))
            )
            self.trajectory_width_slider.setSingleStep(1)
            self.trajectory_width_slider.setMinimumWidth(140)
            self.trajectory_width_slider.valueChanged.connect(
                self._on_setting_trajectory_width
            )
            wh_layout.addWidget(self.trajectory_width_slider, 1)
            self.trajectory_width_value = QLabel(
                f"{self._setting_trajectory_width:.1f} px", width_holder
            )
            self.trajectory_width_value.setMinimumWidth(48)
            wh_layout.addWidget(self.trajectory_width_value)
            width_action = QWidgetAction(self)
            width_action.setDefaultWidget(width_holder)
            menu.addSeparator()
            menu.addAction(width_action)

            btn.setMenu(menu)
            self._settings_menu = menu
            return btn

        # -- setting handlers --------------------------------------------

        def _on_setting_show_axes(self, checked: bool) -> None:
            self._setting_show_axes = bool(checked)
            self._apply_axes_grid()

        def _on_setting_show_grid(self, checked: bool) -> None:
            self._setting_show_grid = bool(checked)
            self._apply_axes_grid()

        def _on_setting_show_vector_preview(self, checked: bool) -> None:
            self._setting_show_vector_preview = bool(checked)
            # Repaint the welcome state only when no trajectory has been
            # rendered yet — once a sim has landed, the preview has been
            # cleared and re-enabling the setting will surface it on the
            # next sim cycle.
            if self._current_renderer is None and self.viewer is not None:
                if checked:
                    self._render_vector_field_preview()
                else:
                    try:
                        self.viewer.clear()
                        self.viewer.set_background(self._setting_bg_color)
                    except (AttributeError, RuntimeError):
                        pass
                    self._force_viewport_render()

        def _on_setting_bg_color(self, hex_color: str) -> None:
            self._setting_bg_color = str(hex_color)
            for key, act in self._bg_actions.items():
                act.setChecked(key == hex_color.lower())
            self._apply_bg_color()

        def _on_setting_bg_color_pick(self) -> None:
            from PySide6.QtGui import QColor

            initial = QColor(self._setting_bg_color)
            picked = QColorDialog.getColor(initial, self, "Pick background color")
            if not picked.isValid():
                return
            hex_color = picked.name()
            self._setting_bg_color = hex_color
            # Sync the preset checkmarks (an arbitrary color clears them all).
            for key, act in self._bg_actions.items():
                act.setChecked(key == hex_color.lower())
            self._apply_bg_color()

        def _on_setting_trajectory_width(self, value: int) -> None:
            self._setting_trajectory_width = float(value) / 10.0
            self.trajectory_width_value.setText(
                f"{self._setting_trajectory_width:.1f} px"
            )
            # Push to the renderer if one is attached. We rebuild the line
            # actor via the existing color-by-progress path so we never
            # rebuild the head sphere or the polyline PolyData.
            r = self._current_renderer
            if r is None:
                return
            try:
                r._line_width = self._setting_trajectory_width  # noqa: SLF001
                # Trigger a line-actor rebuild by flipping color-by-progress
                # off and on; the kwargs are read fresh each pass.
                if hasattr(r, "set_line_width"):
                    r.set_line_width(self._setting_trajectory_width)
                else:
                    # Fall back: flip the color-by-progress toggle to force
                    # a line-mesh rebuild that picks up any new attribute.
                    enabled = getattr(r, "_color_by_progress_enabled", True)
                    r.set_color_by_progress(not enabled)
                    r.set_color_by_progress(bool(enabled))
            except (AttributeError, RuntimeError):  # pragma: no cover - defensive
                pass

        def _apply_axes_grid(self) -> None:
            """Reflect the axes/grid checkboxes onto the active plotter."""

            if self.viewer is None:
                return
            try:
                if self._setting_show_axes:
                    self.viewer.show_axes()
                else:
                    try:
                        self.viewer.hide_axes()
                    except (AttributeError, RuntimeError):
                        pass
                if self._setting_show_grid:
                    try:
                        self.viewer.show_grid()
                    except (AttributeError, RuntimeError, TypeError):
                        pass
                else:
                    try:
                        self.viewer.remove_bounds_axes()
                    except (AttributeError, RuntimeError):
                        try:
                            self.viewer.show_grid(show_xaxis=False, show_yaxis=False,
                                                  show_zaxis=False)
                        except (AttributeError, RuntimeError, TypeError):
                            pass
            finally:
                self._force_viewport_render()

        def _apply_bg_color(self) -> None:
            """Push the current background-color setting onto the plotter."""

            if self.viewer is None:
                return
            try:
                self.viewer.set_background(self._setting_bg_color)
            except (AttributeError, RuntimeError):  # pragma: no cover - defensive
                pass
            self._force_viewport_render()

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

            # State chip — Idle / Running / Playing / Exporting / Error.
            self.state_chip = QLabel("Idle", bar)
            self.state_chip.setProperty("role", "chip")
            self.state_chip.setProperty("state", "idle")
            self.state_chip.setToolTip("Current run state")

            # Frame chip — i / N. Hidden until a trajectory exists so the
            # idle status bar isn't dominated by decorative zeros.
            self.frame_chip = QLabel("frame 0 / 0", bar)
            self.frame_chip.setProperty("role", "chip")
            self.frame_chip.setToolTip("Animated frame index / total frames")
            self.frame_chip.setVisible(False)

            # Time chip — t = ...
            self.time_chip = QLabel("t = 0.000", bar)
            self.time_chip.setProperty("role", "chip")
            self.time_chip.setToolTip("Current simulation time")
            self.time_chip.setVisible(False)

            # Lyapunov chip — λ₁ = ... when computed.
            self.lyapunov_chip = QLabel("λ₁ = —", bar)
            self.lyapunov_chip.setProperty("role", "chip")
            self.lyapunov_chip.setProperty("highlight", "lyapunov")
            self.lyapunov_chip.setToolTip(
                "Largest Lyapunov exponent (positive = chaotic)"
            )
            self.lyapunov_chip.setVisible(False)

            # Busy spinner — Apple-style rotating arc shown to the LEFT of
            # the state chip during indeterminate work (simulation / export
            # warm-up). Hides as soon as the determinate progress chunk can
            # take over.
            self.status_spinner = _BusySpinner(bar, diameter=14)

            # Determinate progress chunk — Apple-style bevelled pill,
            # gradient fill. Only visible while the export pipeline is
            # actively shipping frames; for the simulation pipeline the
            # spinner does the work.
            self.status_progress = QProgressBar(bar)
            self.status_progress.setObjectName("status_progress")
            self.status_progress.setProperty("variant", "pill")
            self.status_progress.setRange(0, 100)
            self.status_progress.setValue(0)
            self.status_progress.setTextVisible(False)
            self.status_progress.setFixedHeight(8)
            self.status_progress.setMinimumWidth(140)
            self.status_progress.setMaximumWidth(220)
            self.status_progress.setVisible(False)

            # Pre-export estimate chip — visible only after a sim completes
            # so the user can size up the download before clicking Export.
            self.export_estimate_chip = QLabel("", bar)
            self.export_estimate_chip.setProperty("role", "chip")
            self.export_estimate_chip.setProperty("highlight", "estimate")
            self.export_estimate_chip.setToolTip(
                "Estimated export size, frame count, and duration"
            )
            self.export_estimate_chip.setVisible(False)

            bar.addWidget(self.status_spinner)
            bar.addWidget(self.state_chip)
            bar.addWidget(self.status_progress)
            bar.addPermanentWidget(self.export_estimate_chip)
            bar.addPermanentWidget(self.frame_chip)
            bar.addPermanentWidget(self.time_chip)
            bar.addPermanentWidget(self.lyapunov_chip)

            # Back-compat alias for the (now-removed) left-panel progress
            # bar. Anything still calling ``self.progress_bar.setVisible``
            # actually toggles the status-bar pill — and the spinner takes
            # over for indeterminate phases via ``_show_busy``.
            self.progress_bar = self.status_progress

        # ----- pre-export size estimate ----------------------------------

        # Empirical bytes-per-second for the renderer's default 1280x720
        # libx264 q=8 output. Calibrated against a 10 s reference clip
        # (~21 MB observed). Tweak if the renderer defaults change.
        EXPORT_EST_MB_PER_SEC: float = 2.1
        EXPORT_EST_FPS: int = 30

        def _format_export_estimate(
            self,
            *,
            n_frames: int,
            fps: int,
            mb_per_sec: float,
        ) -> str:
            """Return a human-readable size estimate.

            ``n_frames`` is the trajectory sample count. We don't always
            export every sample (the export pipeline picks a fixed
            ``duration_seconds`` at 30 fps, ~10 s default), so the
            estimate is for a *full* trajectory at the renderer's default
            fps.
            """

            if n_frames <= 0 or fps <= 0:
                return "—"
            # Match the export worker's actual fixed 10 s clip default —
            # what the user will get when they hit Export today.
            duration_s = float(self._export_duration_seconds(n_frames, fps))
            est_mb = duration_s * float(mb_per_sec)
            return (
                f"~{est_mb:.1f} MB · {n_frames} frames · "
                f"{duration_s:.1f} s @ {fps} fps"
            )

        def _export_duration_seconds(self, n_frames: int, fps: int) -> float:
            """Compute the export clip duration that matches the worker default.

            Today the export worker hard-codes a 10 s clip; if the source
            trajectory is shorter than that at ``fps``, the worker will
            still ship the full polyline so the clip is bounded by the
            trajectory length. We mirror that ceiling here so the
            estimate doesn't lie.
            """

            if fps <= 0 or n_frames <= 0:
                return 0.0
            # The worker caps duration at 10 s; we cap our estimate too.
            return float(min(10.0, max(2.0 / fps, n_frames / float(fps))))

        def _refresh_export_estimate(self) -> None:
            """Recompute and surface the pre-export size estimate.

            Called after every successful simulation. Updates the
            tooltip on the toolbar Export action and the status-bar
            estimate chip. If no trajectory exists yet, the chip is
            hidden and the action's tooltip says "Run a simulation
            first".
            """

            traj = self._last_trajectory
            n_frames = 0
            if traj is not None:
                try:
                    t = np.asarray(traj.t, dtype=float)
                    n_frames = int(t.size)
                except (AttributeError, ValueError, TypeError):
                    n_frames = 0
            export_action = self._transport_actions.get("action_export")
            if n_frames <= 0:
                if hasattr(self, "export_estimate_chip"):
                    self.export_estimate_chip.setVisible(False)
                    self.export_estimate_chip.setText("")
                if export_action is not None:
                    export_action.setToolTip(
                        "Render the current trajectory to an MP4 file "
                        "(Ctrl-E)\n— Run a simulation first."
                    )
                return
            text = self._format_export_estimate(
                n_frames=n_frames,
                fps=self.EXPORT_EST_FPS,
                mb_per_sec=self.EXPORT_EST_MB_PER_SEC,
            )
            if hasattr(self, "export_estimate_chip"):
                self.export_estimate_chip.setText(text)
                self.export_estimate_chip.setVisible(True)
            if export_action is not None:
                export_action.setToolTip(
                    "Render the current trajectory to an MP4 file "
                    f"(Ctrl-E)\nEstimated: {text}"
                )

        def _show_busy(self, busy: bool) -> None:
            """Toggle the indeterminate spinner + hide/show the progress pill.

            ``busy=True`` runs the rotating-arc spinner and hides the
            determinate progress chunk. ``busy=False`` stops the spinner
            and resets the progress chunk to a hidden / zeroed state.
            """

            if busy:
                self.status_spinner.start()
                self.status_progress.setVisible(False)
                self.status_progress.setValue(0)
            else:
                self.status_spinner.stop()
                self.status_progress.setVisible(False)
                self.status_progress.setRange(0, 100)
                self.status_progress.setValue(0)

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
            t_end = self._trajectory_t_value(max(0, n - 1))
            if t_now is None:
                self.time_chip.setText("t = 0.000")
            elif t_end is None:
                self.time_chip.setText(f"t = {t_now:.3f}")
            else:
                self.time_chip.setText(f"t = {t_now:.3f} / {t_end:.3f}")
            # Reveal the frame/time chips once a trajectory exists.
            self.frame_chip.setVisible(n > 0)
            self.time_chip.setVisible(n > 0)
            # The Lyapunov chip stays hidden until a value is actually
            # computed; we don't have an estimator wired in here, so we
            # leave it hidden but available for callers that want to set
            # it after the fact.
            if hasattr(self, "_is_playing") and self._is_playing:
                self._set_state_chip(
                    f"Playing: t = {t_now or 0.0:.1f} / {(t_end or 0.0):.1f} s",
                    "running",
                )

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
                # Force the entire viewport frame to repaint AND the
                # QtInteractor to clear its framebuffer so the previous
                # overlay's pixels don't bleed through under the new
                # (potentially narrower) chip.
                if hasattr(self, "_viewport_frame"):
                    self._viewport_frame.repaint()
                self._force_viewport_render()

        def _reposition_overlay(self) -> None:
            """Pin the overlay to the top-left and the hint to bottom-center."""

            if (
                not hasattr(self, "viewport_overlay")
                or self.viewport_overlay is None
                or not hasattr(self, "_viewport_frame")
            ):
                return
            margin = 12
            self.viewport_overlay.move(margin, margin)
            self.viewport_overlay.raise_()
            if (
                hasattr(self, "viewport_hint")
                and self.viewport_hint is not None
                and self.viewport_hint.isVisible()
            ):
                self.viewport_hint.adjustSize()
                fw = self._viewport_frame.width()
                fh = self._viewport_frame.height()
                self.viewport_hint.move(
                    (fw - self.viewport_hint.width()) // 2,
                    fh - self.viewport_hint.height() - 14,
                )
                self.viewport_hint.raise_()

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

        # Minimum trajectory size at which we run the prerender worker.
        # Below this, the arc-length table is cheap (< 1 ms) and the VTK
        # warm-up adds latency without enough payoff to be worth a
        # determinate-progress UI. Tune by measuring against a long
        # trajectory: see ``docs/prerender_design.md`` for the rationale.
        _PRERENDER_MIN_FRAMES: int = 500

        def _build_transport_panel(self, parent: QWidget) -> QWidget:
            """Build the scrubber strip under the viewport.

            Layout::

                Speed: [1× v]   [=====O==========] t = 12.3 / 40.0

            Run / Pause / Stop / Jump-to-end live in the top toolbar — this
            strip is for *time scrubbing during/after a simulation*, not
            for triggering one. Play / Stop / Jump-end QPushButton handles
            are kept as hidden widgets so internal slots and tests keep
            working without per-call ``hasattr`` checks.
            """

            host = QWidget(parent)
            row = QHBoxLayout(host)
            row.setContentsMargins(6, 2, 6, 2)
            row.setSpacing(6)

            # Hidden compatibility shims. These keep the playback state
            # machine and the existing test fixtures wired against a
            # single set of widgets — they're just never shown.
            self.play_button = QPushButton("Play", host)
            self.play_button.setCheckable(True)
            self.play_button.clicked.connect(self._on_toggle_play)
            self.play_button.setVisible(False)
            self.stop_button = QPushButton("Stop", host)
            self.stop_button.clicked.connect(self._on_stop)
            self.stop_button.setVisible(False)
            self.jump_end_button = QPushButton("End", host)
            self.jump_end_button.clicked.connect(self._on_jump_to_end)
            self.jump_end_button.setVisible(False)

            self.speed_box = QComboBox(host)
            self.speed_box.setToolTip("Playback speed (relative to real-time)")
            for s in self._SPEED_PRESETS:
                label = f"{s:g}×"  # multiplication sign
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
            self.frame_scrubber.setToolTip("Scrub through trajectory frames")
            self.frame_scrubber.sliderPressed.connect(self._on_scrubber_press)
            self.frame_scrubber.sliderReleased.connect(self._on_scrubber_release)
            self.frame_scrubber.valueChanged.connect(self._on_scrubber_value)

            self.time_label = QLabel("t = 0.000 / 0.000", host)
            self.time_label.setMinimumWidth(140)
            self.time_label.setToolTip("Current playback time / trajectory length")

            speed_label = QLabel("Speed:", host)
            speed_label.setProperty("role", "caption")
            row.addWidget(speed_label)
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
            """Pick a fractional ``_frames_per_tick_base`` for fluid playback.

            At 1×, the polyline should grow from frame 0 to frame ``n-1``
            over ``target_playback_seconds``. The timer fires every
            ``_base_tick_ms`` (~16 ms / 60 Hz); the per-tick stride is a
            *float* so dense trajectories advance at fractional rates and
            the head sphere is sub-frame-interpolated. The stride is
            capped at ``_MAX_STRIDE`` so even a 10000-frame trajectory
            never teleports more than four samples per tick — playback
            just runs slightly longer than the target if it has to.
            """

            n = self._renderer_total_frames()
            if n <= 0:
                self._frames_per_tick_base = 1.0
                return
            target_ms = max(50.0, float(self.target_playback_seconds) * 1000.0)
            ticks = max(1.0, target_ms / float(self._base_tick_ms))
            ideal = float(n) / ticks
            self._frames_per_tick_base = float(
                min(max(ideal, 1.0 / 64.0), float(self._MAX_STRIDE))
            )

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
                new_speed = float(data)
            except (TypeError, ValueError):
                new_speed = 1.0
            old_speed = float(self._speed_multiplier)
            self._speed_multiplier = new_speed
            if self._is_playing and new_speed != old_speed:
                # Rebase the wall-clock anchors so the playhead doesn't
                # jump when the user switches speed mid-playback. The
                # *current* arc position is the new start; ``now``
                # becomes the new wall-start. The next tick will
                # advance at the new rate without rewinding.
                import time

                self._play_wall_start = time.perf_counter()
                self._play_arc_start = float(self._anim_arc_position)
                self._play_position_start = float(self._anim_position)

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
            # Reset the arc-length integrator to match the current
            # integer-frame position. This makes Play-from-mid-scrub
            # behave correctly — playback resumes from where the
            # scrubber points, not from frame 0.
            self._sync_arc_position_from_frame(self._current_frame_index)
            # Anchor wall-clock pacing: every subsequent tick computes
            # ``target = start_arc + (now - wall_start) * arc_per_second``.
            # This is vsync-independent — a missed timer tick causes
            # the next render to land at the correct *wall-clock*
            # position rather than falling behind.
            import time

            self._play_wall_start = time.perf_counter()
            self._play_arc_start = float(self._anim_arc_position)
            self._play_position_start = float(self._anim_position)
            self._anim_timer.start(self._base_tick_ms)

        def _sync_arc_position_from_frame(self, frame_index: int) -> None:
            """Set ``_anim_arc_position`` to match a given integer frame.

            Used whenever the scrubber jumps or play starts mid-scrub —
            keeps the arc-length playback parameter consistent with the
            integer frame the UI is showing. No-op if the renderer
            doesn't have an arc-length table.
            """

            r = self._current_renderer
            if r is None:
                self._anim_arc_position = 0.0
                return
            arc = getattr(r, "_arc_lengths", None)
            if arc is None or len(arc) == 0:
                self._anim_arc_position = 0.0
                return
            idx = int(np.clip(frame_index, 0, len(arc) - 1))
            self._anim_arc_position = float(arc[idx])

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
            self._anim_position = float(idx)
            # Keep the arc-length integrator in sync with the scrubber
            # so toggling play after a manual seek resumes from the
            # right point.
            self._sync_arc_position_from_frame(idx)
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
            import time

            n = r.n_frames
            now = time.perf_counter()
            elapsed = max(0.0, now - self._play_wall_start)
            speed = float(self._speed_multiplier)
            # Single time-based pacing path. Earlier iterations branched
            # to arc-length pacing when a prerender cache was warm; that
            # gave Manim-style uniform visual speed but made the
            # displayed integration time ``t`` advance non-linearly with
            # wall-clock (fast in slow regions, slow in fast regions),
            # which read as broken. Now we pace by integration time —
            # ``t`` grows linearly with wall-clock — and rely on the
            # Catmull-Rom + 4x oversample path inside
            # ``seek_interpolated`` to keep the geometry smooth.
            ticks_elapsed = elapsed * 1000.0 / max(1.0, float(self._base_tick_ms))
            samples_per_tick = float(self._frames_per_tick_base) * speed
            target_pos = self._play_position_start + ticks_elapsed * samples_per_tick
            if target_pos >= n - 1:
                self._seek_to(n - 1)
                self._pause()
                return
            self._anim_position = target_pos
            try:
                r.seek_interpolated(target_pos)
            except (AttributeError, TypeError):  # pragma: no cover - older renderer
                r.seek(int(target_pos))
            self._record_trace(now, r)
            idx_int = int(np.floor(target_pos))
            self._current_frame_index = idx_int
            # Keep the scrubber + time label in sync against the integer
            # index for predictability.
            block = self.frame_scrubber.blockSignals(True)
            try:
                self.frame_scrubber.setValue(idx_int)
            finally:
                self.frame_scrubber.blockSignals(block)
            self._update_time_label(idx_int)
            self._update_status_frame(idx_int)

        def _record_trace(self, wall_time: float, renderer: Renderer3D) -> None:
            """Append a ``(t, x, y, z)`` row to the optional animation trace.

            Used by ``tools/validate_smoothness.py`` and the smoothness
            unit tests to measure per-frame head displacement. No-op
            unless :attr:`_anim_trace` has been pre-allocated by the
            caller (e.g. the validator script sets it to ``[]`` before
            triggering playback).
            """

            if self._anim_trace is None:
                return
            pos = renderer.head_position
            self._anim_trace.append(
                (float(wall_time), float(pos[0]), float(pos[1]), float(pos[2]))
            )

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
            if kind == "IntegratorDivergedError":
                # Euler on Lorenz at dt=0.01 is the canonical trigger; the
                # exception message already carries the integrator name and
                # the t at which it blew up, so the hint just nudges
                # toward the two real fixes.
                return (
                    message
                    + "\n\nHint: pick a higher-order integrator (RK4, RK45, "
                    "DOP853) or shrink dt by ~10×. Explicit Euler is a 1st-"
                    "order baseline and is unstable on chaotic / stiff "
                    "systems like Lorenz at dt above ~1e-3."
                )
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
                "running": "Simulating...",
                "playing": "Playing",
                "exporting": "Exporting",
                "error": "Error",
                "done": "Ready",
            }
            chip_label = label_map.get(inferred, inferred.capitalize())
            chip_state = inferred if inferred not in ("done", "playing") else (
                "idle" if inferred == "done" else "running"
            )
            self._set_state_chip(chip_label, chip_state)
            # Spinner is shown during indeterminate phases (sim, export
            # warm-up). The bevelled progress chunk only appears for the
            # determinate export path; ``_show_busy`` handles that.

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
            for thread in (self._sim_thread, self._export_thread, self._prerender_thread):
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
