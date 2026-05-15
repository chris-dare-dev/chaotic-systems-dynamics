"""Symbolic Lagrangian -> numerical ODE pipeline.

Given a Lagrangian :math:`L(q, \\dot q, t)` over generalized coordinates
:math:`q = (q_1, \\dots, q_n)`, the Euler-Lagrange equations are

.. math::

    \\frac{d}{dt} \\frac{\\partial L}{\\partial \\dot q_i}
    - \\frac{\\partial L}{\\partial q_i} = 0,
    \\quad i = 1, \\dots, n.

Expanding the time derivative gives a system of :math:`n` second-order
ODEs of the form :math:`M(q, \\dot q, t) \\, \\ddot q = F(q, \\dot q, t)`
where :math:`M_{ij} = \\partial^2 L / \\partial \\dot q_i \\partial \\dot q_j`
is the mass matrix and :math:`F` is the generalized force.

This module reduces the second-order system to a first-order ODE on the
state :math:`(q, \\dot q) \\in \\mathbb{R}^{2n}` and ``lambdify``\\s the
right-hand side for fast numerical evaluation. The construction is done
once at instantiation time and cached.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import sympy as sp

from chaotic_systems.core.base import FloatArray


@dataclass(slots=True)
class LagrangianSystem:
    """Symbolic Lagrangian -> fast numerical RHS.

    Parameters
    ----------
    coords
        Sequence of sympy ``Function`` instances representing the
        generalized coordinates :math:`q_i(t)`.
    time
        The sympy symbol for time :math:`t`.
    lagrangian
        Symbolic expression for :math:`L(q, \\dot q, t)`. May reference
        the entries of ``coords``, their first derivatives, ``time``, and
        any symbols listed in ``params``.
    params
        Optional list of sympy symbols treated as numerical parameters.
        Their values are supplied at call time via the ``params`` dict
        argument to :meth:`rhs`.

    Notes
    -----
    The mass matrix is inverted symbolically when small (n <= 3) and at
    runtime by ``numpy.linalg.solve`` for larger systems.
    """

    coords: Sequence[sp.Function]
    time: sp.Symbol
    lagrangian: sp.Expr
    params: Sequence[sp.Symbol] = ()

    # Filled by __post_init__.
    _state_dim: int = 0
    _rhs_func: Any = None
    _euler_lagrange: tuple[sp.Expr, ...] = ()
    _qdotdot_expr: tuple[sp.Expr, ...] = ()
    _latex_cache: str = ""

    def __post_init__(self) -> None:
        n = len(self.coords)
        self._state_dim = 2 * n

        t = self.time
        # q_i(t), \dot q_i(t), \ddot q_i(t)
        qs = [c(t) for c in self.coords]
        qdots = [sp.diff(q, t) for q in qs]
        qddots = [sp.diff(qd, t) for qd in qdots]

        L = self.lagrangian
        # Euler-Lagrange: d/dt(dL/dqdot_i) - dL/dq_i = 0
        EL = [sp.diff(sp.diff(L, qd), t) - sp.diff(L, q) for q, qd in zip(qs, qdots)]
        self._euler_lagrange = tuple(EL)

        # Solve EL = 0 for \ddot q. The system is linear in qddots since
        # qddot appears only through d/dt(dL/dqdot_i).
        solution = sp.solve(EL, qddots, dict=True)
        if not solution:
            raise ValueError(
                "Failed to solve Euler-Lagrange equations symbolically — "
                "is the Lagrangian regular?"
            )
        sol = solution[0]
        qddot_exprs = [sp.simplify(sol[qd]) for qd in qddots]
        self._qdotdot_expr = tuple(qddot_exprs)

        # Build numerical RHS. State y = [q1, ..., qn, qdot1, ..., qdotn].
        # dy/dt = [qdot1, ..., qdotn, qddot1, ..., qddotn]
        q_syms = sp.symbols(f"_q1:{n + 1}", real=True)
        qd_syms = sp.symbols(f"_qd1:{n + 1}", real=True)
        subs_map: dict[sp.Expr, sp.Expr] = {}
        for i in range(n):
            subs_map[qdots[i]] = qd_syms[i]
            subs_map[qs[i]] = q_syms[i]
        qddot_substituted = [e.subs(subs_map) for e in qddot_exprs]

        all_args = [t, *q_syms, *qd_syms, *self.params]
        # cse=True dramatically reduces the size of the compiled function
        # for non-trivial Lagrangians (double pendulum especially).
        func = sp.lambdify(all_args, qddot_substituted, modules="numpy", cse=True)
        self._rhs_func = func

    # ----- public API --------------------------------------------------

    @property
    def state_dim(self) -> int:
        """``2 * len(coords)``."""
        return self._state_dim

    @property
    def euler_lagrange(self) -> tuple[sp.Expr, ...]:
        """Tuple of Euler-Lagrange expressions (all == 0)."""
        return self._euler_lagrange

    @property
    def qdotdot_expressions(self) -> tuple[sp.Expr, ...]:
        """Solved expressions for :math:`\\ddot q_i` in the original symbols."""
        return self._qdotdot_expr

    def lagrangian_latex(self) -> str:
        """LaTeX of the Lagrangian (cached)."""
        if not self._latex_cache:
            self._latex_cache = sp.latex(self.lagrangian)
        return self._latex_cache

    def rhs(
        self, t: float, y: FloatArray, params: Mapping[sp.Symbol | str, float] | None = None
    ) -> FloatArray:
        """Evaluate :math:`\\dot y` at ``(t, y)``.

        ``params`` maps parameter symbols (or their names as strings) to
        numerical values. Missing parameters raise ``KeyError``.
        """
        n = self.state_dim // 2
        q = y[:n]
        qd = y[n:]

        # Build a positional list aligned with self.params.
        if params is None:
            param_values: list[float] = []
        else:
            # Accept either Symbol keys or string keys.
            normalized: dict[str, float] = {}
            for k, v in params.items():
                normalized[str(k)] = float(v)
            param_values = []
            for s in self.params:
                key = str(s)
                if key not in normalized:
                    raise KeyError(
                        f"missing value for Lagrangian parameter {key!r}; "
                        f"got {sorted(normalized)}"
                    )
                param_values.append(normalized[key])

        qddot = self._rhs_func(t, *q, *qd, *param_values)
        result = np.empty(self.state_dim, dtype=np.float64)
        result[:n] = qd
        result[n:] = np.asarray(qddot, dtype=np.float64).ravel()
        return result


__all__ = ["LagrangianSystem"]
