"""Tests for the symbolic Hamiltonian pipeline."""

from __future__ import annotations

import numpy as np
import sympy as sp

from chaotic_systems.core.hamiltonian import HamiltonianSystem


def test_harmonic_oscillator_separable() -> None:
    """1-DOF harmonic oscillator: H = p^2/2 + omega^2 q^2 / 2."""
    t, q, p, omega = sp.symbols("t q p omega", real=True)
    T = sp.Rational(1, 2) * p**2
    V = sp.Rational(1, 2) * omega**2 * q**2
    H = T + V

    sys = HamiltonianSystem(
        q_syms=(q,),
        p_syms=(p,),
        time=t,
        hamiltonian=H,
        kinetic=T,
        potential=V,
        params=(omega,),
    )
    assert sys.separable
    assert sys.state_dim == 2

    state = np.array([1.0, 0.5], dtype=np.float64)
    dy = sys.rhs(0.0, state, params={omega: 2.0})
    # qdot = p = 0.5
    # pdot = -omega^2 q = -4
    np.testing.assert_allclose(dy, [0.5, -4.0])

    # Energy conserved by definition at the initial state:
    e = sys.energy(state, params={omega: 2.0})
    assert e == 0.5 * 0.25 + 0.5 * 4.0 * 1.0

    # grad_T and grad_V available.
    assert sys.grad_T(np.array([0.5]), params={omega: 2.0})[0] == 0.5
    assert sys.grad_V(np.array([1.0]), params={omega: 2.0})[0] == 4.0


def test_non_separable_raises() -> None:
    t, q, p = sp.symbols("t q p", real=True)
    # H mixes q and p in T — should refuse separable construction.
    T = sp.Rational(1, 2) * p**2 + q * p
    V = sp.Rational(1, 2) * q**2
    H = T + V

    import pytest

    with pytest.raises(ValueError, match="kinetic depends on q"):
        HamiltonianSystem(
            q_syms=(q,),
            p_syms=(p,),
            time=t,
            hamiltonian=H,
            kinetic=T,
            potential=V,
        )
