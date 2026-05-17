"""Tests for the ``DiscreteSystem`` abstraction.

These tests pin the contract that the concrete maps under
``tests/systems/test_*_map.py`` rely on: parameter merging, single-step
shape guards, iterate-trajectory shape, transient discarding, and the
``kind`` discriminator.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pytest

from chaotic_systems.core import DiscreteSystem, DynamicalSystem, Parameter, Trajectory
from chaotic_systems.core.base import FloatArray


class _Doubler(DiscreteSystem):
    """Simple deterministic map ``x -> 2 x + b`` on 1D."""

    name = "Doubler"
    latex = r"x_{n+1} = 2 x_n + b"
    state_dim = 1
    parameters = {"b": Parameter("b", 0.0, -10.0, 10.0)}
    default_initial_state = np.array([1.0], dtype=np.float64)

    def _step(self, y: FloatArray, params: Mapping[str, float]) -> FloatArray:
        return np.array([2.0 * y[0] + params["b"]], dtype=np.float64)


def test_kind_discriminator_is_map_on_discrete_and_ode_on_dynamical() -> None:
    """The whole point of the ``kind`` attribute: the GUI can switch on it."""
    assert _Doubler.kind == "map"
    assert _Doubler().kind == "map"
    # And the existing ODE base class advertises "ode".
    assert DynamicalSystem.kind == "ode"


def test_default_params_and_merged_params() -> None:
    sys = _Doubler()
    assert sys.default_params() == {"b": 0.0}
    assert sys.merged_params({"b": 3.5}) == {"b": 3.5}
    assert sys.merged_params(None) == {"b": 0.0}


def test_merged_params_rejects_unknown_key() -> None:
    sys = _Doubler()
    with pytest.raises(KeyError, match="Unknown parameter"):
        sys.merged_params({"bogus": 1.0})


def test_step_returns_finite_state_with_right_shape() -> None:
    sys = _Doubler()
    out = sys.step(np.array([2.0]))
    assert out.shape == (1,)
    assert out[0] == pytest.approx(4.0)


def test_step_shape_guard_catches_misbehaving_subclass() -> None:
    class _Broken(DiscreteSystem):
        name = "Broken"
        latex = ""
        state_dim = 2
        parameters: dict[str, Parameter] = {}
        default_initial_state = np.zeros(2)

        def _step(self, y, params):
            return np.zeros(3)  # wrong shape

    with pytest.raises(ValueError, match="expected"):
        _Broken().step(np.zeros(2))


def test_iterate_returns_n_steps_plus_one_samples() -> None:
    sys = _Doubler()
    traj = sys.iterate(5, y0=np.array([1.0]), params={"b": 0.0})
    assert isinstance(traj, Trajectory)
    assert traj.t.shape == (6,)
    assert traj.y.shape == (6, 1)
    # Doubling: 1, 2, 4, 8, 16, 32.
    np.testing.assert_allclose(traj.y[:, 0], np.array([1.0, 2.0, 4.0, 8.0, 16.0, 32.0]))
    assert traj.integrator == "map"
    assert traj.system == "Doubler"


def test_iterate_respects_transient_discard() -> None:
    """A 3-step transient on ``x -> 2x`` from x0=1 leaves us at 8."""
    sys = _Doubler()
    traj = sys.iterate(2, y0=np.array([1.0]), n_transient=3)
    # State recorded after burn-in is 8, then 16, 32.
    np.testing.assert_allclose(traj.y[:, 0], np.array([8.0, 16.0, 32.0]))


def test_iterate_validates_n_steps_and_transient() -> None:
    sys = _Doubler()
    with pytest.raises(ValueError, match="n_steps must be >= 1"):
        sys.iterate(0)
    with pytest.raises(ValueError, match="n_transient must be >= 0"):
        sys.iterate(5, n_transient=-1)


def test_iterate_validates_initial_state() -> None:
    sys = _Doubler()
    with pytest.raises(ValueError, match="expected"):
        sys.iterate(5, y0=np.zeros(3))
    with pytest.raises(ValueError, match="non-finite"):
        sys.iterate(5, y0=np.array([np.nan]))


def test_simulate_is_rejected_with_helpful_error() -> None:
    """A caller written for an ODE system should fail loudly, not silently."""
    sys = _Doubler()
    with pytest.raises(TypeError, match=r"discrete map.*iterate"):
        sys.simulate((0.0, 1.0))
