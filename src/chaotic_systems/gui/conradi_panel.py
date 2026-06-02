"""PySide6 panel for the Conradi trigonometric-attractor renderer (CSC-007).

The first GUI surface of the Conradi attractor feature
(``docs/proposals/conradi-attractor-panel-2026-05-31.md``). Embeds a
:class:`matplotlib.backends.backend_qtagg.FigureCanvasQTAgg` so the user can:

1. Set the map parameters ``a`` / ``b`` (the two phase shifts in ``[0, 2*pi]``).
2. Tune the lattice (seeds per axis, iterations per seed) and histogram
   resolution.
3. Pick a colormap (via :func:`chaotic_systems.visualization.colormaps.available`)
   and a tone-map mode, and toggle the Gaussian bloom.
4. Press Render and watch an indeterminate progress pill while a worker thread
   runs :func:`chaotic_systems.visualization.attractor_density.render` off the
   UI thread, then see the resulting density image.
5. Press "Screen (a, b)" to compute a largest-Lyapunov-exponent heatmap over the
   ``(a, b)`` plane (CSC-004, :mod:`chaotic_systems.visualization.attractor_screen`)
   off the UI thread, then click the heatmap to pick ``(a, b)``. The heatmap is
   an informational backdrop: high LLE marks *chaotic* regions, which are
   distinct from the (often periodic) parameters that produce the signature art
   (see ``CONTEXT.md`` CSC-003).
6. Press "Animate loop" to precompute a seamless closed-loop animation (CSC-005,
   :mod:`chaotic_systems.visualization.param_path`): the ``(a, b)`` path is swept
   around a closed Fourier curve and a frame rendered at each step with a fixed
   brightness scale (no flicker), then played back via a ``QTimer`` with a
   synchronized ``(a, b)`` inset + moving marker and a frame scrubber.
7. Press "Export loop" to save the precomputed frames as a seamless GIF (loops
   forever) or MP4 (CSC-006, via
   :func:`chaotic_systems.visualization.renderer.write_frames`).

The default ``(a, b) = (5.46, 4.55)`` is Conradi's canonical art regime: a
single orbit there is periodic, but the rendered image is the *transient flow*
of the dense initial-condition lattice (the renderer bins every iterate), which
is exactly the signature art (see ``CONTEXT.md`` CSC-003 for the LLE finding).

Worker thread
-------------
:class:`_ConradiWorker` runs the (single-shot, numba-jitted or NumPy-fallback)
render off a :class:`PySide6.QtCore.QThread` and emits ``finished(rgba)`` /
``error(kind, message)``. Render is one fused kernel call, not a per-pixel loop,
so the panel shows an *indeterminate* progress bar rather than a percentage, and
there is no mid-render cancel (the kernel cannot be interrupted partway). When
the ``[performance]`` (numba) extra is absent the renderer degrades to the pure-
NumPy path automatically; the panel notes this and starts with a lighter lattice.

References
----------
- Scott Draves & Erik Reckase (2003), *The Fractal Flame Algorithm*,
  https://flam3.com/flame_draves.pdf (the log-density tone map).
- Simone Conradi, ``Nice_orbits.ipynb``,
  https://github.com/profConradi/Python_Simulations (the map + canonical params).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import numpy as np

from chaotic_systems.core._numba import NUMBA_AVAILABLE
from chaotic_systems.visualization import (
    attractor_density,
    attractor_screen,
    colormaps,
    param_path,
)

if TYPE_CHECKING:  # pragma: no cover - import only for type hints
    from PySide6.QtWidgets import QWidget

__all__ = [
    "ConradiPanel",  # noqa: F822 - exported lazily via __getattr__ (PySide6 class)
    "build_conradi_dialog",
    "build_conradi_panel",
]

# Default map regime: Conradi's canonical art still, verbatim from
# ``Nice_orbits.ipynb``. The rendered image is the lattice transient flow.
_DEFAULT_A: float = 5.46
_DEFAULT_B: float = 4.55
_TWO_PI: float = 2.0 * math.pi

# Interactive lattice defaults. Lighter than the still-quality module constants
# (attractor_density.DEFAULT_N_POINTS / DEFAULT_N_ITER / DEFAULT_BINS) so the
# first render is snappy; the user can raise them for a print-quality still.
# With numba absent the NumPy fallback is slower, so we start lighter still.
_PANEL_N_POINTS: int = 220 if NUMBA_AVAILABLE else 140
_PANEL_N_ITER: int = 180 if NUMBA_AVAILABLE else 120
_PANEL_BINS: int = 600 if NUMBA_AVAILABLE else 400
# Generous upper bounds for the print-quality still; the spinboxes clamp here.
_MAX_N_POINTS: int = 600
_MAX_N_ITER: int = 600
_MAX_BINS: int = 1600

# The default tone map reproduces Conradi's notebook (clip(log1p, 0, 5)); magma
# is the perceptually-uniform palette matching the screenshots' violet->white.
_DEFAULT_TONE: str = "log"
_DEFAULT_CMAP: str = "magma"
_TONE_MODES: tuple[str, ...] = ("eq_hist", "log", "cbrt", "linear")

# Animation: frames per loop and playback rate. Lighter when numba is absent.
_ANIM_N_FRAMES: int = param_path.DEFAULT_N_FRAMES if NUMBA_AVAILABLE else 24
_ANIM_FPS: int = 12
_ANIM_TIMER_MS: int = max(1, round(1000 / _ANIM_FPS))
# Lighter lattice for animation frames than a one-off still (many frames).
_ANIM_N_POINTS: int = 220 if NUMBA_AVAILABLE else 120
_ANIM_N_ITER: int = 160 if NUMBA_AVAILABLE else 100
_ANIM_BINS: int = 480 if NUMBA_AVAILABLE else 320

# Screening-heatmap grid resolution (per axis). Coarser than a still render so
# the (a, b) sweep stays interactive on the worker thread.
_SCREEN_GRID: int = 120 if NUMBA_AVAILABLE else 72
# The screening LLE heatmap reads best on a near-black sequential map (the
# chaotic high-LLE ridges glow), routed through the registry like everything
# else (no inline cm.get_cmap).
_SCREEN_CMAP: str = "inferno"


def _build_worker_class() -> type:
    """Build the worker class lazily so PySide6 is only imported on demand."""

    from PySide6.QtCore import QObject, Signal

    class _ConradiWorker(QObject):
        """Run :func:`attractor_density.render` on a worker thread."""

        finished = Signal(object)  # np.ndarray RGBA (H, W, 4) uint8
        error = Signal(str, str)  # (kind, message)

        def __init__(
            self,
            a: float,
            b: float,
            n_points: int,
            n_iter: int,
            bins: int,
            tone: str,
            cmap_name: str,
            bloom: bool,
        ) -> None:
            super().__init__()
            self._a = float(a)
            self._b = float(b)
            self._n_points = int(n_points)
            self._n_iter = int(n_iter)
            self._bins = int(bins)
            self._tone = tone
            self._cmap_name = cmap_name
            self._bloom = bool(bloom)

        def run(self) -> None:
            try:
                rgba = attractor_density.render(
                    self._a,
                    self._b,
                    n_points=self._n_points,
                    n_iter=self._n_iter,
                    bins=self._bins,
                    tone=self._tone,  # type: ignore[arg-type]
                    cmap_name=self._cmap_name,
                    bloom=self._bloom,
                )
            except (ValueError, KeyError, TypeError) as exc:
                self.error.emit(type(exc).__name__, str(exc))
                return
            except Exception as exc:  # pragma: no cover - last-resort guard
                self.error.emit("Exception", f"{type(exc).__name__}: {exc}")
                return
            self.finished.emit(rgba)

    return _ConradiWorker


def _build_screen_worker_class() -> type:
    """Build the (a, b) Lyapunov-screening worker class lazily."""

    from PySide6.QtCore import QObject, Signal

    class _ScreenWorker(QObject):
        """Run :func:`attractor_screen.lyapunov_grid` on a worker thread."""

        finished = Signal(object)  # np.ndarray (grid, grid) LLE field
        error = Signal(str, str)

        def __init__(self, grid: int) -> None:
            super().__init__()
            self._grid = int(grid)

        def run(self) -> None:
            try:
                lle, _spread = attractor_screen.lyapunov_grid(self._grid)
            except (ValueError, KeyError, TypeError) as exc:
                self.error.emit(type(exc).__name__, str(exc))
                return
            except Exception as exc:  # pragma: no cover - last-resort guard
                self.error.emit("Exception", f"{type(exc).__name__}: {exc}")
                return
            self.finished.emit(lle)

    return _ScreenWorker


class _AnimCancelled(Exception):
    """Internal sentinel raised by the anim worker's progress callback."""


