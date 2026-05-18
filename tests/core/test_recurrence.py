"""Tests for the recurrence matrix + RQA scalars (D5).

Reference observables drawn straight from Marwan et al. (2007) §3:

- **Periodic orbit** — unit circle ``(cos t, sin t)`` over two
  periods: DET ≈ 1.0 (every recurrence on a diagonal stripe), LAM
  ≈ 1.0, L_max close to the trajectory length. The hallmark of a
  fully deterministic, fully laminar dynamic.
- **White noise** — IID Gaussian samples: DET ≪ 1, LAM ≪ 1, L_max
  small. The hallmark of a stochastic process.
- **Constant trajectory** — every state identical: RR = 1, DET = 1,
  L_max = N. Degenerate but useful as a sanity floor.

Plus shape / validation / utility coverage on
``suggest_epsilon`` and the matrix builder.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.core import (
    RQAStats,
    recurrence_matrix,
    rqa,
    suggest_epsilon,
)


def _periodic_orbit(n: int = 200, periods: float = 2.0) -> np.ndarray:
    """Sampled unit circle — the cleanest periodic test case."""
    t = np.linspace(0.0, 2 * np.pi * periods, n)
    return np.column_stack([np.cos(t), np.sin(t)])


def _white_noise(n: int = 200, d: int = 2, seed: int = 0) -> np.ndarray:
    """IID standard-normal noise — the cleanest stochastic test case."""
    rng = np.random.default_rng(seed)
    return rng.standard_normal((n, d))


def test_recurrence_matrix_is_symmetric_and_square() -> None:
    traj = _periodic_orbit()
    matrix = recurrence_matrix(traj, epsilon=0.1)
    assert matrix.shape == (200, 200)
    assert matrix.dtype == bool
    np.testing.assert_array_equal(matrix, matrix.T)


def test_recurrence_matrix_diagonal_is_true() -> None:
    """Every state is within epsilon of itself."""
    traj = _periodic_orbit()
    matrix = recurrence_matrix(traj, epsilon=0.1)
    assert np.diag(matrix).all()


def test_periodic_orbit_has_near_unit_determinism() -> None:
    """The signature observable: pure periodic dynamics → DET ≈ 1.0."""
    traj = _periodic_orbit(n=200, periods=2.0)
    eps = suggest_epsilon(traj, fraction=0.05)
    matrix = recurrence_matrix(traj, epsilon=eps)
    stats = rqa(matrix, l_min=2, v_min=2)
    assert isinstance(stats, RQAStats)
    assert stats.det > 0.95, (
        f"expected DET > 0.95 on the periodic unit circle; got {stats.det:.4f}"
    )
    assert stats.lam > 0.95, (
        f"expected LAM > 0.95 on the periodic unit circle; got {stats.lam:.4f}"
    )
    # L_max for two complete periods should be very close to the
    # trajectory length (the diagonal stripe wraps the whole orbit).
    assert stats.l_max > 150, (
        f"expected L_max > 150 (most of N=200); got {stats.l_max}"
    )


def test_white_noise_has_low_determinism() -> None:
    """The other side of the observable: stochastic dynamics → DET ≪ 1."""
    traj = _white_noise(n=200)
    eps = suggest_epsilon(traj, fraction=0.05)
    matrix = recurrence_matrix(traj, epsilon=eps)
    stats = rqa(matrix, l_min=2, v_min=2)
    assert stats.det < 0.35, (
        f"expected DET < 0.35 on white noise; got {stats.det:.4f}"
    )
    # Largest diagonal should be tiny (random chance run of recurrences).
    assert stats.l_max < 10


def test_constant_trajectory_saturates_rqa() -> None:
    """Degenerate case: every state identical → RR = 1, DET = 1, L_max = N.

    Uses ``l_min = 1`` so the corner diagonals of length 1 contribute
    to DET (with the default ``l_min = 2`` they would be filtered out
    and DET would land at ``2448 / 2450 ≈ 0.99918`` for N = 50).
    """
    traj = np.tile(np.array([1.0, 2.0]), (50, 1))
    matrix = recurrence_matrix(traj, epsilon=1e-9)
    assert matrix.all()
    stats = rqa(matrix, l_min=1, v_min=1)
    assert stats.rr == pytest.approx(1.0)
    assert stats.det == pytest.approx(1.0)
    # L_max excludes the line of identity, so the next-longest
    # diagonal is the k = ±1 off-diagonal of length N - 1.
    assert stats.l_max == 49
    # V_max counts every column including the LOI's contribution,
    # so the full column run of length N stays.
    assert stats.v_max == 50


def test_theiler_window_masks_diagonal_band() -> None:
    traj = _periodic_orbit(n=50, periods=1.0)
    matrix = recurrence_matrix(traj, epsilon=0.5, theiler=3)
    # The (i, j) entries with |i - j| < 3 must all be False.
    for i in range(50):
        for j in range(50):
            if abs(i - j) < 3:
                assert matrix[i, j] is np.False_ or matrix[i, j] == 0


def test_max_norm_differs_from_euclidean() -> None:
    """``norm='maximum'`` is the L∞ Chebyshev variant; should give a
    *different* matrix from the L2 default."""
    traj = _periodic_orbit(n=50)
    eps = suggest_epsilon(traj, fraction=0.1)
    m_eucl = recurrence_matrix(traj, epsilon=eps, norm="euclidean")
    m_max = recurrence_matrix(traj, epsilon=eps, norm="maximum")
    assert not np.array_equal(m_eucl, m_max)
    # And both must contain the diagonal.
    assert np.diag(m_eucl).all()
    assert np.diag(m_max).all()


def test_recurrence_matrix_validates_epsilon() -> None:
    traj = _periodic_orbit(n=50)
    with pytest.raises(ValueError, match="epsilon"):
        recurrence_matrix(traj, epsilon=0.0)
    with pytest.raises(ValueError, match="epsilon"):
        recurrence_matrix(traj, epsilon=-0.5)


def test_recurrence_matrix_validates_theiler() -> None:
    traj = _periodic_orbit(n=50)
    with pytest.raises(ValueError, match="theiler"):
        recurrence_matrix(traj, epsilon=0.1, theiler=-1)


def test_recurrence_matrix_validates_norm() -> None:
    traj = _periodic_orbit(n=50)
    with pytest.raises(ValueError, match="unknown norm"):
        recurrence_matrix(traj, epsilon=0.1, norm="bogus")  # type: ignore[arg-type]


def test_recurrence_matrix_rejects_short_trajectory() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        recurrence_matrix(np.array([[0.0, 0.0]]), epsilon=0.1)


def test_recurrence_matrix_rejects_non_finite() -> None:
    traj = _periodic_orbit(n=50)
    traj[10, 0] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        recurrence_matrix(traj, epsilon=0.1)


def test_recurrence_matrix_accepts_duck_typed_trajectory() -> None:
    class _Stub:
        y = np.column_stack([np.cos(np.linspace(0, 6.28, 30)),
                              np.sin(np.linspace(0, 6.28, 30))])

    matrix = recurrence_matrix(_Stub(), epsilon=0.1)
    assert matrix.shape == (30, 30)


def test_rqa_validates_matrix_shape() -> None:
    with pytest.raises(ValueError, match="square"):
        rqa(np.zeros((3, 4), dtype=bool))


def test_rqa_validates_thresholds() -> None:
    m = np.zeros((5, 5), dtype=bool)
    with pytest.raises(ValueError, match="l_min"):
        rqa(m, l_min=0)
    with pytest.raises(ValueError, match="v_min"):
        rqa(m, v_min=0)


def test_rqa_l_min_threshold_filters_short_diagonals() -> None:
    """Raising l_min must lower DET because shorter diagonals stop counting."""
    traj = _periodic_orbit(n=100, periods=3.0)
    matrix = recurrence_matrix(traj, epsilon=0.3)
    s_low = rqa(matrix, l_min=2)
    s_high = rqa(matrix, l_min=10)
    assert s_high.det <= s_low.det


def test_rqa_entr_is_zero_for_exactly_periodic_signal() -> None:
    """Marwan §3.5: a strictly periodic orbit with one diagonal length
    has ENTR = 0.

    Build an exactly-periodic discrete signal: 200 samples placed at
    ``t_i = i * 2π / 100``, so sample at index ``i`` coincides
    with sample at ``i + 100`` (exact repeat after the second period
    completes). The recurrence matrix at any small positive epsilon
    then has exactly two diagonals (k = ±100) of length 100 — one
    length value, ``ENTR = -1 * ln(1) = 0``.
    """
    n_per_period = 100
    n_periods = 2
    n = n_per_period * n_periods
    t = np.arange(n) * 2 * np.pi / n_per_period
    traj = np.column_stack([np.cos(t), np.sin(t)])
    matrix = recurrence_matrix(traj, epsilon=1e-9)
    stats = rqa(matrix, l_min=2)
    assert stats.entr == pytest.approx(0.0, abs=1e-12), (
        f"expected ENTR ≈ 0 for exactly-periodic signal; got {stats.entr:.6f}"
    )
    # And L_max should be exactly the period-stripe length.
    assert stats.l_max == n_per_period


def test_suggest_epsilon_scales_with_bbox() -> None:
    """Doubling the trajectory scale doubles the suggested epsilon."""
    traj = _periodic_orbit(n=50)
    eps1 = suggest_epsilon(traj, fraction=0.1)
    eps2 = suggest_epsilon(traj * 10.0, fraction=0.1)
    assert eps2 == pytest.approx(eps1 * 10.0)


def test_suggest_epsilon_handles_constant_trajectory() -> None:
    """Zero-diameter trajectory falls back to a tiny positive default."""
    traj = np.ones((20, 3))
    eps = suggest_epsilon(traj)
    assert eps > 0.0
    assert eps < 1e-6


def test_suggest_epsilon_validates_fraction() -> None:
    traj = _periodic_orbit(n=20)
    with pytest.raises(ValueError, match="fraction"):
        suggest_epsilon(traj, fraction=0.0)
    with pytest.raises(ValueError, match="fraction"):
        suggest_epsilon(traj, fraction=1.5)
