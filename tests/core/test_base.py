"""Unit tests for the core base classes."""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.core import DynamicalSystem, Parameter, Trajectory


def test_parameter_validates_default_within_range() -> None:
    Parameter("g", 9.81, 0.0, 25.0)  # ok

    with pytest.raises(ValueError, match="default=11.0 not in"):
        Parameter("p", 11.0, 0.0, 10.0)


def test_trajectory_shape_checks() -> None:
    t = np.linspace(0, 1, 11)
    y = np.zeros((11, 3))
    traj = Trajectory(t=t, y=y, system="test", integrator="RK45")
    assert traj.state_dim == 3
    assert traj.n_steps == 11
    assert traj.duration == pytest.approx(1.0)

    # Wrong N
    with pytest.raises(ValueError, match="disagree on N"):
        Trajectory(t=t, y=np.zeros((10, 3)))
    # Wrong t ndim
    with pytest.raises(ValueError, match="t must be 1-D"):
        Trajectory(t=np.zeros((11, 1)), y=y)


class _Linear(DynamicalSystem):
    """y_dot = A y for a simple constant matrix."""

    name = "Linear"
    latex = r"\dot y = A y"
    state_dim = 2
    parameters = {"omega": Parameter("omega", 1.0, 0.0, 10.0)}
    default_initial_state = np.array([1.0, 0.0], dtype=np.float64)

    def _rhs(self, t, y, params):
        w = params["omega"]
        return np.array([y[1], -w * w * y[0]], dtype=np.float64)


def test_dynamical_system_simulate_basic() -> None:
    sys = _Linear()
    traj = sys.simulate((0.0, 1.0), n_points=11, integrator="RK45")
    assert traj.system == "Linear"
    assert traj.params == {"omega": 1.0}
    assert traj.integrator == "RK45"
    assert traj.y.shape == (11, 2)
    # Cos(t) within tight tolerance for harmonic oscillator with omega=1.
    np.testing.assert_allclose(traj.y[:, 0], np.cos(traj.t), atol=1e-6)


def test_dynamical_system_rejects_unknown_param() -> None:
    sys = _Linear()
    with pytest.raises(KeyError, match="Unknown parameter"):
        sys.rhs(0.0, sys.initial_state, bogus=3.0)


def test_dynamical_system_rhs_shape_guard() -> None:
    """Subclasses returning wrong-shape arrays must error explicitly."""

    class _Broken(DynamicalSystem):
        name = "Broken"
        latex = ""
        state_dim = 3
        parameters: dict[str, Parameter] = {}
        default_initial_state = np.zeros(3)

        def _rhs(self, t, y, params):  # noqa: D401 - test stub
            return np.zeros(2)  # wrong shape

    with pytest.raises(ValueError, match="expected"):
        _Broken().rhs(0.0, np.zeros(3))