def _build_anim_worker_class() -> type:
    """Build the loop-precompute worker class lazily."""

    from PySide6.QtCore import QObject, Signal

    class _AnimWorker(QObject):
        """Precompute the closed-loop animation frames on a worker thread."""

        progress = Signal(int, int)  # (done, total)
        finished = Signal(object)  # (frames, ab, count_max) | None on cancel
        error = Signal(str, str)

        def __init__(
            self,
            n_frames: int,
            n_points: int,
            n_iter: int,
            bins: int,
            cmap_name: str,
            bloom: bool,
        ) -> None:
            super().__init__()
            self._n_frames = int(n_frames)
            self._n_points = int(n_points)
            self._n_iter = int(n_iter)
            self._bins = int(bins)
            self._cmap_name = cmap_name
            self._bloom = bool(bloom)
            self._cancelled = False

        def cancel(self) -> None:
            self._cancelled = True

        def run(self) -> None:
            def _progress(done: int, total: int) -> None:
                if self._cancelled:
                    raise _AnimCancelled
                self.progress.emit(done, total)

            try:
                payload = param_path.precompute_loop_frames(
                    self._n_frames,
                    n_points=self._n_points,
                    n_iter=self._n_iter,
                    bins=self._bins,
                    cmap_name=self._cmap_name,
                    bloom=self._bloom,
                    progress=_progress,
                )
            except _AnimCancelled:
                self.finished.emit(None)
                return
            except (ValueError, KeyError, TypeError) as exc:
                self.error.emit(type(exc).__name__, str(exc))
                return
            except Exception as exc:  # pragma: no cover - last-resort guard
                self.error.emit("Exception", f"{type(exc).__name__}: {exc}")
                return
            self.finished.emit(payload)

    return _AnimWorker


