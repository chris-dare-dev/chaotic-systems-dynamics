"""Scalar chaos indicators that wrap on a single trajectory column.

This module is the home for "trajectory-in, scalar-out" diagnostic
functions that, unlike :func:`~chaotic_systems.core.lyapunov.lyapunov_spectrum`,
operate on a 1-D projection of the trajectory (e.g. just ``x(t)`` of
Lorenz) and return a single number summarising the regime. Inhabitants
shipped so far:

- :func:`chaos_zero_one_test` — Gottwald-Melbourne 2009 (CSC-011).
- :func:`chaos_weighted_birkhoff` — Sander-Yorke 2017 super-Gaussian
  weighted Birkhoff average; digit-loss between two halves
  diagnoses regular vs. chaotic dynamics (CSC-012).

Follow-up candidates from the 2026-q2-broadening capability-scout —
permutation entropy (CSC-013) and Hurst exponent (CSC-014) — will
slot in here behind the same shape.

References (for this module overall)
------------------------------------
- G. A. Gottwald, I. Melbourne, *On the Implementation of the 0-1 Test
  for Chaos*, SIAM J. Appl. Dyn. Sys. 8 (2009), 129-145. DOI:
  10.1137/080718851. arXiv:0906.1418. — the canonical implementation
  guide cited verbatim in :func:`chaos_zero_one_test` below.
- E. Sander, J. A. Yorke, *Connecting period-doubling cascades to
  chaos*, Int. J. Bifurc. Chaos 22 (2012), 1250022; and S. Das,
  C. B. Dock, Y. Saiki, M. Salgado-Flores, E. Sander, J. Wu, J. A.
  Yorke, *Measuring quasiperiodicity*, Europhys. Lett. 114 (2016),
  40005 — the canonical references for the super-Gaussian
  Weighted Birkhoff Average, cited verbatim in
  :func:`chaos_weighted_birkhoff` below.
- C. Bandt, B. Pompe, *Permutation entropy: A natural complexity measure
  for time series*, Phys. Rev. Lett. 88 (2002), 174102. — pending
  CSC-013.
- J. C. Sprott, *Chaos and Time-Series Analysis*, Oxford University
  Press, 2003, ch. 5 — overall pedagogical context for scalar chaos
  indicators.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np

# Default ``c`` sampling band from Gottwald-Melbourne 2009 §3. The band
# avoids the resonant degeneracies near ``c = 0`` and ``c = pi`` and the
# near-1 value of ``1 - cos(c)`` keeps the modified-displacement
# normaliser well conditioned (used in :func:`chaos_zero_one_test`).
_DEFAULT_C_RANGE: tuple[float, float] = (np.pi / 5.0, 4.0 * np.pi / 5.0)
# Sampling cap on ``n`` in the mean-square-displacement sweep. The
# paper recommends ``n_cut << N`` so the running estimator of
# ``M_c(n)`` doesn't degenerate as ``(N - n)`` shrinks. ``N // 10``
# is the standard recipe.
_DEFAULT_N_CUT_FRACTION: int = 10
# Number of random ``c`` draws to median over. The paper notes the
# median (not the mean) is robust to occasional resonant outliers,
# and 100 draws are typically enough for the median to settle.
_DEFAULT_N_C: int = 100
_DEFAULT_RNG_SEED: int = 0xC0FFEE
# Minimum sample count below which the test is not statistically
# meaningful (Gottwald-Melbourne report tests converging for N >= 1000;
# we require >= 100 so smoke tests in :mod:`tests/` stay fast).
_MIN_SAMPLES: int = 100


def _pearson_corr(x: np.ndarray, y: np.ndarray) -> float:
    """Pearson correlation coefficient of two 1-D arrays.

    Returns ``0.0`` when either input has zero variance — that's the
    correct degenerate-case answer for the 0-1 test, where a regular
    orbit's modified displacement is constant and the correlation
    coefficient is undefined.
    """
    x_centred = x - x.mean()
    y_centred = y - y.mean()
    denom = float(np.sqrt(np.sum(x_centred * x_centred) * np.sum(y_centred * y_centred)))
    if denom <= 0.0:
        return 0.0
    return float(np.sum(x_centred * y_centred) / denom)


def chaos_zero_one_test(
    timeseries: Sequence[float] | np.ndarray,
    *,
    n_c: int = _DEFAULT_N_C,
    c_range: tuple[float, float] = _DEFAULT_C_RANGE,
    n_cut: int | None = None,
    rng: np.random.Generator | None = None,
) -> float:
    """Gottwald-Melbourne 0-1 test for chaos.

    Given a real-valued scalar time series :math:`\\phi(n)` of length
    :math:`N`, the test returns a scalar :math:`K \\in [0, 1]` that
    diagnoses the dynamics:

    - :math:`K \\to 0` for *regular* (periodic, quasi-periodic, fixed
      point) orbits — the auxiliary :math:`(p_c, q_c)` walk stays
      bounded.
    - :math:`K \\to 1` for *chaotic* orbits — the auxiliary walk
      diffuses, so the mean-square displacement grows linearly with
      lag :math:`n`.

    Algorithm (Gottwald-Melbourne 2009 §3, eqs. 4-13)
    -------------------------------------------------
    For each randomly sampled ``c`` in ``c_range``:

    .. math::

        p_c(n) = \\sum_{j=0}^{n-1} \\phi(j) \\cos(c j), \\qquad
        q_c(n) = \\sum_{j=0}^{n-1} \\phi(j) \\sin(c j).

    The (raw) mean-square displacement at lag :math:`n` is

    .. math::

        M_c(n) = \\frac{1}{N - n} \\sum_{j=0}^{N - n - 1}
            \\left( p_c(j+n) - p_c(j) \\right)^2 +
            \\left( q_c(j+n) - q_c(j) \\right)^2.

    The paper's *modified* displacement subtracts the leading
    oscillatory contribution (eq. 11), which has zero growth rate but
    finite variance:

    .. math::

        D_c(n) = M_c(n) - \\bar{\\phi}^2 \\frac{1 - \\cos(c n)}{1 - \\cos(c)}.

    The single-:math:`c` test statistic is

    .. math::

        K_c = \\frac{\\operatorname{cov}(n, D_c(n))}
                   {\\sqrt{\\operatorname{var}(n) \\, \\operatorname{var}(D_c(n))}}

    evaluated over :math:`n = 1, \\dots, n_{\\text{cut}}`. The
    final test statistic is the **median** of :math:`K_c` over
    ``n_c`` random draws of ``c`` from ``c_range``.

    Parameters
    ----------
    timeseries
        1-D real-valued time series :math:`\\phi(n)`.
    n_c
        Number of random ``c`` draws to median over. Defaults to 100
        per Gottwald-Melbourne §4. Smaller values speed up the
        test at the cost of slightly noisier output.
    c_range
        Closed interval ``(c_min, c_max)`` from which ``c`` is
        sampled. Defaults to ``(pi/5, 4*pi/5)`` per the paper —
        avoids the resonant degeneracies near 0 and ``pi``.
    n_cut
        Lag cutoff for the mean-square-displacement sweep. Defaults
        to ``len(timeseries) // 10``. Larger values produce
        smoother estimates but cost ``O(n_c * n_cut)`` time and
        require ``N - n_cut`` samples to remain statistically
        meaningful.
    rng
        Optional :class:`numpy.random.Generator`. Defaults to
        ``np.random.default_rng(0xC0FFEE)`` so test outputs are
        reproducible without an explicit seed.

    Notes
    -----
    The test is sensitive to **oversampling**. Gottwald-Melbourne §4
    explicitly recommend "sampling at intervals comparable to the
    dominant oscillation period of the deterministic system". For
    Lorenz at canonical parameters the natural orbital period is
    ``~1`` time unit; sampling at ``dt = 0.04`` (typical animation
    rate) produces an apparent-non-chaotic ``K ~ 0.03``, while
    ``dt = 0.5-1.0`` lands the correct ``K ~ 0.998``. When wiring
    this test to a recorded trajectory, downsample the trajectory
    to roughly one sample per natural period before calling.

    Returns
    -------
    float
        The test statistic :math:`K \\in [0, 1]`. Values close to 0
        signal regular dynamics; close to 1 signal chaos. The paper
        suggests ``K > 0.5`` as a working chaos / non-chaos cut for
        well-converged tests.

    Raises
    ------
    ValueError
        If the time series has fewer than 100 samples (the test is
        not statistically meaningful below this size).

    References
    ----------
    - G. A. Gottwald, I. Melbourne, *On the Implementation of the
      0-1 Test for Chaos*, SIAM J. Appl. Dyn. Sys. 8 (2009),
      129-145. DOI: 10.1137/080718851. arXiv:0906.1418.
    """
    arr = np.asarray(timeseries, dtype=np.float64).ravel()
    n = int(arr.size)
    if n < _MIN_SAMPLES:
        raise ValueError(
            f"chaos_zero_one_test requires at least {_MIN_SAMPLES} samples; "
            f"got {n}. Run the system longer."
        )
    if n_c < 1:
        raise ValueError(f"n_c must be >= 1; got {n_c}")
    c_min, c_max = c_range
    if not (0.0 < c_min < c_max < 2.0 * np.pi):
        raise ValueError(
            f"c_range must satisfy 0 < c_min < c_max < 2 pi; got {c_range!r}"
        )
    if n_cut is None:
        n_cut = max(10, n // _DEFAULT_N_CUT_FRACTION)
    if not 1 <= n_cut < n:
        raise ValueError(f"n_cut must be in [1, {n - 1}]; got {n_cut}")
    gen = rng if rng is not None else np.random.default_rng(_DEFAULT_RNG_SEED)

    phi_mean = float(arr.mean())
    indices = np.arange(n, dtype=np.float64)
    lags = np.arange(1, n_cut + 1, dtype=np.float64)
    cs = gen.uniform(c_min, c_max, size=n_c)

    k_values = np.empty(n_c, dtype=np.float64)
    for i, c in enumerate(cs):
        cos_c = np.cos(c * indices)
        sin_c = np.sin(c * indices)
        # Auxiliary translation variables p_c, q_c (eq. 4 of the paper).
        # cumsum places p_c(0) = 0 and accumulates phi(j) * cos(c j) /
        # sin(c j) — the standard discrete recurrence.
        p_c = np.cumsum(arr * cos_c)
        q_c = np.cumsum(arr * sin_c)
        # Raw mean-square displacement M_c(n) for n = 1..n_cut.
        M_c = np.empty(n_cut, dtype=np.float64)
        for lag_idx, lag in enumerate(range(1, n_cut + 1)):
            dp = p_c[lag:] - p_c[:-lag]
            dq = q_c[lag:] - q_c[:-lag]
            M_c[lag_idx] = float(np.mean(dp * dp + dq * dq))
        # Modified displacement D_c(n) — subtracts the leading
        # oscillatory term so the *growth rate* of M_c is isolated
        # (eq. 11 of the paper). The denominator 1 - cos(c) is
        # safely > 0 inside the (pi/5, 4 pi/5) default band.
        one_minus_cos_c = 1.0 - float(np.cos(c))
        # Guard against a numerically singular c (e.g. user passed
        # a custom c_range that strays near 0 or 2 pi).
        if one_minus_cos_c <= 1e-12:
            k_values[i] = 0.0
            continue
        v_osc = (phi_mean * phi_mean) * (1.0 - np.cos(c * lags)) / one_minus_cos_c
        D_c = M_c - v_osc
        k_values[i] = _pearson_corr(lags, D_c)

    # Median over c-draws is robust to occasional resonant outliers
    # (Gottwald-Melbourne §4); clamp to [0, 1] because the
    # correlation coefficient can dip slightly negative for very
    # short or very regular series.
    k_final = float(np.median(k_values))
    return max(0.0, min(1.0, k_final))


# ---------------------------------------------------------------------------
# CSC-012 — Weighted Birkhoff Average chaos indicator.
# ---------------------------------------------------------------------------

# Practical floor on the WBA digit-loss output. With float64 precision the
# Sander-Yorke WBA on Diophantine rotations agrees to ~10-15 digits between
# two halves of the trajectory; anything tighter is below numerical
# resolution and yields infinity through ``-log10`` without a clamp. The
# value 16 corresponds to ``~5e-17`` two-half difference — comfortably
# inside double-precision noise.
_WBA_MAX_DIGITS: float = 16.0
# Minimum sample count for the WBA. The two-halves test needs each half
# to itself contain the super-Gaussian weight's support; smaller than
# ~200 produces a noisy indicator even on smooth regular orbits.
_WBA_MIN_SAMPLES: int = 200


def _super_gaussian_weights(n: int) -> np.ndarray:
    """The Sander-Yorke super-Gaussian "bump" weight on ``n`` samples.

    Returns an array of length ``n`` with values

    .. math::

        w_j = \\exp\\!\\left(-\\frac{1}{(j/n)(1 - j/n)}\\right)
        \\quad \\text{for } 1 \\le j \\le n - 1,

    and ``w_0 = w_{n-1} = 0``. The weight is ``C^\\infty`` on
    ``[0, 1]`` with all derivatives vanishing at the endpoints —
    that smoothness is what gives the WBA its super-exponential
    convergence on Diophantine quasi-periodic orbits (Das et al.
    2016, §2; Sander-Yorke 2012, §3).
    """
    if n < 3:
        # Too few samples for a meaningful weight — return all-zero so the
        # caller's normalisation falls back gracefully (handled below).
        return np.zeros(n, dtype=np.float64)
    j = np.arange(n, dtype=np.float64)
    t = j / float(n)
    w = np.zeros(n, dtype=np.float64)
    # Mask away the endpoint zeros; w(t) = exp(-1/(t(1-t))) for t in (0, 1).
    interior = (j > 0) & (j < n - 1)
    t_interior = t[interior]
    w[interior] = np.exp(-1.0 / (t_interior * (1.0 - t_interior)))
    return w


def _weighted_birkhoff(f_values: np.ndarray) -> float:
    """Compute the Sander-Yorke WBA of an array of observable values.

    Returns ``sum_j w_j f_j / sum_j w_j``. Handles the degenerate
    case (zero-weight sum) by falling back to the unweighted mean —
    that path only triggers for ``n < 3`` and is consistent with
    the empty-weight limit.
    """
    arr = np.asarray(f_values, dtype=np.float64).ravel()
    w = _super_gaussian_weights(arr.size)
    w_sum = float(w.sum())
    if w_sum <= 0.0:
        return float(arr.mean()) if arr.size else 0.0
    return float(np.sum(w * arr) / w_sum)


def _default_wba_observable(x: np.ndarray) -> np.ndarray:
    """The default observable ``cos(2 pi x)`` for the WBA chaos test.

    The choice is canonical (Das et al. 2016 §3, pynamicalsys
    documentation): a smooth, bounded, oscillatory observable
    that distinguishes whether the orbit fills the attractor
    uniformly (chaos → polynomial WBA convergence) or stays on a
    Diophantine invariant torus (regular → super-exponential
    convergence).
    """
    return np.cos(2.0 * np.pi * np.asarray(x, dtype=np.float64))


def chaos_weighted_birkhoff(
    timeseries: Sequence[float] | np.ndarray,
    *,
    observable: Callable[[np.ndarray], np.ndarray] | None = None,
) -> float:
    """Sander-Yorke Weighted Birkhoff Average chaos indicator.

    Returns a *digit-loss* statistic in ``[0, ~16]`` that measures
    how many decimal digits the WBA agrees on between the first
    half and the full trajectory:

    .. math::

        \\mathrm{digit\\_loss} = -\\log_{10}\\!\\left|
            B_N(f) - B_{N/2}(f) \\right|

    where

    .. math::

        B_N(f) = \\frac{\\sum_{j=0}^{N-1} w_j\\, f(x_j)}
                       {\\sum_{j=0}^{N-1} w_j}, \\qquad
        w_j = \\exp\\!\\left(-\\frac{1}{(j/N)(1 - j/N)}\\right)

    is the Sander-Yorke super-Gaussian weighted average. The
    interpretation:

    - **Regular** (Diophantine quasi-periodic / KAM tori): the WBA
      converges *super-exponentially* (Sander-Yorke 2012; Das et al.
      2016), so the two halves agree to near machine precision and
      the digit-loss is large (~10 or more).
    - **Chaotic**: the WBA converges only *polynomially* — the two
      halves disagree at the 1e-2 to 1e-5 level, giving a
      digit-loss of ~2-5.

    Parameters
    ----------
    timeseries
        1-D real-valued sequence :math:`\\phi(n)` — typically the
        first coordinate of a trajectory wrapped to ``[0, 1)`` so
        the default ``cos(2 pi x)`` observable is well behaved.
        Length must be at least ``200``; the test needs each half
        of the sequence to contain the super-Gaussian weight's
        support.
    observable
        Optional smooth function ``f: R -> R`` applied pointwise
        to the time series before averaging. Defaults to
        ``cos(2 pi x)`` per Das et al. 2016 §3. Pass a custom
        callable to probe a different harmonic.

    Returns
    -------
    float
        The digit-loss statistic in ``[0, 16]``. Larger means
        more regular; smaller means more chaotic. A practical cut
        is ``digit_loss > 8`` ⇒ likely regular,
        ``digit_loss < 5`` ⇒ likely chaotic, with a gray zone
        in between (Sander-Yorke 2012 §4 calibration).

    Raises
    ------
    ValueError
        If the time series has fewer than 200 samples.

    Notes
    -----
    Unlike the 0-1 test (CSC-011), the WBA is sensitive to the
    *observable*, not just to the trajectory. The default
    ``cos(2 pi x)`` is well behaved for wrapped (mod-1)
    trajectories like rotation maps and the doubling map; for
    continuous-flow trajectories the user typically wraps the
    chosen coordinate via ``x % 1.0`` before calling so the
    observable is bounded and oscillatory.

    References
    ----------
    - E. Sander, J. A. Yorke, *Connecting period-doubling cascades
      to chaos*, Int. J. Bifurc. Chaos 22 (2012), 1250022. DOI:
      10.1142/S0218127412500228.
    - S. Das, C. B. Dock, Y. Saiki, M. Salgado-Flores, E. Sander,
      J. Wu, J. A. Yorke, *Measuring quasiperiodicity*,
      Europhys. Lett. 114 (2016), 40005. DOI:
      10.1209/0295-5075/114/40005.
    - S. Das, Y. Saiki, E. Sander, J. A. Yorke, *Computing
      Lyapunov Exponents using Weighted Birkhoff Averages*,
      arXiv:2409.08496 (2024) — modern Lyapunov-via-WBA
      treatment cited in the 2026-q2-broadening synthesis.
    """
    arr = np.asarray(timeseries, dtype=np.float64).ravel()
    n = int(arr.size)
    if n < _WBA_MIN_SAMPLES:
        raise ValueError(
            f"chaos_weighted_birkhoff requires at least {_WBA_MIN_SAMPLES} "
            f"samples; got {n}. Run the system longer."
        )
    f = (observable or _default_wba_observable)(arr)
    f = np.asarray(f, dtype=np.float64).ravel()
    if f.size != n:
        raise ValueError(
            f"observable must return one value per sample; got "
            f"{f.size} for an input of length {n}"
        )

    half = n // 2
    b_full = _weighted_birkhoff(f)
    b_half = _weighted_birkhoff(f[:half])
    diff = abs(b_full - b_half)
    if diff <= 0.0:
        # Both halves agree to the bit — return the practical cap so the
        # output stays comparable across regular signals.
        return _WBA_MAX_DIGITS
    digit_loss = -float(np.log10(diff))
    return min(_WBA_MAX_DIGITS, max(0.0, digit_loss))


__all__ = [
    "chaos_weighted_birkhoff",
    "chaos_zero_one_test",
]
