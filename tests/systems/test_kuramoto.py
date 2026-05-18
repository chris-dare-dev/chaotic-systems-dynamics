"""Kuramoto N-oscillator network tests (N4).

Reference observable
--------------------
**The synchronization transition.** With ``N = 20`` Lorentzian-distributed
natural frequencies (scale ``γ = 0.5`` → ``K_c = 2γ = 1.0``):

- Subcritical ``K = 0.1``: oscillators drift independently.
  Time-averaged ``|r|`` over the late 20% of a t = 100 run stays
  below ~0.4 (above the ``1/√N ≈ 0.22`` noise floor but well below
  the locked regime).
- Supercritical ``K = 5.0``: full phase-locking. Late-time
  ``|r| > 0.85``.

Plus deterministic / mathematical pins on ``order_parameter`` and
construction.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.core import Trajectory
from chaotic_systems.systems import Kuramoto
from chaotic_systems.systems.registry import get_system, list_system_names


def test_default_construction_has_canonical_n() -> None:
    sys = Kuramoto()
    assert sys.n == 10
    assert sys.state_dim == 10
    assert sys.initial_state.shape == (10,)
    assert sys.omega.shape == (10,)


def test_custom_n_and_seed_reproducible() -> None:
    """Same seed → same frequency vector; different seeds differ."""
    a = Kuramoto(n=16, freq_seed=7)
    b = Kuramoto(n=16, freq_seed=7)
    np.testing.assert_array_equal(a.omega, b.omega)
    c = Kuramoto(n=16, freq_seed=8)
    assert not np.array_equal(a.omega, c.omega)


def test_construction_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="n >= 2"):
        Kuramoto(n=1)
    with pytest.raises(ValueError, match="freq_scale"):
        Kuramoto(n=10, freq_scale=0.0)
    with pytest.raises(ValueError, match="freq_scale"):
        Kuramoto(n=10, freq_scale=-1.0)


def test_rhs_returns_finite_n_vector() -> None:
    sys = Kuramoto(n=12)
    out = sys.rhs(0.0, sys.initial_state)
    assert out.shape == (12,)
    assert np.isfinite(out).all()


def test_order_parameter_aligned_is_one() -> None:
    """All phases equal → |r| = 1, ψ = that phase."""
    theta = np.full(8, 0.7)
    r, psi = Kuramoto.order_parameter(theta)
    assert r == pytest.approx(1.0, abs=1e-12)
    assert psi == pytest.approx(0.7, abs=1e-12)


def test_order_parameter_uniformly_spaced_is_zero() -> None:
    """N phases evenly spaced on the circle → |r| = 0 by symmetry."""
    n = 12
    theta = np.linspace(0.0, 2 * np.pi, n, endpoint=False)
    r, _ = Kuramoto.order_parameter(theta)
    assert r == pytest.approx(0.0, abs=1e-12)


def test_order_parameter_two_oscillators_antiphase_is_zero() -> None:
    """θ_1 = 0, θ_2 = π gives perfect cancellation."""
    theta = np.array([0.0, np.pi])
    r, _ = Kuramoto.order_parameter(theta)
    assert r == pytest.approx(0.0, abs=1e-12)


def test_omega_property_returns_copy() -> None:
    """``omega`` mutation must not affect the system's internal state."""
    sys = Kuramoto(n=8, freq_seed=1)
    snapshot = sys.omega
    snapshot[0] = 1e9
    # Re-read; internal omega is unchanged.
    assert sys.omega[0] != 1e9


def test_simulate_returns_trajectory_with_metadata() -> None:
    sys = Kuramoto(n=8, freq_seed=3)
    traj = sys.simulate(
        (0.0, 5.0), n_points=20, integrator="DOP853"
    )
    assert isinstance(traj, Trajectory)
    assert traj.t.shape == (20,)
    assert traj.y.shape == (20, 8)
    assert traj.system == "Kuramoto"


def test_synchronization_transition_lorentzian() -> None:
    """The signature observable: subcritical K stays incoherent, super-
    critical K locks the population. Lorentzian freq with γ=0.5 gives
    K_c = 1.0; we test well below (0.1) and well above (5.0)."""
    sys = Kuramoto(n=20, freq_seed=42, freq_scale=0.5)

    sub = sys.simulate(
        (0.0, 100.0),
        params={"K": 0.1},
        n_points=200,
        integrator="DOP853",
    )
    r_sub = np.abs(np.exp(1j * sub.y).mean(axis=1))
    late_sub = float(r_sub[-40:].mean())
    assert late_sub < 0.4, (
        f"expected subcritical K=0.1 to stay incoherent (|r| < 0.4); "
        f"got late-time mean |r| = {late_sub:.4f}"
    )

    sup = sys.simulate(
        (0.0, 100.0),
        params={"K": 5.0},
        n_points=200,
        integrator="DOP853",
    )
    r_sup = np.abs(np.exp(1j * sup.y).mean(axis=1))
    late_sup = float(r_sup[-40:].mean())
    assert late_sup > 0.85, (
        f"expected supercritical K=5.0 to lock (|r| > 0.85); "
        f"got late-time mean |r| = {late_sup:.4f}"
    )


def test_at_zero_coupling_dynamics_are_uncoupled() -> None:
    """K=0 → dθ_i/dt = ω_i constant. Phase at time t is θ_i(0) + ω_i t,
    modulo wrapping. We compare to the closed-form rotation."""
    sys = Kuramoto(n=6, freq_seed=0)
    traj = sys.simulate(
        (0.0, 1.0), params={"K": 0.0}, n_points=2, integrator="DOP853"
    )
    expected = sys.initial_state + sys.omega * 1.0
    # No wrapping over the short integration time used here.
    np.testing.assert_allclose(traj.y[-1], expected, atol=1e-6)


def test_registered_in_systems_registry() -> None:
    names = list_system_names()
    assert "Kuramoto" in names
    instance = get_system("Kuramoto")
    assert isinstance(instance, Kuramoto)
    # Registry singleton uses defaults.
    assert instance.n == 10


def test_educational_notes_present() -> None:
    """E1 contract: every system carries notes citing a textbook author."""
    sys = Kuramoto()
    notes = sys.educational_notes
    assert "Kuramoto" in notes
    assert "Strogatz" in notes or "Acebrón" in notes
    assert len(notes) >= 150
