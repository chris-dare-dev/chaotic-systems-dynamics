"""3D trajectory renderer built on PyVista / VTK.

The :class:`Renderer3D` class is the visualization core. It owns a PyVista
``Plotter`` (off-screen or embedded in a Qt widget) and exposes:

- :meth:`Renderer3D.show` — open an interactive window (blocking).
- :meth:`Renderer3D.attach` — attach to an existing ``pyvistaqt.QtInteractor``
  so the GUI can host the same renderer in a panel.
- :meth:`Renderer3D.animate` — advance the visible trajectory step by step.
- :meth:`Renderer3D.render_to_video` — write an MP4 of the trajectory using
  ``imageio-ffmpeg``.

Design notes
------------
- We keep a single ``pv.PolyData`` allocated up-front with the *full*
  point buffer of the trajectory (plus one extra "tail" slot for
  sub-frame interpolation) and a ``time`` scalar for colormap shading.
  The PolyData's vertex-cell array is explicitly cleared so VTK does
  not render orphan points as visible glyphs while the polyline grows.
  Animation updates the polyline's ``.lines`` connectivity by slicing
  a pre-allocated int buffer (no per-frame numpy allocation) and
  mutating the tail-slot row in place for sub-frame head precision.
- The "head" marker is a single ``pv.Sphere`` allocated once. We update
  its world position via the underlying VTK actor's transform instead
  of re-meshing every frame.
- For off-screen video we use a local plotter so we don't clobber a
  caller-attached interactor. The instance's ``_plotter`` reference is
  saved and restored around the render.

The renderer never imports PySide6 at module load — it only does so when the
caller actually asks for Qt integration. That keeps headless contexts (CI,
batch video) lightweight.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from .contract import Trajectory, as_points

if TYPE_CHECKING:
    from pyvistaqt import QtInteractor

__all__ = ["Renderer3D", "render_lines_as_tubes_default"]


def render_lines_as_tubes_default() -> bool:
    """Whether to draw the trajectory polyline as tubes by default.

    Why this exists: on macOS — especially macOS 26+ where Apple's
    OpenGL implementation is the ``AppleMetalOpenGLRenderer`` shim —
    VTK's polydata mapper has a shader-template substitution bug when
    *tube rendering* is combined with *scalar-colored lines* (our
    viridis colormap on the trajectory). The fragment shader is
    emitted with ``colorTCoordVCGSOutput`` referenced but never
    declared, the GLSL compile fails, and VTK then segfaults inside
    ``vtkOpenGLPolyDataMapper::UpdateShaders`` when it tries to bind a
    uniform on the broken program. See the crash report dated
    2026-05-17 for the full trace.

    The override knob is the ``CHAOTIC_RENDER_TUBES`` environment
    variable:

    - ``"1"`` / ``"true"`` / ``"yes"`` → force tubes on (regardless of OS)
    - ``"0"`` / ``"false"`` / ``"no"`` → force tubes off
    - unset (default) → tubes off on macOS, on elsewhere

    Plain lines look thinner than tubes at the same ``line_width``,
    but "thinner trajectory" beats "GUI segfaults during render."
    """

    override = os.environ.get("CHAOTIC_RENDER_TUBES")
    if override is not None:
        normalized = override.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        # Unknown value — fall through to the OS-based default rather
        # than silently honoring a typo.
    return sys.platform != "darwin"


# Maximum length (in seconds) of an auto-duration video export. Pulled out so
# callers / tests can find and reason about it without grepping the body of
# `render_to_video`.
MAX_VIDEO_SECONDS = 60

# Default playback rate for an exported attractor-art loop (CSC-006).
DEFAULT_LOOP_FPS: int = 24
# GIF "loop forever" flag (imageio / Pillow convention: 0 = infinite).
GIF_LOOP_FOREVER: int = 0
_GIF_SUFFIX: str = ".gif"


def _open_export_writer(
    out_path: Path,
    *,
    fps: int,
    quality: int = 8,
    codec: str = "libx264",
    loop: int = GIF_LOOP_FOREVER,
) -> Any:
    """Open an ``imageio`` writer, branching on the output extension (CSC-006).

    ``.gif`` -> a Pillow-backed GIF writer with ``loop`` (0 = loop forever);
    anything else -> the well-tested ``libx264`` MP4 path (``macro_block_size=1``,
    ``quality``). Both ``render_to_video`` and :func:`write_frames` share this so
    the MP4 path stays byte-for-byte the one the existing export tests exercise.
    """
    import imageio.v2 as imageio

    if out_path.suffix.lower() == _GIF_SUFFIX:
        # Pillow's GIF plugin wants per-frame duration in ms, not fps.
        duration_ms = 1000.0 / float(fps)
        return imageio.get_writer(
            str(out_path), mode="I", duration=duration_ms, loop=loop
        )
    return imageio.get_writer(
        str(out_path),
        fps=fps,
        codec=codec,
        quality=quality,
        macro_block_size=1,
    )


def write_frames(
    path: str | Path,
    frames: list[np.ndarray],
    *,
    fps: int = DEFAULT_LOOP_FPS,
    loop: int = GIF_LOOP_FOREVER,
    quality: int = 8,
    codec: str = "libx264",
    progress: Callable[[int, int], None] | None = None,
    cancel: Callable[[], bool] | None = None,
) -> Path:
    """Write a list of RGBA/RGB ``uint8`` frames to an MP4 or GIF (CSC-006).

    The container is chosen from ``path``'s extension: ``.gif`` produces a
    seamless looping GIF (``loop=0`` = forever), anything else an MP4 via
    ``libx264``. Frames are coerced to contiguous RGB ``uint8`` (an alpha channel
    is dropped). This is the reusable export path for the Conradi animation loop
    (CSC-005), which already holds its frames in memory; ``render_to_video``
    generates its frames from the 3D scene and keeps its own loop.

    Notes
    -----
    GIF is limited to a 256-colour palette, so Pillow quantizes each frame —
    expect mild banding on the smooth magma/inferno gradients relative to the
    MP4. MP4 is the higher-fidelity option; GIF is the portable, autoplaying one.

    Parameters
    ----------
    path
        Output file path; extension selects the format.
    frames
        Sequence of ``(H, W, 3|4)`` ``uint8`` arrays.
    fps
        Playback rate.
    loop
        GIF loop count (0 = forever); ignored for MP4.
    quality, codec
        MP4 encoder settings (ignored for GIF).
    progress
        Optional ``progress(done, total)`` callback, one call per written frame.
    cancel
        Optional ``cancel() -> bool`` polled between frames; stops early if True.

    Returns
    -------
    Path
        The resolved output path.
    """
    if not frames:
        raise ValueError("write_frames requires at least one frame")

    out_path = Path(path).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    total = len(frames)
    writer = _open_export_writer(
        out_path, fps=fps, quality=quality, codec=codec, loop=loop
    )
    try:
        for i, frame in enumerate(frames):
            if cancel is not None and cancel():
                break
            arr = np.asarray(frame)
            if arr.ndim == 3 and arr.shape[2] == 4:
                arr = arr[..., :3]
            arr = np.ascontiguousarray(arr, dtype=np.uint8)
            writer.append_data(arr)
            if progress is not None:
                progress(i + 1, total)
    finally:
        writer.close()
    return out_path


def _full_polyline_connectivity(n: int) -> np.ndarray:
    """Return the VTK ``lines`` array for a single polyline of ``n`` points."""

    lines = np.empty(n + 1, dtype=np.int64)
    lines[0] = n
    lines[1:] = np.arange(n, dtype=np.int64)
    return lines


def _catmull_rom(
    p0: np.ndarray,
    p1: np.ndarray,
    p2: np.ndarray,
    p3: np.ndarray,
    t: float,
) -> np.ndarray:
    """Evaluate the uniform Catmull-Rom spline at parameter ``t`` in ``[0, 1]``.

    The spline interpolates ``p1`` at ``t=0`` and ``p2`` at ``t=1`` while
    using ``p0`` and ``p3`` as the tangent-defining neighbours. Result is
    C^1 continuous across segment boundaries — the velocity vector matches
    on either side of ``p1`` (or ``p2``) — so the head sphere glides
    smoothly through trajectory samples instead of cornering at each.

    Standard uniform form (Catmull-Rom 1974; see Catmull & Rom,
    "A class of local interpolating splines"):

        q(t) = 0.5 * (
            (2 * P1)
            + (-P0 + P2) * t
            + (2*P0 - 5*P1 + 4*P2 - P3) * t^2
            + (-P0 + 3*P1 - 3*P2 + P3) * t^3
        )

    For centripetal weighting (alpha=0.5) use :func:`_centripetal_t_values`
    to reparameterise the segment before calling this function.
    """

    t2 = t * t
    t3 = t2 * t
    return 0.5 * (
        (2.0 * p1)
        + (-p0 + p2) * t
        + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
        + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3
    )


def _centripetal_segment_eval(
    p0: np.ndarray,
    p1: np.ndarray,
    p2: np.ndarray,
    p3: np.ndarray,
    frac: float,
) -> np.ndarray:
    """Evaluate the centripetal Catmull-Rom spline on segment ``[p1, p2]``.

    ``frac`` is in ``[0, 1]`` along the *uniform* parameterization of
    the segment (the caller's notion of "halfway between p1 and p2");
    we remap it to the centripetal parameter so the spline stays well
    behaved in tight curves and avoids overshoot / self-loops.

    The centripetal Catmull-Rom variant (Yuksel et al. 2011, "On the
    Parameterization of Catmull-Rom Curves") uses
    ``t_i+1 = t_i + ||P_i+1 - P_i||^alpha`` with ``alpha = 0.5`` —
    the chord-length raised to 1/2. This is the standard cure for the
    overshoot / cusp artifacts of plain uniform Catmull-Rom.

    Falls back to a uniform Catmull-Rom evaluation when the segment is
    degenerate (zero-length chord between any consecutive pair).
    """

    # Centripetal parameter values. alpha=0.5 → sqrt of chord length.
    def _knot(a: np.ndarray, b: np.ndarray, t_a: float) -> float:
        chord = float(np.linalg.norm(b - a))
        # Guard zero-length segments; collapse to a tiny eps so the
        # parameter strictly increases and the math stays defined.
        return t_a + max(np.sqrt(chord), 1e-12)

    t0 = 0.0
    t1 = _knot(p0, p1, t0)
    t2 = _knot(p1, p2, t1)
    t3 = _knot(p2, p3, t2)

    # Fall back to uniform Catmull-Rom if the parameterization
    # collapsed (e.g. all points identical) — keeps the call total.
    if t2 <= t1 or t3 <= t2 or t1 <= t0:
        return _catmull_rom(p0, p1, p2, p3, float(frac))

    # Map the user's [0, 1] fraction along the [p1, p2] segment to the
    # corresponding centripetal parameter t in [t1, t2].
    t = t1 + float(frac) * (t2 - t1)

    # Barry-Goldman evaluation of the Catmull-Rom segment in
    # non-uniform parameter space. Three linear interpolations down,
    # then two, then one — numerically stable and cheap.
    a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
    a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
    a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
    b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
    b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
    c = (t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2
    return c


def _spline_neighbour_indices(
    i: int, n: int
) -> tuple[int, int, int, int]:
    """Return ``(i-1, i, i+1, i+2)`` clipped to ``[0, n - 1]``.

    Catmull-Rom needs four samples per segment. At the trajectory
    endpoints we clip rather than extrapolate ghost points — the result
    is locally equivalent to a quadratic interpolation, which is fine
    because the endpoints get exactly one sub-frame anyway.
    """

    return (
        max(0, i - 1),
        max(0, min(i, n - 1)),
        max(0, min(i + 1, n - 1)),
        max(0, min(i + 2, n - 1)),
    )


def _orbit_camera_position(
    center: np.ndarray, radius: float, angle: float
) -> list[Any]:
    """Compute a PyVista ``camera_position`` list for an orbiting camera."""

    cam_pos = (
        center[0] + radius * np.cos(angle),
        center[1] + radius * np.sin(angle),
        center[2] + radius * 0.5,
    )
    return [cam_pos, tuple(center), (0.0, 0.0, 1.0)]


class Renderer3D:
    """3D renderer for a single trajectory.

    Parameters
    ----------
    trajectory:
        Either an ``(N, 3)`` ndarray of points or any object exposing ``.t``
        and ``.y`` attributes (the math agent's ``Trajectory`` shape).
        Higher-dimensional states are projected to three components by
        :func:`chaotic_systems.visualization.contract.as_points`. Pass
        ``projection`` to pick which three.
    title:
        Window title for the interactive viewer.
    line_color:
        Color of the trajectory polyline.
    head_color:
        Color of the moving head marker.
    background:
        Background color of the 3D scene.
    cmap:
        Optional colormap name. If set, the polyline is colored by the
        scalar named in ``color_by`` (default ``"time"``).
    projection:
        Optional 3-tuple of state-axis indices for projecting >3D states.
        Default ``None`` projects to the first three axes.
    color_by:
        Name of the scalar to color the polyline by. Today only
        ``"time"`` is computed automatically; the field is exposed so
        callers can override it on the underlying PolyData.
    axes_labels:
        Optional ``(x, y, z)`` axis labels for ``plotter.show_grid``.
    on_non_finite:
        Behavior when the trajectory contains NaN/Inf rows.
        ``"clip"`` (default) drops trailing non-finite rows; ``"raise"``
        raises ``ValueError``.
    """

    def __init__(
        self,
        trajectory: Trajectory | np.ndarray,
        *,
        title: str = "chaotic-systems-dynamics",
        line_color: str = "#1f77b4",
        # Tokyo Night palette accent — keeps the head sphere coherent with
        # the rest of the UI chrome rather than dropping a matplotlib
        # tab10 red into the scene.
        head_color: str = "#7aa2f7",
        background: str = "white",
        cmap: str | None = "viridis",
        projection: tuple[int, int, int] | None = None,
        color_by: str = "time",
        axes_labels: tuple[str, str, str] | None = None,
        on_non_finite: str = "clip",
    ) -> None:
        points = as_points(
            trajectory, projection=projection, on_non_finite=on_non_finite
        )
        if points.ndim != 2 or points.shape[1] != 3:
            raise ValueError(
                f"trajectory must be coerceable to (N, 3); got {points.shape!r}"
            )
        if points.shape[0] < 2:
            raise ValueError(
                "trajectory must have at least 2 finite points to render"
            )
        # Final sanity check — `as_points(..., on_non_finite="clip")` should
        # already have done this; raise here if anything slipped through.
        if not np.isfinite(points).all():
            raise ValueError(
                "trajectory contains non-finite values after screening"
            )

        self.points: np.ndarray = points
        self.title = title
        self.line_color = line_color
        self.head_color = head_color
        self.background = background
        self.cmap = cmap
        self.color_by = color_by
        self.axes_labels = axes_labels
        # Polyline tube width in logical pixels. Surfaced as a setting in
        # the GUI; defaults to the historical 3.5 px so headless callers
        # see no behavioral change.
        self._line_width: float = 3.5

        # These are populated lazily when a plotter is attached / created.
        self._plotter: Any = None
        self._polyline: Any = None
        self._line_actor: Any = None
        self._head_sphere: Any = None
        self._head_actor: Any = None
        self._head_radius: float = 0.0
        self._head_center0: np.ndarray = np.zeros(3, dtype=float)
        self._owns_plotter: bool = False
        self._current_n: int = self.points.shape[0]

        # Pre-allocated, reused per-frame state. The PolyData hosts
        # ``N + 1`` points where the trailing slot is a writable "tail"
        # used by :meth:`seek_interpolated` to extend the polyline by a
        # sub-frame segment. The connectivity buffer is sized once for
        # the worst case (header byte + every integer index + the tail
        # index) and sliced per frame so we never allocate while playing.
        self._allocate_render_buffers(self.points)

        # Cached bbox / center used by both head positioning and the
        # video-export camera orbit. Computed once because the trajectory
        # buffer never changes.
        self._bbox_diag: float = float(
            np.linalg.norm(self.points.max(axis=0) - self.points.min(axis=0))
        )
        self._center: np.ndarray = self.points.mean(axis=0)

        # Prerender cache state. Populated lazily by
        # :meth:`build_prerender_cache`. ``_arc_lengths`` is the cumulative
        # arc-length at each point (``shape == (N,)``); ``_total_arc`` is
        # ``_arc_lengths[-1]``. ``_prerender_built`` flips to True only
        # after both the arc-length table is in place AND VTK has been
        # warmed by at least one ``Render()`` per representative frame.
        # See ``docs/prerender_design.md`` for rationale.
        self._arc_lengths: np.ndarray | None = None
        self._total_arc: float = 0.0
        self._prerender_built: bool = False
        # Tracks the actual lerped head world-position whenever
        # :meth:`seek_arc_length` runs. ``head_position`` falls back to
        # the polyline-end sample if this is ``None`` (the pre-existing
        # contract). Reset by :meth:`_invalidate_cache`.
        self._head_world_pos: np.ndarray | None = None

        # Catmull-Rom-oversampled point array, populated by
        # :meth:`build_prerender_cache(smooth_factor=k)`. When non-None,
        # the polyline geometry is drawn against this dense array
        # (``k * N`` points) instead of the raw integration samples.
        # The integration samples themselves stay in ``self.points``
        # for parameter-display / t-value lookup purposes — they're the
        # authoritative dynamics; ``_smooth_points`` is only there to
        # give VTK a denser curve to render so the polyline body reads
        # as a smooth curve instead of a chain of line segments.
        self._smooth_points: np.ndarray | None = None
        # Cumulative arc-length table over ``_smooth_points``. When this
        # is in place, :meth:`seek_arc_length` consults it instead of
        # ``_arc_lengths`` so head positions land on the smooth curve.
        self._smooth_arc_lengths: np.ndarray | None = None
        self._smooth_total_arc: float = 0.0
        # ``_sample_to_smooth_idx[i]`` is the row in ``_smooth_points``
        # that corresponds to integration sample ``i``. The smooth
        # oversampler guarantees the original samples appear at
        # ``i * stride`` (the integer-aligned subset), so the lookup is
        # an O(1) array read rather than a search.
        self._sample_to_smooth_idx: np.ndarray | None = None
        self._smooth_stride: int = 1

        # V2: overlay trajectory support. ``_overlay_actors`` holds the
        # PyVista actors for any *static* secondary polylines added via
        # :meth:`add_overlay_trajectory`. Each entry is the actor handle
        # returned by ``plotter.add_mesh``; :meth:`clear_overlays` walks
        # the list and calls ``remove_actor`` on each. No head sphere /
        # no animation — overlays are drawn fully and held still while
        # the primary trajectory animates. See
        # ``docs/proposals/capability-roadmap-2026-05-17.md`` V2.
        self._overlay_actors: list[Any] = []

    # ------------------------------------------------------------------ setup

    def _render_points(self) -> np.ndarray:
        """Return the point array VTK should render the polyline against.

        Returns ``_smooth_points`` when the Catmull-Rom oversampled array
        has been built; otherwise the raw integration samples. Callers
        that need to know "how many rows does my polyline have" should
        consult this — it's the source of truth for all buffer-sizing
        operations.
        """

        if self._smooth_points is not None:
            return self._smooth_points
        return self.points

    def _allocate_render_buffers(self, points: np.ndarray) -> None:
        """(Re)allocate the per-frame buffers against ``points``.

        Called from ``__init__`` with the raw integration samples and
        from :meth:`_install_smooth_points` after the Catmull-Rom
        oversampler has produced a denser array. Sizes the points,
        scalar, and connectivity buffers for ``points.shape[0] + 1``
        rows (the extra row is the writable tail slot).
        """

        n_points = int(points.shape[0])
        self._tail_index = n_points
        self._points_buffer = np.empty((n_points + 1, 3), dtype=float)
        self._points_buffer[:n_points] = points
        self._points_buffer[n_points] = points[-1]
        self._scalar_buffer = np.empty(n_points + 1, dtype=float)
        self._scalar_buffer[:n_points] = np.linspace(0.0, 1.0, n_points)
        self._scalar_buffer[n_points] = 1.0
        self._connectivity_buffer = np.empty(n_points + 2, dtype=np.int64)
        self._current_n = n_points

    def _build_scene(self, plotter: Any) -> None:
        """Populate ``plotter`` with the trajectory line and head marker.

        Allocates a single ``pv.PolyData`` with the full point buffer
        (plus one tail slot for sub-frame interpolation) and a single
        head sphere; both are mutated in place during animation.

        The PolyData's vertex-cell array is explicitly cleared. The
        default ``pv.PolyData(points)`` constructor populates a vertex
        cell per point, which VTK would render as a visible point
        glyph for every trajectory sample — that is the "dot cloud"
        artifact callers see while the polyline grows. Clearing
        ``verts`` ensures only the line cells we set up are drawn.
        """

        import pyvista as pv

        render_points = self._render_points()
        n = int(render_points.shape[0])
        # Re-seed the tail and reset the connectivity-state cache. This
        # matters when a renderer is re-attached (e.g. an off-screen
        # video export reuses the instance and rebuilds the scene), and
        # when the Catmull-Rom oversampler has swapped in a denser
        # ``_smooth_points`` array (which requires bigger buffers).
        if self._points_buffer.shape[0] != n + 1:
            self._allocate_render_buffers(render_points)
        self._points_buffer[:n] = render_points
        self._points_buffer[n] = render_points[-1]
        self._scalar_buffer[:n] = np.linspace(0.0, 1.0, n)
        self._scalar_buffer[n] = 1.0

        polyline = pv.PolyData(self._points_buffer)
        # The default constructor populates one vertex cell per point;
        # that's what produced the "viridis dot cloud" the user sees.
        # An empty cell array tells VTK there are no vertex glyphs.
        polyline.verts = np.empty(0, dtype=np.int64)
        # Initial connectivity covers the full trajectory (the historical
        # behavior — the GUI seeks back to frame 0 immediately after).
        polyline.lines = self._make_integer_connectivity(n)
        polyline.point_data[self.color_by] = self._scalar_buffer
        self._polyline = polyline
        self._current_n = n

        # ``render_lines_as_tubes`` is OS-gated: on macOS we leave it off
        # by default because the VTK shader-template path crashes (see
        # ``render_lines_as_tubes_default`` for the full rationale).
        line_kwargs: dict[str, Any] = {
            "line_width": self._line_width,
            "render_lines_as_tubes": render_lines_as_tubes_default(),
        }
        if self.cmap is not None:
            line_kwargs["scalars"] = self.color_by
            line_kwargs["cmap"] = self.cmap
            line_kwargs["show_scalar_bar"] = False
        else:
            line_kwargs["color"] = self.line_color

        self._line_actor = plotter.add_mesh(polyline, **line_kwargs)

        # Head sphere — allocate once, move with a transform on the actor.
        # Slightly larger relative radius (1.5%) than before so the head
        # reads as the focal point even on a 4 px tube polyline.
        radius = self._bbox_diag * 0.015 if self._bbox_diag > 0 else 0.07
        radius = float(np.clip(radius, 1e-3, 1e6))
        self._head_radius = radius
        # Build the sphere at the origin; we'll translate the actor to
        # the desired head position via `SetPosition`. This way we never
        # rebuild the mesh.
        head_sphere = pv.Sphere(radius=radius, center=(0.0, 0.0, 0.0))
        self._head_sphere = head_sphere
        # Slight ambient lift so the accent-colored sphere glows against
        # the dark Tokyo Night viewport background.
        self._head_actor = plotter.add_mesh(
            head_sphere,
            color=self.head_color,
            ambient=0.35,
            specular=0.6,
            specular_power=20.0,
        )
        self._head_center0 = np.zeros(3, dtype=float)
        self._move_head_actor(self.points[-1])

        plotter.set_background(self.background)
        if self.axes_labels is not None:
            xlab, ylab, zlab = self.axes_labels
            try:
                plotter.show_grid(xtitle=xlab, ytitle=ylab, ztitle=zlab)
            except (AttributeError, TypeError):  # pragma: no cover - PyVista API drift
                plotter.show_axes()
        else:
            plotter.show_axes()
        plotter.reset_camera()

    def _move_head_actor(self, position: np.ndarray) -> None:
        """Move the head actor to ``position`` without rebuilding the mesh."""

        if self._head_actor is None:
            return
        # PyVista actor exposes the underlying VTK prop; SetPosition does the
        # translate-only transform. Falls back to translating mesh points if
        # the actor doesn't expose SetPosition (older PyVista builds).
        try:
            self._head_actor.SetPosition(float(position[0]), float(position[1]), float(position[2]))
            return
        except AttributeError:  # pragma: no cover - PyVista API drift
            if self._head_sphere is not None:
                delta = position - self._head_center0
                self._head_sphere.points = self._head_sphere.points + delta
                self._head_center0 = np.asarray(position, dtype=float).copy()

    def _make_integer_connectivity(self, n: int) -> np.ndarray:
        """Return a slice of the pre-allocated connectivity buffer.

        Writes the count header and ``0..n-1`` indices into the shared
        buffer and returns a *view* over the active prefix. The returned
        slice owns no memory — we hand it to VTK which copies it into
        the polyline's underlying cell array (a one-shot ``memcpy``
        rather than a fresh numpy allocation per frame).
        """

        buf = self._connectivity_buffer
        buf[0] = n
        # The integer prefix never changes, but the slice does — VTK
        # only reads the active span.
        buf[1 : n + 1] = np.arange(n, dtype=np.int64)
        return buf[: n + 1]

    def _make_fractional_connectivity(self, i: int) -> np.ndarray:
        """Return a connectivity slice ending in the tail-slot index.

        Produces ``[i + 2, 0, 1, ..., i, tail_index]``. The polyline
        will draw the integer prefix ``points[0..i]`` and then a final
        segment from ``points[i]`` to the tail-slot point (which the
        caller has just written to the interpolated head position).
        """

        buf = self._connectivity_buffer
        n_visible = i + 2  # i + 1 integer points + 1 tail point
        buf[0] = n_visible
        buf[1 : i + 2] = np.arange(i + 1, dtype=np.int64)
        buf[i + 2] = self._tail_index
        return buf[: i + 3]

    def _set_visible_points(self, n: int) -> None:
        """Update the polyline to show only the first ``n`` integration samples.

        We never re-add a mesh or rebuild the sphere — only the lines
        connectivity array on the PolyData and the head actor's position
        get touched. The connectivity slice is taken from a pre-allocated
        buffer so no numpy array is allocated per frame.

        Always reasserts the integer-prefix connectivity. The previous
        call may have set a fractional-tail connectivity via
        :meth:`seek_interpolated`; we need a pure-integer seek to drop
        that tail segment cleanly, so we can't short-circuit even when
        ``n`` already matches ``_current_n``.

        ``n`` is in *integration-sample* units. When the Catmull-Rom
        oversampler has run, we translate ``n`` to the corresponding
        index in ``_smooth_points`` so the polyline body still renders
        the smooth curve.
        """

        n = int(np.clip(n, 2, self.points.shape[0]))
        self._current_n = n
        if self._smooth_points is not None and n >= 2:
            # Integer sample ``n - 1`` corresponds to a known position
            # in the dense smooth array — anchor on it so the polyline
            # tip aligns with the head sphere exactly.
            n_render = self._smooth_index_for_sample(n - 1) + 1
            n_render = int(np.clip(n_render, 2, self._smooth_points.shape[0]))
            tip = self._smooth_points[n_render - 1]
        else:
            n_render = n
            tip = self.points[n - 1]
        if self._polyline is not None:
            self._polyline.lines = self._make_integer_connectivity(n_render)
        if self._head_actor is not None:
            self._move_head_actor(tip)

    # ------------------------------------------------------------------ public

    @property
    def n_frames(self) -> int:
        """Total number of trajectory samples (frames) this renderer can play."""

        return int(self.points.shape[0])

    @property
    def current_frame(self) -> int:
        """One-based count of currently visible samples (clamped to ``[2, n_frames]``)."""

        return int(self._current_n)

    def attach(self, qt_interactor: QtInteractor) -> None:
        """Attach this renderer to an existing ``pyvistaqt.QtInteractor``.

        Use this when embedding the renderer in a Qt window. The renderer
        does not own the plotter in this case; the caller is responsible for
        teardown.
        """

        # Re-attaching against a new plotter invalidates any shader-cache
        # warming we did against the previous one. The arc-length table is
        # still valid (same trajectory) but the GUI should re-run the
        # full prerender to warm the new actor.
        self._prerender_built = False
        self._plotter = qt_interactor
        self._owns_plotter = False
        # If the renderer previously installed a dense Catmull-Rom buffer,
        # ``_build_scene`` will resize the points/scalar/connectivity
        # buffers and lay out the polyline against the smooth array on
        # the new plotter.
        self._build_scene(self._plotter)

    def reset_camera(self) -> None:
        """Reset the camera to the default framing for this trajectory."""

        if self._plotter is not None:
            self._plotter.reset_camera()
            try:
                self._plotter.render()
            except (AttributeError, RuntimeError):  # pragma: no cover
                pass

    # ----------------------------------------------------- V2 overlays

    def add_overlay_trajectory(
        self,
        trajectory: Trajectory | np.ndarray,
        *,
        color: str = "#f7768e",
        line_width: float | None = None,
        opacity: float = 0.85,
        projection: tuple[int, int, int] | None = None,
        on_non_finite: str = "clip",
    ) -> Any:
        """Add a *static* secondary polyline to the current scene.

        Used by the V2 "compare" toggle in the GUI to overlay a
        perturbed-IC (or alternate-integrator) trajectory on the same
        viewport as the primary animated trajectory. The overlay has
        **no head sphere** and is **not** advanced by
        :meth:`animate` / :meth:`seek` — it is drawn fully and held
        still so the user can read the divergence visually as the
        primary plays back.

        Parameters
        ----------
        trajectory
            Any object coerceable by :func:`chaotic_systems.visualization
            .contract.as_points` — a :class:`Trajectory`, a duck-typed
            object with ``.y``, or a raw ``(N, state_dim)`` ndarray.
        color
            Hex string for the polyline. Defaults to the Tokyo Night
            "red-pink" accent (``#f7768e``) so the overlay reads as
            distinct from the primary trajectory's viridis colormap.
            Pick a hex that contrasts with the cmap you set on the
            primary.
        line_width
            Polyline width in logical pixels. Defaults to the primary
            trajectory's ``_line_width`` (so the two read as a
            matched pair).
        opacity
            Overlay opacity in ``[0, 1]``. The default 0.85 keeps the
            overlay readable while letting the primary's animated head
            stay visually dominant. Lower values fade the overlay
            further toward the background.
        projection, on_non_finite
            Forwarded to :func:`as_points` for the secondary trajectory.

        Returns
        -------
        Any
            The PyVista actor for the overlay. The renderer keeps an
            internal reference so :meth:`clear_overlays` can remove it.

        Raises
        ------
        RuntimeError
            If no plotter is currently attached.
        ValueError
            If the secondary trajectory cannot be coerced to a
            ``(N >= 2, 3)`` finite point array.
        """
        if self._plotter is None:
            raise RuntimeError(
                "call attach() or show() before add_overlay_trajectory()"
            )
        import pyvista as pv

        pts = as_points(
            trajectory, projection=projection, on_non_finite=on_non_finite
        )
        if pts.ndim != 2 or pts.shape[1] != 3:
            raise ValueError(
                f"overlay trajectory must be coerceable to (N, 3); "
                f"got shape {pts.shape!r}"
            )
        if pts.shape[0] < 2:
            raise ValueError(
                "overlay trajectory must have at least 2 finite points"
            )
        if not np.isfinite(pts).all():
            raise ValueError(
                "overlay trajectory contains non-finite values after screening"
            )

        # Fresh PolyData per overlay — no shared buffers with the primary.
        # Static polyline so we lay out connectivity once.
        overlay = pv.PolyData(np.ascontiguousarray(pts, dtype=np.float64))
        overlay.verts = np.empty(0, dtype=np.int64)
        overlay.lines = _full_polyline_connectivity(int(pts.shape[0]))

        actor = self._plotter.add_mesh(
            overlay,
            color=color,
            line_width=(
                float(line_width) if line_width is not None else self._line_width
            ),
            opacity=float(opacity),
            render_lines_as_tubes=True,
        )
        self._overlay_actors.append(actor)
        return actor

    def clear_overlays(self) -> None:
        """Remove every overlay polyline added via :meth:`add_overlay_trajectory`.

        Safe to call when no overlays exist or no plotter is attached.
        The GUI calls this before each new sim so a fresh comparison
        run doesn't paint over the previous one.
        """
        if not self._overlay_actors:
            return
        if self._plotter is None:
            # No live plotter to talk to; just clear the bookkeeping list.
            self._overlay_actors.clear()
            return
        for actor in self._overlay_actors:
            try:
                self._plotter.remove_actor(actor, render=False)
            except (AttributeError, RuntimeError):
                # PyVista API drift / actor already gone — fine, drop it.
                continue
        self._overlay_actors.clear()

    @property
    def n_overlays(self) -> int:
        """Number of overlay polylines currently in the scene."""
        return len(self._overlay_actors)

    def show(self) -> None:
        """Open an interactive window. Blocks until the user closes it."""

        import pyvista as pv

        plotter = pv.Plotter(title=self.title)
        self._plotter = plotter
        self._owns_plotter = True
        self._build_scene(plotter)
        plotter.show()

    def animate(self, frame_step: int = 25) -> None:
        """Animate the trajectory in the currently attached plotter.

        ``frame_step`` controls how many trajectory samples advance per render
        tick. The method blocks while iterating; for non-blocking animation in
        a Qt event loop, use a ``QTimer`` and call :meth:`step` repeatedly.
        """

        if self._plotter is None:
            raise RuntimeError("call attach() or show() before animate()")
        # Probe up-front so we don't catch generic exceptions per-frame.
        # ``render()`` is the right primary call here for the same reason
        # as in ``_request_redraw`` — for a ``QtInteractor`` it's the
        # only thing that triggers ``vtkRenderWindow::Render()``;
        # ``update()`` would just schedule a no-op Qt paint. Fall back to
        # ``update()`` only when the plotter lacks ``render()`` (a stub
        # in some tests).
        render_fn = (
            self._plotter.render
            if hasattr(self._plotter, "render")
            else self._plotter.update
        )
        n_total = self.points.shape[0]
        for n in range(2, n_total + 1, max(1, int(frame_step))):
            self._set_visible_points(n)
            render_fn()

    def _request_redraw(self) -> None:
        """Ask the attached plotter to repaint. Safe before initialization.

        The order matters: we call ``plotter.render()`` first because for
        a ``pyvistaqt.QtInteractor`` (the GUI's plotter), that is the
        method that actually triggers ``vtkRenderWindow::Render()`` and
        emits ``render_signal``. Then we follow up with ``update()`` as a
        Qt paint-schedule nudge — the same "render then update" idiom
        the GUI uses in ``_force_viewport_render`` (see
        ``main_window.py``).

        Why **not** the other way around: ``QtInteractor`` does not
        override ``QWidget.update``, so calling ``update()`` only
        schedules a Qt paint event. VTK widgets don't repaint on Qt
        paint events — they repaint when ``Render()`` runs. The old
        order ("update() first, render() only if update() raises")
        therefore short-circuited every animation tick to a no-op once
        the interactor was up, leaving PyVistaQt's internal
        ``render_timer`` (default ``auto_update=5.0``, i.e. 5 Hz) as
        the only thing actually painting at idle. With a 60 Hz
        animation tick, that produced ~12× under-sampling and the
        head-sphere "snapped" between integer-frame positions whenever
        the user wasn't dragging the camera (the interactor's own
        mouse-driven renders had been masking the bug). Crash report
        dated 2026-05-17 traces it end-to-end.
        """

        if self._plotter is None:
            return
        render_fn: Callable[[], Any] | None = getattr(self._plotter, "render", None)
        update_fn: Callable[[], Any] | None = getattr(self._plotter, "update", None)
        if render_fn is not None:
            try:
                render_fn()
            except (RuntimeError, AttributeError):  # pragma: no cover - defensive
                pass
        if update_fn is not None:
            try:
                update_fn()
            except RuntimeError:  # pragma: no cover - defensive
                pass

    def step(self, n_visible: int) -> None:
        """Show the first ``n_visible`` samples (clamped). Returns immediately.

        Convenient for driving the animation from an external ``QTimer``.
        ``n_visible`` is the *cumulative* count of points to display — pass
        ``current_frame + frames_per_tick`` to advance, not a delta.
        """

        self._set_visible_points(n_visible)
        self._request_redraw()

    def seek(self, index: int) -> None:
        """Jump to frame ``index`` (zero-based). Rebuilds the polyline up to it.

        The frame index is interpreted as the *last* sample to display, so
        ``seek(0)`` shows the first two samples (the minimum a polyline can
        carry) and ``seek(n_frames - 1)`` shows the entire trajectory.
        Equivalent in effect to ``step(index + 1)`` but named for the
        transport-control idiom of "scrubbing to a position".
        """

        n_visible = int(np.clip(int(index) + 1, 2, self.points.shape[0]))
        self._set_visible_points(n_visible)
        # Integer-frame API: reset the arc-length head-position cache so
        # ``head_position`` reverts to the polyline-end semantics the
        # transport scrubber expects.
        self._head_world_pos = None
        self._request_redraw()

    def seek_interpolated(self, index_float: float) -> None:
        """Jump to a *fractional* frame index for sub-frame smoothness.

        Both the polyline and the head sphere are updated to a fractional
        position: the polyline extends to ``points[i]`` and then draws a
        final segment to the lerped point between ``points[i]`` and
        ``points[i+1]`` (written into the PolyData's tail slot in
        place); the head sphere sits on top of that lerped point. At
        60 FPS with even a small stride this is the difference between
        "head and polyline-tail teleport between samples" and "both
        glide smoothly".

        When the Catmull-Rom oversampler has run, the polyline tip and
        head position come from the spline (C^1 continuous) rather than
        the linear chord. The integer-frame index is still the
        authoritative playhead coordinate the GUI cares about — the
        spline is just the geometry the renderer draws.

        Falls back to integer :meth:`seek` semantics when the fractional
        part is zero (or ``index_float`` is at the last sample).
        """

        n_total = self.points.shape[0]
        if n_total <= 1:
            return
        # Clamp into the valid float range so the head never lerps past
        # the final sample.
        idx_f = float(np.clip(index_float, 0.0, n_total - 1))
        i = int(np.floor(idx_f))
        frac = idx_f - i
        if frac == 0.0 or i >= n_total - 1:
            # Pure integer seek — no tail point needed; use the
            # cheaper integer-connectivity path.
            self._set_visible_points(i + 1)
            self._request_redraw()
            return
        # Sub-frame branch: write the tail point in place, set the
        # fractional connectivity, and move the head sphere too.
        if self._smooth_points is not None:
            head_pos, n_render_prefix, scalar = self._smooth_subframe(i, frac)
        else:
            p0 = self.points[i]
            p1 = self.points[i + 1]
            head_pos = p0 + frac * (p1 - p0)
            n_render_prefix = i + 1
            scalar = float(
                self._scalar_buffer[i]
                + frac * (self._scalar_buffer[i + 1] - self._scalar_buffer[i])
            )
        # ``_current_n`` tracks the *integer prefix* count (i + 1)
        # — that's what the public ``current_frame`` and the
        # transport bookkeeping want to see. We update it whether or
        # not a plotter is attached so headless callers still get the
        # right ``current_frame`` value.
        self._current_n = i + 1
        # Mutate the underlying VTK-backed points array directly so
        # only one row is touched per frame.
        if self._polyline is not None:
            poly_pts = self._polyline.points
            poly_pts[self._tail_index] = head_pos
            # Keep the scalar in sync so the tail segment colours match
            # the cmap progression.
            poly_scalar = self._polyline.point_data[self.color_by]
            poly_scalar[self._tail_index] = scalar
            self._polyline.lines = self._make_fractional_connectivity(
                n_render_prefix - 1
            )
        if self._head_actor is not None:
            self._move_head_actor(head_pos)
        # Cache the spline-evaluated head position so :prop:`head_position`
        # returns the smooth-curve point. Only when the smooth path ran;
        # the legacy linear path keeps the polyline-end fallback so the
        # pre-existing transport-scrubber contract is unchanged.
        if self._smooth_points is not None:
            self._head_world_pos = np.asarray(head_pos, dtype=float).copy()
        self._request_redraw()

    def _smooth_subframe(
        self, i: int, frac: float
    ) -> tuple[np.ndarray, int, float]:
        """Compute the spline-evaluated tail / head for sample ``i + frac``.

        Returns ``(head_pos, n_render_prefix, scalar)`` where:
        - ``head_pos`` is the centripetal Catmull-Rom point at fractional
          position ``frac`` along the segment ``[points[i], points[i+1]]``.
        - ``n_render_prefix`` is how many dense smooth-points should be
          drawn before the tail point — pick the largest dense index
          whose arc-length is strictly less than the spline-evaluated
          tail's arc-length, so the polyline body+tail covers the smooth
          curve exactly once.
        - ``scalar`` is the cmap parameter at the head position
          (linear in [0, 1]).

        Assumes ``_smooth_points`` and ``_sample_to_smooth_idx`` are in
        place (the caller checks before invoking this).
        """

        # Centripetal Catmull-Rom evaluation. Clip neighbour indices at
        # the trajectory endpoints instead of using ghost points; near
        # the boundary the segment degrades gracefully to a quadratic
        # interpolation.
        n_total = self.points.shape[0]
        i0, i1, i2, i3 = _spline_neighbour_indices(i, n_total)
        head_pos = _centripetal_segment_eval(
            self.points[i0],
            self.points[i1],
            self.points[i2],
            self.points[i3],
            float(frac),
        ).astype(float, copy=False)

        # Pick the polyline prefix length so the rendered curve stops
        # *just before* the head — the tail segment then connects the
        # last dense smooth-point to the spline-evaluated head, closing
        # any tiny gap from quadrature error.
        assert self._sample_to_smooth_idx is not None  # noqa: S101
        n_prefix = int(self._sample_to_smooth_idx[i]) + 1
        # Walk forward through the smooth array as long as we haven't
        # passed the head position's parameter (frac fraction of the
        # segment). We pre-cache the per-sample stride at oversample
        # time so this is a constant-time slice.
        stride = int(self._smooth_stride)
        n_prefix_target = n_prefix + int(np.floor(frac * stride))
        max_prefix = self._smooth_points.shape[0] - 1
        n_prefix_target = int(np.clip(n_prefix_target, n_prefix, max_prefix))

        n_total_samples = self.points.shape[0]
        scalar = (float(i) + float(frac)) / max(1.0, n_total_samples - 1)
        return head_pos, n_prefix_target + 1, scalar

    # --------------------------------------------------------- prerender API

    @property
    def has_prerender_cache(self) -> bool:
        """True iff the arc-length table is built *and* VTK is warmed."""

        return bool(self._prerender_built) and self._arc_lengths is not None

    @property
    def total_arc_length(self) -> float:
        """Length of the trajectory polyline in world-space units.

        Zero until :meth:`build_prerender_cache` has been called. Callers
        can drive a wall-clock playback rate by mapping
        ``total_arc_length / target_seconds`` to a per-tick arc-length
        increment and feeding the result to :meth:`seek_arc_length`.
        """

        return float(self._total_arc)

    def _build_arc_length_table(self) -> None:
        """Compute the cumulative arc-length table.

        Internal helper; called from :meth:`build_prerender_cache`. Cheap
        even for large trajectories — a single ``np.diff`` + ``cumsum``.
        Idempotent: returns immediately if the table is already built.
        """

        if self._arc_lengths is not None:
            return
        diffs = np.diff(self.points, axis=0)
        seg_lens = np.linalg.norm(diffs, axis=1)
        # Prepend a 0.0 so ``_arc_lengths[i]`` is the cumulative arc-length
        # at sample ``i`` — matches the indexing convention used by
        # :meth:`seek_arc_length`.
        arc = np.concatenate(([0.0], np.cumsum(seg_lens)))
        # Guard against pathological all-zero-segment trajectories (e.g.
        # a fixed-point initial condition). We never want to divide by
        # zero in :meth:`seek_arc_length`.
        self._arc_lengths = arc.astype(float, copy=False)
        self._total_arc = float(arc[-1])

    def _smooth_index_for_sample(self, i: int) -> int:
        """Return the row in ``_smooth_points`` matching integration sample ``i``."""

        if self._sample_to_smooth_idx is None:
            return int(i)
        i = int(np.clip(i, 0, self._sample_to_smooth_idx.shape[0] - 1))
        return int(self._sample_to_smooth_idx[i])

    def _build_smooth_points(self, factor: int) -> None:
        """Oversample the trajectory ``factor`` times via centripetal Catmull-Rom.

        Produces a dense ``_smooth_points`` array of shape
        ``((N - 1) * factor + 1, 3)`` that interpolates through every
        original integration sample at indices ``i * factor`` and fills
        in ``factor - 1`` spline-evaluated points between each pair.

        The accompanying ``_smooth_arc_lengths`` table covers the dense
        curve so :meth:`seek_arc_length` can land on it directly.
        ``_sample_to_smooth_idx[i] = i * factor`` provides the
        constant-time mapping from integration sample to dense index.

        Memory: at 4× oversampling on a 4000-sample trajectory the
        dense buffer is ~376 KB (3 floats × 8 bytes × 16k rows). Well
        inside the 10 MB budget called out in the task brief.

        Idempotent: returns immediately if the smooth buffer is already
        in place. Skips construction when ``factor <= 1`` (the
        oversampled curve degenerates to the original samples).
        """

        if factor <= 1:
            return
        if self._smooth_points is not None:
            return
        n = self.points.shape[0]
        if n < 2:
            return
        # Pre-allocate the dense buffer. The endpoints coincide with
        # the trajectory endpoints; the (factor - 1) interior points
        # per segment are filled by the spline.
        m = (n - 1) * factor + 1
        smooth = np.empty((m, 3), dtype=float)
        # Pre-compute the fractional samples for each interior point.
        # Index ``k`` in [1, factor) → frac = k / factor.
        fracs = np.arange(1, factor, dtype=float) / float(factor)
        # Walk segments. The dense array layout is:
        #   smooth[i * factor]        == points[i]            (anchor)
        #   smooth[i * factor + k]    == spline(i, frac=k/factor) for k in 1..factor-1
        for i in range(n - 1):
            i0, i1, i2, i3 = _spline_neighbour_indices(i, n)
            p0 = self.points[i0]
            p1 = self.points[i1]
            p2 = self.points[i2]
            p3 = self.points[i3]
            # Anchor sample lands exactly on the integration point.
            smooth[i * factor] = p1
            # Interior spline-evaluated points.
            for k_idx, frac in enumerate(fracs):
                smooth[i * factor + 1 + k_idx] = _centripetal_segment_eval(
                    p0, p1, p2, p3, float(frac)
                )
        # Tail anchor.
        smooth[-1] = self.points[-1]

        # Cumulative arc-length over the dense array.
        d = np.diff(smooth, axis=0)
        seg_lens = np.linalg.norm(d, axis=1)
        smooth_arc = np.concatenate(([0.0], np.cumsum(seg_lens)))

        # Sample-to-smooth index map. Each integration sample lands at
        # ``i * factor`` in the dense array.
        idx_map = np.arange(n, dtype=np.int64) * factor

        self._smooth_points = smooth
        self._smooth_arc_lengths = smooth_arc.astype(float, copy=False)
        self._smooth_total_arc = float(smooth_arc[-1])
        self._sample_to_smooth_idx = idx_map
        self._smooth_stride = int(factor)

    # Default oversampling factor for the Catmull-Rom dense-points
    # array. 4× gives a noticeably smoother polyline body without
    # blowing the memory budget — a 4000-sample trajectory expands to
    # 16k smooth points, ~376 KB. Bumping to 8 quadruples the buffer
    # but the visible smoothness improvement plateaus.
    SMOOTH_OVERSAMPLE_FACTOR: int = 4

    def build_prerender_cache(
        self,
        *,
        progress_cb: Callable[[int, int], None] | None = None,
        cancel_cb: Callable[[], bool] | None = None,
        smooth_factor: int | None = None,
    ) -> bool:
        """Build the arc-length table and warm VTK's render pipeline.

        Idempotent: returns immediately (with ``True``) if the cache is
        already in place. Otherwise the method does four things:

        1. Builds the cumulative arc-length table (mechanism (d) in the
           design doc — fast, always done, drives uniform visual speed).
        2. Oversamples the trajectory ``smooth_factor`` times via
           centripetal Catmull-Rom (default 4×) so the polyline body
           reads as a C^1-smooth curve instead of straight-line
           segments between integration samples.
        3. Calls :meth:`_set_visible_points` at the trajectory endpoints
           to ensure VTK has observed the full and empty polyline
           configurations (mechanism (a)).
        4. Calls :meth:`seek_arc_length` at five evenly spaced
           arc-length positions, each followed by a redraw, so the VTK
           shader cache for the polyline mapper and the head-sphere
           actor pipeline are populated before the user-visible
           playback loop starts (mechanism (c)).

        Parameters
        ----------
        progress_cb:
            Optional ``callable(current, total)`` invoked between each
            warm-up step. ``total`` is fixed at the number of warm-up
            calls (currently 6: five seek positions + the return to
            arc-length zero).
        cancel_cb:
            Optional ``callable() -> bool`` polled between warm-up
            steps. If it returns ``True``, the loop exits and the cache
            is left in a *partially-built* state — the arc-length table
            stands (it was computed in step 1 and is cheap to recompute
            anyway), but ``has_prerender_cache`` returns ``False`` so
            the GUI can decide whether to retry or fall back.
        smooth_factor:
            Override the Catmull-Rom oversampling factor. ``None``
            uses :attr:`SMOOTH_OVERSAMPLE_FACTOR` (4); set to ``1`` to
            disable the dense-curve geometry entirely (the renderer
            falls back to drawing the polyline against the raw
            integration samples — this is the legacy behavior).

        Returns
        -------
        bool
            ``True`` if the cache is fully built, ``False`` if the
            caller cancelled mid-warm-up.
        """

        if self.has_prerender_cache:
            return True
        # Step 1 — arc-length table. Cheap, always done.
        self._build_arc_length_table()
        # Step 2 — Catmull-Rom oversampling. Done before any VTK warm-up
        # so the shader cache is built against the *final* geometry.
        factor = int(
            self.SMOOTH_OVERSAMPLE_FACTOR if smooth_factor is None else smooth_factor
        )
        had_smooth_before = self._smooth_points is not None
        if factor > 1 and self._smooth_points is None:
            self._build_smooth_points(factor)
        # If we just installed the smooth geometry, swap the PolyData
        # to render against it (needs bigger buffers).
        if self._smooth_points is not None and not had_smooth_before:
            self._install_smooth_geometry()

        # Step 3 & 4 — VTK pipeline warm-up. Only meaningful when a
        # plotter is attached; if not, we still expose the arc-length
        # table for headless callers (tests use this path).
        if self._plotter is None or self._polyline is None:
            self._prerender_built = True
            if progress_cb is not None:
                progress_cb(1, 1)
            return True

        # Warm-up positions in arc-length space. The first and last
        # exercise the full / empty polyline; the three midpoints
        # exercise the integer-prefix seek path; the final return to
        # zero leaves the renderer in a known state for the play loop.
        total = self._total_arc
        warmup_arcs: list[float] = [
            0.0,
            total * 0.25,
            total * 0.5,
            total * 0.75,
            total,
            0.0,
        ]
        n_steps = len(warmup_arcs)
        for i, s in enumerate(warmup_arcs):
            if cancel_cb is not None and cancel_cb():
                # Leave _prerender_built False so the GUI / tests can
                # tell the cache is incomplete.
                return False
            self.seek_arc_length(s)
            if progress_cb is not None:
                progress_cb(i + 1, n_steps)
        self._prerender_built = True
        return True

    def _install_smooth_geometry(self) -> None:
        """Rebuild the PolyData against ``_smooth_points``.

        Resizes the points / scalar / connectivity buffers and re-adds
        the line actor against the denser PolyData. The head actor and
        plotter handle are left untouched.

        Called from :meth:`build_prerender_cache` once the Catmull-Rom
        oversampler has produced its dense array. The cost is a one-shot
        VTK re-mesh — a few ms on a 16k-point polyline.
        """

        import pyvista as pv

        if self._smooth_points is None:
            return
        # Reallocate the per-frame buffers against the dense array.
        self._allocate_render_buffers(self._smooth_points)
        # When there's no plotter attached (headless callers, tests),
        # we still keep the dense buffer state — the polyline gets
        # populated lazily on the next :meth:`attach`.
        if self._plotter is None:
            return
        # Remove the existing line actor before swapping the PolyData.
        try:
            self._plotter.remove_actor(self._line_actor, render=False)
        except (AttributeError, RuntimeError, TypeError):  # pragma: no cover
            pass
        polyline = pv.PolyData(self._points_buffer)
        polyline.verts = np.empty(0, dtype=np.int64)
        polyline.lines = self._make_integer_connectivity(
            self._smooth_points.shape[0]
        )
        polyline.point_data[self.color_by] = self._scalar_buffer
        self._polyline = polyline
        # ``render_lines_as_tubes`` is OS-gated: on macOS we leave it off
        # by default because the VTK shader-template path crashes (see
        # ``render_lines_as_tubes_default`` for the full rationale).
        line_kwargs: dict[str, Any] = {
            "line_width": self._line_width,
            "render_lines_as_tubes": render_lines_as_tubes_default(),
        }
        cmap_enabled = getattr(self, "_color_by_progress_enabled", True)
        new_cmap = self.cmap if cmap_enabled else None
        if new_cmap is not None:
            line_kwargs["scalars"] = self.color_by
            line_kwargs["cmap"] = new_cmap
            line_kwargs["show_scalar_bar"] = False
        else:
            line_kwargs["color"] = self.line_color
        self._line_actor = self._plotter.add_mesh(self._polyline, **line_kwargs)

    def seek_arc_length(self, s: float) -> None:
        """Move the playhead to arc-length position ``s``.

        ``s`` is clamped to ``[0, total_arc_length]``. The polyline
        extends to the integer-prefix that *just precedes* the requested
        arc-length, and the head sphere lerps along the segment between
        samples ``i`` and ``i+1`` to land exactly at arc-length ``s``.
        This is the Manim-style ``point_from_proportion`` analog —
        playback driven by *visual* distance rather than *integration*
        time, so chaotic stretches advance slowly and calm regions zip
        past at uniform visual speed.

        If the arc-length table has not been built yet, this method
        builds it on the fly (the table is cheap; the more expensive
        VTK warm-up only happens via :meth:`build_prerender_cache`).
        """

        if self._arc_lengths is None:
            self._build_arc_length_table()
        arc = self._arc_lengths
        # ``_build_arc_length_table`` always populates the cache, but
        # mypy can't see that — narrow the type explicitly.
        assert arc is not None  # noqa: S101 - invariant; cheap, ms-fast
        n_total = self.points.shape[0]
        if n_total <= 1 or self._total_arc <= 0.0:
            return

        # Smooth-geometry path. When the Catmull-Rom oversampler has
        # run, drive the playhead off the *dense* arc-length table so
        # both the polyline tip and the head sphere land on the smooth
        # curve (C^1 continuous through every sample).
        if (
            self._smooth_points is not None
            and self._smooth_arc_lengths is not None
            and self._smooth_total_arc > 0.0
        ):
            self._seek_arc_length_smooth(s)
            return

        s_clamped = float(np.clip(s, 0.0, self._total_arc))
        # ``np.searchsorted`` finds the index where ``arc[idx-1] <= s < arc[idx]``
        # with ``side="right"``; subtract 1 to get the floor sample.
        idx = int(np.searchsorted(arc, s_clamped, side="right")) - 1
        idx = int(np.clip(idx, 0, n_total - 2))
        seg_len = float(arc[idx + 1] - arc[idx])
        if seg_len <= 0.0:
            # Zero-length segment — fall through to a pure integer seek.
            self.seek_interpolated(float(idx))
            return
        frac = float(np.clip((s_clamped - arc[idx]) / seg_len, 0.0, 1.0))
        # Delegate to the existing fractional-seek path so we re-use
        # the head-sphere lerp and the polyline tail-slot machinery.
        self.seek_interpolated(idx + frac)
        # Track the exact head world-position so ``head_position`` can
        # return the lerped point (the polyline-end-sample fallback is
        # only used when no arc-length seek has run yet — the
        # pre-existing contract for callers that don't use the
        # prerender path).
        p0 = self.points[idx]
        p1 = self.points[idx + 1]
        head_pos = (p0 + frac * (p1 - p0)).astype(float, copy=True)
        # Special case at ``s == 0``: ``seek_interpolated(0.0)`` would
        # have parked the head at ``points[1]`` (the polyline's two-point
        # minimum); restore it to ``points[0]`` so the arc-length seek
        # is mathematically consistent with its mirror at
        # ``s == total_arc_length``.
        if s_clamped == 0.0:
            head_pos = np.asarray(self.points[0], dtype=float).copy()
            if self._head_actor is not None:
                self._move_head_actor(head_pos)
        self._head_world_pos = head_pos

    def _seek_arc_length_smooth(self, s: float) -> None:
        """Arc-length seek against the Catmull-Rom dense curve.

        Drives the playhead off ``_smooth_arc_lengths`` so the head
        sphere and polyline tip both glide along the C^1-continuous
        spline. Updates ``_current_n`` against the *integration-sample*
        index so the GUI's scrubber / time-label bookkeeping still
        works (``current_frame`` semantics unchanged).
        """

        assert self._smooth_points is not None  # noqa: S101
        assert self._smooth_arc_lengths is not None  # noqa: S101
        smooth = self._smooth_points
        smooth_arc = self._smooth_arc_lengths
        total = self._smooth_total_arc
        # Map ``s`` from the linear arc-length parameterization (what
        # the GUI hands us, computed against the integration polyline)
        # to the smooth arc-length parameterization. The two scales
        # differ slightly because the smooth curve is a hair longer
        # than the linear chord. A linear remap is exact at the
        # endpoints and close enough in between for our purposes (sub-
        # frame error doesn't matter visually).
        if self._total_arc > 0.0:
            s_smooth = (
                float(np.clip(s, 0.0, self._total_arc))
                / self._total_arc
                * total
            )
        else:
            s_smooth = 0.0
        s_smooth = float(np.clip(s_smooth, 0.0, total))
        m = smooth.shape[0]
        # Binary search the dense arc-length table.
        idx = int(np.searchsorted(smooth_arc, s_smooth, side="right")) - 1
        idx = int(np.clip(idx, 0, m - 2))
        seg_len = float(smooth_arc[idx + 1] - smooth_arc[idx])
        if seg_len <= 0.0:
            frac = 0.0
        else:
            frac = float(
                np.clip((s_smooth - smooth_arc[idx]) / seg_len, 0.0, 1.0)
            )
        # Head position on the smooth curve. The dense array is itself
        # the centripetal spline, so a linear interp between two dense
        # samples is already very close to the underlying spline.
        p0 = smooth[idx]
        p1 = smooth[idx + 1]
        head_pos = (p0 + frac * (p1 - p0)).astype(float, copy=True)

        # Map back to integration-sample units for the GUI scrubber.
        stride = max(1, int(self._smooth_stride))
        sample_idx = int(idx // stride)
        sample_idx = int(np.clip(sample_idx, 0, self.points.shape[0] - 1))
        self._current_n = sample_idx + 1

        # Update VTK geometry. The polyline body grows along the dense
        # array, and the tail slot carries the spline-evaluated head.
        if self._polyline is not None:
            n_prefix = idx + 1
            poly_pts = self._polyline.points
            poly_pts[self._tail_index] = head_pos
            scalar_top = float(sample_idx + frac) / max(
                1.0, float(self.points.shape[0] - 1)
            )
            poly_scalar = self._polyline.point_data[self.color_by]
            poly_scalar[self._tail_index] = scalar_top
            if frac == 0.0:
                self._polyline.lines = self._make_integer_connectivity(n_prefix)
            else:
                self._polyline.lines = self._make_fractional_connectivity(
                    n_prefix - 1
                )
        if self._head_actor is not None:
            self._move_head_actor(head_pos)
        self._head_world_pos = head_pos
        self._request_redraw()

    def _invalidate_cache(self) -> None:
        """Drop the prerender cache.

        Called by every code path that materially changes the geometry
        the cache depends on (new trajectory attached, line-actor
        rebuilt, etc.). The arc-length table is dropped because a new
        trajectory will need a different one; the ``_prerender_built``
        flag is cleared so the GUI re-runs the warm-up. Calling this on
        an already-clean cache is a no-op.

        The Catmull-Rom dense-points buffer is *not* dropped — it's
        geometry-only and survives changes that only affect the VTK
        actor (line width, colormap toggle). Code paths that change
        the trajectory itself rebuild a fresh ``Renderer3D`` instance.
        """

        self._arc_lengths = None
        self._total_arc = 0.0
        self._prerender_built = False
        self._head_world_pos = None

    # ------------------------------------------------------------------------

    def set_line_width(self, width: float) -> None:
        """Set the trajectory polyline width (logical pixels).

        Rebuilds the line actor in place so the head sphere and polyline
        PolyData are not disturbed. Safe to call before :meth:`attach`;
        the value will be picked up on the next scene build.
        """

        self._line_width = float(max(0.1, width))
        if self._plotter is None or self._polyline is None:
            return
        try:
            self._plotter.remove_actor(self._line_actor, render=False)
        except (AttributeError, RuntimeError, TypeError):  # pragma: no cover
            pass
        # ``render_lines_as_tubes`` is OS-gated: on macOS we leave it off
        # by default because the VTK shader-template path crashes (see
        # ``render_lines_as_tubes_default`` for the full rationale).
        line_kwargs: dict[str, Any] = {
            "line_width": self._line_width,
            "render_lines_as_tubes": render_lines_as_tubes_default(),
        }
        new_cmap = self.cmap if getattr(self, "_color_by_progress_enabled", True) else None
        if new_cmap is not None:
            line_kwargs["scalars"] = self.color_by
            line_kwargs["cmap"] = new_cmap
            line_kwargs["show_scalar_bar"] = False
        else:
            line_kwargs["color"] = self.line_color
        self._line_actor = self._plotter.add_mesh(self._polyline, **line_kwargs)
        # The shader cache is cold against the new actor — drop the
        # prerender flag so the GUI re-warms before the next play loop.
        self._prerender_built = False
        self._request_redraw()

    def set_color_by_progress(self, enabled: bool) -> None:
        """Toggle perceptually-uniform color shading along the trajectory.

        When enabled, the polyline is colored by a normalized "time" scalar
        (``[0, 1]`` along the trajectory) using the renderer's ``cmap``
        (default ``viridis``). When disabled, the polyline reverts to the
        flat ``line_color``. Safe to call before or after :meth:`attach`.

        Returns immediately if the scene hasn't been built yet — the change
        takes effect at the next ``attach`` / ``show``.
        """

        new_cmap: str | None = self.cmap if enabled else None
        # No-op if state already matches; we use a sentinel cached attribute
        # so the *first* call after attach with the same value still rebuilds
        # if the scene was constructed under a different setting.
        previous = getattr(self, "_color_by_progress_enabled", None)
        self._color_by_progress_enabled = bool(enabled)
        if previous == bool(enabled) and self._line_actor is not None:
            return

        if self._plotter is None or self._polyline is None:
            return
        # Rebuild only the line mesh — keep head actor and camera intact.
        try:
            self._plotter.remove_actor(self._line_actor, render=False)
        except (AttributeError, RuntimeError, TypeError):  # pragma: no cover
            pass
        # ``render_lines_as_tubes`` is OS-gated: on macOS we leave it off
        # by default because the VTK shader-template path crashes (see
        # ``render_lines_as_tubes_default`` for the full rationale).
        line_kwargs: dict[str, Any] = {
            "line_width": self._line_width,
            "render_lines_as_tubes": render_lines_as_tubes_default(),
        }
        if new_cmap is not None:
            line_kwargs["scalars"] = self.color_by
            line_kwargs["cmap"] = new_cmap
            line_kwargs["show_scalar_bar"] = False
        else:
            line_kwargs["color"] = self.line_color
        self._line_actor = self._plotter.add_mesh(self._polyline, **line_kwargs)
        # New actor — shader cache is cold; force a re-warm at the next
        # opportunity.
        self._prerender_built = False
        self._request_redraw()

    @property
    def head_position(self) -> np.ndarray:
        """Current world-space position of the head marker.

        When :meth:`seek_arc_length` has been called, this returns the
        exact lerped world position the head sphere was moved to (the
        arc-length-driven playback path). Otherwise — for callers using
        the legacy integer-frame :meth:`seek` / :meth:`step` API — it
        returns the last sample displayed by the polyline, which is the
        historical behavior the transport-scrubber tests pin in place.
        """

        if self._head_world_pos is not None:
            return np.asarray(self._head_world_pos, dtype=float).copy()
        n = int(np.clip(self._current_n, 2, self.points.shape[0]))
        return np.asarray(self.points[n - 1], dtype=float).copy()

    # ------------------------------------------------------------------ video

    def render_to_video(
        self,
        path: str | Path,
        *,
        fps: int = 30,
        duration_seconds: float | None = None,
        size: tuple[int, int] = (1280, 720),
        rotate: bool = True,
        progress: Callable[[int, int], None] | None = None,
        cancel: Callable[[], bool] | None = None,
        quality: int = 8,
        codec: str = "libx264",
    ) -> Path:
        """Render the trajectory to an MP4 file using ``imageio-ffmpeg``.

        Parameters
        ----------
        path:
            Output file path. The extension determines the container; ``.mp4``
            is the default and well-tested.
        fps:
            Frames per second.
        duration_seconds:
            If given, the animation is stretched/compressed to this duration.
            Otherwise, every sample of the trajectory becomes one frame (capped
            at :data:`MAX_VIDEO_SECONDS` of video to avoid accidental enormous
            renders).
        size:
            Window/render size in pixels.
        rotate:
            If True, slowly rotate the camera around the attractor for a more
            informative video.
        progress:
            Optional ``callable(frame_index, total_frames)`` invoked once per
            frame. Useful for driving a ``QProgressDialog`` from a worker
            thread.
        cancel:
            Optional ``callable() -> bool``. If it returns ``True`` between
            frames the render stops early; the partial file is left intact.
        quality, codec:
            Forwarded to ``imageio.get_writer``. The default ``libx264 / q=8``
            balances size and quality; bump ``quality`` to 10 for crisper
            output at the cost of file size.

        Returns
        -------
        Path
            The path the video was written to.
        """

        import pyvista as pv

        out_path = Path(path).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        n_total = self.points.shape[0]
        if duration_seconds is None:
            n_frames = min(n_total, fps * MAX_VIDEO_SECONDS)
        else:
            n_frames = max(2, int(round(duration_seconds * fps)))
        sample_indices = np.linspace(2, n_total, n_frames, dtype=int)

        # Use a *local* off-screen plotter so we don't clobber any plotter
        # the caller previously attached via .attach() / .show(). Save and
        # restore the instance state so the renderer is reusable.
        saved_plotter = self._plotter
        saved_owns = self._owns_plotter
        saved_polyline = self._polyline
        saved_line_actor = self._line_actor
        saved_head_sphere = self._head_sphere
        saved_head_actor = self._head_actor
        saved_current_n = self._current_n

        plotter = pv.Plotter(off_screen=True, window_size=list(size))
        # Reset scene-internal handles so _build_scene populates them fresh
        # against the new plotter, but our `saved_*` keep the originals.
        self._plotter = plotter
        self._owns_plotter = True
        self._polyline = None
        self._line_actor = None
        self._head_sphere = None
        self._head_actor = None
        self._current_n = self.points.shape[0]
        try:
            self._build_scene(plotter)
            plotter.show(auto_close=False, interactive=False)

            writer = _open_export_writer(
                out_path, fps=fps, quality=quality, codec=codec
            )
            try:
                radius = max(self._bbox_diag, 1.0)
                for i, n in enumerate(sample_indices):
                    if cancel is not None and cancel():
                        break
                    self._set_visible_points(int(n))
                    if rotate:
                        angle = 2.0 * np.pi * (i / max(1, n_frames - 1))
                        plotter.camera_position = _orbit_camera_position(
                            self._center, radius, angle
                        )
                    plotter.render()
                    frame = np.asarray(plotter.screenshot(return_img=True))
                    # PyVista returns RGBA or RGB; ffmpeg wants RGB.
                    if frame.ndim == 3 and frame.shape[2] == 4:
                        frame = frame[..., :3]
                    writer.append_data(frame)
                    if progress is not None:
                        progress(i + 1, n_frames)
            finally:
                writer.close()
        finally:
            try:
                plotter.close()
            except (AttributeError, RuntimeError):  # pragma: no cover
                pass
            # Restore previous plotter state so this renderer can be reused.
            self._plotter = saved_plotter
            self._owns_plotter = saved_owns
            self._polyline = saved_polyline
            self._line_actor = saved_line_actor
            self._head_sphere = saved_head_sphere
            self._head_actor = saved_head_actor
            self._current_n = saved_current_n

        return out_path

    def close(self) -> None:
        """Close the owned plotter, if any."""

        if self._plotter is not None and self._owns_plotter:
            try:
                self._plotter.close()
            except (AttributeError, RuntimeError):  # pragma: no cover
                pass
        self._plotter = None
