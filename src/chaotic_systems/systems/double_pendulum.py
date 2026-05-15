"""Double pendulum — built from a sympy Lagrangian.

Two point masses :math:`m_1, m_2` on massless rods of length
:math:`l_1, l_2` swinging in a vertical plane under gravity :math:`g`.
Let :math:`\\theta_1, \\theta_2` be the angles from the downward
vertical of the two rods.

Cartesian positions:

.. math::

    x_1 &= l_1 \\sin\\theta_1, & y_1 &= -l_1 \\cos\\theta_1, \\\\
    x_2 &= x_1 + l_2 \\sin\\theta_2, & y_2 &= y_1 - l_2 \\cos\\theta_2.

Kinetic energy:

.. math::

    T = \\tfrac{1}{2} m_1 (\\dot x_1^2 + \\dot y_1^2)
      + \\tfrac{1}{2} m_2 (\\dot x_2^2 + \\dot y_2^2)
      = \\tfrac{1}{2}(m_1 + m_2) l_1^2 \\dot\\theta_1^2
      + \\tfrac{1}{2} m_2 l_2^2 \\dot\\theta_2^2
      + m_2 l_1 l_2 \\dot\\theta_1 \\dot\\theta_2 \\cos(\\theta_1 - \\theta_2).

Potential energy (taking the pivot as zero):

.. math::

    V = -(m_1 + m_2) g l_1 \\cos\\theta_1 - m_2 g l_2 \\cos\\theta_2.

Lagrangian :math:`L = T - V`. The Euler-Lagrange equations are derived
symbolically by :class:`~chaotic_systems.core.LagrangianSystem` — we
don't hand-code :math:`\\ddot\\theta_1, \\ddot\\theta_2`. This is the
core demonstration of the symbolic-to-numeric pipeline.

References
----------
- L. D. Landau, E. M. Lifshitz, *Mechanics* (3rd ed.), Pergamon 1976 —
  derivation of the Lagrangian.
- T. Stachowiak, T. Okada, *A numerical analysis of chaos in the double
  pendulum*, Chaos, Solitons & Fractals 29 (2006), 417-422.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import cached_property

import numpy as np
import sympy as sp

from chaotic_systems.core.base import DynamicalSystem, FloatArray, Parameter
from chaotic_systems.core.lagrangian import LagrangianSystem


class DoublePendulum(DynamicalSystem):
    """Double pendulum derived from a sympy Lagrangian."""

    name = "DoublePendulum"
    latex = (
        r"\begin{aligned}T &= \tfrac{1}{2}(m_1+m_2) l_1^2 \dot\theta_1^2 "
        r"+ \tfrac{1}{2} m_2 l_2^2 \dot\theta_2^2 "
        r"+ m_2 l_1 l_2 \dot\theta_1 \dot\theta_2 \cos(\theta_1-\theta_2)\\"
        r"V &= -(m_1+m_2) g l_1 \cos\theta_1 - m_2 g l_2 \cos\theta_2\\"
        r"L &= T - V\end{aligned}"
    )
    lagrangian_latex = (
        r"L = \tfrac{1}{2}(m_1+m_2) l_1^2 \dot\theta_1^2 "
        r"+ \tfrac{1}{2} m_2 l_2^2 \dot\theta_2^2 "
        r"+ m_2 l_1 l_2 \dot\theta_1 \dot\theta_2 \cos(\theta_1-\theta_2) "
        r"+ (m_1+m_2) g l_1 \cos\theta_1 + m_2 g l_2 \cos\theta_2"
    )
    state_dim = 4  # [theta1, theta2, theta1_dot, theta2_dot]
    parameters = {
        "m1": Parameter("m1", 1.0, 0.01, 10.0, "upper-bob mass", "kg"),
        "m2": Parameter("m2", 1.0, 0.01, 10.0, "lower-bob mass", "kg"),
        "l1": Parameter("l1", 1.0, 0.01, 10.0, "upper-rod length", "m"),
        "l2": Parameter("l2", 1.0, 0.01, 10.0, "lower-rod length", "m"),
        "g": Parameter("g", 9.81, 0.0, 25.0, "gravitational acceleration", "m/s^2"),
    }
    # Mildly off vertical so it actually swings.
    default_initial_state = np.array(
        [2.0, 2.5, 0.0, 0.0], dtype=np.float64
    )

    @cached_property
    def _lsys(self) -> LagrangianSystem:
        """Build the symbolic LagrangianSystem once and cache it."""
        t = sp.symbols("t", real=True)
        theta1 = sp.Function("theta1")
        theta2 = sp.Function("theta2")
        m1, m2, l1, l2, g = sp.symbols("m1 m2 l1 l2 g", positive=True)
        th1 = theta1(t)
        th2 = theta2(t)
        th1d = sp.diff(th1, t)
        th2d = sp.diff(th2, t)

        T = (
            sp.Rational(1, 2) * (m1 + m2) * l1**2 * th1d**2
            + sp.Rational(1, 2) * m2 * l2**2 * th2d**2
            + m2 * l1 * l2 * th1d * th2d * sp.cos(th1 - th2)
        )
        V = -(m1 + m2) * g * l1 * sp.cos(th1) - m2 * g * l2 * sp.cos(th2)
        L = T - V

        return LagrangianSystem(
            coords=(theta1, theta2),
            time=t,
            lagrangian=L,
            params=(m1, m2, l1, l2, g),
        )

    def _rhs(
        self, t: float, y: FloatArray, params: Mapping[str, float]
    ) -> FloatArray:
        # Reorder y = [theta1, theta2, theta1_dot, theta2_dot] —
        # LagrangianSystem already uses this convention (q first, qdot second).
        return self._lsys.rhs(t, y, params)

    def energy(self, y: FloatArray, params: Mapping[str, float] | None = None) -> float:
        """Total mechanical energy :math:`T + V` (a conserved quantity)."""
        merged = self.merged_params(params)
        m1 = merged["m1"]
        m2 = merged["m2"]
        l1 = merged["l1"]
        l2 = merged["l2"]
        g = merged["g"]
        th1, th2, th1d, th2d = y[0], y[1], y[2], y[3]
        T = (
            0.5 * (m1 + m2) * l1 * l1 * th1d * th1d
            + 0.5 * m2 * l2 * l2 * th2d * th2d
            + m2 * l1 * l2 * th1d * th2d * np.cos(th1 - th2)
        )
        V = -(m1 + m2) * g * l1 * np.cos(th1) - m2 * g * l2 * np.cos(th2)
        return float(T + V)


__all__ = ["DoublePendulum"]
