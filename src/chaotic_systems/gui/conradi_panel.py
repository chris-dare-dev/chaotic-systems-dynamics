"""PySide6 panel for the Conradi trigonometric-attractor renderer (CSC-007).

The first GUI surface of the Conradi attractor feature
(``docs/proposals/conradi-attractor-panel-2026-05-31.md``). Embeds a
:class:`matplotlib.backends.backend_qtagg.FigureCanvasQTAgg` so the user can:

1. Choose an art-map (Conradi or Clifford) from the map selector and set its
   parameters via the per-map form (Conradi: ``a``/``b`` in ``[0, 2*pi]``;
   Clifford: ``a``/``b``/``c``/``d`` in ``[-3, 3]``), optionally from a curated
   "Preset" dropdown (CMP-002 / CMP-005). Screening works per-map (CMP-004); the
   ``(a, b)`` animation loop is Conradi-only for now (a Clifford loop geometry
   is a follow-up), so Animate is disabled for other maps.
2. Tune the lattice (seeds per axis, iterations per seed) and histogram
   resolution.
3. Pick a colormap (via :func:`chaotic_systems.visualization.colormaps.available`)
   and a tone-map mode, and toggle the Gaussian bloom.
4. Press Render and watch an indeterminate progress pill while a worker thread
   runs :func:`chaotic_systems.visualization.attractor_density.render` off the
   UI thread, then see the resulting density image.
5. Press "Screen (a, b)" to compute a largest-Lyapunov-exponent heatmap over the
   selected map's ``(a, b)`` plane (CSC-004 / CMP-004,
   :mod:`chaotic_systems.visualization.attractor_screen`) off the UI thread,
   then click the heatmap to pick ``(a, b)``. Works for every map (the screening
   step + Jacobian-push are passed per-map). The heatmap is an informational
   backdrop: high LLE marks *chaotic* regions, which are distinct from the
   (often periodic) parameters that produce the signature art (CONTEXT.md CSC-003).
6. Press "Animate loop" to precompute a seamless closed-loop animation (CSC-005,
   :mod:`chaotic_systems.visualization.param_path`): the ``(a, b)`` path is swept
   around a closed Fourier curve and a frame rendered at each step with a fixed
   brightness scale (no flicker), then played back via a ``QTimer`` with a
   synchronized ``(a, b)`` inset + moving marker and a frame scrubber.
7. Press "Export loop" to save the precomputed frames as a seamless GIF (loops
   forever) or MP4 (CSC-006, via
   :func:`chaotic_systems.visualization.renderer.write_frames`).
8. Shape the loop before animating (LOOP-EDIT). The **Frames** spinbox sets how
   many frames are rendered around the loop and **Speed** sets the playback +
   export fps (both live). Press **"Edit loop"** to drag the ``(a, b)`` path
   directly on the parameter plane (over the screening heatmap when one is
   available): drag the white centre dot to reposition the loop, and the cyan
   rim handles to resize / rotate it. The geometry feeds :func:`param_path.param_loop`
   via a closure, so the inset and the precompute always reflect the edited path;
   with the per-map defaults the loop is byte-identical to the original. During
   playback the ``(a, b)`` inset doubles as a **rotation knob**: drag it to spin
   the loop live, and on release the frames re-precompute at the new rotation
   (the swept ``(a, b)`` change, so the frames must re-render).

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
from chaotic_systems.systems.clifford import (
    CLIFFORD_PRESETS,
    CliffordMap,
    clifford_extent,
    make_clifford_map_fn,
)
from chaotic_systems.systems.conradi import CONRADI_PRESETS
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
# These are now the *defaults* of the user-facing Frames / Speed spinboxes
# (LOOP-EDIT) rather than fixed constants.
_ANIM_N_FRAMES: int = param_path.DEFAULT_N_FRAMES if NUMBA_AVAILABLE else 24
_ANIM_FPS: int = 12
_ANIM_TIMER_MS: int = max(1, round(1000 / _ANIM_FPS))
# User-adjustable bounds for the Frames / Speed (fps) spinboxes (LOOP-EDIT).
_MIN_FRAMES: int = 8
_MAX_FRAMES: int = 360
_MIN_FPS: int = 1
_MAX_FPS: int = 60
# Lighter lattice for animation frames than a one-off still (many frames).
_ANIM_N_POINTS: int = 220 if NUMBA_AVAILABLE else 120
_ANIM_N_ITER: int = 160 if NUMBA_AVAILABLE else 100
_ANIM_BINS: int = 480 if NUMBA_AVAILABLE else 320

# Loop editor (LOOP-EDIT): grab radius for a drag handle, as a fraction of the
# (a, b) plane (per-axis-normalized so it is DPI- and aspect-independent), and
# the fundamental-ellipse semi-axis clamps (kept inside the parameter plane).
_HANDLE_TOL_FRAC: float = 0.06
_MIN_LOOP_RADIUS: float = 0.05

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
            map_fn: attractor_density.MapFn | None = None,
            extent: tuple[float, float, float, float] | None = None,
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
            # CMP-001: forward the active map + its render window. Defaults keep
            # the Conradi behaviour byte-stable (render()/accumulate() default to
            # conradi_map / DEFAULT_EXTENT).
            self._map_fn = attractor_density.conradi_map if map_fn is None else map_fn
            self._extent = attractor_density.DEFAULT_EXTENT if extent is None else extent

        def run(self) -> None:
            try:
                rgba = attractor_density.render(
                    self._a,
                    self._b,
                    n_points=self._n_points,
                    n_iter=self._n_iter,
                    bins=self._bins,
                    extent=self._extent,
                    tone=self._tone,  # type: ignore[arg-type]
                    cmap_name=self._cmap_name,
                    bloom=self._bloom,
                    map_fn=self._map_fn,
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

        def __init__(
            self,
            grid: int,
            a_range: tuple[float, float],
            b_range: tuple[float, float],
            step_fn: Any = None,
            jacobian_push_fn: Any = None,
        ) -> None:
            super().__init__()
            self._grid = int(grid)
            self._a_range = a_range
            self._b_range = b_range
            self._step_fn = step_fn
            self._jacobian_push_fn = jacobian_push_fn

        def run(self) -> None:
            try:
                lle, _spread = attractor_screen.lyapunov_grid(
                    self._grid,
                    a_range=self._a_range,
                    b_range=self._b_range,
                    step_fn=self._step_fn,
                    jacobian_push_fn=self._jacobian_push_fn,
                )
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
            map_fn: attractor_density.MapFn | None = None,
            extent: tuple[float, float, float, float] | None = None,
            path_fn: param_path.PathFn | None = None,
        ) -> None:
            super().__init__()
            self._n_frames = int(n_frames)
            self._n_points = int(n_points)
            self._n_iter = int(n_iter)
            self._bins = int(bins)
            self._cmap_name = cmap_name
            self._bloom = bool(bloom)
            # CMP-001: forward the active map + render window (Conradi defaults).
            self._map_fn = attractor_density.conradi_map if map_fn is None else map_fn
            self._extent = attractor_density.DEFAULT_EXTENT if extent is None else extent
            # CAL-001: per-map (a, b) loop geometry; None -> the default Conradi
            # param_loop (precompute_loop_frames falls back to it).
            self._path_fn = path_fn
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
                    path_fn=self._path_fn,
                    map_fn=self._map_fn,
                    extent=self._extent,
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
    path_fn: param_path.PathFn | None = None,
    n: int = 400,
    *,
    wrapped: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """Dense ``(a, b)`` polyline of the active loop for the inset (CAL-001).

    ``path_fn`` defaults to the Conradi :func:`param_path.param_loop`. When
    ``wrapped`` is ``True`` the loop can cross the ``2*pi`` boundary (Conradi's
    ``a, b`` are 2*pi-periodic), so NaN is inserted at each wrap to stop
    matplotlib drawing a spurious line across the inset. For a non-wrapping loop
    (``wrapped=False``, e.g. Clifford) the curve is continuous and is NOT split.
    """
    if path_fn is None:
        path_fn = param_path.param_loop
    ts = np.linspace(0.0, 1.0, n)
    a, b = path_fn(ts)
    a = np.asarray(a, dtype=np.float64).copy()
    b = np.asarray(b, dtype=np.float64).copy()
    if wrapped:
        jump = (np.abs(np.diff(a)) > np.pi) | (np.abs(np.diff(b)) > np.pi)
        a[:-1][jump] = np.nan
        b[:-1][jump] = np.nan
    return a, b


def _loop_axis_limits(
    values: np.ndarray, marker: float, margin_frac: float = 0.08
) -> tuple[float, float]:
    """Inset axis limits from a loop polyline's finite range + the marker (CAL-001).

    Spans the loop's own coordinate range (NaN-aware) plus the current marker,
    with a small margin, so the inset fits whatever map's loop is shown
    (Conradi ``[0, 2*pi]`` or Clifford ``[-3, 3]``) instead of a fixed window.
    """
    finite = values[np.isfinite(values)]
    lo = min(float(np.min(finite)), float(marker)) if finite.size else float(marker)
    hi = max(float(np.max(finite)), float(marker)) if finite.size else float(marker)
    span = hi - lo
    pad = margin_frac * span if span > 1e-9 else 0.5
    return lo - pad, hi + pad


def _build_screen_figure(
    lle: np.ndarray,
    a: float,
    b: float,
    a_range: tuple[float, float],
    b_range: tuple[float, float],
) -> Any:
    """Build a matplotlib Figure of the (a, b) LLE screening heatmap.

    ``a_range`` / ``b_range`` are the swept parameter domain (per-map: Conradi
    ``[0, 2*pi]``, Clifford ``[-3, 3]``), used for the imshow extent + axes.
    """
    from matplotlib.figure import Figure

    a0, a1 = a_range
    b0, b1 = b_range
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


def _build_figure(
    rgba: np.ndarray,
    a: float,
    b: float,
    extent: tuple[float, float, float, float] = attractor_density.DEFAULT_EXTENT,
) -> Any:
    """Build a matplotlib Figure showing an RGBA density image on black.

    ``extent`` is the render window the image was binned over (CMP-001); it
    defaults to the Conradi ``[-1, 1]^2`` box but must match the active map's
    extent (e.g. ``clifford_extent(c, d)``) so the axes are scaled correctly.
    """
    from matplotlib.figure import Figure

    fig = Figure(figsize=(6.0, 6.0), facecolor="black")
    ax = fig.add_subplot(111)
    ax.set_facecolor("black")
    # origin="lower": histogram row 0 is the ymin edge (see attractor_density).
    ax.imshow(
        rgba,
        origin="lower",
        extent=extent,
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
    return _build_figure(np.zeros((2, 2, 4), dtype=np.uint8), _DEFAULT_A, _DEFAULT_B)


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
        QStackedWidget,
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
            # (a, b) Lyapunov screening state (CSC-004 / CMP-004).
            self._last_lle: np.ndarray | None = None
            self._screen_mode: bool = False
            self._click_cid: int | None = None
            # The swept-parameter domain of the most recent screening heatmap
            # (per-map; set in _on_screen). Drives the heatmap axes + click clamp.
            self._screen_a_range: tuple[float, float] = attractor_screen.SCREEN_A_RANGE
            self._screen_b_range: tuple[float, float] = attractor_screen.SCREEN_B_RANGE
            # Closed-loop animation state (CSC-005).
            self._frames: list[np.ndarray] | None = None
            self._frame_ab: list[tuple[float, float]] | None = None
            self._anim_index: int = 0
            self._is_playing: bool = False
            self._timer: QTimer | None = None
            self._anim_im: Any = None
            self._anim_marker: Any = None
            # LOOP-EDIT: drag-to-rotate on the playback (a, b) inset. The inset
            # acts as a rotation knob; a release re-precomputes the loop at the
            # new rotation (the swept (a, b) change, so frames must re-render).
            self._anim_inset_ax: Any = None
            self._anim_inset_line: Any = None
            self._inset_cids: list[int] = []
            self._inset_rotating: bool = False
            self._rot_at_grab: float = 0.0
            self._angle_at_grab: float = 0.0
            # CMP-001: the active map's render callable + window. The panel is
            # Conradi-only today (the map-preset picker is CMP-002); these fields
            # are the single seam the picker will flip per selection. Workers and
            # the figure builders read them so every render/animation path is
            # already map-agnostic.
            self._map_fn: Any = attractor_density.conradi_map
            self._extent: tuple[float, float, float, float] = attractor_density.DEFAULT_EXTENT
            # CAL-001 / LOOP-EDIT: per-map (a, b) animation-loop geometry. The
            # loop is a closed Fourier curve (param_path.param_loop); its
            # centre / semi-axes / rotation are now editable by dragging handles
            # in the loop editor (_build_loop_editor). _loop_path_fn is always a
            # closure over this state (rebuilt by _rebuild_loop_fn), so the inset
            # and precompute read the live geometry. _loop_wrapped drives the
            # inset's NaN-split (only the wrapped Conradi loop is split).
            self._loop_center: list[float] = list(param_path.DEFAULT_CENTER)
            self._loop_radius: list[float] = list(param_path.DEFAULT_RADIUS)
            self._loop_rotation: float = float(param_path.DEFAULT_ROTATION)
            self._loop_harmonics: tuple[tuple[float, float], ...] = param_path.DEFAULT_HARMONICS
            self._loop_wrapped: bool = True
            #: Set once the user drags a handle; stops the editor re-seeding the
            #: centre from the current (a, b) pick on each open.
            self._loop_customized: bool = False
            self._loop_path_fn: Any = None
            # Loop-editor view state (the draggable (a, b) canvas).
            self._loop_edit_mode: bool = False
            self._drag_handle: str | None = None
            self._editor_ax: Any = None
            self._editor_cids: list[int] = []
            self._loop_line: Any = None
            self._handle_pts: dict[str, Any] = {}
            self._axis_lines: dict[str, Any] = {}

            from chaotic_systems.gui._panel_helpers import apply_panel_margins

            outer = QVBoxLayout(self)
            apply_panel_margins(outer)

            # --- Map selector + per-map parameter form (CMP-002) ----------
            # A QComboBox drives a QStackedWidget of per-map QFormLayout pages
            # (HoloViz attractors / ParaView property-panel idiom, native Qt).
            # The Conradi page keeps the original a_spin/b_spin objectNames so
            # the CSC-007 panel tests resolve them unchanged.
            cliff_params = CliffordMap().parameters
            # Clifford's (a, b) share the [-3, 3] parameter range; the screening
            # sweep + heatmap axes use it for non-Conradi maps (CMP-004).
            self._clifford_ab_range: tuple[float, float] = (
                cliff_params["a"].min,
                cliff_params["a"].max,
            )

            map_form = QFormLayout()
            map_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            self.map_box = QComboBox(self)
            self.map_box.setObjectName("conradi_map_select")
            self.map_box.addItem("Conradi")
            self.map_box.addItem("Clifford")
            self.map_box.setToolTip(
                "Choose the art-map to render (Conradi sin/cos-of-z² or "
                "Clifford). Screening / animation are Conradi-only for now."
            )
            map_form.addRow(QLabel("Map"), self.map_box)
            outer.addLayout(map_form)

            self.param_stack = QStackedWidget(self)
            self.param_stack.setObjectName("conradi_param_stack")

            # -- Conradi page: preset + a + b -----------------------------
            conradi_page = QWidget(self.param_stack)
            conradi_form = QFormLayout(conradi_page)
            conradi_form.setContentsMargins(0, 0, 0, 0)
            self.conradi_preset_box = QComboBox(conradi_page)
            self.conradi_preset_box.setObjectName("conradi_preset")
            for entry in CONRADI_PRESETS:
                self.conradi_preset_box.addItem(entry[0])
            self.conradi_preset_box.setToolTip("Curated Conradi parameter sets.")
            self.conradi_preset_box.activated.connect(self._on_conradi_preset)
            conradi_form.addRow(QLabel("Preset"), self.conradi_preset_box)

            self.a_spin = QDoubleSpinBox(conradi_page)
            self.a_spin.setObjectName("conradi_a")
            self.a_spin.setRange(0.0, _TWO_PI)
            self.a_spin.setDecimals(3)
            self.a_spin.setSingleStep(0.05)
            self.a_spin.setValue(_DEFAULT_A)
            self.a_spin.setToolTip("Real-channel phase shift a in [0, 2π].")
            conradi_form.addRow(QLabel("a (real phase)"), self.a_spin)

            self.b_spin = QDoubleSpinBox(conradi_page)
            self.b_spin.setObjectName("conradi_b")
            self.b_spin.setRange(0.0, _TWO_PI)
            self.b_spin.setDecimals(3)
            self.b_spin.setSingleStep(0.05)
            self.b_spin.setValue(_DEFAULT_B)
            self.b_spin.setToolTip("Imag-channel phase shift b in [0, 2π].")
            conradi_form.addRow(QLabel("b (imag phase)"), self.b_spin)
            self.param_stack.addWidget(conradi_page)

            # -- Clifford page: preset + a + b + c + d --------------------
            clifford_page = QWidget(self.param_stack)
            clifford_form = QFormLayout(clifford_page)
            clifford_form.setContentsMargins(0, 0, 0, 0)
            self.clifford_preset_box = QComboBox(clifford_page)
            self.clifford_preset_box.setObjectName("conradi_clifford_preset")
            for entry in CLIFFORD_PRESETS:
                self.clifford_preset_box.addItem(entry[0])
            self.clifford_preset_box.setToolTip("Paul Bourke's reference Clifford parameter sets.")
            self.clifford_preset_box.activated.connect(self._on_clifford_preset)
            clifford_form.addRow(QLabel("Preset"), self.clifford_preset_box)

            # Built from CliffordMap.parameters so range/default stay single-sourced.
            self.clifford_spins: dict[str, Any] = {}
            for key in ("a", "b", "c", "d"):
                p = cliff_params[key]
                spin = QDoubleSpinBox(clifford_page)
                spin.setObjectName(f"conradi_clifford_{key}")
                spin.setRange(p.min, p.max)
                spin.setDecimals(3)
                spin.setSingleStep(0.05)
                spin.setValue(p.default)
                spin.setToolTip(p.description or f"Clifford parameter {key}.")
                clifford_form.addRow(QLabel(key), spin)
                self.clifford_spins[key] = spin
            self.param_stack.addWidget(clifford_page)

            outer.addWidget(self.param_stack)
            self.map_box.currentIndexChanged.connect(self._on_map_changed)

            # --- Shared lattice + render controls -------------------------
            controls = QFormLayout()
            controls.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

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
            self.bins_spin.setToolTip("Histogram resolution (output is bins × bins pixels).")
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
            self.bloom_check.setToolTip("Add a multi-scale Gaussian halo around the hot cores.")
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

            # --- Loop frame-count + speed (LOOP-EDIT) ---------------------
            # Frames per loop and playback/export speed were fixed constants;
            # they are now user-adjustable. Speed drives BOTH the live preview
            # QTimer and the exported GIF/MP4 fps so what you see is what you save.
            loop_opts_row = QHBoxLayout()
            loop_opts_row.addWidget(QLabel("Frames"))
            self.frames_spin = QSpinBox(self)
            self.frames_spin.setObjectName("conradi_frames")
            self.frames_spin.setRange(_MIN_FRAMES, _MAX_FRAMES)
            self.frames_spin.setValue(_ANIM_N_FRAMES)
            self.frames_spin.setToolTip(
                "Number of frames rendered around the loop. More frames = "
                "smoother motion and a longer precompute."
            )
            loop_opts_row.addWidget(self.frames_spin)
            loop_opts_row.addSpacing(16)
            loop_opts_row.addWidget(QLabel("Speed"))
            self.fps_spin = QSpinBox(self)
            self.fps_spin.setObjectName("conradi_fps")
            self.fps_spin.setRange(_MIN_FPS, _MAX_FPS)
            self.fps_spin.setValue(_ANIM_FPS)
            self.fps_spin.setToolTip(
                "Playback + export frame rate (fps). Applies live to the "
                "preview and to the exported GIF/MP4."
            )
            self.fps_spin.valueChanged.connect(self._on_fps_changed)
            loop_opts_row.addWidget(self.fps_spin)
            loop_opts_row.addWidget(QLabel("fps"))
            loop_opts_row.addStretch(1)
            outer.addLayout(loop_opts_row)

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

            self.edit_loop_button = QPushButton("Edit loop", self)
            self.edit_loop_button.setObjectName("conradi_edit_loop")
            self.edit_loop_button.setToolTip(
                "Open the (a, b) loop editor: drag the centre dot to move the "
                "loop over the parameter plane, and the rim handles to resize "
                "and rotate it. Then press Animate loop to render the new path."
            )
            self.edit_loop_button.clicked.connect(self._on_edit_loop)
            anim_row.addWidget(self.edit_loop_button)

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
                    "  (NumPy fallback — install the [performance] extra for faster renders.)"
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

            # Seed the per-map loop geometry + build the initial path closure.
            self._init_loop_geometry()

        # ----- loop geometry (LOOP-EDIT) ------------------------------

        def _init_loop_geometry(self) -> None:
            """Reset the loop geometry to the active map's default shape.

            Conradi uses the canonical Fourier teardrop (centre near the
            notebook's (5.46, 4.55), wrapped to ``[0, 2*pi)``); Clifford uses a
            plain non-wrapping ellipse centred in ``[-3, 3]``. Called at
            construction and whenever the map changes; clears the "customized"
            flag so the editor may re-seed the centre from the current pick.
            """
            if self._is_conradi_selected():
                self._loop_center = list(param_path.DEFAULT_CENTER)
                self._loop_radius = list(param_path.DEFAULT_RADIUS)
                self._loop_rotation = float(param_path.DEFAULT_ROTATION)
                self._loop_harmonics = param_path.DEFAULT_HARMONICS
                self._loop_wrapped = True
            else:
                self._loop_center = list(param_path.CLIFFORD_LOOP_CENTER)
                self._loop_radius = list(param_path.CLIFFORD_LOOP_RADIUS)
                self._loop_rotation = 0.0
                self._loop_harmonics = ()
                self._loop_wrapped = False
            self._loop_customized = False
            self._rebuild_loop_fn()

        def _rebuild_loop_fn(self) -> None:
            """Rebuild ``_loop_path_fn`` as a closure over the current geometry.

            Every animation path (the precompute worker + the inset polyline)
            reads ``_loop_path_fn``, so editing the geometry and calling this is
            all that is needed to re-shape the loop. With the per-map defaults
            this closure is point-for-point identical to the previous fixed
            ``param_loop`` / ``clifford_param_loop`` behaviour.
            """
            center = (float(self._loop_center[0]), float(self._loop_center[1]))
            radius = (float(self._loop_radius[0]), float(self._loop_radius[1]))
            rotation = float(self._loop_rotation)
            harmonics = self._loop_harmonics
            wrap = self._loop_wrapped

            def _fn(
                t: Any,
                _c: Any = center,
                _r: Any = radius,
                _h: Any = harmonics,
                _rot: float = rotation,
                _w: bool = wrap,
            ) -> Any:
                return param_path.param_loop(
                    t, center=_c, radius=_r, harmonics=_h, rotation=_rot, wrap=_w
                )

            self._loop_path_fn = _fn

        # ----- click-to-pick (screening mode) -------------------------

        def _bind_click(self, canvas: Any) -> None:
            """Connect the matplotlib button-press handler to ``canvas``."""
            self._click_cid = canvas.mpl_connect("button_press_event", self._on_canvas_click)

        def _on_canvas_click(self, event: Any) -> None:
            """In screening mode, a click sets (a, b) to the clicked cell.

            Clamps to and writes the *active* map's (a, b) spinboxes / parameter
            range (Conradi or Clifford), so click-to-pick is correct per map.
            """
            if not self._screen_mode or event.inaxes is None:
                return
            if event.xdata is None or event.ydata is None:
                return
            a0, a1 = self._screen_a_range
            b0, b1 = self._screen_b_range
            a = min(max(float(event.xdata), a0), a1)
            b = min(max(float(event.ydata), b0), b1)
            a_spin, b_spin = self._active_ab_spins()
            a_spin.setValue(a)
            b_spin.setValue(b)
            self.status_label.setText(f"Picked a = {a:.3f}, b = {b:.3f}. Press Render to draw it.")
            if self._last_lle is not None:
                self._show_screen(self._last_lle)  # redraw marker at new (a, b)

        # ----- map selection (CMP-002) --------------------------------

        def _is_conradi_selected(self) -> bool:
            return self.map_box.currentText() == "Conradi"

        def _active_render_spec(self) -> tuple[float, float, Any, tuple]:
            """Return ``(a, b, map_fn, extent)`` for the currently-selected map.

            Conradi sweeps ``(a, b)`` over the default ``[-1, 1]^2`` window;
            Clifford bakes its fixed ``(c, d)`` into the closure + bounding box
            (``make_clifford_map_fn`` / ``clifford_extent``, CSC-008).
            """
            if self._is_conradi_selected():
                return (
                    float(self.a_spin.value()),
                    float(self.b_spin.value()),
                    attractor_density.conradi_map,
                    attractor_density.DEFAULT_EXTENT,
                )
            c = float(self.clifford_spins["c"].value())
            d = float(self.clifford_spins["d"].value())
            return (
                float(self.clifford_spins["a"].value()),
                float(self.clifford_spins["b"].value()),
                make_clifford_map_fn(c, d),
                clifford_extent(c, d),
            )

        def _active_ab_spins(self) -> tuple[Any, Any]:
            """The (a, b) spinboxes for the currently-selected map."""
            if self._is_conradi_selected():
                return self.a_spin, self.b_spin
            return self.clifford_spins["a"], self.clifford_spins["b"]

        def _active_param_range(
            self,
        ) -> tuple[tuple[float, float], tuple[float, float]]:
            """The ``(a_range, b_range)`` screening sweep domain for the map."""
            if self._is_conradi_selected():
                return attractor_screen.SCREEN_A_RANGE, attractor_screen.SCREEN_B_RANGE
            return self._clifford_ab_range, self._clifford_ab_range

        def _active_screen_fns(self) -> tuple[Any, Any]:
            """``(step_fn, jacobian_push_fn)`` for ``lyapunov_grid``.

            ``(None, None)`` for Conradi (the function's built-in default);
            the Clifford vectorized pair (closing over ``c, d``) otherwise (CMP-004).
            """
            if self._is_conradi_selected():
                return None, None
            c = float(self.clifford_spins["c"].value())
            d = float(self.clifford_spins["d"].value())
            return attractor_screen.clifford_screen_fns(c, d)

        def _on_map_changed(self, _index: int) -> None:
            """Switch the parameter page + sync the active map / control gating."""
            is_conradi = self._is_conradi_selected()
            self.param_stack.setCurrentIndex(0 if is_conradi else 1)
            # Leaving the current map cancels any in-flight playback / anim view
            # and closes the loop editor.
            self._stop_play()
            self._teardown_editor()
            self._teardown_anim_view()
            _a, _b, map_fn, extent = self._active_render_spec()
            self._map_fn = map_fn
            self._extent = extent
            # CAL-001 / LOOP-EDIT: reset to the new map's default loop geometry.
            # Conradi uses the 2*pi-wrapped Fourier teardrop; Clifford a plain
            # non-wrapping ellipse in [-3, 3]. Screening (CMP-004) + animation
            # (CAL-001) + the loop editor (LOOP-EDIT) all work for every map.
            self._init_loop_geometry()
            self.screen_button.setEnabled(True)
            self.animate_button.setEnabled(True)
            name = self.map_box.currentText()
            self.status_label.setText(f"{name} map selected — press Render.")

        def _on_conradi_preset(self, index: int) -> None:
            if 0 <= index < len(CONRADI_PRESETS):
                _label, a, b = CONRADI_PRESETS[index]
                self.a_spin.setValue(a)
                self.b_spin.setValue(b)

        def _on_clifford_preset(self, index: int) -> None:
            if 0 <= index < len(CLIFFORD_PRESETS):
                _label, a, b, c, d = CLIFFORD_PRESETS[index]
                self.clifford_spins["a"].setValue(a)
                self.clifford_spins["b"].setValue(b)
                self.clifford_spins["c"].setValue(c)
                self.clifford_spins["d"].setValue(d)

        # ----- actions ------------------------------------------------

        def _on_render(self) -> None:
            if self._thread is not None and self._thread.isRunning():
                return
            n_points = int(self.n_points_spin.value())
            n_iter = int(self.n_iter_spin.value())
            bins = int(self.bins_spin.value())
            a, b, map_fn, extent = self._active_render_spec()
            # Keep the panel seam in sync so _refresh_plot uses the right extent.
            self._map_fn = map_fn
            self._extent = extent

            self._stop_play()
            self._set_busy(True)
            self.progress_bar.setRange(0, 0)  # indeterminate: one fused call
            self.progress_bar.setVisible(True)
            self.status_label.setText(
                f"Rendering {self.map_box.currentText()}: {n_points}×{n_points} "
                f"seeds × {n_iter} iterations into a {bins}×{bins} histogram..."
            )

            worker = worker_cls(
                a=a,
                b=b,
                n_points=n_points,
                n_iter=n_iter,
                bins=bins,
                tone=self.tone_box.currentText(),
                cmap_name=self.cmap_box.currentText(),
                bloom=self.bloom_check.isChecked(),
                map_fn=map_fn,
                extent=extent,
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
                f"Rendered {rgba.shape[1]}×{rgba.shape[0]}: {lit}/{total} lit pixels."
            )
            self._refresh_plot(rgba)

        def _on_error(self, kind: str, message: str) -> None:
            self._set_busy(False)
            self.progress_bar.setVisible(False)
            self.status_label.setText(f"{kind}: {message}")

        def _set_busy(self, busy: bool) -> None:
            """Enable/disable the compute buttons while a worker runs.

            Render, Screen (CMP-004), and Animate (CAL-001) all work for every
            map, so they simply track the idle state.
            """
            self.render_button.setEnabled(not busy)
            self.screen_button.setEnabled(not busy)
            self.animate_button.setEnabled(not busy)
            self.edit_loop_button.setEnabled(not busy)

        # ----- screening (CSC-004 / CMP-004) --------------------------

        def _on_screen(self) -> None:
            if self._thread is not None and self._thread.isRunning():
                return
            self._stop_play()
            self._set_busy(True)
            self.progress_bar.setRange(0, 0)
            self.progress_bar.setVisible(True)
            # Per-map sweep domain + screening callables (CMP-004).
            a_range, b_range = self._active_param_range()
            step_fn, jacobian_push_fn = self._active_screen_fns()
            self._screen_a_range = a_range
            self._screen_b_range = b_range
            self.status_label.setText(
                f"Screening the {self.map_box.currentText()} (a, b) plane on a "
                f"{_SCREEN_GRID}×{_SCREEN_GRID} grid (largest Lyapunov exponent)..."
            )
            worker = screen_worker_cls(_SCREEN_GRID, a_range, b_range, step_fn, jacobian_push_fn)
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

            self._teardown_editor()  # the heatmap replaces any open loop editor
            a_spin, b_spin = self._active_ab_spins()
            fig = _build_screen_figure(
                lle,
                float(a_spin.value()),
                float(b_spin.value()),
                self._screen_a_range,
                self._screen_b_range,
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
            n_frames = int(self.frames_spin.value())
            self.progress_bar.setRange(0, n_frames)
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(True)
            self.status_label.setText(
                f"Precomputing {n_frames} loop frames (fixed brightness scale)..."
            )
            worker = anim_worker_cls(
                n_frames,
                _ANIM_N_POINTS,
                _ANIM_N_ITER,
                _ANIM_BINS,
                self.cmap_box.currentText(),
                self.bloom_check.isChecked(),
                map_fn=self._map_fn,
                extent=self._extent,
                path_fn=self._loop_path_fn,
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

            self._teardown_editor()  # the playback view replaces the editor
            self._disconnect_inset()  # drop any prior inset-rotation handlers
            assert self._frames is not None and self._frame_ab is not None
            a, b = self._frame_ab[self._anim_index]
            fig = Figure(figsize=(6.0, 6.0), facecolor="black")
            ax = fig.add_subplot(111)
            ax.set_facecolor("black")
            self._anim_im = ax.imshow(
                self._frames[self._anim_index],
                origin="lower",
                extent=self._extent,
                interpolation="nearest",
                aspect="equal",
            )
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)

            # (a, b) loop inset, upper-right, with the moving marker. CAL-001:
            # the inset draws the ACTIVE map's loop; axis limits come from the
            # loop's own range (with a margin) so a Clifford loop in [-3, 3]
            # renders correctly rather than being squashed into [0, 2*pi].
            inset = fig.add_axes((0.70, 0.70, 0.27, 0.27))
            inset.set_facecolor("black")
            loop_a, loop_b = _loop_polyline(self._loop_path_fn, wrapped=self._loop_wrapped)
            # LOOP-EDIT: keep a handle on the inset loop line so drag-to-rotate
            # can spin it live before the frames re-render.
            (self._anim_inset_line,) = inset.plot(loop_a, loop_b, color="#ffe100", linewidth=1.0)
            (self._anim_marker,) = inset.plot([a], [b], marker="o", color="white", markersize=5)
            xlo, xhi = _loop_axis_limits(loop_a, a)
            ylo, yhi = _loop_axis_limits(loop_b, b)
            inset.set_xlim(xlo, xhi)
            inset.set_ylim(ylo, yhi)
            inset.set_xticks([])
            inset.set_yticks([])
            inset.set_title("(a, b) — drag to rotate", color="white", fontsize=8)
            for spine in inset.spines.values():
                spine.set_color("#555555")
            self._anim_inset_ax = inset

            new_canvas = FigureCanvasQTAgg(fig)
            new_canvas.setObjectName("conradi_canvas")
            swap_mpl_canvas(self.layout(), self.canvas, new_canvas)
            self.canvas = new_canvas
            self._bind_click(new_canvas)
            # LOOP-EDIT: drag-to-rotate handlers on the playback (a, b) inset.
            self._inset_cids = [
                new_canvas.mpl_connect("button_press_event", self._on_inset_press),
                new_canvas.mpl_connect("motion_notify_event", self._on_inset_motion),
                new_canvas.mpl_connect("button_release_event", self._on_inset_release),
            ]
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

        def _timer_interval_ms(self) -> int:
            """Playback timer interval (ms) from the Speed (fps) spinbox."""
            fps = max(_MIN_FPS, int(self.fps_spin.value()))
            return max(1, round(1000 / fps))

        def _start_play(self) -> None:
            if self._frames is None:
                return
            if self._timer is None:
                self._timer = QTimer(self)
                self._timer.timeout.connect(self._on_timer_tick)
            # Pick up the current Speed each time playback starts.
            self._timer.setInterval(self._timer_interval_ms())
            self._is_playing = True
            self.play_button.setText("Pause")
            self._timer.start()

        def _on_fps_changed(self, _value: int) -> None:
            """Apply a Speed change live to an already-running playback timer."""
            if self._timer is not None and self._is_playing:
                self._timer.setInterval(self._timer_interval_ms())

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

        # ----- drag-to-rotate the playback (a, b) inset (LOOP-EDIT) ---

        def _inset_angle(self, event: Any) -> float | None:
            """Cursor angle (rad) about the loop centre, in inset (a, b) coords."""
            if self._anim_inset_ax is None or event.inaxes is not self._anim_inset_ax:
                return None
            if event.xdata is None or event.ydata is None:
                return None
            cx, cy = self._loop_center
            return math.atan2(float(event.ydata) - cy, float(event.xdata) - cx)

        def _on_inset_press(self, event: Any) -> None:
            if self._anim_inset_ax is None or getattr(event, "button", None) != 1:
                return
            if self._thread is not None and self._thread.isRunning():
                return  # a precompute is in flight; don't start a rotation
            angle = self._inset_angle(event)
            if angle is None:
                return
            # Grab: remember the rotation + cursor angle so motion is relative.
            self._stop_play()
            self._inset_rotating = True
            self._rot_at_grab = float(self._loop_rotation)
            self._angle_at_grab = angle

        def _on_inset_motion(self, event: Any) -> None:
            if not self._inset_rotating:
                return
            if not self._left_button_held(event):
                # Missed button-release (released off the inset/canvas): commit
                # the rotation done so far instead of leaving it stuck to hover.
                self._on_inset_release(event)
                return
            angle = self._inset_angle(event)
            if angle is None:
                return
            self._loop_rotation = self._rot_at_grab + (angle - self._angle_at_grab)
            self._loop_customized = True
            self._rebuild_loop_fn()
            self._spin_inset_loop()
            self.status_label.setText(
                f"Loop rotation {math.degrees(self._loop_rotation) % 360:.0f}° "
                "— release to re-render the loop."
            )

        def _on_inset_release(self, _event: Any) -> None:
            if not self._inset_rotating:
                return
            self._inset_rotating = False
            # Nothing to do if the rotation didn't actually change (a bare click).
            if abs(self._loop_rotation - self._rot_at_grab) < 1e-9:
                return
            # The swept (a, b) changed, so re-precompute the frames at the new
            # rotation. Reuses the Animate path (progress bar + view rebuild).
            self._on_animate()

        def _spin_inset_loop(self) -> None:
            """Live-update the inset loop polyline as the user rotates it."""
            if self._anim_inset_line is None or self._anim_inset_ax is None:
                return
            loop_a, loop_b = _loop_polyline(self._loop_path_fn, wrapped=self._loop_wrapped)
            self._anim_inset_line.set_data(loop_a, loop_b)
            xlo, xhi = _loop_axis_limits(loop_a, self._loop_center[0])
            ylo, yhi = _loop_axis_limits(loop_b, self._loop_center[1])
            self._anim_inset_ax.set_xlim(xlo, xhi)
            self._anim_inset_ax.set_ylim(ylo, yhi)
            self.canvas.draw_idle()

        def _disconnect_inset(self) -> None:
            """Disconnect inset-rotation handlers + drop the inset artists."""
            self._inset_rotating = False
            for cid in self._inset_cids:
                try:
                    self.canvas.mpl_disconnect(cid)
                except Exception:  # pragma: no cover - canvas already gone
                    pass
            self._inset_cids = []
            self._anim_inset_ax = None
            self._anim_inset_line = None

        # ----- interactive loop editor (LOOP-EDIT) --------------------

        def _on_edit_loop(self) -> None:
            """Open the draggable (a, b) loop editor on the main canvas.

            If the loop is still at its per-map default (the user has not yet
            dragged a handle), the centre is seeded from the current ``(a, b)``
            pick — so picking a point in the screening heatmap and then editing
            starts the loop already centred there.
            """
            if self._thread is not None and self._thread.isRunning():
                return
            self._stop_play()
            if not self._loop_customized:
                a_spin, b_spin = self._active_ab_spins()
                (a_lo, a_hi), (b_lo, b_hi) = self._active_param_range()
                self._loop_center = [
                    min(max(float(a_spin.value()), a_lo), a_hi),
                    min(max(float(b_spin.value()), b_lo), b_hi),
                ]
                self._rebuild_loop_fn()
            self._build_loop_editor()
            self.status_label.setText(
                "Loop editor: drag the white centre dot to move the loop, the "
                "cyan rim handles to resize / rotate. Then press Animate loop."
            )

        def _handle_positions(
            self,
        ) -> tuple[dict[str, tuple[float, float]], tuple[float, float], tuple[float, float]]:
            """Editor handle anchor points + the loop's local axis unit vectors.

            Handles track the *fundamental ellipse* frame (the harmonics that
            bend the drawn curve are ignored for the gizmo): ``center`` at the
            centroid, ``ra`` at ``center + radius_a * u_x`` (primary axis,
            controls length + rotation), ``rb`` at ``center + radius_b * u_y``
            (secondary axis, controls width).
            """
            cx, cy = float(self._loop_center[0]), float(self._loop_center[1])
            ra, rb = float(self._loop_radius[0]), float(self._loop_radius[1])
            rot = float(self._loop_rotation)
            ux = (math.cos(rot), math.sin(rot))
            uy = (-math.sin(rot), math.cos(rot))
            pos = {
                "center": (cx, cy),
                "ra": (cx + ra * ux[0], cy + ra * ux[1]),
                "rb": (cx + rb * uy[0], cy + rb * uy[1]),
            }
            return pos, ux, uy

        def _build_loop_editor(self) -> None:
            """Swap the canvas to the draggable (a, b) loop editor."""
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
            from matplotlib.figure import Figure

            from chaotic_systems.gui._panel_helpers import swap_mpl_canvas

            self._teardown_editor()  # disconnect any prior editor first
            (a_lo, a_hi), (b_lo, b_hi) = self._active_param_range()
            span_a, span_b = a_hi - a_lo, b_hi - b_lo

            fig = Figure(figsize=(6.0, 6.0), facecolor="black")
            ax = fig.add_subplot(111)
            ax.set_facecolor("black")
            # Use the most recent screening heatmap as a backdrop when it covers
            # this map's (a, b) plane, so the user places the loop over visible
            # structure. (The ranges must match the active map's sweep domain.)
            if (
                self._last_lle is not None
                and abs(self._screen_a_range[0] - a_lo) < 1e-6
                and abs(self._screen_a_range[1] - a_hi) < 1e-6
                and abs(self._screen_b_range[0] - b_lo) < 1e-6
                and abs(self._screen_b_range[1] - b_hi) < 1e-6
            ):
                ax.imshow(
                    self._last_lle,
                    origin="lower",
                    extent=(a_lo, a_hi, b_lo, b_hi),
                    cmap=colormaps.get(_SCREEN_CMAP),
                    aspect="auto",
                    interpolation="nearest",
                    alpha=0.85,
                )
            ax.set_xlim(a_lo - 0.08 * span_a, a_hi + 0.08 * span_a)
            ax.set_ylim(b_lo - 0.08 * span_b, b_hi + 0.08 * span_b)
            ax.set_xlabel("a", color="white")
            ax.set_ylabel("b", color="white")
            ax.tick_params(colors="#888888")
            ax.set_title(
                "Loop editor — drag to position / resize / rotate",
                color="white",
                fontsize=10,
            )
            for spine in ax.spines.values():
                spine.set_color("#555555")
            self._editor_ax = ax
            self._draw_loop_artists(ax)

            new_canvas = FigureCanvasQTAgg(fig)
            new_canvas.setObjectName("conradi_canvas")
            swap_mpl_canvas(self.layout(), self.canvas, new_canvas)
            self.canvas = new_canvas
            self._bind_click(new_canvas)  # generic click stays bound but inert
            self._editor_cids = [
                new_canvas.mpl_connect("button_press_event", self._on_editor_press),
                new_canvas.mpl_connect("motion_notify_event", self._on_editor_motion),
                new_canvas.mpl_connect("button_release_event", self._on_editor_release),
            ]
            self._loop_edit_mode = True
            self._screen_mode = False
            self._drag_handle = None
            # Leaving the playback view: drop the (now-dead) anim artists +
            # inset-rotation handlers.
            self._stop_play()
            self._disconnect_inset()
            self._anim_im = None
            self._anim_marker = None
            self.play_button.setEnabled(False)
            self.scrubber.setEnabled(False)

        def _draw_loop_artists(self, ax: Any) -> None:
            """Draw the loop polyline + the three drag handles + axis guides."""
            loop_a, loop_b = _loop_polyline(self._loop_path_fn, wrapped=self._loop_wrapped)
            (self._loop_line,) = ax.plot(loop_a, loop_b, color="#ffe100", linewidth=1.6, zorder=5)
            pos, _ux, _uy = self._handle_positions()
            cx, cy = pos["center"]
            self._axis_lines = {}
            for name in ("ra", "rb"):
                (self._axis_lines[name],) = ax.plot(
                    [cx, pos[name][0]],
                    [cy, pos[name][1]],
                    color="#777777",
                    linewidth=0.8,
                    zorder=4,
                )
            colors = {"center": "#ffffff", "ra": "#00e5ff", "rb": "#00e5ff"}
            self._handle_pts = {}
            for name in ("center", "ra", "rb"):
                (self._handle_pts[name],) = ax.plot(
                    [pos[name][0]],
                    [pos[name][1]],
                    marker="o",
                    color=colors[name],
                    markersize=9,
                    markeredgecolor="black",
                    markeredgewidth=1.0,
                    linestyle="None",
                    zorder=6,
                )

        def _update_loop_artists(self) -> None:
            """Refresh the loop + handle artists in place after a drag."""
            if self._loop_line is None:
                return
            loop_a, loop_b = _loop_polyline(self._loop_path_fn, wrapped=self._loop_wrapped)
            self._loop_line.set_data(loop_a, loop_b)
            pos, _ux, _uy = self._handle_positions()
            cx, cy = pos["center"]
            for name in ("ra", "rb"):
                line = self._axis_lines.get(name)
                if line is not None:
                    line.set_data([cx, pos[name][0]], [cy, pos[name][1]])
            for name in ("center", "ra", "rb"):
                pt = self._handle_pts.get(name)
                if pt is not None:
                    pt.set_data([pos[name][0]], [pos[name][1]])
            self.canvas.draw_idle()

        def _hit_test_handle(self, event: Any) -> str | None:
            """Return the handle name under the cursor, or None.

            Hit-tests in *data* coordinates (``event.xdata`` / ``event.ydata``)
            with a per-axis-normalized tolerance, NOT in display pixels. Pixel
            hit-testing via ``event.x`` / ``event.y`` vs ``transData`` is
            unreliable on hi-DPI displays (the Qt backend's device-pixel-ratio
            makes the two coordinate systems disagree), which made the handles
            un-grabbable on scaled Windows displays. Data coords are
            DPI-independent; normalizing each axis by its span makes the grab
            radius aspect-independent (the editor uses ``aspect="auto"``).
            """
            if self._editor_ax is None or event.inaxes is not self._editor_ax:
                return None
            if event.xdata is None or event.ydata is None:
                return None
            (a_lo, a_hi), (b_lo, b_hi) = self._active_param_range()
            span_a = max(a_hi - a_lo, 1e-9)
            span_b = max(b_hi - b_lo, 1e-9)
            px, py = float(event.xdata), float(event.ydata)
            pos, _ux, _uy = self._handle_positions()
            best: str | None = None
            best_d = _HANDLE_TOL_FRAC
            for name in ("center", "ra", "rb"):
                hx, hy = pos[name]
                d = math.hypot((hx - px) / span_a, (hy - py) / span_b)
                if d <= best_d:
                    best_d = d
                    best = name
            return best

        @staticmethod
        def _left_button_held(event: Any) -> bool:
            """True if the left mouse button is held during a motion event.

            matplotlib 3.x reports held buttons on ``motion_notify_event`` via
            the ``buttons`` frozenset (``button`` is ``None`` for motion). We use
            it to **self-heal a missed** ``button_release_event``: if the user
            releases the mouse off the axes / off the canvas, the release never
            reaches us, so a stale ``_drag_handle`` would make the handle stick
            to the *hovering* cursor — the "can't readjust a second time" bug.
            A motion with no left button held is treated as a drop. Falls back to
            ``event.button`` for synthesized test events that lack ``buttons``.
            """
            buttons = getattr(event, "buttons", None)
            if buttons is not None:
                return 1 in buttons
            return getattr(event, "button", None) == 1

        def _on_editor_press(self, event: Any) -> None:
            if not self._loop_edit_mode or getattr(event, "button", None) != 1:
                return
            self._drag_handle = self._hit_test_handle(event)

        def _on_editor_motion(self, event: Any) -> None:
            if not self._loop_edit_mode or self._drag_handle is None:
                return
            if not self._left_button_held(event):
                self._drag_handle = None  # self-heal a missed button-release
                return
            if event.inaxes is not self._editor_ax:
                return
            if event.xdata is None or event.ydata is None:
                return
            px, py = float(event.xdata), float(event.ydata)
            self._loop_customized = True
            (a_lo, a_hi), (b_lo, b_hi) = self._active_param_range()
            r_max = 0.49 * min(a_hi - a_lo, b_hi - b_lo)

            def _clamp_r(value: float) -> float:
                return min(max(value, _MIN_LOOP_RADIUS), r_max)

            if self._drag_handle == "center":
                self._loop_center = [
                    min(max(px, a_lo), a_hi),
                    min(max(py, b_lo), b_hi),
                ]
            elif self._drag_handle == "ra":
                cx, cy = self._loop_center
                vx, vy = px - cx, py - cy
                self._loop_rotation = math.atan2(vy, vx)
                self._loop_radius[0] = _clamp_r(math.hypot(vx, vy))
            elif self._drag_handle == "rb":
                cx, cy = self._loop_center
                rot = self._loop_rotation
                uy = (-math.sin(rot), math.cos(rot))
                proj = (px - cx) * uy[0] + (py - cy) * uy[1]
                self._loop_radius[1] = _clamp_r(abs(proj))
            self._rebuild_loop_fn()
            self._update_loop_artists()
            self.status_label.setText(
                f"Loop centre ({self._loop_center[0]:.2f}, "
                f"{self._loop_center[1]:.2f}), size ({self._loop_radius[0]:.2f}, "
                f"{self._loop_radius[1]:.2f}), rot "
                f"{math.degrees(self._loop_rotation):.0f}°. Press Animate loop."
            )

        def _on_editor_release(self, _event: Any) -> None:
            self._drag_handle = None

        def _teardown_editor(self) -> None:
            """Disconnect the editor drag handlers and drop its artists."""
            self._loop_edit_mode = False
            self._drag_handle = None
            for cid in self._editor_cids:
                try:
                    self.canvas.mpl_disconnect(cid)
                except Exception:  # pragma: no cover - canvas already gone
                    pass
            self._editor_cids = []
            self._editor_ax = None
            self._loop_line = None
            self._handle_pts = {}
            self._axis_lines = {}

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
            fps = max(_MIN_FPS, int(self.fps_spin.value()))
            try:
                out = write_frames(path, self._frames, fps=fps)
            except (ValueError, OSError, RuntimeError, ImportError) as exc:
                self.status_label.setText(f"Export failed: {type(exc).__name__}: {exc}")
                return False
            self.status_label.setText(
                f"Saved {len(self._frames)} frames at {fps} fps to {out.name}."
            )
            return True

        def _teardown_anim_view(self) -> None:
            """Drop the animation artists + transport when leaving anim view.

            Called when a render / screen canvas replaces the animation canvas so
            the (now-dead) AxesImage / marker are never updated by a stray tick.
            """
            self._stop_play()
            self._disconnect_inset()
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

            self._teardown_editor()  # a still replaces any open loop editor

            fig = _build_figure(
                rgba,
                float(self.a_spin.value()),
                float(self.b_spin.value()),
                extent=self._extent,
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
