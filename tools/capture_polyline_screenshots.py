"""Capture polyline screenshots at 25/50/75 % playback for iteration 4.

Renders three offscreen frames of the Lorenz trajectory at each of
two smoothness modes so the improvement can be inspected visually.

Output paths::

  /tmp/polyline_t1.png             SMOOTH @ 25%
  /tmp/polyline_t2.png             SMOOTH @ 50%
  /tmp/polyline_t3.png             SMOOTH @ 75%
  /tmp/polyline_t1_linear.png      LINEAR @ 25%
  /tmp/polyline_t2_linear.png      LINEAR @ 50%
  /tmp/polyline_t3_linear.png      LINEAR @ 75%

Each frame is rendered at 1280x720 with a fixed camera so the three
shots are easy to compare side-by-side.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
import pyvista as pv

from chaotic_systems.integrators import RK45
from chaotic_systems.systems.lorenz import Lorenz
from chaotic_systems.visualization.renderer import Renderer3D


def _simulate_lorenz(n_samples: int = 2400) -> np.ndarray:
    system = Lorenz()
    traj = RK45.integrate(
        system.rhs,
        (0.0, 40.0),
        np.array([1.0, 1.0, 1.0]),
        n_points=n_samples,
    )
    return np.asarray(traj.y, dtype=float)


def _capture_mode(points: np.ndarray, *, smooth_factor: int, suffix: str) -> None:
    plotter = pv.Plotter(off_screen=True, window_size=(1280, 720))
    r = Renderer3D(points, title=f"Lorenz iter 4 ({suffix or 'smooth'})")
    r.attach(plotter)
    r.build_prerender_cache(smooth_factor=smooth_factor)
    if r._smooth_points is not None:  # noqa: SLF001
        print(f"  smooth points: {r._smooth_points.shape}")  # noqa: SLF001
    else:
        print("  smooth points: (none — linear polyline)")
    plotter.reset_camera()

    total_arc = r.total_arc_length
    fractions = [0.25, 0.50, 0.75]
    for i, frac in enumerate(fractions, start=1):
        path = Path("/tmp") / f"polyline_t{i}{suffix}.png"
        r.seek_arc_length(frac * total_arc)
        plotter.render()
        frame = np.asarray(plotter.screenshot(return_img=True))
        if frame.ndim == 3 and frame.shape[2] == 4:
            frame = frame[..., :3]
        imageio.imwrite(str(path), frame)
        print(f"  wrote {path} at frac={frac}")

    plotter.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only", choices=("smooth", "linear", "both"), default="both"
    )
    args = parser.parse_args()

    points = _simulate_lorenz()
    print(f"Simulated {points.shape[0]} samples")

    if args.only in ("smooth", "both"):
        print("SMOOTH (Catmull-Rom 4x):")
        _capture_mode(points, smooth_factor=4, suffix="")
    if args.only in ("linear", "both"):
        print("LINEAR baseline:")
        _capture_mode(points, smooth_factor=1, suffix="_linear")


if __name__ == "__main__":
    main()
