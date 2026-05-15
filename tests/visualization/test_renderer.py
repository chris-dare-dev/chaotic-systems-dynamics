"""Tests for the 3D renderer.

The interactive ``show()`` path is not exercised here — we only test what can
run headlessly. The off-screen video render is run on a small trajectory to
verify the integration end-to-end without spending time on a long animation.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chaotic_systems.visualization.renderer import Renderer3D


@pytest.fixture()
def lorenz_points() -> np.ndarray:
    """A short Lorenz trajectory for testing."""

    from scipy.integrate import solve_ivp

    def rhs(t: float, y: np.ndarray) -> np.ndarray:
        return np.array(
            [
                10.0 * (y[1] - y[0]),
                y[0] * (28.0 - y[2]) - y[1],
                y[0] * y[1] - (8.0 / 3.0) * y[2],
            ]
        )

    sol = solve_ivp(
        rhs,
        (0.0, 2.0),
        [1.0, 1.0, 1.0],
        method="RK45",
        t_eval=np.linspace(0.0, 2.0, 200),
        rtol=1e-7,
        atol=1e-9,
    )
    return sol.y.T


def test_renderer_constructs(lorenz_points: np.ndarray) -> None:
    r = Renderer3D(lorenz_points)
    assert r.points.shape == lorenz_points.shape
    assert r.points.shape[1] == 3


def test_renderer_rejects_invalid_shape() -> None:
    with pytest.raises(ValueError):
        Renderer3D(np.zeros((5,)))


def test_renderer_video_export(tmp_path: Path, lorenz_points: np.ndarray) -> None:
    """End-to-end: render a tiny MP4 and verify the file exists & is non-empty."""

    pytest.importorskip("imageio_ffmpeg")
    pytest.importorskip("pyvista")

    out = tmp_path / "lorenz.mp4"
    r = Renderer3D(lorenz_points, cmap="viridis")
    written = r.render_to_video(out, fps=15, duration_seconds=1.0, size=(320, 240))
    assert written.exists()
    assert written.stat().st_size > 1024  # at least a kilobyte of video
