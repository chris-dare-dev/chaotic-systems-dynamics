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
  point buffer of the trajectory, plus a ``time`` scalar for colormap
  shading. Animation updates the polyline's ``.lines`` connectivity
  (cheap — just an int array swap) instead of re-uploading point data
  every frame.
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

        # Cached bbox / center used by both head positioning and the
        # video-export camera orbit. Computed once because the trajectory
        # buffer never changes.
        self._bbox_diag: float = float(
            np.linalg.norm(self.points.max(axis=0) - self.points.min(axis=0))
        )
        self._center: np.ndarray = self.points.mean(axis=0)

    # ------------------------------------------------------------------ setup

    def _build_scene(self, plotter: Any) -> None:
        """Populate ``plotter`` with the trajectory line and head marker.

        Allocates a single ``pv.PolyData`` with the full point buffer and
        a single head sphere, both of which are mutated in place during
        animation.
        """

        import pyvista as pv

        n = self.points.shape[0]
        polyline = pv.PolyData(self.points.copy())
        polyline.lines = _full_polyline_connectivity(n)
        polyline.point_data[self.color_by] = np.linspace(0.0, 1.0, n)
        self._polyline = polyline

        line_kwargs: dict[str, Any] = {
            "line_width": 3.5,
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

    def _set_visible_points(self, n: int) -> None:
        """Update the polyline to show only the first ``n`` points.

        We never re-add a mesh or rebuild the sphere — only the lines
        connectivity array on the PolyData and the head actor's position
        get touched, both ``O(n)`` light operations.
        """

        n = int(np.clip(n, 2, self.points.shape[0]))
        if n == self._current_n and self._polyline is not None:
            return
        self._current_n = n
        if self._polyline is not None:
            self._polyline.lines = _full_polyline_connectivity(n)
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
            "line_width": 3.5,
            "render_lines_as_tubes": True,
        }
        if new_cmap is not None:
            line_kwargs["scalars"] = self.color_by
            line_kwargs["cmap"] = new_cmap
            line_kwargs["show_scalar_bar"] = False
        else:
            line_kwargs["color"] = self.line_color
        self._line_actor = self._plotter.add_mesh(self._polyline, **line_kwargs)
        self._request_redraw()

    @property
    def head_position(self) -> np.ndarray:
        """Current world-space position of the head marker.

        Returns the last sample displayed by the polyline, regardless of
        whether the head actor itself has been built yet.
        """

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
