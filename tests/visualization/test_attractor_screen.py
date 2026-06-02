"""Tests for the (a, b) Lyapunov screening sweep (CSC-004).

Pinned observables:

- ``lyapunov_grid`` returns ``(grid, grid)`` exponent + spread fields.
- A 1x1 grid reproduces the scalar CSC-003 estimator (the vectorized form is
  the same Benettin algorithm), anchoring this to the Henon-validated estimator.
- **The proposal's observable:** the screening classifier (sign of the largest
  exponent) agrees with a 20-sample hand-labelled chaotic/quiet validation set
  to >= 90%. The labels were fixed by a precise single-point estimate
  (n=30000); the points are chosen well clear of the chaos/order boundary.
- The degeneracy guard rejects collapsed point attractors: Conradi's canonical
  art point (5.46, 4.55) collapses to a fixed point (spread ~ 0) and is both
  non-chaotic and degenerate.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.core.lyapunov import largest_lyapunov_discrete
from chaotic_systems.systems.conradi import ConradiMap
from chaotic_systems.visualization import attractor_screen as scr

# Hand-labelled validation set. Labels fixed by largest_lyapunov_discrete at
# n=30000; points chosen with |lambda_1| comfortably off zero (chaotic > 0.15,
# quiet < -0.10) so a coarse screening budget classifies them robustly.
_CHAOTIC: tuple[tuple[float, float], ...] = (
    (0.5607, 1.0849), (2.2583, 1.0245), (0.6035, 2.0416), (2.4177, 0.9629),
    (3.6215, 4.2843), (3.5689, 4.4539), (0.6126, 1.7937), (3.6574, 4.9417),
    (3.7300, 4.3532), (0.4642, 1.6404),
)
_QUIET: tuple[tuple[float, float], ...] = (
    (0.8078, 3.1371), (2.3185, 3.2132), (0.8669, 4.9514), (2.2197, 3.7171),
    (1.4784, 5.0404), (5.4496, 0.8090), (2.9347, 1.7414), (0.5222, 5.6294),
    (5.6639, 1.3644), (0.2078, 1.2615),
)

# Conradi's canonical art parameters (verbatim from Nice_orbits.ipynb).
_ART_A, _ART_B = 5.46, 4.55


def _screen_point(a: float, b: float) -> float:
    """Largest exponent at a single (a, b) via a 1x1 screening grid."""
    lle, _ = scr.lyapunov_grid(1, a_range=(a, a), b_range=(b, b))
    return float(lle[0, 0])


def test_grid_shapes() -> None:
    lle, spread = scr.lyapunov_grid(16, n=200, n_transient=50)
    assert lle.shape == (16, 16)
    assert spread.shape == (16, 16)
    assert np.all(np.isfinite(lle))
    assert np.all(spread >= 0.0)


def test_single_cell_matches_scalar_estimator() -> None:
    """A 1x1 grid reproduces largest_lyapunov_discrete (same Benettin algo)."""
    a, b = 3.9, 4.6
    m = ConradiMap()
    scalar = largest_lyapunov_discrete(
        lambda y: m.step(y, a=a, b=b),
        lambda y: m.jacobian(y, a=a, b=b),
        np.array([0.1, 0.1]),
        n=20_000,
        n_transient=3_000,
    )
    grid_lle, _ = scr.lyapunov_grid(
        1, n=20_000, n_transient=3_000, a_range=(a, a), b_range=(b, b)
    )
    assert float(grid_lle[0, 0]) == pytest.approx(scalar, abs=0.03)


def test_screening_agrees_with_hand_labels() -> None:
    """The >=90% observable: screening sign vs the 20-sample validation set."""
    agree = 0
    for a, b in _CHAOTIC:
        agree += _screen_point(a, b) > 0.0
    for a, b in _QUIET:
        agree += _screen_point(a, b) <= 0.0
    total = len(_CHAOTIC) + len(_QUIET)
    assert agree / total >= 0.90, f"only {agree}/{total} agreed"


def test_degeneracy_guard_rejects_art_fixed_point() -> None:
    """Canonical art (5.46, 4.55): collapses to a fixed point, flagged degenerate.

    A single orbit there is periodic/fixed (lambda_1 <= 0) with near-zero spread,
    so it is NOT in the interesting (chaotic, non-degenerate) mask -- the density
    art comes from the lattice transient, not a chaotic attractor (CSC-003).
    """
    lle, spread = scr.lyapunov_grid(
        1, a_range=(_ART_A, _ART_A), b_range=(_ART_B, _ART_B)
    )
    assert float(lle[0, 0]) <= 0.0
    assert float(spread[0, 0]) < scr.SPREAD_FLOOR
    mask = scr.interesting_mask(lle, spread)
    assert not bool(mask[0, 0])


def test_interesting_mask_combines_lle_and_spread() -> None:
    lle = np.array([[0.2, 0.2], [-0.1, 0.2]])
    spread = np.array([[0.5, 1e-6], [0.5, 0.5]])
    mask = scr.interesting_mask(lle, spread)
    # (0,0): chaotic + spread -> True. (0,1): chaotic but collapsed -> False.
    # (1,0): not chaotic -> False. (1,1): chaotic + spread -> True.
    assert mask.tolist() == [[True, False], [False, True]]


def test_full_grid_smoke() -> None:
    """The default screening grid runs and finds both chaotic and quiet cells."""
    lle, spread = scr.lyapunov_grid()
    assert lle.shape == (scr.DEFAULT_GRID, scr.DEFAULT_GRID)
    frac_chaotic = float((lle > 0.0).mean())
    assert 0.0 < frac_chaotic < 1.0


def test_invalid_args_raise() -> None:
    with pytest.raises(ValueError, match="grid must be"):
        scr.lyapunov_grid(0)
    with pytest.raises(ValueError, match="n must be"):
        scr.lyapunov_grid(8, n=0)


# --- CMP-004: per-map screening (step_fn / jacobian_push_fn) ---------------


def test_clifford_screening_reports_positive_lle() -> None:
    """Clifford screening at the canonical (-1.4, 1.6, 1.0, 0.7) is chaotic.

    Matches the CSC-008 observable (lambda_1 ~ 0.29) — confirms the vectorized
    Clifford step + Jacobian-push are wired correctly through lyapunov_grid.
    """
    step_fn, jacobian_push_fn = scr.clifford_screen_fns(1.0, 0.7)
    lle, spread = scr.lyapunov_grid(
        1,
        n=20_000,
        n_transient=3_000,
        a_range=(-1.4, -1.4),
        b_range=(1.6, 1.6),
        step_fn=step_fn,
        jacobian_push_fn=jacobian_push_fn,
    )
    assert float(lle[0, 0]) > 0.1
    assert float(spread[0, 0]) > scr.SPREAD_FLOOR  # non-degenerate


def test_clifford_screening_full_grid_finds_chaotic_and_quiet() -> None:
    step_fn, jacobian_push_fn = scr.clifford_screen_fns(1.0, 0.7)
    lle, _ = scr.lyapunov_grid(
        32,
        a_range=(-3.0, 3.0),
        b_range=(-3.0, 3.0),
        step_fn=step_fn,
        jacobian_push_fn=jacobian_push_fn,
    )
    assert lle.shape == (32, 32)
    assert 0.0 < float((lle > 0.0).mean()) < 1.0


def test_default_step_fn_is_conradi_unchanged() -> None:
    """step_fn=None reproduces the Conradi path (the chaotic anchor stays positive)."""
    explicit, _ = scr.lyapunov_grid(
        1, n=20_000, n_transient=3_000, a_range=(3.9, 3.9), b_range=(4.6, 4.6)
    )
    assert float(explicit[0, 0]) > 0.1  # Conradi (3.9, 4.6) is chaotic
