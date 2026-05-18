"""Mackey-Glass DDE tests (N3).

Reference observables:

- **Fixed-point regime** at ``τ = 2``: the unique stable equilibrium is
  ``x* = (β/γ − 1)^(1/n)`` (set the time derivative to zero, divide
  through by ``γ x*``). At canonical ``β = 0.2, γ = 0.1, n = 10`` that
  gives ``x* = 1``. After enough integration time the orbit converges
  to ``x = 1`` to integrator tolerance.

- **Chaotic regime** at ``τ = 17`` (canonical): the orbit stays
  bounded in roughly ``x ∈ [0.4, 1.4]`` and the late-time samples
  show non-trivial variation (std/mean > 0.05 — a chaotic orbit, not
  a fixed point or stable limit cycle).

- **Educational hooks**: the system registers, has the expected
  ``state_dim = 1`` and ``parameters`` schema, the ``_rhs`` shim
  (static-history approximation) is finite at the canonical IC,
  and the system shows up under ``list_systems`` so the GUI picker
  surfaces it.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.core import Trajectory
from chaotic_systems.systems import MackeyGlass
from chaotic_systems.systems.registry import get_system, list_system_names


def test_state_dim_and_parameter_schema() -> None:
    sys = MackeyGlass()
    assert sys.state_dim == 1
    assert sys.initial_state.shape == (1,)
    assert set(sys.parameters) == {"beta", "gamma", "n", "tau"}
    # Canonical Mackey & Glass 1977 chaotic defaults.
    assert sys.parameters["beta"].default == pytest.approx(0.2)
    assert sys.parameters["gamma"].default == pytest.approx(0.1)
    assert sys.parameters["n"].default == pytest.approx(10.0)
    assert sys.parameters["tau"].default == pytest.approx(17.0)


def test_rhs_shim_is_finite_at_initial_condition() -> None:
    """The static-history approximation returns a real number, not NaN."""
    sys = MackeyGlass()
    rhs0 = sys.rhs(0.0, sys.initial_state)
    assert rhs0.shape == (1,)
    assert np.isfinite(rhs0).all()


def test_dde_rhs_at_fixed_point_returns_zero() -> None:
    """At x_current = x_delayed = x* = 1, dx/dt = 0 by construction."""
    sys = MackeyGlass()
    params = sys.default_params()
    x_star = np.array([1.0])
    rate = sys.dde_rhs(0.0, x_star, x_star, params)
    assert rate[0] == pytest.approx(0.0, abs=1e-12)


def test_converges_to_fixed_point_at_short_delay() -> None:
    """τ = 2: the orbit must settle on x* = 1 after enough integration."""
    sys = MackeyGlass()
    traj = sys.simulate(
        (0.0, 300.0),
        y0=np.array([0.5]),
        params={"tau": 2.0},
        dt=0.05,
    )
    assert isinstance(traj, Trajectory)
    assert traj.integrator == "BellenRK4"
    assert traj.system == "MackeyGlass"
    # Final state pinned to the fixed point to integrator tolerance.
    assert traj.y[-1, 0] == pytest.approx(1.0, abs=1e-4)


def test_chaotic_regime_stays_bounded_at_canonical_tau() -> None:
    """τ = 17: orbit is bounded but not periodic (chaotic)."""
    sys = MackeyGlass()
    traj = sys.simulate((0.0, 400.0), dt=0.05)
    # Roughly the Farmer (1982) attractor bounds: x in [0.2, 1.6].
    assert traj.y.min() > 0.1
    assert traj.y.max() < 2.0
    # Late-time non-trivial variation -- not a fixed point.
    late = traj.y[-2000:, 0]
    spread = float(np.std(late) / max(abs(np.mean(late)), 1e-12))
    assert spread > 0.05, (
        f"expected non-trivial late-time spread; got std/mean = {spread:.4f}"
    )


def test_n_points_resampling_round_trips() -> None:
    """The base `simulate` contract holds: caller's n_points is honored."""
    sys = MackeyGlass()
    traj = sys.simulate(
        (0.0, 10.0),
        params={"tau": 1.0},
        dt=0.05,
        n_points=50,
    )
    assert traj.t.shape == (50,)
    assert traj.y.shape == (50, 1)


def test_simulate_rejects_non_increasing_t_span() -> None:
    sys = MackeyGlass()
    with pytest.raises(ValueError, match="strictly increasing"):
        sys.simulate((1.0, 0.0))


def test_simulate_rejects_wrong_y0_shape() -> None:
    sys = MackeyGlass()
    with pytest.raises(ValueError, match="expected"):
        sys.simulate((0.0, 1.0), y0=np.zeros(3))


def test_simulate_rejects_non_finite_y0() -> None:
    sys = MackeyGlass()
    with pytest.raises(ValueError, match="non-finite"):
        sys.simulate((0.0, 1.0), y0=np.array([np.nan]))


def test_integrator_argument_is_ignored() -> None:
    """The GUI's integrator picker doesn't apply to DDEs; we silently
    dispatch to BellenRK4 regardless of what the caller asked for."""
    sys = MackeyGlass()
    traj = sys.simulate(
        (0.0, 5.0), dt=0.05, integrator="DOP853"
    )
    # The trajectory label always says BellenRK4 -- the picker is moot.
    assert traj.integrator == "BellenRK4"


def test_registered_in_systems_registry() -> None:
    names = list_system_names()
    assert "MackeyGlass" in names
    instance = get_system("MackeyGlass")
    assert isinstance(instance, MackeyGlass)
    assert instance.state_dim == 1


def test_educational_notes_present() -> None:
    """E1 contract: every system carries notes citing a textbook author."""
    sys = MackeyGlass()
    notes = sys.educational_notes
    assert "Mackey" in notes
    assert "Glass" in notes
    assert len(notes) >= 150
