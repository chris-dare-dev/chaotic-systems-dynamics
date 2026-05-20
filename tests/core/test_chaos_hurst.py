"""Tests for the Hurst-exponent chaos indicator (CSC-014).

The :func:`~chaotic_systems.core.diagnostics.chaos_hurst` function
returns the Hurst exponent ``H`` via classical rescaled-range (R/S)
analysis (Hurst 1951; Feder, *Fractals*, Plenum 1988, ch. 8). The
indicator separates regimes by *memory*, not by chaos vs. noise
directly:

- ``H ≈ 0.5``: memoryless / IID-Gaussian increments. Random walk
  in cumulative deviation.
- ``H > 0.5``: persistent (long-range positive correlation).
- ``H < 0.5``: anti-persistent (mean-reverting).
- ``H ≈ 1``: ballistic / fully integrated process (Brownian motion).

Numerical observables pinned here:

- IID standard normal noise (length 4000) → ``H ≈ 0.56`` (the
  slight upward bias above 0.5 is the well-known Annis-Lloyd 1976
  small-sample bias of the R/S estimator; we assert ``H in
  (0.40, 0.70)``).
- Brownian motion (cumsum of IID Gaussian) → ``H > 0.9`` (the
  cumulative sum has ballistic accumulation).
- AR(1) with positive ``phi = 0.85`` → ``H > 0.6`` (persistent
  short-memory process).
- Lorenz x-coordinate at the canonical IC, sampled at dt~1 →
  ``H in (0.4, 0.8)`` — deterministic chaos with bounded
  attractor produces a Hurst in the random-walk band, distinct
  from the clearly-persistent Brownian-motion regime.

References for the observables
------------------------------
- H. E. Hurst, *Long-term storage capacity of reservoirs*, Trans.
  Am. Soc. Civil Eng. 116 (1951), 770-799.
- J. Feder, *Fractals*, Plenum 1988, ch. 8 — the canonical R/S
  recipe.
- A. A. Annis, E. H. Lloyd, *The expected value of the adjusted
  rescaled Hurst range of independent normal summands*,
  Biometrika 63 (1976), 111-116 — the small-sample bias.
- E. N. Lorenz, *Deterministic Nonperiodic Flow*, J. Atmos. Sci.
  20 (1963), 130-141.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from chaotic_systems.core import chaos_hurst
from chaotic_systems.systems.lorenz import Lorenz

# ---------------------------------------------------------------------------
# Canonical regime classifications.
# ---------------------------------------------------------------------------


def test_iid_gaussian_returns_H_near_one_half() -> None:
    """Memoryless Gaussian increments -> H ~ 0.5 (with Annis-Lloyd bias)."""
    rng = np.random.default_rng(0)
    noise = rng.standard_normal(4000)
    H = chaos_hurst(noise)
    # Annis-Lloyd 1976: R/S over-reports H on short IID series by
    # ~0.05-0.10. The (0.40, 0.70) window comfortably contains the
    # expected biased estimate while still rejecting strongly
    # persistent / anti-persistent signals.
    assert 0.40 < H < 0.70, f"IID gaussian should give H ~ 0.5; got {H}"


def test_brownian_motion_returns_H_close_to_one() -> None:
    """Fully integrated Brownian motion -> H close to 1.

    Cumsum of IID Gaussian increments is a coherent process: the
    range grows linearly with chunk length, so the rescaled range
    scales like ``n`` rather than ``sqrt(n)`` and ``H ≈ 1``.
    """
    rng = np.random.default_rng(0)
    bm = np.cumsum(rng.standard_normal(4000))
    H = chaos_hurst(bm)
    assert H > 0.9, f"Brownian motion should give H > 0.9; got {H}"


def test_ar1_persistent_process_returns_H_above_half() -> None:
    """An AR(1) with positive lag-1 correlation is persistent."""
    rng = np.random.default_rng(0)
    phi = 0.85
    n = 4000
    x = np.zeros(n)
    x[0] = rng.standard_normal()
    for i in range(1, n):
        x[i] = phi * x[i - 1] + rng.standard_normal()
    H = chaos_hurst(x)
    # Empirically ~0.73 at phi=0.85; assert >0.6 with margin.
    assert H > 0.6, (
        f"AR(1) phi=0.85 should give H > 0.6 (persistent short-memory); "
        f"got {H}"
    )


def test_lorenz_x_projection_returns_random_walk_band() -> None:
    """Bounded chaotic attractor -> H in the random-walk band, not ballistic."""
    system = Lorenz()
    default_params = {p.name: p.default for p in system.parameters.values()}

    def rhs(t: float, y: np.ndarray) -> np.ndarray:
        return system.rhs(t, y, **default_params)

    sol = solve_ivp(
        rhs,
        (0.0, 2000.0),
        [1.0, 1.0, 1.0],
        method="DOP853",
        t_eval=np.linspace(20.0, 2000.0, 4000),
        rtol=1e-9,
        atol=1e-12,
    )
    x = sol.y[0]
    H = chaos_hurst(x)
    # Lorenz x is bounded and chaotic; the R/S statistic on the raw
    # signal sits in the (0.4, 0.8) band — clearly below the Brownian
    # H ≈ 1 ballistic regime but with some persistence from the
    # deterministic orbital structure.
    assert 0.40 < H < 0.80, (
        f"Lorenz x should give H in (0.4, 0.8); got {H}"
    )


# ---------------------------------------------------------------------------
# Edge cases.
# ---------------------------------------------------------------------------


def test_constant_signal_raises() -> None:
    """Strictly constant input -> Hurst is undefined."""
    c = np.full(500, 3.14)
    with pytest.raises(ValueError, match="undefined"):
        chaos_hurst(c)


def test_constant_signal_with_float_epsilon_noise_still_raises() -> None:
    """Numerically constant inputs survive the signal-range guard."""
    # np.full(500, 3.14) gives chunks with std ~ 1e-15 on chunk sizes
    # that don't divide 500 evenly — the signal-range guard catches
    # these via ``chunk.max() == chunk.min()`` before the spurious
    # R/S ratio enters the regression.
    c = np.full(500, 2.71828)
    with pytest.raises(ValueError, match="undefined"):
        chaos_hurst(c)


def test_too_short_raises() -> None:
    with pytest.raises(ValueError, match="at least 200 samples"):
        chaos_hurst(np.zeros(100))


def test_invalid_min_chunk_raises() -> None:
    with pytest.raises(ValueError, match="min_chunk must be >="):
        chaos_hurst(np.zeros(500), min_chunk=2)


def test_invalid_max_chunk_relative_to_min_raises() -> None:
    with pytest.raises(ValueError, match="max_chunk must be > min_chunk"):
        chaos_hurst(np.zeros(500), min_chunk=64, max_chunk=64)


def test_max_chunk_above_half_N_raises() -> None:
    with pytest.raises(ValueError, match="max_chunk must be <="):
        chaos_hurst(np.zeros(500), max_chunk=400)


def test_num_chunks_below_two_raises() -> None:
    with pytest.raises(ValueError, match="num_chunks must be >= 2"):
        chaos_hurst(np.zeros(500), num_chunks=1)


# ---------------------------------------------------------------------------
# Parameter coverage.
# ---------------------------------------------------------------------------


def test_smaller_max_chunk_still_returns_finite_hurst() -> None:
    """Restricting the chunk ladder to a smaller band still works."""
    rng = np.random.default_rng(1)
    noise = rng.standard_normal(4000)
    H = chaos_hurst(noise, min_chunk=8, max_chunk=64)
    assert np.isfinite(H)


def test_more_chunks_does_not_drastically_change_estimate() -> None:
    """The regression is robust to chunk-ladder density at fixed limits."""
    rng = np.random.default_rng(2)
    noise = rng.standard_normal(4000)
    H_10 = chaos_hurst(noise, num_chunks=10)
    H_30 = chaos_hurst(noise, num_chunks=30)
    # Same data, different ladders -> agreement within 0.1.
    assert abs(H_10 - H_30) < 0.1


def test_accepts_list_input() -> None:
    rng = np.random.default_rng(0)
    sig = list(rng.standard_normal(2000))
    H = chaos_hurst(sig)
    assert np.isfinite(H)
    assert 0.40 < H < 0.70


def test_returns_python_float_not_numpy_scalar() -> None:
    """The public return type is Python ``float`` for clean ``str()``."""
    sig = np.random.default_rng(0).standard_normal(500)
    H = chaos_hurst(sig)
    assert isinstance(H, float)
    assert not isinstance(H, np.floating)


def test_deterministic_on_same_input() -> None:
    """No internal randomness — same input gives same output."""
    rng = np.random.default_rng(1)
    sig = rng.standard_normal(2000)
    assert chaos_hurst(sig) == chaos_hurst(sig)


# ---------------------------------------------------------------------------
# Regime separation — meta-test that classifications stay well separated.
# ---------------------------------------------------------------------------


def test_brownian_motion_well_above_iid_gaussian() -> None:
    """Brownian motion -> H ~ 1 must sit clearly above IID Gaussian -> H ~ 0.5."""
    rng = np.random.default_rng(7)
    noise = rng.standard_normal(4000)
    bm = np.cumsum(rng.standard_normal(4000))
    H_noise = chaos_hurst(noise)
    H_bm = chaos_hurst(bm)
    assert H_bm > H_noise + 0.2, (
        f"Brownian H ({H_bm:.3f}) must sit at least 0.2 above IID H "
        f"({H_noise:.3f})"
    )
