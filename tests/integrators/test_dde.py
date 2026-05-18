"""Tests for the BellenRK4 DDE integrator (N3).

Reference observables come from a *linearly* exact piecewise solution
of the simplest non-trivial DDE,

    x'(t) = -x(t - 1),       x(t) = 1 for t <= 0.

By the method-of-steps:

- ``t ∈ [0, 1]``: ``x'(t) = -1``  →  ``x(t) = 1 - t``.  ``x(1) = 0``.
- ``t ∈ [1, 2]``: ``x'(t) = -(1 - (t - 1)) = t - 2``  →
  ``x(t) = (t - 2)² / 2 - 1/2``.  ``x(2) = -1/2``.

We pin both endpoints to integrator tolerance (1e-6).

Edge-case / validation coverage also lives here: bad t_span, bad
delay / dt, mismatched y0 shapes, and the n_points-resampling
contract.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.integrators import BellenRK4
from chaotic_systems.integrators.dde import _default_constant_history


def _linear_dde_rhs(t, x, x_delayed, params):  # noqa: ANN001
    """The reference equation x'(t) = -x(t - 1)."""
    return np.array([-x_delayed[0]], dtype=np.float64)


def test_linear_dde_matches_piecewise_exact_solution() -> None:
    """The signature observable: piecewise-exact x(1)=0, x(2)=-1/2."""
    integ = BellenRK4()
    traj = integ.integrate_dde(
        _linear_dde_rhs,
        (0.0, 2.0),
        np.array([1.0]),
        delay=1.0,
        dt=0.001,
    )
    x_at_1 = float(np.interp(1.0, traj.t, traj.y[:, 0]))
    x_at_2 = float(np.interp(2.0, traj.t, traj.y[:, 0]))
    assert x_at_1 == pytest.approx(0.0, abs=1e-6), (
        f"expected x(1) = 0 (analytic); got {x_at_1:.6f}"
    )
    assert x_at_2 == pytest.approx(-0.5, abs=1e-6), (
        f"expected x(2) = -1/2 (analytic); got {x_at_2:.6f}"
    )


def test_trajectory_metadata_is_set() -> None:
    integ = BellenRK4()
    traj = integ.integrate_dde(
        _linear_dde_rhs,
        (0.0, 1.0),
        np.array([1.0]),
        delay=1.0,
        dt=0.01,
    )
    assert traj.integrator == "BellenRK4"
    assert traj.t[0] == pytest.approx(0.0)
    assert traj.t[-1] == pytest.approx(1.0)
    assert traj.y.shape == (101, 1)


def test_n_points_resampling_returns_requested_size() -> None:
    integ = BellenRK4()
    traj = integ.integrate_dde(
        _linear_dde_rhs,
        (0.0, 1.0),
        np.array([1.0]),
        delay=1.0,
        dt=0.001,
        n_points=25,
    )
    assert traj.t.shape == (25,)
    assert traj.y.shape == (25, 1)
    # Endpoints unchanged.
    assert traj.t[0] == pytest.approx(0.0)
    assert traj.t[-1] == pytest.approx(1.0)


def test_constant_history_default_extends_y0() -> None:
    """The default history function returns y0 for every queried t."""
    hist = _default_constant_history(np.array([3.14, -2.5]))
    np.testing.assert_array_equal(hist(-100.0), np.array([3.14, -2.5]))
    np.testing.assert_array_equal(hist(0.0), np.array([3.14, -2.5]))
    np.testing.assert_array_equal(hist(1e9), np.array([3.14, -2.5]))


