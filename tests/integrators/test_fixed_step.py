"""Tests for fixed-step integrators (RK4, Euler)."""

from __future__ import annotations

import warnings

import numpy as np
import pytest

from chaotic_systems.integrators import RK4, Euler, IntegratorDivergedError


def _harmonic_rhs(t: float, y: np.ndarray) -> np.ndarray:
    return np.array([y[1], -y[0]], dtype=np.float64)


def test_rk4_recovers_cosine() -> None:
    y0 = np.array([1.0, 0.0])
    traj = RK4.integrate(_harmonic_rhs, (0.0, 10.0), y0, dt=1e-3)
    # RK4 with dt=1e-3 over 10 units of time is comfortably below 1e-7 error.
    np.testing.assert_allclose(traj.y[:, 0], np.cos(traj.t), atol=1e-7)


def test_euler_diverges_more_than_rk4() -> None:
    y0 = np.array([1.0, 0.0])
    tr_rk = RK4.integrate(_harmonic_rhs, (0.0, 10.0), y0, dt=1e-2)
    tr_eu = Euler.integrate(_harmonic_rhs, (0.0, 10.0), y0, dt=1e-2)
    err_rk = float(np.max(np.abs(tr_rk.y[:, 0] - np.cos(tr_rk.t))))
    err_eu = float(np.max(np.abs(tr_eu.y[:, 0] - np.cos(tr_eu.t))))
    assert err_rk < err_eu


def test_fixed_step_requires_dt_or_n_points() -> None:
    y0 = np.array([1.0, 0.0])
    with pytest.raises(ValueError, match="require either"):
        RK4.integrate(_harmonic_rhs, (0.0, 1.0), y0)


def _lorenz_rhs(t: float, y: np.ndarray) -> np.ndarray:
    sigma, rho, beta = 10.0, 28.0, 8.0 / 3.0
    x, y_, z = y[0], y[1], y[2]
    return np.array(
        [sigma * (y_ - x), x * (rho - z) - y_, x * y_ - beta * z],
        dtype=np.float64,
    )


def test_euler_diverges_on_lorenz_raises_integrator_diverged_error() -> None:
    """Past the stability threshold, Euler on Lorenz must surface a
    clean exception — not a flood of overflow / invalid-value warnings.

    Empirically, Euler on canonical Lorenz with y0=(1,1,1) is stable
    up to dt≈0.02 and diverges from dt≈0.025 onward. We pick
    dt=0.05 to stay clearly past the threshold so this test is not
    flaky under floating-point variation across platforms.
    """

    y0 = np.array([1.0, 1.0, 1.0], dtype=np.float64)
    with warnings.catch_warnings():
        # If divergence detection regresses and the loop continues to
        # accumulate inf/nan, numpy will emit overflow warnings — turn
        # those into errors so the regression is loud.
        warnings.simplefilter("error", RuntimeWarning)
        with pytest.raises(IntegratorDivergedError) as info:
            Euler.integrate(_lorenz_rhs, (0.0, 40.0), y0, dt=0.05)

    err = info.value
    assert err.integrator == "Euler"
    assert err.step_index >= 0
    # Divergence at dt=0.05 lands well before t=40; this is a sanity
    # check that we caught it early, not a tight bound.
    assert err.t < 40.0
    assert "Euler" in str(err)


def test_rk4_handles_lorenz_dt_005_without_diverging() -> None:
    """RK4 at a dt that kills Euler is still stable on Lorenz — the
    regression we want to prevent is "RK4 falsely flagged as diverged"."""

    y0 = np.array([1.0, 1.0, 1.0], dtype=np.float64)
    traj = RK4.integrate(_lorenz_rhs, (0.0, 40.0), y0, dt=0.05)
    assert np.isfinite(traj.y).all()


def test_integrator_diverged_error_is_runtime_error() -> None:
    """The GUI worker has a generic RuntimeError fallback; subclassing
    keeps that path working for any caller that doesn't special-case
    IntegratorDivergedError yet."""

    assert issubclass(IntegratorDivergedError, RuntimeError)
