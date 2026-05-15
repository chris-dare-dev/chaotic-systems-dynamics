"""Symplectic integrators for separable Hamiltonian systems.

For a separable Hamiltonian :math:`H(q, p) = T(p) + V(q)` the equations
of motion are :math:`\\dot q = \\partial T / \\partial p` and
:math:`\\dot p = -\\partial V / \\partial q`. Symplectic splitting
methods alternate applications of the kinetic and potential flows; they
preserve the symplectic 2-form :math:`\\omega = dq \\wedge dp` exactly
and exhibit *bounded* energy error over arbitrarily long horizons —
unlike RK4 / RK45, whose energy drifts linearly with time.

Three methods are exposed:

- ``velocity_verlet`` — 2nd-order, the workhorse of molecular dynamics.
  Same accuracy as leapfrog but stores (q, p) at the same time grid.
- ``leapfrog`` — 2nd-order, equivalent to velocity Verlet but with p
  stored at the half-integer grid. Slightly cheaper if you only need q.
- ``yoshida4`` — 4th-order composition of three velocity Verlet steps
  with the Yoshida coefficients. Best accuracy-per-step for problems
  where you can afford 3x the work per step (Yoshida 1990).

These integrators consume a *Hamiltonian RHS* — a callable returning the
gradients :math:`\\nabla T(p)` and :math:`\\nabla V(q)` separately. The
adapter :func:`from_hamiltonian` builds one from a
:class:`~chaotic_systems.core.HamiltonianSystem`.

The integrators also conform to the generic ``Integrator`` protocol via
the helper :class:`_SymplecticAdaptor`; when called with a flat ``rhs``,
the adaptor expects the caller to have supplied ``grad_T`` and
``grad_V`` via the ``kwargs`` ``grad_t_fn`` and ``grad_v_fn``.

References
----------
- E. Hairer, C. Lubich, G. Wanner, *Geometric Numerical Integration*,
  2nd ed., Springer 2006.
- H. Yoshida, *Construction of higher order symplectic integrators*,
  Physics Letters A 150 (1990), 262-268.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from chaotic_systems.core.base import FloatArray, Trajectory
from chaotic_systems.integrators._protocol import RHS

GradFn = Callable[[float, FloatArray], FloatArray]


# ---------------------------------------------------------------------------
# Core symplectic steppers — operate on (q, p) directly.
# ---------------------------------------------------------------------------


def _velocity_verlet_step(
    grad_T: GradFn,
    grad_V: GradFn,
    t: float,
    q: FloatArray,
    p: FloatArray,
    h: float,
) -> tuple[FloatArray, FloatArray]:
    """One velocity-Verlet step. 2nd order, symplectic, time-reversible."""
    p_half = p - 0.5 * h * grad_V(t, q)
    q_new = q + h * grad_T(t + 0.5 * h, p_half)
    p_new = p_half - 0.5 * h * grad_V(t + h, q_new)
    return q_new, p_new


def _leapfrog_step(
    grad_T: GradFn,
    grad_V: GradFn,
    t: float,
    q: FloatArray,
    p: FloatArray,
    h: float,
) -> tuple[FloatArray, FloatArray]:
    """Synchronized leapfrog — algebraically identical to velocity Verlet."""
    return _velocity_verlet_step(grad_T, grad_V, t, q, p, h)


# Yoshida 4th-order coefficients.
_YOSH_W1 = 1.0 / (2.0 - 2.0 ** (1.0 / 3.0))
_YOSH_W0 = 1.0 - 2.0 * _YOSH_W1
_YOSH_COEFFS: tuple[float, float, float] = (_YOSH_W1, _YOSH_W0, _YOSH_W1)


def _yoshida4_step(
    grad_T: GradFn,
    grad_V: GradFn,
    t: float,
    q: FloatArray,
    p: FloatArray,
    h: float,
) -> tuple[FloatArray, FloatArray]:
    """One Yoshida-4 step: composition of three velocity-Verlet substeps."""
    t_cur = t
    q_cur, p_cur = q, p
    for c in _YOSH_COEFFS:
        h_i = c * h
        q_cur, p_cur = _velocity_verlet_step(grad_T, grad_V, t_cur, q_cur, p_cur, h_i)
        t_cur += h_i
    return q_cur, p_cur


# ---------------------------------------------------------------------------
# Integrator wrappers conforming to the generic Integrator protocol.
# ---------------------------------------------------------------------------


def _grad_fns_from_kwargs(kwargs: dict[str, Any]) -> tuple[GradFn, GradFn]:
    try:
        grad_T = kwargs.pop("grad_t_fn")
        grad_V = kwargs.pop("grad_v_fn")
    except KeyError as exc:
        raise ValueError(
            "Symplectic integrators require `grad_t_fn` and `grad_v_fn` keyword "
            "arguments (or use `from_hamiltonian` to build them)."
        ) from exc
    return grad_T, grad_V


@dataclass(slots=True)
class _Symplectic:
    name: str
    stepper: Callable[..., tuple[FloatArray, FloatArray]]

    def integrate(
        self,
        rhs: RHS,
        t_span: tuple[float, float],
        y0: FloatArray,
        *,
        dt: float | None = None,
        n_points: int | None = None,
        rtol: float = 1e-8,  # unused
        atol: float = 1e-10,  # unused
        **kwargs: Any,
    ) -> Trajectory:
        del rhs  # Symplectic integrators consume grad_T / grad_V, not a flat rhs.
        if dt is None:
            raise ValueError(
                f"{self.name} requires a fixed step `dt` (got dt=None). "
                "If you supplied n_points only, derive dt = (t1 - t0) / (n_points - 1)."
            )
        grad_T, grad_V = _grad_fns_from_kwargs(dict(kwargs))
        t0, t1 = float(t_span[0]), float(t_span[1])
        h = float(dt)
        n_steps = max(1, int(np.floor((t1 - t0) / h)))

        y = np.asarray(y0, dtype=np.float64).copy()
        d = y.shape[0]
        if d % 2 != 0:
            raise ValueError(
                f"symplectic state dimension must be even (got {d}); "
                "y = [q; p]."
            )
        n = d // 2
        q = y[:n].copy()
        p = y[n:].copy()

        ts = np.empty(n_steps + 1, dtype=np.float64)
        ys = np.empty((n_steps + 1, d), dtype=np.float64)
        ts[0] = t0
        ys[0, :n] = q
        ys[0, n:] = p
        t_cur = t0
        for k in range(n_steps):
            q, p = self.stepper(grad_T, grad_V, t_cur, q, p, h)
            t_cur += h
            ts[k + 1] = t_cur
            ys[k + 1, :n] = q
            ys[k + 1, n:] = p

        return Trajectory(t=ts, y=ys, integrator=self.name)


velocity_verlet = _Symplectic(name="velocity_verlet", stepper=_velocity_verlet_step)
leapfrog = _Symplectic(name="leapfrog", stepper=_leapfrog_step)
yoshida4 = _Symplectic(name="yoshida4", stepper=_yoshida4_step)


def from_hamiltonian(integrator: _Symplectic, system: Any) -> tuple[GradFn, GradFn]:
    """Build ``grad_T`` and ``grad_V`` callables from a :class:`HamiltonianSystem`.

    Convenience helper for callers that already have a
    :class:`~chaotic_systems.core.HamiltonianSystem` and want to drive a
    symplectic integrator.
    """
    if not system.separable:  # pragma: no cover - guarded by HamiltonianSystem
        raise ValueError("system is not separable; cannot build grad_T / grad_V")
    del integrator  # only used as a marker for type clarity

    def grad_T(t: float, p: FloatArray) -> FloatArray:
        return system.grad_T(p, t=t)

    def grad_V(t: float, q: FloatArray) -> FloatArray:
        return system.grad_V(q, t=t)

    return grad_T, grad_V


__all__ = [
    "velocity_verlet",
    "leapfrog",
    "yoshida4",
    "from_hamiltonian",
    "_velocity_verlet_step",
    "_yoshida4_step",
]
