"""Symbolic Hamiltonian -> numerical ODE pipeline.

For a Hamiltonian :math:`H(q, p, t)` with :math:`q, p \\in \\mathbb{R}^n`,
Hamilton's equations are

.. math::

    \\dot q_i = \\frac{\\partial H}{\\partial p_i},
    \\quad
    \\dot p_i = -\\frac{\\partial H}{\\partial q_i}.

This module symbolically differentiates :math:`H` once and ``lambdify``\\s
the result. For *separable* Hamiltonians :math:`H = T(p) + V(q)` we also
expose :meth:`grad_T` and :meth:`grad_V` separately, which is what
symplectic splitting integrators (leapfrog, Yoshida4) need.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import sympy as sp

from chaotic_systems.core.base import FloatArray


@dataclass(slots=True)
class HamiltonianSystem:
    """Symbolic Hamiltonian -> fast numerical RHS.

    Parameters
    ----------
    q_syms, p_syms
        Tuples of sympy symbols for generalized coordinates and momenta.
        Must have the same length.
    time
        Sympy symbol for time.
    hamiltonian
        Symbolic :math:`H(q, p, t)`.
    params
        Optional list of sympy symbols treated as numerical parameters.
    kinetic, potential
        Optional. If both are supplied and the Hamiltonian decomposes as
        ``H = kinetic + potential`` with ``kinetic`` depending only on
        ``p`` (and ``params``, ``time``) and ``potential`` depending only
        on ``q``, then :attr:`separable` is True and :meth:`grad_T` /
        :meth:`grad_V` are available.
    """

    q_syms: Sequence[sp.Symbol]
    p_syms: Sequence[sp.Symbol]
    time: sp.Symbol
    hamiltonian: sp.Expr
    params: Sequence[sp.Symbol] = ()
    kinetic: sp.Expr | None = None
    potential: sp.Expr | None = None

    _state_dim: int = 0
    _rhs_func: Any = None
    _gradT_func: Any = None
    _gradV_func: Any = None
    _H_func: Any = None
    _latex_cache: str = ""

    def __post_init__(self) -> None:
        if len(self.q_syms) != len(self.p_syms):
            raise ValueError(
                f"len(q_syms)={len(self.q_syms)} != len(p_syms)={len(self.p_syms)}"
            )
        n = len(self.q_syms)
        self._state_dim = 2 * n

        H = self.hamiltonian
        dHdq = [sp.diff(H, q) for q in self.q_syms]
        dHdp = [sp.diff(H, p) for p in self.p_syms]

        all_args = [self.time, *self.q_syms, *self.p_syms, *self.params]
        # rhs returns (qdot, pdot) flat: [dH/dp ... , -dH/dq ...]
        rhs_expr = [*dHdp, *[-e for e in dHdq]]
        self._rhs_func = sp.lambdify(all_args, rhs_expr, modules="numpy", cse=True)
        self._H_func = sp.lambdify(all_args, H, modules="numpy", cse=True)

        if self.kinetic is not None and self.potential is not None:
            # Validate separability: T should not depend on q, V should not depend on p.
            T_free = self.kinetic.free_symbols
            V_free = self.potential.free_symbols
            if any(q in T_free for q in self.q_syms):
                raise ValueError("kinetic depends on q; not a separable Hamiltonian")
            if any(p in V_free for p in self.p_syms):
                raise ValueError("potential depends on p; not a separable Hamiltonian")
            # grad T wrt p (n-vector); grad V wrt q (n-vector).
            gradT = [sp.diff(self.kinetic, p) for p in self.p_syms]
            gradV = [sp.diff(self.potential, q) for q in self.q_syms]
            T_args = [self.time, *self.p_syms, *self.params]
            V_args = [self.time, *self.q_syms, *self.params]
            self._gradT_func = sp.lambdify(T_args, gradT, modules="numpy", cse=True)
            self._gradV_func = sp.lambdify(V_args, gradV, modules="numpy", cse=True)

    # ----- public API --------------------------------------------------

    @property
    def state_dim(self) -> int:
        return self._state_dim

    @property
    def separable(self) -> bool:
        """True if the system is :math:`H(q,p) = T(p) + V(q)`."""
        return self._gradT_func is not None and self._gradV_func is not None

    def hamiltonian_latex(self) -> str:
        if not self._latex_cache:
            self._latex_cache = sp.latex(self.hamiltonian)
        return self._latex_cache

    def _param_values(self, params: Mapping[sp.Symbol | str, float] | None) -> list[float]:
        if params is None:
            normalized: dict[str, float] = {}
        else:
            normalized = {str(k): float(v) for k, v in params.items()}
        values: list[float] = []
        for s in self.params:
            key = str(s)
            if key not in normalized:
                raise KeyError(
                    f"missing value for Hamiltonian parameter {key!r}; "
                    f"got {sorted(normalized)}"
                )
            values.append(normalized[key])
        return values

    def rhs(
        self,
        t: float,
        y: FloatArray,
        params: Mapping[sp.Symbol | str, float] | None = None,
    ) -> FloatArray:
        """Evaluate Hamilton's equations as a flat ``[qdot; pdot]`` vector."""
        n = self.state_dim // 2
        q = y[:n]
        p = y[n:]
        pv = self._param_values(params)
        out = self._rhs_func(t, *q, *p, *pv)
        return np.asarray(out, dtype=np.float64).ravel()

    def energy(
        self,
        y: FloatArray,
        t: float = 0.0,
        params: Mapping[sp.Symbol | str, float] | None = None,
    ) -> float:
        """Evaluate :math:`H(q, p, t)` at the given state."""
        n = self.state_dim // 2
        q = y[:n]
        p = y[n:]
        pv = self._param_values(params)
        return float(self._H_func(t, *q, *p, *pv))

    def grad_T(
        self,
        p: FloatArray,
        t: float = 0.0,
        params: Mapping[sp.Symbol | str, float] | None = None,
    ) -> FloatArray:
        """Return :math:`\\partial T / \\partial p` (the qdot half of the flow).

        Only available if :attr:`separable`.
        """
        if self._gradT_func is None:
            raise RuntimeError("grad_T requires a separable Hamiltonian")
        pv = self._param_values(params)
        out = self._gradT_func(t, *p, *pv)
        return np.asarray(out, dtype=np.float64).ravel()

    def grad_V(
        self,
        q: FloatArray,
        t: float = 0.0,
        params: Mapping[sp.Symbol | str, float] | None = None,
    ) -> FloatArray:
        """Return :math:`\\partial V / \\partial q` (the *negative* of pdot)."""
        if self._gradV_func is None:
            raise RuntimeError("grad_V requires a separable Hamiltonian")
        pv = self._param_values(params)
        out = self._gradV_func(t, *q, *pv)
        return np.asarray(out, dtype=np.float64).ravel()


__all__ = ["HamiltonianSystem"]
