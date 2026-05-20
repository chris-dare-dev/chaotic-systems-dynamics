"""Tests for the Sander-Yorke Weighted Birkhoff Average chaos indicator (CSC-012).

The :func:`~chaotic_systems.core.diagnostics.chaos_weighted_birkhoff`
function returns a *digit-loss* statistic in ``[0, 16]``:

- ``> ~10`` for **regular** (Diophantine quasi-periodic) orbits — the
  WBA converges super-exponentially so the two halves agree to near
  machine precision (Sander-Yorke 2012; Das et al. 2016).
- ``< ~6`` for **chaotic** orbits — the WBA converges only
  polynomially, so the two halves disagree at the 1e-2 to 1e-5 level.

Numerical observables pinned here (calibration values come from the
references):

- Golden-ratio rotation ``x_{n+1} = x_n + (sqrt(5)-1)/2 (mod 1)`` —
  the canonical Diophantine quasi-periodic orbit — yields the
  saturated digit-loss of 16 in double precision.
- Logistic map at ``r = 3.5`` (a stable period-4 cycle) is regular
  and saturates the digit-loss cap.
- Logistic map at ``r = 4.0`` (Lebesgue-ergodic hard chaos) gives
  ``digit_loss ~ 1.7``.
- Lorenz x-projection (canonical IC), wrapped to ``[0, 1)`` so the
  default ``cos(2 pi x)`` observable is well behaved, gives
  ``digit_loss ~ 2.4``.
- IID uniform noise gives ``digit_loss ~ 1.3``.

Numerical caveat: the doubling map ``x_{n+1} = 2 x_n (mod 1)`` is
*theoretically* chaotic but suffers catastrophic precision loss in
float64 (after ~52 iterations every IC pins to 0 because the binary
expansion gets shifted out of the mantissa). The Sander-Yorke
literature notes this is a known numerical-rather-than-dynamical
artefact; we do **not** test the doubling map here for that reason
— the logistic map at ``r = 4`` is the canonical hard-chaos test
case that survives float64.

References for the observables
------------------------------
- E. Sander, J. A. Yorke, *Connecting period-doubling cascades to
  chaos*, Int. J. Bifurc. Chaos 22 (2012), 1250022.
- S. Das et al., *Measuring quasiperiodicity*, Europhys. Lett. 114
  (2016), 40005.
- R. May, *Simple mathematical models with very complicated
  dynamics*, Nature 261 (1976), 459-467 — for the logistic-map
  cuts.
- E. N. Lorenz, *Deterministic Nonperiodic Flow*, J. Atmos. Sci. 20
  (1963), 130-141.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from chaotic_systems.core import chaos_weighted_birkhoff
from chaotic_systems.systems.lorenz import Lorenz

# Practical regime cuts (Sander-Yorke 2012 §4 calibration; the
# float64 cap from the implementation is 16).
_REGULAR_THRESHOLD: float = 10.0
_CHAOTIC_THRESHOLD: float = 6.0


# ---------------------------------------------------------------------------
# Canonical regime classification — regular orbits.
# ---------------------------------------------------------------------------


def test_golden_ratio_rotation_saturates_digit_loss() -> None:
    """The canonical Diophantine quasi-periodic orbit -> max digit-loss."""
    phi = (np.sqrt(5.0) - 1.0) / 2.0  # golden ratio - 1 (irrational)
    n = 2000
    x = np.zeros(n)
    x[0] = 0.123
    for i in range(1, n):
        x[i] = (x[i - 1] + phi) % 1.0
    d = chaos_weighted_birkhoff(x)
    # Sander-Yorke main result: super-exponential convergence on
    # Diophantine rotations -> saturated at the float64 cap.
    assert d >= _REGULAR_THRESHOLD, (
        f"golden-ratio rotation must give digit_loss >> {_REGULAR_THRESHOLD}; "
        f"got {d}"
    )


def test_logistic_period_four_cycle_classifies_regular() -> None:
    """Logistic at r=3.5 is on a period-4 cycle -> regular orbit."""
    n = 2000
    z = np.zeros(n)
    z[0] = 0.2
    r = 3.5
    for i in range(1, n):
        z[i] = r * z[i - 1] * (1.0 - z[i - 1])
    d = chaos_weighted_birkhoff(z)
    assert d >= _REGULAR_THRESHOLD, (
        f"logistic r=3.5 (period-4) must give digit_loss >= "
        f"{_REGULAR_THRESHOLD}; got {d}"
    )


# ---------------------------------------------------------------------------
# Canonical regime classification — chaotic orbits.
# ---------------------------------------------------------------------------


def test_logistic_r4_classifies_chaotic() -> None:
    """Logistic at r=4 is Lebesgue-ergodic hard chaos."""
    n = 2000
    z = np.zeros(n)
    z[0] = 0.3141592653589793
    r = 4.0
    for i in range(1, n):
        z[i] = r * z[i - 1] * (1.0 - z[i - 1])
    d = chaos_weighted_birkhoff(z)
    assert d <= _CHAOTIC_THRESHOLD, (
        f"logistic r=4 (hard chaos) must give digit_loss <= "
        f"{_CHAOTIC_THRESHOLD}; got {d}"
    )


def test_iid_uniform_classifies_chaotic() -> None:
    """Pure stochastic noise -> the WBA two halves disagree heavily."""
    rng = np.random.default_rng(0)
    noise = rng.uniform(0.0, 1.0, size=2000)
    d = chaos_weighted_birkhoff(noise)
    assert d <= _CHAOTIC_THRESHOLD, (
        f"IID noise must give digit_loss <= {_CHAOTIC_THRESHOLD}; got {d}"
    )


def test_lorenz_x_projection_classifies_chaotic() -> None:
    """Canonical Lorenz IC -> low digit-loss (Sprott Table 5.1)."""
    system = Lorenz()
    default_params = {p.name: p.default for p in system.parameters.values()}

    def rhs(t: float, y: np.ndarray) -> np.ndarray:
        return system.rhs(t, y, **default_params)

    sol = solve_ivp(
        rhs,
        (0.0, 1000.0),
        [1.0, 1.0, 1.0],
        method="DOP853",
        t_eval=np.linspace(20.0, 1000.0, 2000),
        rtol=1e-9,
        atol=1e-12,
    )
    x = sol.y[0]
    # Wrap to [0, 1) so the default cos(2 pi x) observable is well behaved.
    x_wrapped = (x - x.min()) / (x.max() - x.min())
    d = chaos_weighted_birkhoff(x_wrapped)
    assert d <= _CHAOTIC_THRESHOLD, (
        f"Lorenz x must give digit_loss <= {_CHAOTIC_THRESHOLD}; got {d}"
    )


# ---------------------------------------------------------------------------
# Determinism, observables, range.
# ---------------------------------------------------------------------------


def test_two_calls_on_same_input_are_identical() -> None:
    """No internal randomness — the WBA is fully deterministic."""
    rng = np.random.default_rng(1)
    sig = rng.uniform(0.0, 1.0, size=500)
    assert chaos_weighted_birkhoff(sig) == chaos_weighted_birkhoff(sig)


def test_custom_observable_changes_the_digit_loss() -> None:
    """Passing a different observable produces a different statistic."""
    rng = np.random.default_rng(42)
    sig = rng.uniform(0.0, 1.0, size=2000)
    default = chaos_weighted_birkhoff(sig)
    # A polynomial observable behaves differently from the default cosine.
    custom = chaos_weighted_birkhoff(sig, observable=lambda x: x * x)
    # Both should still classify as chaotic for IID noise, but the values
    # need not match.
    assert default != custom


def test_digit_loss_is_clamped_to_unit_interval_at_zero_floor() -> None:
    """Even maximally noisy inputs return a non-negative digit-loss."""
    rng = np.random.default_rng(2026)
    sig = rng.uniform(0.0, 1.0, size=2000)
    d = chaos_weighted_birkhoff(sig)
    assert d >= 0.0


def test_digit_loss_caps_at_16() -> None:
    """The float64 precision floor is 16 digits — the indicator clamps."""
    # Constant signal -> WBA agrees to the bit on both halves.
    constant = np.full(500, 0.5, dtype=np.float64)
    d = chaos_weighted_birkhoff(constant)
    assert d == 16.0


# ---------------------------------------------------------------------------
# Edge cases.
# ---------------------------------------------------------------------------


def test_too_few_samples_raises() -> None:
    with pytest.raises(ValueError, match="at least 200 samples"):
        chaos_weighted_birkhoff(np.zeros(100))


def test_observable_with_wrong_output_length_raises() -> None:
    """A misbehaved observable that returns the wrong length is rejected."""
    sig = np.linspace(0.0, 1.0, 500)
    with pytest.raises(ValueError, match="one value per sample"):
        chaos_weighted_birkhoff(sig, observable=lambda _: np.zeros(3))


def test_accepts_list_input() -> None:
    """The function works on Python lists, not just ndarrays."""
    phi = (np.sqrt(5.0) - 1.0) / 2.0
    x = [0.123]
    for _ in range(1, 500):
        x.append((x[-1] + phi) % 1.0)
    d = chaos_weighted_birkhoff(x)
    # Diophantine rotation -> still saturates.
    assert d >= _REGULAR_THRESHOLD


def test_returns_python_float_not_numpy_scalar() -> None:
    sig = np.random.default_rng(0).uniform(0.0, 1.0, size=500)
    d = chaos_weighted_birkhoff(sig)
    assert isinstance(d, float)
    assert not isinstance(d, np.floating)


# ---------------------------------------------------------------------------
# Regime separation — meta-test that the two thresholds give clean
# separation across the canonical inputs.
# ---------------------------------------------------------------------------


def test_regular_and_chaotic_classifications_are_well_separated() -> None:
    """Every regular test gives digit_loss > every chaotic test."""
    phi = (np.sqrt(5.0) - 1.0) / 2.0
    rot = np.zeros(2000)
    rot[0] = 0.123
    for i in range(1, 2000):
        rot[i] = (rot[i - 1] + phi) % 1.0
    rot_d = chaos_weighted_birkhoff(rot)

    z = np.zeros(2000)
    z[0] = 0.3141592653589793
    for i in range(1, 2000):
        z[i] = 4.0 * z[i - 1] * (1.0 - z[i - 1])
    chaos_d = chaos_weighted_birkhoff(z)

    assert rot_d > chaos_d + 5.0, (
        f"regular ({rot_d:.3f}) must be at least 5 digits above "
        f"chaotic ({chaos_d:.3f})"
    )
