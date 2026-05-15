"""Tests for the visualization/contract adapter layer."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from chaotic_systems.visualization.contract import (
    Parameter,
    _coerce_parameter,
    as_points,
    default_params,
)


def test_as_points_passthrough_n3() -> None:
    pts = np.random.default_rng(0).normal(size=(50, 3))
    out = as_points(pts)
    assert out.shape == (50, 3)
    assert np.allclose(out, pts)


def test_as_points_transposes_3xn() -> None:
    pts = np.random.default_rng(1).normal(size=(3, 100))
    traj = SimpleNamespace(t=np.linspace(0, 1, 100), y=pts)
    out = as_points(traj)
    assert out.shape == (100, 3)
    assert np.allclose(out[:, 0], pts[0])


def test_as_points_projects_high_dim() -> None:
    pts = np.random.default_rng(2).normal(size=(40, 7))
    traj = SimpleNamespace(t=np.linspace(0, 1, 40), y=pts)
    out = as_points(traj)
    assert out.shape == (40, 3)
    assert np.allclose(out, pts[:, :3])


def test_as_points_pads_2d() -> None:
    pts = np.random.default_rng(3).normal(size=(20, 2))
    traj = SimpleNamespace(t=np.linspace(0, 1, 20), y=pts)
    out = as_points(traj)
    assert out.shape == (20, 3)
    assert np.allclose(out[:, 2], 0.0)


def test_coerce_parameter_from_namespace() -> None:
    raw = SimpleNamespace(default=1.5, min=0.0, max=3.0, description="x")
    p = _coerce_parameter("foo", raw)
    assert p == Parameter(name="foo", default=1.5, min=0.0, max=3.0, description="x")


def test_default_params_reads_defaults() -> None:
    class FakeSystem:
        parameters = {
            "a": Parameter("a", default=1.0, min=0.0, max=2.0),
            "b": SimpleNamespace(default=2.5, min=-1.0, max=10.0),
        }

    out = default_params(FakeSystem())  # type: ignore[arg-type]
    assert out == {"a": 1.0, "b": 2.5}
