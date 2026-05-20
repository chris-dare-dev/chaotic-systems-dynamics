"""Tests for the Gottwald-Melbourne 0-1 test for chaos (CSC-011).

The test returns ``K in [0, 1]``: close to 0 for regular dynamics,
close to 1 for chaos. Pinned against:

- A pure sine wave (periodic) — ``K`` should be very near 0.
- IID Gaussian noise (random walk in the auxiliary ``(p_c, q_c)``
  variables) — ``K`` should be very near 1.
- A Lorenz x-projection at the canonical IC, sampled at ``dt = 1`` to
  match the system's natural orbital period — ``K`` should be > 0.95.
- A constant signal (zero-variance) — ``K`` should be exactly 0 by
  the degenerate-case branch in :func:`_pearson_corr`.
- Edge cases: too-short input, malformed ``c_range``, ``n_cut`` out
  of range.

The numerical observable matches the synthesis CSC-011 acceptance
criterion: "K → 1 for Lorenz (chaotic), K → 0 for SHO (regular)".

References for the canonical observables
----------------------------------------
- G. A. Gottwald, I. Melbourne, *On the Implementation of the 0-1
  Test for Chaos*, SIAM J. Appl. Dyn. Sys. 8 (2009), 129-145.
  DOI: 10.1137/080718851. arXiv:0906.1418.
- Lorenz at the canonical IC ``(1, 1, 1)`` with sigma=10, rho=28,
  beta=8/3 has largest Lyapunov ~0.9056 (Sprott, *Chaos and
  Time-Series Analysis*, Oxford 2003, Table 5.1). The 0-1 test
  is a different statistic but both diagnose the regime.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from chaotic_systems.core import chaos_zero_one_test
from chaotic_systems.systems.lorenz import Lorenz

# ---------------------------------------------------------------------------
# Canonical regime classification.
# ---------------------------------------------------------------------------


def test_pure_sine_wave_returns_K_near_zero() -> None:
    """A periodic signal must classify as regular."""
    t = np.linspace(0.0, 200.0, 2000)
    sine = np.sin(2.0 * np.pi * t / 10.0)
    K = chaos_zero_one_test(sine)
    assert 0.0 <= K <= 0.1, f"sine wave should give K << 0.5; got {K}"


def test_iid_gaussian_returns_K_near_one() -> None:
    """A truly stochastic series (auxiliary walk diffuses) → K close to 1."""
    rng = np.random.default_rng(42)
    walk = rng.standard_normal(2000)
    K = chaos_zero_one_test(walk)
    assert 0.9 <= K <= 1.0, f"IID noise should give K close to 1; got {K}"


def test_lorenz_x_projection_classifies_chaotic() -> None:
    """Canonical IC, sampled at the system's natural orbital period."""
    system = Lorenz()
    default_params = {p.name: p.default for p in system.parameters.values()}

    def rhs(t: float, y: np.ndarray) -> np.ndarray:
        return system.rhs(t, y, **default_params)

    # Run for 2000 time units; downsample to dt ~ 1.0 so we get
    # roughly one sample per natural Lorenz orbital period. The
    # docstring explains why oversampling makes the test miss
    # chaos.
    sol = solve_ivp(
        rhs,
        (0.0, 2000.0),
        [1.0, 1.0, 1.0],
        method="DOP853",
        t_eval=np.linspace(20.0, 2000.0, 2000),
        rtol=1e-9,
        atol=1e-12,
    )
    x = sol.y[0]
    K = chaos_zero_one_test(x)
    assert 0.95 <= K <= 1.0, (
        f"Lorenz x-projection at dt~1 should give K close to 1 "
        f"(canonical chaotic Lorenz, Sprott Table 5.1); got {K}"
    )


def test_constant_signal_returns_K_zero() -> None:
    """Zero-variance input → degenerate Pearson correlation → K = 0."""
    constant = np.full(500, 1.7, dtype=np.float64)
    K = chaos_zero_one_test(constant)
    assert K == 0.0


def test_K_value_clamped_to_unit_interval() -> None:
    """Every well-formed input returns K in [0, 1] (function clamps)."""
    rng = np.random.default_rng(0)
    for _ in range(5):
        sig = rng.standard_normal(1000)
        K = chaos_zero_one_test(sig)
        assert 0.0 <= K <= 1.0


# ---------------------------------------------------------------------------
# Reproducibility.
# ---------------------------------------------------------------------------


def test_default_seed_is_deterministic() -> None:
    """Two calls without explicit rng must return the identical statistic."""
    rng = np.random.default_rng(1)
    sig = rng.standard_normal(800)
    K1 = chaos_zero_one_test(sig)
    K2 = chaos_zero_one_test(sig)
    assert K1 == K2


def test_explicit_rng_changes_the_statistic_only_slightly() -> None:
    """Different rng seeds → different K but both in the same regime."""
    rng = np.random.default_rng(1)
    sig = rng.standard_normal(800)
    K_seed_a = chaos_zero_one_test(sig, rng=np.random.default_rng(1))
    K_seed_b = chaos_zero_one_test(sig, rng=np.random.default_rng(2))
    # Both seeds see the same noise -> both should classify as chaotic.
    assert K_seed_a > 0.9 and K_seed_b > 0.9
    # The seeds sample different `c`'s, so the medians differ at the
    # 1e-3 level but not at the regime level.
    assert abs(K_seed_a - K_seed_b) < 0.1


# ---------------------------------------------------------------------------
# Edge cases.
# ---------------------------------------------------------------------------


def test_too_few_samples_raises() -> None:
    with pytest.raises(ValueError, match="at least 100 samples"):
        chaos_zero_one_test(np.zeros(50))


def test_invalid_n_c_raises() -> None:
    with pytest.raises(ValueError, match="n_c must be >= 1"):
        chaos_zero_one_test(np.zeros(500), n_c=0)


def test_invalid_c_range_raises() -> None:
    with pytest.raises(ValueError, match="c_range"):
        chaos_zero_one_test(np.zeros(500), c_range=(0.0, 1.0))
    with pytest.raises(ValueError, match="c_range"):
        chaos_zero_one_test(np.zeros(500), c_range=(1.0, 10.0))
    with pytest.raises(ValueError, match="c_range"):
        chaos_zero_one_test(np.zeros(500), c_range=(2.0, 1.0))


def test_invalid_n_cut_raises() -> None:
    with pytest.raises(ValueError, match="n_cut"):
        chaos_zero_one_test(np.zeros(500), n_cut=0)
    with pytest.raises(ValueError, match="n_cut"):
        chaos_zero_one_test(np.zeros(500), n_cut=500)


def test_accepts_list_input() -> None:
    """The function works on Python lists, not just ndarrays."""
    t = np.linspace(0.0, 100.0, 1000).tolist()
    sine_list = [np.sin(2.0 * np.pi * x / 10.0) for x in t]
    K = chaos_zero_one_test(sine_list)
    assert 0.0 <= K <= 0.1


def test_returns_python_float_not_numpy_scalar() -> None:
    """The public return type is Python ``float`` for clean ``str()``."""
    sig = np.random.default_rng(0).standard_normal(500)
    K = chaos_zero_one_test(sig)
    assert isinstance(K, float)
    assert not isinstance(K, np.floating)
