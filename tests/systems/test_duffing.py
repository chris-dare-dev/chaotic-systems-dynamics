"""Duffing system tests — added with V3 to cover ``.energy()``.

Reference observables for the energy method:

- ``E(x=0, v=0)`` = 0 (origin sits at the saddle of the standard
  double-well potential with ``alpha = -1``, ``beta = 1``).
- ``E(x=1, v=0)`` = -1/4 (well bottom; ``V(1) = -1/2 + 1/4 = -1/4``).
- ``E(x=0, v=1)`` = +1/2 (kinetic only).
- ``E(x=-1, v=0)`` == ``E(x=1, v=0)`` (symmetric well).
- ``E`` is conserved over time when ``gamma = delta = 0`` (the
  V3-conservation-overlay headline case).
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.systems import Duffing


def test_energy_at_saddle_is_zero() -> None:
    duf = Duffing()
    e = duf.energy(np.array([0.0, 0.0]))
    assert e == pytest.approx(0.0, abs=1e-12)


def test_energy_at_well_bottom_matches_canonical_value() -> None:
    """V(±1) = -1/2 + 1/4 = -1/4 with default alpha=-1, beta=1."""
    duf = Duffing()
    e_right = duf.energy(np.array([1.0, 0.0]))
    e_left = duf.energy(np.array([-1.0, 0.0]))
    assert e_right == pytest.approx(-0.25, abs=1e-12)
    assert e_left == pytest.approx(-0.25, abs=1e-12)


def test_energy_kinetic_only_at_origin() -> None:
    duf = Duffing()
    e = duf.energy(np.array([0.0, 1.0]))
    assert e == pytest.approx(0.5, abs=1e-12)


def test_energy_is_conserved_when_undriven_and_undamped() -> None:
    """gamma = delta = 0 → energy conservation up to integrator drift."""
    duf = Duffing()
    params = {
        "alpha": -1.0,
        "beta": 1.0,
        "delta": 0.0,
        "gamma": 0.0,
        "omega": 1.0,
    }
    traj = duf.simulate(
        (0.0, 50.0), dt=0.01, integrator="RK45", params=params
    )
    e0 = duf.energy(traj.y[0], params)
    drift = max(abs(duf.energy(y, params) - e0) for y in traj.y)
    denom = abs(e0) if abs(e0) > 1e-12 else 1.0
    assert drift / denom < 1e-3


def test_energy_accepts_param_overrides() -> None:
    """A non-default alpha/beta must flow into the potential term."""
    duf = Duffing()
    # alpha = +1, beta = 0 gives a simple harmonic oscillator E = 0.5(v² + x²).
    e = duf.energy(
        np.array([1.0, 1.0]),
        {"alpha": 1.0, "beta": 0.0, "delta": 0.0, "gamma": 0.0, "omega": 1.0},
    )
    assert e == pytest.approx(1.0, abs=1e-12)