def _loop_polyline(
    n: int = 400,
) -> tuple[np.ndarray, np.ndarray]:
    """Dense ``(a, b)`` polyline of the default loop, NaN-split at 2*pi wraps.

    The loop can cross the ``a``/``b`` = ``2*pi`` boundary (a, b are 2*pi-periodic
    phase shifts); inserting NaN at the wrap stops matplotlib drawing a spurious
    line straight across the inset.
    """
    ts = np.linspace(0.0, 1.0, n)
    a, b = param_path.param_loop(ts)
    a = np.asarray(a, dtype=np.float64).copy()
    b = np.asarray(b, dtype=np.float64).copy()
    jump = (np.abs(np.diff(a)) > np.pi) | (np.abs(np.diff(b)) > np.pi)
    a[:-1][jump] = np.nan
    b[:-1][jump] = np.nan
    return a, b


def _build_screen_figure(lle: np.ndarray, a: float, b: float) -> Any:
    """Build a matplotlib Figure of the (a, b) LLE screening heatmap."""
    from matplotlib.figure import Figure

    a0, a1 = attractor_screen.SCREEN_A_RANGE
    b0, b1 = attractor_screen.SCREEN_B_RANGE
    fig = Figure(figsize=(6.0, 6.0))
    ax = fig.add_subplot(111)
    im = ax.imshow(
        lle,
        origin="lower",
        extent=(a0, a1, b0, b1),
        cmap=colormaps.get(_SCREEN_CMAP),
        aspect="auto",
        interpolation="nearest",
    )
    fig.colorbar(im, ax=ax, label="largest Lyapunov exponent")
    # Marker at the current (a, b) — click the heatmap to move it.
    ax.plot([a], [b], marker="+", color="white", markersize=12, mew=2.0)
    ax.set_title("(a, b) Lyapunov screening — click to pick", fontsize=10)
    ax.set_xlabel("a")
    ax.set_ylabel("b")
    fig.tight_layout()
    return fig


def _build_figure(rgba: np.ndarray, a: float, b: float) -> Any:
    """Build a matplotlib Figure showing an RGBA density image on black."""
    from matplotlib.figure import Figure

    fig = Figure(figsize=(6.0, 6.0), facecolor="black")
    ax = fig.add_subplot(111)
    ax.set_facecolor("black")
    # origin="lower": histogram row 0 is the ymin edge (see attractor_density).
    ax.imshow(
        rgba,
        origin="lower",
        extent=attractor_density.DEFAULT_EXTENT,
        interpolation="nearest",
        aspect="equal",
    )
    ax.set_title(f"a = {a:.3f},  b = {b:.3f}", color="white", fontsize=10)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.tight_layout()
    return fig


def _placeholder_figure() -> Any:
    """A pure-black placeholder before the first render."""
    return _build_figure(
        np.zeros((2, 2, 4), dtype=np.uint8), _DEFAULT_A, _DEFAULT_B
    )


