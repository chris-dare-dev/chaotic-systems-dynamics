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

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from .contract import Trajectory, as_points

if TYPE_CHECKING:
    from pyvistaqt import QtInteractor

__all__ = ["Renderer3D"]


# Maximum length (in seconds) of an auto-duration video export. Pulled out so
# callers / tests can find and reason about it without grepping the body of
# `render_to_video`.
MAX_VIDEO_SECONDS = 60


def _full_polyline_connectivity(n: int) -> np.ndarray:
    """Return the VTK ``lines`` array for a single polyline of ``n`` points."""

    lines = np.empty(n + 1, dtype=np.int64)
    lines[0] = n
    lines[1:] = np.arange(n, dtype=np.int64)
    return lines


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
        n_points = self.points.shape[0]
        self._tail_index: int = n_points  # row index of the tail slot
        self._points_buffer: np.ndarray = np.empty((n_points + 1, 3), dtype=float)
        self._points_buffer[:n_points] = self.points
        self._points_buffer[n_points] = self.points[-1]
        self._scalar_buffer: np.ndarray = np.empty(n_points + 1, dtype=float)
        self._scalar_buffer[:n_points] = np.linspace(0.0, 1.0, n_points)
        self._scalar_buffer[n_points] = 1.0
        # Worst-case connectivity is [count, 0..n-1, tail] = n + 2 ints.
        # We re-bind a slice each frame so VTK only sees the active prefix.
        self._connectivity_buffer: np.ndarray = np.empty(
            n_points + 2, dtype=np.int64
        )

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

    # ------------------------------------------------------------------ setup

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

        n = self.points.shape[0]
        # Re-seed the tail and reset the connectivity-state cache. This
        # matters when a renderer is re-attached (e.g. an off-screen
        # video export reuses the instance and rebuilds the scene).
        self._points_buffer[:n] = self.points
        self._points_buffer[n] = self.points[-1]
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

        line_kwargs: dict[str, Any] = {
            "line_width": self._line_width,
            "render_lines_as_tubes": True,
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
        """Update the polyline to show only the first ``n`` points.

        We never re-add a mesh or rebuild the sphere — only the lines
        connectivity array on the PolyData and the head actor's position
        get touched. The connectivity slice is taken from a pre-allocated
        buffer so no numpy array is allocated per frame.

        Always reasserts the integer-prefix connectivity. The previous
        call may have set a fractional-tail connectivity via
        :meth:`seek_interpolated`; we need a pure-integer seek to drop
        that tail segment cleanly, so we can't short-circuit even when
        ``n`` already matches ``_current_n``.
        """

        n = int(np.clip(n, 2, self.points.shape[0]))
        self._current_n = n
        if self._polyline is not None:
            self._polyline.lines = self._make_integer_connectivity(n)
        if self._head_actor is not None:
            self._move_head_actor(self.points[n - 1])

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
        self._build_scene(self._plotter)

    def reset_camera(self) -> None:
        """Reset the camera to the default framing for this trajectory."""

        if self._plotter is not None:
            self._plotter.reset_camera()
            try:
                self._plotter.render()
            except (AttributeError, RuntimeError):  # pragma: no cover
                pass

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
        update_fn = (
            self._plotter.update
            if hasattr(self._plotter, "update")
            else self._plotter.render
        )
        n_total = self.points.shape[0]
        for n in range(2, n_total + 1, max(1, int(frame_step))):
            self._set_visible_points(n)
            update_fn()

    def _request_redraw(self) -> None:
        """Ask the attached plotter to repaint. Safe before initialization.

        We prefer ``plotter.update()`` (the recommended PyVista API for
        interactive plotters) but fall back to ``plotter.render()`` if the
        interactor hasn't been initialized yet — which happens when callers
        drive an off-screen plotter step-by-step before calling
        ``plotter.show()``.
        """

        if self._plotter is None:
            return
        update_fn: Callable[[], Any] | None = getattr(self._plotter, "update", None)
        render_fn: Callable[[], Any] | None = getattr(self._plotter, "render", None)
        if update_fn is not None:
            try:
                update_fn()
                return
            except RuntimeError:
                pass
        if render_fn is not None:
            try:
                render_fn()
            except (RuntimeError, AttributeError):  # pragma: no cover - defensive
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
        p0 = self.points[i]
        p1 = self.points[i + 1]
        head_pos = p0 + frac * (p1 - p0)
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
            # the cmap progression. ``i + 1`` indexes the scalar at the
            # next integer sample (``linspace(0,1,n)[i+1]``).
            scalar = self._scalar_buffer[i] + frac * (
                self._scalar_buffer[i + 1] - self._scalar_buffer[i]
            )
            poly_scalar = self._polyline.point_data[self.color_by]
            poly_scalar[self._tail_index] = scalar
            self._polyline.lines = self._make_fractional_connectivity(i)
        if self._head_actor is not None:
            self._move_head_actor(head_pos)
        self._request_redraw()

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

    def build_prerender_cache(
        self,
        *,
        progress_cb: Callable[[int, int], None] | None = None,
        cancel_cb: Callable[[], bool] | None = None,
    ) -> bool:
        """Build the arc-length table and warm VTK's render pipeline.

        Idempotent: returns immediately (with ``True``) if the cache is
        already in place. Otherwise the method does three things:

        1. Builds the cumulative arc-length table (mechanism (d) in the
           design doc — fast, always done, drives uniform visual speed).
        2. Calls :meth:`_set_visible_points` at the trajectory endpoints
           to ensure VTK has observed the full and empty polyline
           configurations (mechanism (a)).
        3. Calls :meth:`seek_arc_length` at five evenly spaced
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
        # Step 2 & 3 — VTK pipeline warm-up. Only meaningful when a
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

    def _invalidate_cache(self) -> None:
        """Drop the prerender cache.

        Called by every code path that materially changes the geometry
        the cache depends on (new trajectory attached, line-actor
        rebuilt, etc.). The arc-length table is dropped because a new
        trajectory will need a different one; the ``_prerender_built``
        flag is cleared so the GUI re-runs the warm-up. Calling this on
        an already-clean cache is a no-op.
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
        line_kwargs: dict[str, Any] = {
            "line_width": self._line_width,
            "render_lines_as_tubes": True,
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
        line_kwargs: dict[str, Any] = {
            "line_width": self._line_width,
            "render_lines_as_tubes": True,
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

        import imageio.v2 as imageio
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

            writer = imageio.get_writer(
                str(out_path),
                fps=fps,
                codec=codec,
                quality=quality,
                macro_block_size=1,
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
