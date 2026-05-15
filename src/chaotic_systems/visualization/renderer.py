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
- We keep a single ``pv.PolyData`` line for the trajectory and update its
  point count via ``n_points``. This is the cheapest way to animate progressive
  reveal of a polyline in VTK.
- We keep an additional small sphere (or arrow) for the leading "head" so the
  current state is visible.
- For off-screen video, we drive the plotter manually frame-by-frame and feed
  each rendered frame into an ``imageio`` ffmpeg writer. This avoids depending
  on PyVista's own movie API, which has historically been fragile across
  vtk versions.

The renderer never imports PySide6 at module load — it only does so when the
caller actually asks for Qt integration. That keeps headless contexts (CI,
batch video) lightweight.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from .contract import Trajectory, as_points

if TYPE_CHECKING:
    import pyvista as pv
    from pyvistaqt import QtInteractor

__all__ = ["Renderer3D"]


def _make_polyline(points: np.ndarray) -> "pv.PolyData":
    """Construct a single-line PolyData from a ``(N, 3)`` array."""

    import pyvista as pv

    n = points.shape[0]
    if n < 2:
        # PyVista needs at least two points; pad by repeating the first.
        points = np.vstack([points, points[-1:]] if n == 1 else [np.zeros((2, 3))])
        n = points.shape[0]
    lines = np.empty(n + 1, dtype=np.int64)
    lines[0] = n
    lines[1:] = np.arange(n, dtype=np.int64)
    pdata = pv.PolyData(points)
    pdata.lines = lines
    return pdata


