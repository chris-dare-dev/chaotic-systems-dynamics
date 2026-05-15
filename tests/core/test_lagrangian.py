"""Tests for the symbolic Lagrangian -> numerical ODE pipeline.

The canonical sanity check: the simple pendulum :math:`L = \\tfrac{1}{2}
m l^2 \\dot\\theta^2 + m g l \\cos\\theta` should produce the ODE
:math:`\\ddot\\theta = -(g/l) \\sin\\theta`.
"""

from __future__ import annotations

import numpy as np
import sympy as sp

from chaotic_systems.core.lagrangian import LagrangianSystem


def test_simple_pendulum_matches_analytic_ode() -> None:
    t = sp.symbols("t", real=True)
    theta = sp.Function("theta")
    m, length, g = sp.symbols("m l g", positive=True)
    th = theta(t)
    thd = sp.diff(th, t)
    L = sp.Rational(1, 2) * m * length**2 * thd**2 + m * g * length * sp.cos(th)

    sys = LagrangianSystem(
        coords=(theta,), time=t, lagrangian=L, params=(m, length, g)
    )
    assert sys.state_dim == 2

    # Pick concrete numbers.
    m_val, l_val, g_val = 2.0, 0.5, 9.81
    # State y = [theta, theta_dot]
    for th_val, thd_val in [
        (0.1, 0.0),
        (0.5, 0.3),
        (-0.7, 0.2),
        (1.2, -0.4),
    ]:
        y = np.array([th_val, thd_val], dtype=np.float64)
        dy = sys.rhs(0.0, y, params={m: m_val, length: l_val, g: g_val})
        # dy[0] should be thd_val (definition of state).
        assert dy[0] == thd_val
        # dy[1] should equal -(g/l) sin(theta).
        expected = -(g_val / l_val) * np.sin(th_val)
        assert abs(dy[1] - expected) < 1e-12


def test_simple_pendulum_string_params() -> None:
    """Parameter values may be passed by symbol *or* string name."""
    t = sp.symbols("t", real=True)
    theta = sp.Function("theta")
    g = sp.symbols("g", positive=True)
    th = theta(t)
    thd = sp.diff(th, t)
    L = sp.Rational(1, 2) * thd**2 + g * sp.cos(th)
    sys = LagrangianSystem(coords=(theta,), time=t, lagrangian=L, params=(g,))
    y = np.array([0.1, 0.0])
    via_sym = sys.rhs(0.0, y, params={g: 9.81})
    via_str = sys.rhs(0.0, y, params={"g": 9.81})
    np.testing.assert_allclose(via_sym, via_str)


def test_lagrangian_latex_cache() -> None:
    t = sp.symbols("t", real=True)
    theta = sp.Function("theta")
    L = sp.Rational(1, 2) * sp.diff(theta(t), t) ** 2 - sp.cos(theta(t))
    sys = LagrangianSystem(coords=(theta,), time=t, lagrangian=L, params=())
    s1 = sys.lagrangian_latex()
    s2 = sys.lagrangian_latex()
    assert s1 == s2  # cached
    # Loosely check that the LaTeX mentions theta.
    assert "theta" in s1.lower() or "\\theta" in s1 or r"\theta" in s1
