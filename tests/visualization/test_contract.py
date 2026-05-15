"""Tests for the visualization/contract adapter layer."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from chaotic_systems.visualization.contract import (
    ParameterSpec,
    _coerce_parameter,
    as_points,
    default_params,
    get_system_safe,
    list_systems_safe,
)


def test_as_points_passthrough_n3() -> None:
    pts = np.random.default_rng(0).normal(size=(50, 3))
    out = as_points(pts)
    assert out.shape == (50, 3)
    assert np.allclose(out, pts)


def test_as_points_uses_state_dim_to_orient() -> None:
    """Use the trajectory's declared `state_dim` to pick the time axis."""

    pts = np.random.default_rng(1).normal(size=(3, 100))
    traj = SimpleNamespace(
        t=np.linspace(0, 1, 100), y=pts, state_dim=3
    )
    out = as_points(traj)
    assert out.shape == (100, 3)
    # Should have transposed so the first column is the original first row.
    assert np.allclose(out[:, 0], pts[0])


def test_as_points_short_state_dim4_trajectory_uses_state_dim() -> None:
    """A (3, 4) trajectory is 3 steps of 4D state -> orient correctly."""

    pts = np.random.default_rng(2).normal(size=(3, 4))
    traj = SimpleNamespace(t=np.linspace(0, 1, 3), y=pts, state_dim=4)
    out = as_points(traj)
    assert out.shape == (3, 3)
    # First three columns of pts (since state_dim==4 > 3).
    assert np.allclose(out, pts[:, :3])


def test_as_points_short_trajectory_using_t_length() -> None:
    """Without a `state_dim`, fall back to len(t) to pick the time axis."""

    pts = np.random.default_rng(3).normal(size=(2, 3))  # 2 steps, 3D state
    traj = SimpleNamespace(t=np.linspace(0, 1, 2), y=pts)
    out = as_points(traj)
    assert out.shape == (2, 3)
    assert np.allclose(out, pts)


def test_as_points_projects_high_dim_with_custom_projection() -> None:
    pts = np.random.default_rng(4).normal(size=(40, 4))
    traj = SimpleNamespace(t=np.linspace(0, 1, 40), y=pts, state_dim=4)
    out = as_points(traj, projection=(0, 1, 3))  # HenonHeiles: x, y, py
    assert out.shape == (40, 3)
    assert np.allclose(out[:, 0], pts[:, 0])
    assert np.allclose(out[:, 1], pts[:, 1])
    assert np.allclose(out[:, 2], pts[:, 3])


def test_as_points_pads_2d() -> None:
    pts = np.random.default_rng(5).normal(size=(20, 2))
    traj = SimpleNamespace(t=np.linspace(0, 1, 20), y=pts, state_dim=2)
    out = as_points(traj)
    assert out.shape == (20, 3)
    assert np.allclose(out[:, 2], 0.0)


def test_as_points_clips_trailing_non_finite_by_default() -> None:
    pts = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 1.0, 1.0],
            [2.0, 2.0, 2.0],
            [np.nan, np.nan, np.nan],
            [np.inf, 0.0, 0.0],
        ]
    )
    out = as_points(pts)
    # Trailing non-finite rows dropped.
    assert out.shape == (3, 3)
    assert np.isfinite(out).all()


def test_as_points_raises_on_non_finite_when_requested() -> None:
    pts = np.array([[0.0, 0.0, 0.0], [np.nan, 0.0, 0.0]])
    with pytest.raises(ValueError, match="non-finite"):
        as_points(pts, on_non_finite="raise")


def test_coerce_parameter_from_namespace() -> None:
    raw = SimpleNamespace(default=1.5, min=0.0, max=3.0, description="x")
    p = _coerce_parameter("foo", raw)
    assert p == ParameterSpec(
        name="foo", default=1.5, min=0.0, max=3.0, description="x"
    )


def test_default_params_reads_defaults() -> None:
    class FakeSystem:
        parameters = {
            "a": ParameterSpec("a", default=1.0, min=0.0, max=2.0),
            "b": SimpleNamespace(default=2.5, min=-1.0, max=10.0),
        }

    out = default_params(FakeSystem())  # type: ignore[arg-type]
    assert out == {"a": 1.0, "b": 2.5}


def test_list_systems_safe_returns_instances() -> None:
    """When the real registry is present, we get instances back."""

    systems = list_systems_safe()
    assert len(systems) >= 1
    # Every entry has `name` / `initial_state` / `rhs` / `simulate`.
    for s in systems:
        assert isinstance(getattr(s, "name", ""), str)
        assert isinstance(np.asarray(s.initial_state), np.ndarray)


def test_get_system_safe_returns_none_for_unknown() -> None:
    assert get_system_safe("not-a-real-system") is None


def test_get_system_safe_returns_singleton() -> None:
    a = get_system_safe("Lorenz")
    b = get_system_safe("Lorenz")
    assert a is not None and b is not None
    assert a is b
