"""4D Rössler hyperchaos tests.

The defining property of this system is **two positive Lyapunov
exponents** — the ``(+, +, 0, -)`` signature. We pin:

- The RHS at the canonical IC returns finite values with the right shape.
- The Lyapunov spectrum at canonical parameters has exactly two
  positive exponents (within a 1e-2 zero-tolerance band — Stankevich
  & Wilczak 2015 report λ_2 ≈ 0.019, low but well-resolved by the
  Benettin estimator).
- The system is registered and resolves through the registry.

The Lyapunov compute is slow (~10 s); marked accordingly. Run with
``pytest tests/systems/test_rossler_hyper.py -k spectrum`` to skip
the fast tests, or ``-m "not slow"`` to skip the spectrum one.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.core.lyapunov import lyapunov_spectrum
from chaotic_systems.systems import RosslerHyper
from chaotic_systems.systems.registry import get_system, list_systems


def test_rhs_returns_finite_4vector_at_default_ic() -> None:
    sys = RosslerHyper()
    y0 = np.asarray(sys.initial_state, dtype=float)
    assert y0.shape == (4,)
    out = sys.rhs(0.0, y0)
    assert out.shape == (4,)
    assert np.isfinite(out).all()


def test_default_parameters_are_canonical() -> None:
    """Defaults match Rössler 1979 / Stankevich & Wilczak 2015."""
    sys = RosslerHyper()
    assert sys.parameters["a"].default == pytest.approx(0.25)
    assert sys.parameters["b"].default == pytest.approx(3.0)
    assert sys.parameters["c"].default == pytest.approx(0.5)
    assert sys.parameters["d"].default == pytest.approx(0.05)


def test_state_dim_is_4() -> None:
    sys = RosslerHyper()
    assert sys.state_dim == 4


def test_short_simulation_stays_bounded() -> None:
    """The attractor is bounded; a 50-time-unit run shouldn't blow up."""
    sys = RosslerHyper()
    traj = sys.simulate(
        (0.0, 50.0), n_points=200, integrator="DOP853", rtol=1e-9, atol=1e-12
    )
    assert traj.y.shape == (200, 4)
    # All visited points stay within a reasonable bounding box.
    assert np.isfinite(traj.y).all()
    assert np.abs(traj.y).max() < 1000.0  # generous bound


def test_registered_in_systems_registry() -> None:
    """The new system shows up in the GUI's source-of-truth registry."""
    names = [s.name for s in list_systems()]
    assert "RosslerHyper" in names
    instance = get_system("RosslerHyper")
    assert instance is not None
    assert instance.state_dim == 4


@pytest.mark.slow
def test_spectrum_has_two_positive_exponents() -> None:
    """The (+, +, 0, -) signature — the defining hyperchaos feature.

    This is the proof that the system is what its docstring claims.
    Tolerance: |lambda| > 1e-2 counts as "positive" — matches the
    GUI's classifier and is loose enough that the slowly-converging
    second exponent (Stankevich & Wilczak report λ_2 ≈ 0.019) still
    registers reliably.
    """
    sys = RosslerHyper()
    # t_total bumped past the default 500 so λ_2 has time to converge.
    spectrum = lyapunov_spectrum(
        sys, t_transient=100.0, t_total=1500.0, dt=1.0
    )
    sorted_desc = np.sort(np.asarray(spectrum, dtype=float))[::-1]
    n_positive = int(np.sum(sorted_desc > 1e-2))
    assert n_positive == 2, (
        f"expected 2 positive exponents (hyperchaos); got "
        f"{n_positive} from spectrum {sorted_desc!r}"
    )
    # And the dissipation sum is strongly negative (volume contracts).
    assert sorted_desc.sum() < -10.0, (
        f"expected strongly negative sum (volume contraction); "
        f"got sum={sorted_desc.sum():.4f}"
    )
