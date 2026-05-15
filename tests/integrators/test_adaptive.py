"""Tests for adaptive scipy-wrapped integrators."""

from __future__ import annotations

import numpy as np

from chaotic_systems.integrators import (
    BDF,
    DOP853,
    LSODA,
    RK23,
    RK45,
    Radau,
    get_integrator,
    list_integrators,
)


def _harmonic_rhs(t: float, y: np.ndarray) -> np.ndarray:
    return np.array([y[1], -y[0]], dtype=np.float64)


def test_registry_lists_all_integrators() -> None:
    names = list_integrators()
    for required in [
        "RK45",
        "RK23",
        "DOP853",
        "Radau",
        "BDF",
        "LSODA",
        "RK4",
        "Euler",
        "leapfrog",
        "velocity_verlet",
        "yoshida4",
    ]:
        assert required in names


def test_get_integrator_unknown() -> None:
    import pytest

    with pytest.raises(KeyError, match="unknown integrator"):
        get_integrator("bogus")


def test_all_adaptive_integrate_harmonic_oscillator() -> None:
    """Every scipy method recovers cos(t) on a 0..2pi span to ~1e-5."""
    y0 = np.array([1.0, 0.0])
    for integ in (RK45, RK23, DOP853, Radau, BDF, LSODA):
        traj = integ.integrate(
            _harmonic_rhs,
            (0.0, 2.0 * np.pi),
            y0,
            n_points=101,
            rtol=1e-9,
            atol=1e-12,
        )
        assert traj.integrator == integ.name
        np.testing.assert_allclose(traj.y[:, 0], np.cos(traj.t), atol=1e-5)
        np.testing.assert_allclose(traj.y[:, 1], -np.sin(traj.t), atol=1e-5)


def test_adaptive_with_dt_grid() -> None:
    y0 = np.array([1.0, 0.0])
    traj = RK45.integrate(_harmonic_rhs, (0.0, 1.0), y0, dt=0.1, rtol=1e-10, atol=1e-12)
    # Grid should be roughly 0, 0.1, 0.2, ..., 1.0
    assert traj.t.shape[0] == 11
    np.testing.assert_allclose(traj.t, np.linspace(0.0, 1.0, 11))