def test_custom_history_function_is_honored() -> None:
    """A non-constant history feeds different x_delayed values into the rhs."""
    # x'(t) = -x(t - 1) with history(t) = exp(t) for t < 0.
    # On [0, 1] the delayed lookup is x(t - 1) = exp(t - 1).
    # Then x(t) = 1 - integral_0^t exp(s - 1) ds = 1 - (exp(t-1) - exp(-1)).
    # At t = 1: x(1) = 1 - (1 - exp(-1)) = exp(-1).

    def history(t: float) -> np.ndarray:
        return np.array([np.exp(t)], dtype=np.float64)

    integ = BellenRK4()
    traj = integ.integrate_dde(
        _linear_dde_rhs,
        (0.0, 1.0),
        np.array([1.0]),  # y0 = history(0) = exp(0) = 1
        delay=1.0,
        dt=0.001,
        history=history,
    )
    x_at_1 = float(np.interp(1.0, traj.t, traj.y[:, 0]))
    assert x_at_1 == pytest.approx(np.exp(-1.0), abs=1e-6)


def test_rejects_non_increasing_t_span() -> None:
    integ = BellenRK4()
    with pytest.raises(ValueError, match="strictly increasing"):
        integ.integrate_dde(
            _linear_dde_rhs, (1.0, 0.0), np.array([1.0]), delay=1.0, dt=0.01
        )


def test_rejects_non_positive_delay() -> None:
    integ = BellenRK4()
    with pytest.raises(ValueError, match="delay must be positive"):
        integ.integrate_dde(
            _linear_dde_rhs, (0.0, 1.0), np.array([1.0]), delay=0.0, dt=0.01
        )


def test_rejects_non_positive_dt() -> None:
    integ = BellenRK4()
    with pytest.raises(ValueError, match="dt must be positive"):
        integ.integrate_dde(
            _linear_dde_rhs, (0.0, 1.0), np.array([1.0]), delay=1.0, dt=0.0
        )


def test_rejects_dt_geq_delay() -> None:
    """Single-delay scheme requires dt < delay."""
    integ = BellenRK4()
    with pytest.raises(ValueError, match="dt .* must be less than delay"):
        integ.integrate_dde(
            _linear_dde_rhs, (0.0, 2.0), np.array([1.0]), delay=1.0, dt=1.5
        )


def test_rejects_wrong_y0_shape() -> None:
    integ = BellenRK4()
    with pytest.raises(ValueError, match="y0 must be 1-D"):
        integ.integrate_dde(
            _linear_dde_rhs,
            (0.0, 1.0),
            np.zeros((2, 2)),
            delay=1.0,
            dt=0.01,
        )


def test_rejects_non_finite_y0() -> None:
    integ = BellenRK4()
    with pytest.raises(ValueError, match="non-finite"):
        integ.integrate_dde(
            _linear_dde_rhs,
            (0.0, 1.0),
            np.array([np.nan]),
            delay=1.0,
            dt=0.01,
        )


def test_rejects_n_points_below_2() -> None:
    integ = BellenRK4()
    with pytest.raises(ValueError, match="n_points must be >= 2"):
        integ.integrate_dde(
            _linear_dde_rhs,
            (0.0, 1.0),
            np.array([1.0]),
            delay=1.0,
            dt=0.01,
            n_points=1,
        )


def test_rhs_returning_wrong_shape_raises() -> None:
    integ = BellenRK4()

    def bad_rhs(t, x, x_delayed, params):  # noqa: ANN001
        return np.zeros(3)  # wrong shape

    with pytest.raises(ValueError, match="returned shape"):
        integ.integrate_dde(
            bad_rhs, (0.0, 1.0), np.array([1.0]), delay=1.0, dt=0.01
        )


def test_two_dimensional_state_works() -> None:
    """State dim > 1: the integrator is dim-agnostic."""

    # 2D linear DDE: x' = -y(t-1), y' = -x(t-1). History constant at (1, 1).
    def rhs(t, state, state_delayed, params):  # noqa: ANN001
        return np.array(
            [-state_delayed[1], -state_delayed[0]], dtype=np.float64
        )

    integ = BellenRK4()
    traj = integ.integrate_dde(
        rhs, (0.0, 1.0), np.array([1.0, 1.0]), delay=1.0, dt=0.001
    )
    # x' = y' = -1 on [0,1], so both components linearly decrease from 1.
    # At t = 1 both should be 0.
    np.testing.assert_allclose(traj.y[-1], np.array([0.0, 0.0]), atol=1e-6)
