"""Registry round-trip — every registered system can be instantiated,
its RHS evaluated, and a short trajectory simulated. This is what the
GUI calls.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.core import DynamicalSystem, Trajectory
from chaotic_systems.systems import get_system, list_system_names, list_systems


def test_list_systems_returns_instances_in_stable_order() -> None:
    instances = list_systems()
    # Should hand back instances (not classes) so downstream callers can
    # read `.initial_state`, `.parameters`, etc. directly.
    assert all(isinstance(s, DynamicalSystem) for s in instances)
    names = [s.name for s in instances]
    assert names == list_system_names()
    # The Lorenz attractor should be first — it's the public face of the project.
    assert names[0] == "Lorenz"
    assert "DoublePendulum" in names
    assert "HenonHeiles" in names


def test_get_system_returns_registry_singleton() -> None:
    """``get_system(name)`` returns the same instance every call."""
    a = get_system("Lorenz")
    b = get_system("Lorenz")
    assert a is b


@pytest.mark.parametrize("name", list_system_names())
def test_each_system_runs_short_simulation(name: str) -> None:
    sys = get_system(name)
    assert isinstance(sys, DynamicalSystem)
    assert sys.name == name
    assert sys.state_dim == sys.initial_state.shape[0]
    # Sanity-check the LaTeX representation.
    assert isinstance(sys.latex, str)
    assert len(sys.latex) > 0
    # rhs returns the right shape.
    f0 = sys.rhs(0.0, sys.initial_state)
    assert f0.shape == (sys.state_dim,)
    # Simulate a tiny bit.
    traj = sys.simulate((0.0, 0.5), n_points=20, integrator="DOP853")
    assert isinstance(traj, Trajectory)
    assert traj.t.shape == (20,)
    assert traj.y.shape == (20, sys.state_dim)
    assert np.isfinite(traj.y).all()
    assert traj.system == name


def test_get_system_unknown() -> None:
    with pytest.raises(KeyError, match="unknown system"):
        get_system("does-not-exist")