class Renderer3D:
    """3D renderer for a single trajectory.

    Parameters
    ----------
    trajectory:
        Either an ``(N, 3)`` ndarray of points or any object exposing ``.t``
        and ``.y`` attributes (the math agent's ``Trajectory`` shape).
        Higher-dimensional states are projected to the first three components
        by :func:`chaotic_systems.visualization.contract.as_points`.
    title:
        Window title for the interactive viewer.
    line_color:
        Color of the trajectory polyline.
    head_color:
        Color of the moving head marker.
    background:
        Background color of the 3D scene.
    cmap:
        Optional colormap name. If set, the polyline is colored by an index
        scalar (i.e. by time order along the trajectory).
    """

    def __init__(
        self,
        trajectory: Trajectory | np.ndarray,
        *,
        title: str = "chaotic-systems-dynamics",
        line_color: str = "#1f77b4",
        head_color: str = "#d62728",
        background: str = "white",
        cmap: str | None = "viridis",
    ) -> None:
        self.points: np.ndarray = as_points(trajectory)
        if self.points.ndim != 2 or self.points.shape[1] != 3:
            raise ValueError(
                f"trajectory must be coerceable to (N, 3); got {self.points.shape!r}"
            )
        self.title = title
        self.line_color = line_color
        self.head_color = head_color
        self.background = background
        self.cmap = cmap

        # These are populated lazily when a plotter is attached / created.
        self._plotter: Any = None
        self._polyline: Any = None
        self._line_actor: Any = None
        self._head_actor: Any = None
        self._owns_plotter: bool = False
        self._current_n: int = self.points.shape[0]

    # ------------------------------------------------------------------ setup

    def _build_scene(self, plotter: Any) -> None:
        """Populate ``plotter`` with the trajectory line and head marker."""

        import pyvista as pv

        polyline = _make_polyline(self.points)
        # A "time" scalar runs 0..1 so the cmap reveals the order of integration.
        n = self.points.shape[0]
        polyline.point_data["time"] = np.linspace(0.0, 1.0, n)
        self._polyline = polyline

        line_kwargs: dict[str, Any] = {
            "line_width": 2.0,
            "render_lines_as_tubes": False,
        }
        if self.cmap is not None:
            line_kwargs["scalars"] = "time"
            line_kwargs["cmap"] = self.cmap
            line_kwargs["show_scalar_bar"] = False
        else:
            line_kwargs["color"] = self.line_color

        self._line_actor = plotter.add_mesh(polyline, **line_kwargs)

        head_pos = self.points[-1]
        bbox = self.points.max(axis=0) - self.points.min(axis=0)
        radius = float(np.linalg.norm(bbox)) * 0.01 if np.any(bbox) else 0.05
        head_sphere = pv.Sphere(radius=max(radius, 1e-3), center=head_pos)
        self._head_actor = plotter.add_mesh(head_sphere, color=self.head_color)

        plotter.set_background(self.background)
        try:
            plotter.show_axes()
        except Exception:
            pass
        plotter.reset_camera()

    def _set_visible_points(self, n: int) -> None:
        """Update the plotter to show only the first ``n`` points of the trajectory."""

        import pyvista as pv

        n = int(np.clip(n, 2, self.points.shape[0]))
        if n == self._current_n and self._polyline is not None:
            return
        self._current_n = n
        pts = self.points[:n]
        new_line = _make_polyline(pts)
        new_line.point_data["time"] = np.linspace(0.0, 1.0, n)
        # Replace the underlying data in place (cheaper than re-adding the actor).
        if self._polyline is not None:
            self._polyline.points = new_line.points
            self._polyline.lines = new_line.lines
            self._polyline.point_data["time"] = new_line.point_data["time"]
        # Move the head.
        if self._head_actor is not None and self._plotter is not None:
            head_pos = pts[-1]
            self._plotter.remove_actor(self._head_actor)
            bbox = self.points.max(axis=0) - self.points.min(axis=0)
            radius = float(np.linalg.norm(bbox)) * 0.01 if np.any(bbox) else 0.05
            head_sphere = pv.Sphere(radius=max(radius, 1e-3), center=head_pos)
            self._head_actor = self._plotter.add_mesh(head_sphere, color=self.head_color)

    # ------------------------------------------------------------------ public

    def attach(self, qt_interactor: "QtInteractor") -> None:
        """Attach this renderer to an existing ``pyvistaqt.QtInteractor``.

        Use this when embedding the renderer in a Qt window. The renderer
        does not own the plotter in this case; the caller is responsible for
        teardown.
        """

        self._plotter = qt_interactor
        self._owns_plotter = False
        self._build_scene(self._plotter)

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
        n_total = self.points.shape[0]
        for n in range(2, n_total + 1, max(1, int(frame_step))):
            self._set_visible_points(n)
            try:
                self._plotter.update()
            except Exception:
                # Some plotter backends use ``render()`` instead.
                self._plotter.render()

    def step(self, n_visible: int) -> None:
        """Show the first ``n_visible`` samples (clamped). Returns immediately.

        Convenient for driving the animation from an external ``QTimer``.
        """

        self._set_visible_points(n_visible)
        if self._plotter is not None:
            try:
                self._plotter.update()
            except Exception:
                self._plotter.render()

    # ------------------------------------------------------------------ video

    def render_to_video(
        self,
        path: str | Path,
        *,
        fps: int = 30,
        duration_seconds: float | None = None,
        size: tuple[int, int] = (1280, 720),
        rotate: bool = True,
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
            at 60 seconds of video to avoid accidental enormous renders).
        size:
            Window/render size in pixels.
        rotate:
            If True, slowly rotate the camera around the attractor for a more
            informative video.

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
            n_frames = min(n_total, fps * 60)
        else:
            n_frames = max(2, int(round(duration_seconds * fps)))
        sample_indices = np.linspace(2, n_total, n_frames, dtype=int)

        # Use an off-screen plotter regardless of whether we have a display.
        plotter = pv.Plotter(off_screen=True, window_size=list(size))
        self._plotter = plotter
        self._owns_plotter = True
        self._build_scene(plotter)
        plotter.show(auto_close=False, interactive=False)

        # imageio with the ffmpeg plugin handles MP4 nicely.
        writer = imageio.get_writer(
            str(out_path),
            fps=fps,
            codec="libx264",
            quality=8,
            macro_block_size=1,
        )
        try:
            center = self.points.mean(axis=0)
            radius = float(np.linalg.norm(self.points.max(axis=0) - self.points.min(axis=0)))
            radius = max(radius, 1.0)
            for i, n in enumerate(sample_indices):
                self._set_visible_points(int(n))
                if rotate:
                    angle = 2.0 * np.pi * (i / max(1, n_frames - 1))
                    cam_pos = (
                        center[0] + radius * np.cos(angle),
                        center[1] + radius * np.sin(angle),
                        center[2] + radius * 0.5,
                    )
                    plotter.camera_position = [
                        cam_pos,
                        tuple(center),
                        (0.0, 0.0, 1.0),
                    ]
                plotter.render()
                frame = np.asarray(plotter.screenshot(return_img=True))
                # PyVista returns RGBA or RGB; ffmpeg wants RGB.
                if frame.ndim == 3 and frame.shape[2] == 4:
                    frame = frame[..., :3]
                writer.append_data(frame)
        finally:
            writer.close()
            try:
                plotter.close()
            except Exception:
                pass

        return out_path

    def close(self) -> None:
        """Close the owned plotter, if any."""

        if self._plotter is not None and self._owns_plotter:
            try:
                self._plotter.close()
            except Exception:
                pass
        self._plotter = None
