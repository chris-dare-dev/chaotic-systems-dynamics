"""Scalar chaos indicators that wrap on a single trajectory column.

This module is the home for "trajectory-in, scalar-out" diagnostic
functions that, unlike :func:`~chaotic_systems.core.lyapunov.lyapunov_spectrum`,
operate on a 1-D projection of the trajectory (e.g. just ``x(t)`` of
Lorenz) and return a single number summarising the regime. The first
inhabitant is the Gottwald-Melbourne **0-1 test for chaos** (CSC-011);
follow-up candidates from the 2026-q2-broadening capability-scout —
weighted Birkhoff average (CSC-012), permutation entropy (CSC-013),
Hurst exponent (CSC-014) — will slot in here behind the same shape.

References (for this module overall)
------------------------------------
- G. A. Gottwald, I. Melbourne, *On the Implementation of the 0-1 Test
  for Chaos*, SIAM J. Appl. Dyn. Sys. 8 (2009), 129-145. DOI:
  10.1137/080718851. arXiv:0906.1418. — the canonical implementation
  guide cited verbatim in :func:`chaos_zero_one_test` below.
- C. Bandt, B. Pompe, *Permutation entropy: A natural complexity measure
  for time series*, Phys. Rev. Lett. 88 (2002), 174102. — pending
  CSC-013.
- J. C. Sprott, *Chaos and Time-Series Analysis*, Oxford University
  Press, 2003, ch. 5 — overall pedagogical context for scalar chaos
  indicators.
"""

from __future__ import annotations

from collections.abc import Sequence

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


__all__ = ["chaos_zero_one_test"]
