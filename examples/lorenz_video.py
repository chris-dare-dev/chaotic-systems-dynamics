"""Render a 10-second MP4 of the Lorenz attractor (no GUI).

Usage::

    python examples/lorenz_video.py [output_path.mp4]

If ``output_path`` is omitted, the video is written to ``./lorenz.mp4``.
This example does not require a display — it uses an off-screen plotter.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp

from chaotic_systems.visualization.renderer import Renderer3D


def _lorenz_rhs(t: float, y: np.ndarray, sigma: float, rho: float, beta: float) -> np.ndarray:
    x1, x2, x3 = y
    return np.array([sigma * (x2 - x1), x1 * (rho - x3) - x2, x1 * x2 - beta * x3])


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    out_path = Path(args[0]) if args else Path.cwd() / "lorenz.mp4"

    sigma, rho, beta = 10.0, 28.0, 8.0 / 3.0
    t_span = (0.0, 40.0)
    t_eval = np.linspace(*t_span, 8000)
    sol = solve_ivp(
        lambda t, y: _lorenz_rhs(t, y, sigma, rho, beta),
        t_span,
        np.array([1.0, 1.0, 1.0]),
        method="RK45",
        t_eval=t_eval,
        rtol=1e-7,
        atol=1e-9,
    )
    points = sol.y.T  # (N, 3)

    renderer = Renderer3D(points, title="Lorenz attractor", cmap="viridis")
    final = renderer.render_to_video(out_path, fps=30, duration_seconds=10.0)
    print(f"wrote {final}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
