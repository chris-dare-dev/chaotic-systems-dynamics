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
from typing import Any

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
    # Canonical chaotic IC: both arms well past horizontal (2.0 rad ~= 115°,
    # 2.5 rad ~= 143°). Past energies where the upper arm could flip over.
    # See Stachowiak-Okada 2006 §3 for the chaos threshold in this regime.
    default_initial_state = np.array(
        [2.0, 2.5, 0.0, 0.0], dtype=np.float64
    )
    educational_notes = """\
**The classroom poster of mechanical chaos.** Two coupled pendulums,
no driving — pure Hamiltonian dynamics. Energy is conserved
*exactly*; the chaos is entirely a phase-space-volume-conserving
shuffle.

**Where to read about it:** Landau & Lifshitz, *Mechanics* 3e
(§5, §15) for the Lagrangian derivation; Strogatz §6.6
"Conservative Systems"; Stachowiak & Okada, *A numerical analysis
of chaos in the double pendulum*, Chaos, Solitons & Fractals 29
(2006).

**Two regimes, governed by total energy E:**

- *Low-energy regime* (small displacements): quasi-periodic —
  motion is the linear combination of two normal modes.
- *High-energy regime* (the default IC θ₁=2.0, θ₂=2.5): genuine
  chaos. The upper arm can flip over the pivot; small IC changes
  diverge exponentially.

**Pair with a symplectic integrator.** Pick *yoshida4* from the
integrator dropdown — it preserves the symplectic 2-form
exactly, so energy stays bounded for arbitrary integration time.
Compare to RK45, which slowly leaks energy. (The choice doesn't
matter on Lorenz / Rössler, but here it does.)

**Try the V1 phase portrait** on (θ₁, θ₁_dot): the
*Poincaré recurrences* are obvious as the orbit re-visits the
same region of phase space.
"""

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

    def post_sim_diagnostics(self, trajectory: Any) -> Mapping[str, str]:
        """Return total energy + integrator drift as display chips (CSC-033).

        The double pendulum is Hamiltonian (in the lifted phase
        space) but the project drives it with a non-symplectic
        ``DOP853`` because the underlying Lagrangian is non-separable.
        Surfacing the energy drift makes the integrator's accuracy
        budget concrete: ``|ΔE/E_0|`` on the order of 1e-9 to 1e-7
        for the canonical chaotic IC at ``rtol = 1e-9``.
        """
        y = np.asarray(getattr(trajectory, "y", []), dtype=np.float64)
        if y.ndim != 2 or y.shape[0] == 0:
            return {}
        params_obj = getattr(trajectory, "params", None)
        params = params_obj if isinstance(params_obj, Mapping) else None
        try:
            e0 = self.energy(y[0], params)
            e_last = self.energy(y[-1], params)
        except (KeyError, ValueError):
            return {}
        out: dict[str, str] = {"E": f"{e_last:+.4e}"}
        if abs(e0) > 0.0:
            drift_rel = abs(e_last - e0) / abs(e0)
            out["|ΔE/E₀|"] = f"{drift_rel:.2e}"
        else:
            out["|ΔE|"] = f"{abs(e_last - e0):.2e}"
        return out


__all__ = ["DoublePendulum"]
