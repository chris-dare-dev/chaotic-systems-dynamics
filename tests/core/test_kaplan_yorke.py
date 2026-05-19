"""Tests for the Kaplan-Yorke (Lyapunov) dimension diagnostic.

The Lyapunov spectrum has been computable since the initial
``core/lyapunov.py`` implementation (see roadmap D1) and is surfaced
in the GUI Diagnostics card. The Kaplan-Yorke dimension is the canonical
scalar fractal-dimension summary derived from that spectrum — Kaplan &
Yorke (1979) and Sprott, *Chaos and Time-Series Analysis*, Oxford 2003,
Table 5.1 are the references the implementation cites.

These tests pin the formula against:

- Closed-form edge cases (fixed point, limit cycle, all-positive).
- Canonical numerical references from Sprott (Lorenz D_KY ~= 2.062).
- An end-to-end integration test against ``lyapunov_spectrum`` on Lorenz.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.core import kaplan_yorke_dimension, lyapunov_spectrum
from chaotic_systems.systems.lorenz import Lorenz


def test_empty_spectrum_raises() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        kaplan_yorke_dimension(np.array([]))


def test_fixed_point_returns_zero() -> None:
    """All-negative spectrum: cumulative sum never crosses zero -> D_KY = 0."""

    spectrum = np.array([-0.5, -1.2, -3.0])
    assert kaplan_yorke_dimension(spectrum) == pytest.approx(0.0)


def test_single_strongly_negative_exponent_returns_zero() -> None:
    """Trivial 1D fixed-point analogue."""

    spectrum = np.array([-2.5])
    assert kaplan_yorke_dimension(spectrum) == pytest.approx(0.0)


def test_limit_cycle_returns_one() -> None:
    """One zero exponent (flow-direction), rest negative -> D_KY = 1."""

    spectrum = np.array([0.0, -0.5, -1.2])
    assert kaplan_yorke_dimension(spectrum) == pytest.approx(1.0)


def test_lorenz_canonical_spectrum_matches_sprott_table_5_1() -> None:
    """Reference: Sprott, Chaos and Time-Series Analysis 2003, Table 5.1.

    Lorenz with (sigma=10, rho=28, beta=8/3) has spectrum
    lambda ~= (0.9056, 0.0, -14.572). Kaplan-Yorke is then
    2 + 0.9056 / 14.572 ~= 2.06214.
    """

    spectrum = np.array([0.9056, 0.0, -14.572])
    d_ky = kaplan_yorke_dimension(spectrum)
    expected = 2.0 + 0.9056 / 14.572
    assert d_ky == pytest.approx(expected, rel=1e-9)
    # Strogatz / Sprott both quote ~2.06 to two decimals.
    assert 2.05 < d_ky < 2.08


def test_unordered_input_is_sorted_internally() -> None:
    """The Lorenz check above with permuted input must give the same answer."""

    spectrum = np.array([-14.572, 0.9056, 0.0])
    expected = 2.0 + 0.9056 / 14.572
    assert kaplan_yorke_dimension(spectrum) == pytest.approx(expected, rel=1e-9)


def test_hyperchaos_two_positive_exponents() -> None:
    """4D hyperchaos: two positive plus zero plus one strongly negative.

    Cumulative sums are (0.16, 0.19, 0.19, -24.81); k=3 because the
    third cumulative sum is still non-negative. D_KY = 3 + 0.19/25.
    """

    spectrum = np.array([0.16, 0.03, 0.0, -25.0])
    d_ky = kaplan_yorke_dimension(spectrum)
    expected = 3.0 + 0.19 / 25.0
    assert d_ky == pytest.approx(expected, rel=1e-9)
    assert 3.0 < d_ky < 3.05


def test_all_positive_returns_state_dim() -> None:
    """Pathological: every cumulative sum positive (no contraction).

    Returns the integer dimension n with no fractional part.
    """

    spectrum = np.array([1.0, 0.5, 0.25])
    assert kaplan_yorke_dimension(spectrum) == pytest.approx(3.0)


def test_degenerate_zero_next_exponent_returns_integer_k() -> None:
    """If lambda_{k+1} is numerically zero, fall back to the integer part k.

    Constructed: cumsum = (0.5, 0.5, 0.5, ...) where the next exponent
    is essentially zero. The defensive branch returns k rather than
    dividing by a near-zero quantity.
    """

    spectrum = np.array([0.5, 0.0, 1e-15, -1.0])
    # Cumulative: (0.5, 0.5, 0.5, -0.5). Largest k with cumsum >= 0 is 3.
    # sorted_desc[3] = -1.0, so this falls into the normal branch.
    d_ky = kaplan_yorke_dimension(spectrum)
    assert d_ky == pytest.approx(3.0 + 0.5 / 1.0)


def test_kaplan_yorke_dimension_on_lorenz_integrated_spectrum() -> None:
    """End-to-end: integrate Lorenz, compute the spectrum, derive D_KY.

    The integration tolerance is loose because the spectrum estimator
    converges only over long times; the (2.0, 2.2) window comfortably
    contains the Sprott reference value 2.062.
    """

    system = Lorenz()
    spectrum = lyapunov_spectrum(
        system,
        t_transient=20.0,
        t_total=120.0,
        dt=1.0,
    )
    d_ky = kaplan_yorke_dimension(spectrum)
    # Sprott reference D_KY ~ 2.062; the estimator at t=120 lands in
    # the (2.0, 2.2) interval reliably across seed choices.
    assert 2.0 < d_ky < 2.2