def _build_panel_class() -> type:
    """Build the ConradiPanel class lazily; mirrors the other panel modules."""

    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from PySide6.QtCore import Qt, QThread, QTimer
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QProgressBar,
        QPushButton,
        QSlider,
        QSpinBox,
        QVBoxLayout,
        QWidget,
    )

    worker_cls = _build_worker_class()
    screen_worker_cls = _build_screen_worker_class()
    anim_worker_cls = _build_anim_worker_class()

    class ConradiPanel(QWidget):
        """Self-contained Conradi trigonometric-attractor density renderer."""

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self._worker: object | None = None
            self._thread: QThread | None = None
            self._last_rgba: np.ndarray | None = None
            # (a, b) Lyapunov screening state (CSC-004).
            self._last_lle: np.ndarray | None = None
            self._screen_mode: bool = False
            self._click_cid: int | None = None
            # Closed-loop animation state (CSC-005).
            self._frames: list[np.ndarray] | None = None
            self._frame_ab: list[tuple[float, float]] | None = None
            self._anim_index: int = 0
            self._is_playing: bool = False
            self._timer: QTimer | None = None
            self._anim_im: Any = None
            self._anim_marker: Any = None

            from chaotic_systems.gui._panel_helpers import apply_panel_margins

            outer = QVBoxLayout(self)
            apply_panel_margins(outer)

            # --- Controls -------------------------------------------------
            controls = QFormLayout()
            controls.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

            self.a_spin = QDoubleSpinBox(self)
            self.a_spin.setObjectName("conradi_a")
            self.a_spin.setRange(0.0, _TWO_PI)
            self.a_spin.setDecimals(3)
            self.a_spin.setSingleStep(0.05)
            self.a_spin.setValue(_DEFAULT_A)
            self.a_spin.setToolTip("Real-channel phase shift a in [0, 2π].")
            controls.addRow(QLabel("a (real phase)"), self.a_spin)

            self.b_spin = QDoubleSpinBox(self)
            self.b_spin.setObjectName("conradi_b")
            self.b_spin.setRange(0.0, _TWO_PI)
            self.b_spin.setDecimals(3)
            self.b_spin.setSingleStep(0.05)
            self.b_spin.setValue(_DEFAULT_B)
            self.b_spin.setToolTip("Imag-channel phase shift b in [0, 2π].")
            controls.addRow(QLabel("b (imag phase)"), self.b_spin)

            self.n_points_spin = QSpinBox(self)
            self.n_points_spin.setObjectName("conradi_n_points")
            self.n_points_spin.setRange(50, _MAX_N_POINTS)
            self.n_points_spin.setValue(_PANEL_N_POINTS)
            self.n_points_spin.setToolTip(
                "Initial-condition seeds per axis (n × n total). "
                "Conradi's notebook uses 300-500 for stills."
            )
            controls.addRow(QLabel("Seeds (n × n)"), self.n_points_spin)

            self.n_iter_spin = QSpinBox(self)
            self.n_iter_spin.setObjectName("conradi_n_iter")
            self.n_iter_spin.setRange(50, _MAX_N_ITER)
            self.n_iter_spin.setValue(_PANEL_N_ITER)
            self.n_iter_spin.setToolTip(
                "Iterations per seed (the transient flow that forms the image)."
            )
            controls.addRow(QLabel("Iterations / seed"), self.n_iter_spin)

            self.bins_spin = QSpinBox(self)
            self.bins_spin.setObjectName("conradi_bins")
            self.bins_spin.setRange(128, _MAX_BINS)
            self.bins_spin.setValue(_PANEL_BINS)
            self.bins_spin.setToolTip(
                "Histogram resolution (output is bins × bins pixels)."
            )
            controls.addRow(QLabel("Resolution (px)"), self.bins_spin)

            self.cmap_box = QComboBox(self)
            self.cmap_box.setObjectName("conradi_cmap")
            for name in colormaps.available():
                self.cmap_box.addItem(name)
            self.cmap_box.setCurrentText(_DEFAULT_CMAP)
            self.cmap_box.setToolTip("Colormap (resolved through the registry).")
            controls.addRow(QLabel("Colormap"), self.cmap_box)

            self.tone_box = QComboBox(self)
            self.tone_box.setObjectName("conradi_tone")
            for mode in _TONE_MODES:
                self.tone_box.addItem(mode)
            self.tone_box.setCurrentText(_DEFAULT_TONE)
            self.tone_box.setToolTip(
                "Tone map: eq_hist (stills), log (notebook-faithful, stable "
                "for animation), cbrt, linear."
            )
            controls.addRow(QLabel("Tone map"), self.tone_box)

            self.bloom_check = QCheckBox("Gaussian bloom", self)
            self.bloom_check.setObjectName("conradi_bloom")
            self.bloom_check.setChecked(False)
            self.bloom_check.setToolTip(
                "Add a multi-scale Gaussian halo around the hot cores."
            )
            controls.addRow(QLabel("Glow"), self.bloom_check)

            outer.addLayout(controls)

            # --- Action row -----------------------------------------------
            action_row = QHBoxLayout()
            self.render_button = QPushButton("Render", self)
            self.render_button.setObjectName("conradi_render")
            self.render_button.setProperty("variant", "primary")
            self.render_button.clicked.connect(self._on_render)
            action_row.addWidget(self.render_button)

            self.screen_button = QPushButton("Screen (a, b)", self)
            self.screen_button.setObjectName("conradi_screen")
            self.screen_button.setToolTip(
                "Compute the largest Lyapunov exponent over the (a, b) plane "
                "and show it as a heatmap. Click the heatmap to pick (a, b). "
                "Note: high LLE = chaotic, which is distinct from the (often "
                "periodic) parameters that produce the signature art."
            )
            self.screen_button.clicked.connect(self._on_screen)
            action_row.addWidget(self.screen_button)

            self.progress_bar = QProgressBar(self)
            self.progress_bar.setObjectName("conradi_progress")
            # Indeterminate (busy) bar: render is one fused kernel call.
            self.progress_bar.setRange(0, 0)
            self.progress_bar.setVisible(False)
            action_row.addWidget(self.progress_bar, 1)
            outer.addLayout(action_row)

            # --- Animation transport (CSC-005) ----------------------------
            anim_row = QHBoxLayout()
            self.animate_button = QPushButton("Animate loop", self)
            self.animate_button.setObjectName("conradi_animate")
            self.animate_button.setToolTip(
                "Precompute a seamless closed-loop animation: sweep (a, b) "
                "around a closed path and render a frame at each step "
                "(fixed brightness scale, so the loop does not flicker)."
            )
            self.animate_button.clicked.connect(self._on_animate)
            anim_row.addWidget(self.animate_button)

            self.play_button = QPushButton("Play", self)
            self.play_button.setObjectName("conradi_play")
            self.play_button.setEnabled(False)
            self.play_button.clicked.connect(self._on_play_pause)
            anim_row.addWidget(self.play_button)

            self.scrubber = QSlider(Qt.Orientation.Horizontal, self)
            self.scrubber.setObjectName("conradi_scrub")
            self.scrubber.setEnabled(False)
            self.scrubber.setRange(0, 0)
            self.scrubber.valueChanged.connect(self._on_scrub)
            anim_row.addWidget(self.scrubber, 1)

            self.export_button = QPushButton("Export loop…", self)
            self.export_button.setObjectName("conradi_export")
            self.export_button.setEnabled(False)
            self.export_button.setToolTip(
                "Save the precomputed loop as a seamless GIF (loops forever) or "
                "MP4. GIF is portable but 256-colour (mild banding); MP4 is "
                "higher fidelity."
            )
            self.export_button.clicked.connect(self._on_export)
            anim_row.addWidget(self.export_button)
            outer.addLayout(anim_row)

            # --- Status ---------------------------------------------------
            base_msg = "Press Render to draw the Conradi attractor."
            if not NUMBA_AVAILABLE:
                base_msg += (
                    "  (NumPy fallback — install the [performance] extra "
                    "for faster renders.)"
                )
            self.status_label = QLabel(base_msg, self)
            self.status_label.setObjectName("conradi_status")
            self.status_label.setWordWrap(True)
            outer.addWidget(self.status_label)

            # --- Canvas (placeholder until first render) ------------------
            self.canvas = FigureCanvasQTAgg(_placeholder_figure())
            self.canvas.setObjectName("conradi_canvas")
            self._bind_click(self.canvas)
            outer.addWidget(self.canvas, 1)

        # ----- click-to-pick (screening mode) -------------------------

        def _bind_click(self, canvas: Any) -> None:
            """Connect the matplotlib button-press handler to ``canvas``."""
            self._click_cid = canvas.mpl_connect(
                "button_press_event", self._on_canvas_click
            )

        def _on_canvas_click(self, event: Any) -> None:
            """In screening mode, a click sets (a, b) to the clicked cell."""
            if not self._screen_mode or event.inaxes is None:
                return
            if event.xdata is None or event.ydata is None:
                return
            a = min(max(float(event.xdata), 0.0), _TWO_PI)
            b = min(max(float(event.ydata), 0.0), _TWO_PI)
            self.a_spin.setValue(a)
            self.b_spin.setValue(b)
            self.status_label.setText(
                f"Picked a = {a:.3f}, b = {b:.3f}. Press Render to draw it."
            )
            if self._last_lle is not None:
                self._show_screen(self._last_lle)  # redraw marker at new (a, b)

        # ----- actions ------------------------------------------------

        def _on_render(self) -> None:
            if self._thread is not None and self._thread.isRunning():
                return
            n_points = int(self.n_points_spin.value())
            n_iter = int(self.n_iter_spin.value())
            bins = int(self.bins_spin.value())

            self._stop_play()
            self._set_busy(True)
            self.progress_bar.setRange(0, 0)  # indeterminate: one fused call
            self.progress_bar.setVisible(True)
            self.status_label.setText(
                f"Rendering {n_points}×{n_points} seeds × {n_iter} iterations "
                f"into a {bins}×{bins} histogram..."
            )

            worker = worker_cls(
                a=float(self.a_spin.value()),
                b=float(self.b_spin.value()),
                n_points=n_points,
                n_iter=n_iter,
                bins=bins,
                tone=self.tone_box.currentText(),
                cmap_name=self.cmap_box.currentText(),
                bloom=self.bloom_check.isChecked(),
            )
            thread = QThread(self)
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.finished.connect(self._on_finished)
            worker.error.connect(self._on_error)
            worker.finished.connect(thread.quit)
            worker.error.connect(thread.quit)
            thread.finished.connect(self._cleanup_thread)
            self._worker = worker
            self._thread = thread
            thread.start()

        def _on_finished(self, rgba: np.ndarray | None) -> None:
            self._set_busy(False)
            self.progress_bar.setVisible(False)
            if rgba is None:
                self.status_label.setText("Cancelled.")
                return
            self._last_rgba = rgba
            lit = int(np.any(rgba[..., :3] > 0, axis=2).sum())
            total = int(rgba.shape[0] * rgba.shape[1])
            self.status_label.setText(
                f"Rendered {rgba.shape[1]}×{rgba.shape[0]}: "
                f"{lit}/{total} lit pixels."
            )
            self._refresh_plot(rgba)

        def _on_error(self, kind: str, message: str) -> None:
            self._set_busy(False)
            self.progress_bar.setVisible(False)
            self.status_label.setText(f"{kind}: {message}")

        def _set_busy(self, busy: bool) -> None:
            """Enable/disable the compute buttons while a worker runs."""
            self.render_button.setEnabled(not busy)
            self.screen_button.setEnabled(not busy)
            self.animate_button.setEnabled(not busy)

        # ----- screening (CSC-004) ------------------------------------

        def _on_screen(self) -> None:
            if self._thread is not None and self._thread.isRunning():
                return
            self._stop_play()
            self._set_busy(True)
            self.progress_bar.setRange(0, 0)
            self.progress_bar.setVisible(True)
            self.status_label.setText(
                f"Screening the (a, b) plane on a {_SCREEN_GRID}×{_SCREEN_GRID} "
                "grid (largest Lyapunov exponent)..."
            )
            worker = screen_worker_cls(_SCREEN_GRID)
            thread = QThread(self)
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.finished.connect(self._on_screen_finished)
            worker.error.connect(self._on_error)
            worker.finished.connect(thread.quit)
            worker.error.connect(thread.quit)
            thread.finished.connect(self._cleanup_thread)
            self._worker = worker
            self._thread = thread
            thread.start()

        def _on_screen_finished(self, lle: np.ndarray | None) -> None:
            self._set_busy(False)
            self.progress_bar.setVisible(False)
            if lle is None:
                self.status_label.setText("Cancelled.")
                return
            self._last_lle = lle
            frac = float((lle > 0.0).mean())
            self.status_label.setText(
                f"(a, b) screening done: {frac:.0%} of the plane is chaotic "
                "(λ₁ > 0). Click the heatmap to pick (a, b)."
            )
            self._show_screen(lle)

        def _show_screen(self, lle: np.ndarray) -> None:
            """Swap the canvas to the (a, b) screening heatmap."""
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

            from chaotic_systems.gui._panel_helpers import swap_mpl_canvas

            fig = _build_screen_figure(
                lle, float(self.a_spin.value()), float(self.b_spin.value())
            )
            new_canvas = FigureCanvasQTAgg(fig)
            new_canvas.setObjectName("conradi_canvas")
            swap_mpl_canvas(self.layout(), self.canvas, new_canvas)
            self.canvas = new_canvas
            self._bind_click(new_canvas)
            self._screen_mode = True
            self._teardown_anim_view()

        # ----- closed-loop animation (CSC-005) ------------------------

        def _on_animate(self) -> None:
            if self._thread is not None and self._thread.isRunning():
                return
            self._stop_play()
            self._set_busy(True)
            self.export_button.setEnabled(False)
            self.progress_bar.setRange(0, _ANIM_N_FRAMES)
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(True)
            self.status_label.setText(
                f"Precomputing {_ANIM_N_FRAMES} loop frames "
                "(fixed brightness scale)..."
            )
            worker = anim_worker_cls(
                _ANIM_N_FRAMES,
                _ANIM_N_POINTS,
                _ANIM_N_ITER,
                _ANIM_BINS,
                self.cmap_box.currentText(),
                self.bloom_check.isChecked(),
            )
            thread = QThread(self)
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.progress.connect(self._on_anim_progress)
            worker.finished.connect(self._on_anim_finished)
            worker.error.connect(self._on_error)
            worker.finished.connect(thread.quit)
            worker.error.connect(thread.quit)
            thread.finished.connect(self._cleanup_thread)
            self._worker = worker
            self._thread = thread
            thread.start()

        def _on_anim_progress(self, done: int, total: int) -> None:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(done)

        def _on_anim_finished(self, payload: object | None) -> None:
            self._set_busy(False)
            self.progress_bar.setVisible(False)
            if payload is None:
                self.status_label.setText("Cancelled.")
                return
            frames, ab, _count_max = payload  # type: ignore[misc]
            self._frames = frames
            self._frame_ab = ab
            self._anim_index = 0
            self._build_anim_canvas()
            self.play_button.setEnabled(True)
            self.play_button.setText("Play")
            self.scrubber.setEnabled(True)
            self.scrubber.blockSignals(True)
            self.scrubber.setRange(0, len(frames) - 1)
            self.scrubber.setValue(0)
            self.scrubber.blockSignals(False)
            self.export_button.setEnabled(True)
            self.status_label.setText(
                f"Loop ready: {len(frames)} frames. Press Play, drag the "
                "scrubber, or Export loop. Closed path -> seamless loop."
            )

        def _build_anim_canvas(self) -> None:
            """Build the animation figure (main image + (a, b) loop inset)."""
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
            from matplotlib.figure import Figure

            from chaotic_systems.gui._panel_helpers import swap_mpl_canvas

            assert self._frames is not None and self._frame_ab is not None
            a, b = self._frame_ab[self._anim_index]
            fig = Figure(figsize=(6.0, 6.0), facecolor="black")
            ax = fig.add_subplot(111)
            ax.set_facecolor("black")
            self._anim_im = ax.imshow(
                self._frames[self._anim_index],
                origin="lower",
                extent=attractor_density.DEFAULT_EXTENT,
                interpolation="nearest",
                aspect="equal",
            )
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)

            # (a, b) loop inset, upper-right, with the moving marker.
            inset = fig.add_axes((0.70, 0.70, 0.27, 0.27))
            inset.set_facecolor("black")
            loop_a, loop_b = _loop_polyline()
            inset.plot(loop_a, loop_b, color="#ffe100", linewidth=1.0)
            (self._anim_marker,) = inset.plot(
                [a], [b], marker="o", color="white", markersize=5
            )
            inset.set_xlim(0.0, _TWO_PI)
            inset.set_ylim(0.0, _TWO_PI)
            inset.set_xticks([])
            inset.set_yticks([])
            inset.set_title("(a, b)", color="white", fontsize=8)
            for spine in inset.spines.values():
                spine.set_color("#555555")

            new_canvas = FigureCanvasQTAgg(fig)
            new_canvas.setObjectName("conradi_canvas")
            swap_mpl_canvas(self.layout(), self.canvas, new_canvas)
            self.canvas = new_canvas
            self._bind_click(new_canvas)
            self._screen_mode = False

        def _show_frame(self, index: int) -> None:
            """Display loop frame ``index`` by updating the artists in place."""
            if self._frames is None or self._frame_ab is None:
                return
            index = max(0, min(index, len(self._frames) - 1))
            self._anim_index = index
            if self._anim_im is not None:
                self._anim_im.set_data(self._frames[index])
            if self._anim_marker is not None:
                a, b = self._frame_ab[index]
                self._anim_marker.set_data([a], [b])
            self.canvas.draw_idle()

        def _on_play_pause(self) -> None:
            if self._frames is None:
                return
            if self._is_playing:
                self._stop_play()
            else:
                self._start_play()

        def _start_play(self) -> None:
            if self._frames is None:
                return
            if self._timer is None:
                self._timer = QTimer(self)
                self._timer.setInterval(_ANIM_TIMER_MS)
                self._timer.timeout.connect(self._on_timer_tick)
            self._is_playing = True
            self.play_button.setText("Pause")
            self._timer.start()

        def _stop_play(self) -> None:
            if self._timer is not None:
                self._timer.stop()
            self._is_playing = False
            if hasattr(self, "play_button"):
                self.play_button.setText("Play")

        def _on_timer_tick(self) -> None:
            if self._frames is None:
                return
            nxt = (self._anim_index + 1) % len(self._frames)
            self._show_frame(nxt)
            self.scrubber.blockSignals(True)
            self.scrubber.setValue(nxt)
            self.scrubber.blockSignals(False)

        def _on_scrub(self, value: int) -> None:
            self._stop_play()
            self._show_frame(int(value))

        # ----- export (CSC-006) ---------------------------------------

        def _on_export(self) -> None:
            if not self._frames:
                return
            self._stop_play()
            path, _selected = QFileDialog.getSaveFileName(
                self,
                "Export attractor loop",
                "conradi_loop.gif",
                "Animated GIF (*.gif);;MP4 video (*.mp4)",
            )
            if not path:
                return
            self._export_frames_to(path)

        def _export_frames_to(self, path: str) -> bool:
            """Write the precomputed loop to ``path`` (GIF or MP4). Returns ok."""
            from chaotic_systems.visualization.renderer import write_frames

            if not self._frames:
                self.status_label.setText("Nothing to export — animate first.")
                return False
            try:
                out = write_frames(path, self._frames, fps=_ANIM_FPS)
            except (ValueError, OSError, RuntimeError, ImportError) as exc:
                self.status_label.setText(
                    f"Export failed: {type(exc).__name__}: {exc}"
                )
                return False
            self.status_label.setText(
                f"Saved {len(self._frames)} frames to {out.name}."
            )
            return True

        def _teardown_anim_view(self) -> None:
            """Drop the animation artists + transport when leaving anim view.

            Called when a render / screen canvas replaces the animation canvas so
            the (now-dead) AxesImage / marker are never updated by a stray tick.
            """
            self._stop_play()
            self._anim_im = None
            self._anim_marker = None
            self.play_button.setEnabled(False)
            self.scrubber.setEnabled(False)
            self.export_button.setEnabled(False)

        def _cleanup_thread(self) -> None:
            if self._worker is not None:
                self._worker.deleteLater()  # type: ignore[attr-defined]
            if self._thread is not None:
                self._thread.deleteLater()
            self._worker = None
            self._thread = None

        def _refresh_plot(self, rgba: np.ndarray) -> None:
            """Rebuild the figure and re-bind a Qt canvas."""
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

            from chaotic_systems.gui._panel_helpers import swap_mpl_canvas

            fig = _build_figure(
                rgba, float(self.a_spin.value()), float(self.b_spin.value())
            )
            new_canvas = FigureCanvasQTAgg(fig)
            new_canvas.setObjectName("conradi_canvas")
            swap_mpl_canvas(self.layout(), self.canvas, new_canvas)
            self.canvas = new_canvas
            self._bind_click(new_canvas)
            # Showing a density render leaves screening mode (clicks inert).
            self._screen_mode = False
            self._teardown_anim_view()

        # ----- public read-only accessors used by tests ---------------

        def last_rgba(self) -> np.ndarray | None:
            """Return the most-recently-rendered RGBA image (or ``None``)."""
            return self._last_rgba

        def last_lle(self) -> np.ndarray | None:
            """Return the most-recent (a, b) screening LLE field (or ``None``)."""
            return self._last_lle

        def last_frames(self) -> list[np.ndarray] | None:
            """Return the most-recent precomputed loop frames (or ``None``)."""
            return self._frames

    return ConradiPanel


def build_conradi_panel(parent: QWidget | None = None) -> QWidget:
    """Construct a :class:`ConradiPanel`."""
    return _build_panel_class()(parent)


def build_conradi_dialog(parent: QWidget | None = None) -> QWidget:
    """Build a ``QDockWidget`` wrapping :class:`ConradiPanel` (FU-018)."""
    from chaotic_systems.gui._panel_helpers import make_panel_dialog

    panel = build_conradi_panel(parent)
    return make_panel_dialog(
        object_name="conradi_dialog",
        title="Conradi attractor — density renderer",
        panel=panel,
        size=(720, 820),
        parent=parent,
        panel_attr="conradi_panel",
    )


def __getattr__(name: str) -> type:
    if name == "ConradiPanel":
        return _build_panel_class()
    raise AttributeError(name)
