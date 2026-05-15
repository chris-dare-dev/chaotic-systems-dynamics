"""Adaptive integrators (thin wrappers around ``scipy.integrate.solve_ivp``).

Exports one class per scipy method: ``RK45``, ``RK23``, ``DOP853``,
``Radau``, ``BDF``, ``LSODA``. Each conforms to the
:class:`~chaotic_systems.integrators._protocol.Integrator` protocol.

When the caller supplies ``n_points``, the integrator returns a uniformly
sampled trajectory via ``t_eval``. When only ``dt`` is supplied, we
evaluate at ``arange(t0, t1, dt)`` *with the endpoint snapped to* ``t1``
so downstream code that expects ``traj.t[-1] == t1`` is never surprised.
Otherwise we hand back scipy's native step grid (``sol.t`` and ``sol.y``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.integrate import solve_ivp

from chaotic_systems.core.base import FloatArray, Trajectory
from chaotic_systems.integrators._protocol import RHS


def _grid_from_dt(t0: float, t1: float, dt: float) -> FloatArray:
    """Build a ``[t0, t0+dt, ..., t1]`` grid; the last sample is snapped to ``t1``."""

    if dt <= 0.0:
        raise ValueError(f"dt must be positive (got {dt!r})")
    n_steps = max(1, int(round((t1 - t0) / dt)))
    grid = t0 + dt * np.arange(n_steps + 1, dtype=np.float64)
    # Drop anything past t1 (rounding can push the last sample 1 ulp over)
    # and snap the final entry exactly to t1 so trajectory consumers can
    # rely on `traj.t[-1] == t1`.
    grid = grid[grid <= t1 + 1e-12]
    if grid.size == 0 or grid[-1] < t1:
        grid = np.concatenate([grid, [t1]])
    else:
        grid[-1] = t1
    return grid


@dataclass(slots=True)
class _ScipyAdaptive:
    """Common adaptive-integrator wrapper. Subclasses set :attr:`name`."""

    name: str

    def integrate(
        self,
        rhs: RHS,
        t_span: tuple[float, float],
        y0: FloatArray,
        *,
        dt: float | None = None,
        n_points: int | None = None,
        rtol: float = 1e-8,
        atol: float = 1e-10,
        **kwargs: Any,
    ) -> Trajectory:
        t0, t1 = float(t_span[0]), float(t_span[1])
        if t1 <= t0:
            raise ValueError(
                f"t_span must be increasing (got t0={t0!r}, t1={t1!r})"
            )

        t_eval: FloatArray | None
        if n_points is not None:
            n_p = int(n_points)
            if n_p < 2:
                raise ValueError(f"n_points must be >= 2 (got {n_points!r})")
            t_eval = np.linspace(t0, t1, n_p, dtype=np.float64)
        elif dt is not None:
            t_eval = _grid_from_dt(t0, t1, float(dt))
        else:
            t_eval = None

        sol = solve_ivp(
            rhs,
            (t0, t1),
            np.asarray(y0, dtype=np.float64),
            method=self.name,
            t_eval=t_eval,
            rtol=rtol,
            atol=atol,
            dense_output=False,
            **kwargs,
        )
        if not sol.success:
            raise RuntimeError(
                f"{self.name} integration failed: {sol.message!r}"
            )
        return Trajectory(
            t=np.ascontiguousarray(sol.t, dtype=np.float64),
            y=np.ascontiguousarray(sol.y.T, dtype=np.float64),
            integrator=self.name,
        )


# Concrete instances (importable as drop-in integrators).
RK45 = _ScipyAdaptive(name="RK45")
RK23 = _ScipyAdaptive(name="RK23")
DOP853 = _ScipyAdaptive(name="DOP853")
Radau = _ScipyAdaptive(name="Radau")
BDF = _ScipyAdaptive(name="BDF")
LSODA = _ScipyAdaptive(name="LSODA")


__all__ = ["RK45", "RK23", "DOP853", "Radau", "BDF", "LSODA"]
