"""Hénon-Heiles — a 2-DOF Hamiltonian system with chaotic dynamics.

.. math::

    H(x, y, p_x, p_y) = \\tfrac{1}{2}(p_x^2 + p_y^2)
    + \\tfrac{1}{2}(x^2 + y^2) + x^2 y - \\tfrac{1}{3} y^3.

Originally proposed as a toy model for stellar motion in an
axisymmetric galactic potential. Trajectories are bounded for energies
:math:`E < 1/6`; above that, particles can escape. For
:math:`E \\approx 1/8` the dynamics are mixed regular / chaotic and
make a beautiful Poincaré section through :math:`x = 0, p_x > 0`.

The system is separable: :math:`H = T(p) + V(q)` with
:math:`T = \\tfrac{1}{2}(p_x^2 + p_y^2)` and
:math:`V = \\tfrac{1}{2}(x^2 + y^2) + x^2 y - \\tfrac{1}{3} y^3`. We
expose the underlying :class:`HamiltonianSystem` via
:meth:`hamiltonian` so symplectic integrators can drive it.

References
----------
- M. Hénon, C. Heiles, *The applicability of the third integral of
  motion: some numerical experiments*, Astron. J. 69 (1964), 73-79.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import cached_property

import numpy as np
import sympy as sp

from chaotic_systems.core.base import DynamicalSystem, FloatArray, Parameter
from chaotic_systems.core.hamiltonian import HamiltonianSystem


class HenonHeiles(DynamicalSystem):
    """Hénon-Heiles Hamiltonian on :math:`\\mathbb{R}^4` (q=(x,y), p=(px,py))."""

    name = "HenonHeiles"
    latex = (
        r"H = \tfrac{1}{2}(p_x^2 + p_y^2) + \tfrac{1}{2}(x^2 + y^2) "
        r"+ x^2 y - \tfrac{1}{3} y^3"
    )
    lagrangian_latex = (
        r"L = \tfrac{1}{2}(\dot x^2 + \dot y^2) - \tfrac{1}{2}(x^2 + y^2) "
        r"- x^2 y + \tfrac{1}{3} y^3"
    )
    state_dim = 4
    parameters: dict[str, Parameter] = {}  # parameter-free in the standard formulation
    default_initial_state = np.array([0.0, 0.1, 0.45, 0.0], dtype=np.float64)

    def _rhs(
        self, t: float, y: FloatArray, params: Mapping[str, float]
    ) -> FloatArray:
        # State: [x, y, px, py]
        x, y_, px, py = y[0], y[1], y[2], y[3]
        return np.array(
            [
                px,
                py,
                -x - 2.0 * x * y_,
                -y_ - x * x + y_ * y_,
            ],
            dtype=np.float64,
        )

    def energy(self, y: FloatArray) -> float:
        """Return the Hamiltonian evaluated at the given state."""
        x, y_, px, py = y[0], y[1], y[2], y[3]
        return float(
            0.5 * (px * px + py * py)
            + 0.5 * (x * x + y_ * y_)
            + x * x * y_
            - (1.0 / 3.0) * y_ * y_ * y_
        )

    @cached_property
    def hamiltonian(self) -> HamiltonianSystem:
        """Underlying symbolic :class:`HamiltonianSystem` (cached).

        Used by symplectic integrators via
        :func:`chaotic_systems.integrators.from_hamiltonian`.
        """
        t = sp.symbols("t", real=True)
        x, y_ = sp.symbols("x y", real=True)
        px, py = sp.symbols("p_x p_y", real=True)
        T_expr = sp.Rational(1, 2) * (px**2 + py**2)
        V_expr = (
            sp.Rational(1, 2) * (x**2 + y_**2)
            + x**2 * y_
            - sp.Rational(1, 3) * y_**3
        )
        H_expr = T_expr + V_expr
        return HamiltonianSystem(
            q_syms=(x, y_),
            p_syms=(px, py),
            time=t,
            hamiltonian=H_expr,
            kinetic=T_expr,
            potential=V_expr,
        )


__all__ = ["HenonHeiles"]
