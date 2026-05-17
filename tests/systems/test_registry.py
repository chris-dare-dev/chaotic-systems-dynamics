"""Registry round-trip — every registered system can be instantiated,
its RHS evaluated, and a short trajectory simulated. This is what the
GUI calls.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.core import DiscreteSystem, DynamicalSystem, Trajectory
from chaotic_systems.systems import (
    get_any_system,
    get_map,
    get_system,
    list_all_systems,
    list_map_names,
    list_maps,
    list_system_names,
    list_systems,
)


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


# --- Discrete maps -------------------------------------------------------


def test_list_systems_excludes_maps() -> None:
    """``list_systems`` is the ODE-only surface; maps are reachable via
    ``list_maps`` instead. This preserves the existing contract that
    every entry passes ``isinstance(x, DynamicalSystem)``."""
    ode_names = set(list_system_names())
    map_names = set(list_map_names())
    assert ode_names.isdisjoint(map_names)


def test_list_maps_returns_discrete_instances_in_stable_order() -> None:
    maps = list_maps()
    assert all(isinstance(m, DiscreteSystem) for m in maps)
    assert all(m.kind == "map" for m in maps)
    names = [m.name for m in maps]
    assert names == list_map_names()
    # All four canonical maps from proposal N1 must be present.
    for expected in ("Logistic", "HenonMap", "Ikeda", "StandardMap"):
        assert expected in names


def test_get_map_returns_registry_singleton() -> None:
    a = get_map("Logistic")
    b = get_map("Logistic")
    assert a is b


def test_get_map_unknown() -> None:
    with pytest.raises(KeyError, match="unknown map"):
        get_map("does-not-exist")


@pytest.mark.parametrize("name", list_map_names())
def test_each_map_iterates_a_short_trajectory(name: str) -> None:
    m = get_map(name)
    assert isinstance(m, DiscreteSystem)
    assert m.name == name
    assert m.kind == "map"
    assert m.state_dim == m.initial_state.shape[0]
    # Sanity-check the LaTeX representation.
    assert isinstance(m.latex, str)
    assert len(m.latex) > 0
    # Single-step output has the right shape.
    f0 = m.step(m.initial_state)
    assert f0.shape == (m.state_dim,)
    # Short iterate trajectory.
    traj = m.iterate(n_steps=20)
    assert isinstance(traj, Trajectory)
    assert traj.t.shape == (21,)
    assert traj.y.shape == (21, m.state_dim)
    assert np.isfinite(traj.y).all()
    assert traj.system == name
    assert traj.integrator == "map"


def test_list_all_systems_is_the_union_with_kind_discriminators() -> None:
    all_entries = list_all_systems()
    ode_count = len(list_systems())
    map_count = len(list_maps())
    assert len(all_entries) == ode_count + map_count
    kinds = [e.kind for e in all_entries]
    # ODE flows first, then maps — order matches the registry.
    assert kinds[:ode_count] == ["ode"] * ode_count
    assert kinds[ode_count:] == ["map"] * map_count


def test_get_any_system_resolves_both_kinds() -> None:
    ode = get_any_system("Lorenz")
    mp = get_any_system("Logistic")
    assert isinstance(ode, DynamicalSystem)
    assert isinstance(mp, DiscreteSystem)


def test_get_any_system_unknown() -> None:
    with pytest.raises(KeyError, match="unknown system or map"):
        get_any_system("does-not-exist")
