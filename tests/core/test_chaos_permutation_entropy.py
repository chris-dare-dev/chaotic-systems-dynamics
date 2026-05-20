"""Tests for the Bandt-Pompe permutation entropy chaos indicator (CSC-013).

The :func:`~chaotic_systems.core.diagnostics.chaos_permutation_entropy`
function returns a normalised Shannon entropy in ``[0, 1]``:

- ``0`` for strictly regular signals (constant, monotonic — only one
  ordinal pattern appears).
- ``log(k)/log(m!)`` for periodic orbits visiting ``k`` ordinal
  patterns equally (the period-4 logistic cycle at ``r = 3.5`` hits
  exactly this theoretical value).
- ``~1`` for chaotic / stochastic signals (the empirical pattern
  distribution is broad, approaching uniform).

Numerical observables pinned here (all values match the
Bandt-Pompe 2002 paper or are derivable in closed form):

- Constant signal at order=4 → ``H = 0`` exactly (one pattern
  ``(0, 1, 2, 3)`` with probability 1).
- Strictly increasing ramp → ``H = 0`` exactly (same reason).
- Logistic map at ``r = 3.5`` (period-4 cycle) → ``H = log(4)/log(24)
  ≈ 0.4368`` (theoretical: 4 cyclically-shifted patterns equally
  likely; m=4 has 24 total patterns).
- Logistic map at ``r = 4.0`` (hard chaos, *but* the logistic family
  has "forbidden patterns") → ``H ≈ 0.74`` per Bandt-Pompe Fig. 2.
- IID uniform noise → ``H > 0.99`` (close to the maximum).
- Lorenz x-projection (canonical IC) → ``H > 0.99``.

References for the observables
------------------------------
- C. Bandt, B. Pompe, *Permutation entropy: A natural complexity
  measure for time series*, Phys. Rev. Lett. 88 (2002), 174102 —
  the canonical reference. Fig. 2 (right panel) shows H_PE on the
  logistic map vs. r; at r=4 the curve sits at H_norm ~ 0.74-0.78
  (the dips below ln(m!) come from "forbidden patterns" — orbit
  segments the dynamics never visit).
- R. May, *Simple mathematical models with very complicated
  dynamics*, Nature 261 (1976), 459-467 — for the logistic-map
  cuts.
- E. N. Lorenz, *Deterministic Nonperiodic Flow*, J. Atmos. Sci. 20
  (1963), 130-141.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from chaotic_systems.core import chaos_permutation_entropy
from chaotic_systems.systems.lorenz import Lorenz

# ---------------------------------------------------------------------------
# Closed-form regime classifications.
# ---------------------------------------------------------------------------


def test_constant_signal_returns_zero() -> None:
    """A constant signal collapses to one pattern -> H = 0."""
    c = np.full(500, 1.7, dtype=np.float64)
    H = chaos_permutation_entropy(c)
    assert H == 0.0


def test_monotonic_ramp_returns_zero() -> None:
    """A strictly monotonic ramp also visits only one ordinal pattern."""
    ramp = np.arange(500, dtype=np.float64)
    H = chaos_permutation_entropy(ramp)
    assert H == 0.0


def test_monotonic_decreasing_ramp_returns_zero() -> None:
    """Decreasing is also one ordinal pattern (the reverse permutation)."""
    ramp = np.linspace(10.0, -5.0, 500)
    H = chaos_permutation_entropy(ramp)
    assert H == 0.0


def test_logistic_period_four_matches_theoretical_value() -> None:
    """Period-4 cycle: 4 ordinal patterns equally → H = log(4)/log(24).

    The logistic map at r=3.5 lands on a stable period-4 cycle. The
    m=4 sliding window samples the cycle at lag 1, hitting exactly
    4 cyclically-shifted ordinal patterns with equal frequency. The
    theoretical normalised entropy is ``log(4)/log(4!) ~ 0.43679``.
    """
    z = np.zeros(2000, dtype=np.float64)
    z[0] = 0.2
    r = 3.5
    for i in range(1, 2000):
        z[i] = r * z[i - 1] * (1.0 - z[i - 1])
    # Discard the transient — the cycle settles after ~50 iterates.
    settled = z[200:]
    H = chaos_permutation_entropy(settled, order=4)
    expected = math.log(4) / math.log(math.factorial(4))
    assert H == pytest.approx(expected, abs=0.01), (
        f"period-4 logistic should give H = log(4)/log(24) ~ "
        f"{expected:.4f}; got {H}"
    )


# ---------------------------------------------------------------------------
# Chaotic / stochastic classifications.
# ---------------------------------------------------------------------------


def test_iid_uniform_noise_approaches_max_entropy() -> None:
    """Pure stochastic noise → normalised entropy close to 1."""
    rng = np.random.default_rng(0)
    noise = rng.uniform(0.0, 1.0, size=2000)
    H = chaos_permutation_entropy(noise)
    assert H > 0.99, f"IID noise should give H > 0.99; got {H}"


def test_lorenz_x_projection_classifies_chaotic() -> None:
    """Canonical Lorenz IC, sampled at dt~1 → H close to 1."""
    system = Lorenz()
    default_params = {p.name: p.default for p in system.parameters.values()}

    def rhs(t: float, y: np.ndarray) -> np.ndarray:
        return system.rhs(t, y, **default_params)

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
    H = chaos_permutation_entropy(x)
    assert H > 0.99, (
        f"Lorenz x at dt~1 should give H > 0.99 (broad ordinal-pattern "
        f"distribution); got {H}"
    )


def test_logistic_r4_classifies_chaotic_with_forbidden_patterns() -> None:
    """Logistic r=4 has hard chaos *and* forbidden ordinal patterns.

    Bandt-Pompe 2002 Fig. 2 shows H_PE(r=4) ~ 0.74-0.78 at m=4 —
    significantly below 1 because the logistic family has
    "forbidden patterns" (orbit segments the dynamics never
    visit). The test pins H ∈ (0.6, 0.85) to capture this
    distinctive behaviour while still landing clearly above the
    period-4 value ~ 0.44.
    """
    z = np.zeros(2000, dtype=np.float64)
    z[0] = 0.3141592653589793
    for i in range(1, 2000):
        z[i] = 4.0 * z[i - 1] * (1.0 - z[i - 1])
    settled = z[200:]
    H = chaos_permutation_entropy(settled)
    assert 0.6 < H < 0.85, (
        f"Logistic r=4 should give H in (0.6, 0.85) per Bandt-Pompe "
        f"Fig. 2 (forbidden patterns); got {H}"
    )


# ---------------------------------------------------------------------------
# Sine-wave regime — partial pattern usage.
# ---------------------------------------------------------------------------


def test_oversampled_sine_returns_low_entropy() -> None:
    """An oversampled sine visits only the smooth ordinal patterns."""
    t = np.linspace(0.0, 100.0, 2000)
    sine = np.sin(2.0 * np.pi * t / 5.0)
    H = chaos_permutation_entropy(sine)
    # Smooth signal -> only a few patterns -> H well below 0.5.
    assert H < 0.5, f"oversampled sine should give H < 0.5; got {H}"


# ---------------------------------------------------------------------------
# Parameter coverage.
# ---------------------------------------------------------------------------


def test_unnormalized_output_lands_in_log_factorial_band() -> None:
    """With normalize=False the output is in [0, log(m!)]."""
    rng = np.random.default_rng(42)
    noise = rng.uniform(0.0, 1.0, size=2000)
    H = chaos_permutation_entropy(noise, normalize=False)
    log_m_fact = math.log(math.factorial(4))
    assert 0.0 <= H <= log_m_fact
    # Normalised version should equal H / log(m!).
    H_norm = chaos_permutation_entropy(noise, normalize=True)
    assert H_norm == pytest.approx(H / log_m_fact)


@pytest.mark.parametrize("order", [3, 4, 5, 6])
def test_iid_noise_at_each_order_approaches_one(order: int) -> None:
    """Permutation entropy on noise approaches 1 for every reasonable order."""
    rng = np.random.default_rng(7)
    # Each order requires >= 5 * m! samples; m=6 needs 5*720 = 3600.
    n = max(2000, 5 * math.factorial(order) + 100)
    noise = rng.uniform(0.0, 1.0, size=n)
    H = chaos_permutation_entropy(noise, order=order)
    # The approach to 1 is slower at higher orders because m! grows
    # faster than the available pattern count, but stays > 0.9 with
    # the 5 * m! minimum.
    assert H > 0.9, f"order={order} on noise gave H = {H}"


def test_delay_parameter_changes_the_indicator_on_oversampled_sine() -> None:
    """delay > 1 desamples the oversampled sine and raises its entropy."""
    t = np.linspace(0.0, 200.0, 4000)
    sine = np.sin(2.0 * np.pi * t / 5.0)
    H_d1 = chaos_permutation_entropy(sine, delay=1)
    H_d10 = chaos_permutation_entropy(sine, delay=10)
    # Larger delay -> samples span more of the period -> more
    # ordinal patterns visited -> higher entropy.
    assert H_d10 > H_d1


# ---------------------------------------------------------------------------
# Edge cases.
# ---------------------------------------------------------------------------


def test_too_short_for_order_raises() -> None:
    with pytest.raises(ValueError, match=r"too short"):
        chaos_permutation_entropy(np.zeros(50))


def test_order_out_of_band_raises() -> None:
    with pytest.raises(ValueError, match=r"order must be in"):
        chaos_permutation_entropy(np.zeros(1000), order=1)
    with pytest.raises(ValueError, match=r"order must be in"):
        chaos_permutation_entropy(np.zeros(1000), order=8)


def test_invalid_delay_raises() -> None:
    with pytest.raises(ValueError, match=r"delay must be >= 1"):
        chaos_permutation_entropy(np.zeros(1000), delay=0)


def test_accepts_list_input() -> None:
    """The function works on Python lists, not just ndarrays."""
    sig = list(np.linspace(0.0, 1.0, 500))
    H = chaos_permutation_entropy(sig)
    # Monotonic list -> H = 0.
    assert H == 0.0


def test_returns_python_float_not_numpy_scalar() -> None:
    """The public return type is Python ``float`` for clean ``str()``."""
    sig = np.random.default_rng(0).uniform(0.0, 1.0, size=500)
    H = chaos_permutation_entropy(sig)
    assert isinstance(H, float)
    assert not isinstance(H, np.floating)


def test_deterministic_on_same_input() -> None:
    """No internal randomness — same input gives same output."""
    rng = np.random.default_rng(1)
    sig = rng.uniform(0.0, 1.0, size=2000)
    assert chaos_permutation_entropy(sig) == chaos_permutation_entropy(sig)
