"""Tests for the 3D renderer.

The interactive ``show()`` path is not exercised here — we only test what can
run headlessly. The off-screen video render is run on a small trajectory to
verify the integration end-to-end without spending time on a long animation.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

from chaotic_systems.visualization.renderer import (
    Renderer3D,
    render_lines_as_tubes_default,
)


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


# --- render_lines_as_tubes_default --------------------------------------
#
# Background: on macOS 26+ the VTK polydata mapper crashes inside
# ``vtkOpenGLPolyDataMapper::UpdateShaders`` when tube rendering is
# combined with scalar-colored lines (our viridis-colored trajectory).
# Tubes are off by default on darwin to dodge that path. These tests
# pin the helper's contract.

def test_tubes_default_off_on_darwin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHAOTIC_RENDER_TUBES", raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    assert render_lines_as_tubes_default() is False


def test_tubes_default_on_for_non_darwin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHAOTIC_RENDER_TUBES", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    assert render_lines_as_tubes_default() is True


@pytest.mark.parametrize("on_value", ["1", "true", "TRUE", "yes", "on"])
def test_tubes_env_force_on(monkeypatch: pytest.MonkeyPatch, on_value: str) -> None:
    """Even on macOS, the env override forces tubes on."""

    monkeypatch.setenv("CHAOTIC_RENDER_TUBES", on_value)
    monkeypatch.setattr(sys, "platform", "darwin")
    assert render_lines_as_tubes_default() is True


@pytest.mark.parametrize("off_value", ["0", "false", "FALSE", "no", "off"])
def test_tubes_env_force_off(monkeypatch: pytest.MonkeyPatch, off_value: str) -> None:
    """Even on non-macOS, the env override turns tubes off."""

    monkeypatch.setenv("CHAOTIC_RENDER_TUBES", off_value)
    monkeypatch.setattr(sys, "platform", "linux")
    assert render_lines_as_tubes_default() is False


def test_tubes_env_unknown_value_falls_back_to_os_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A typo in CHAOTIC_RENDER_TUBES should not silently flip the
    behavior — fall back to the OS default rather than guessing."""

    monkeypatch.setenv("CHAOTIC_RENDER_TUBES", "maybe")
    monkeypatch.setattr(sys, "platform", "darwin")
    assert render_lines_as_tubes_default() is False
    monkeypatch.setattr(sys, "platform", "linux")
    assert render_lines_as_tubes_default() is True
