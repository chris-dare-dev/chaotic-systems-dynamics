"""Adaptive integrators (thin wrappers around ``scipy.integrate.solve_ivp``).

Exports one class per scipy method: ``RK45``, ``RK23``, ``DOP853``,
``Radau``, ``BDF``, ``LSODA``. Each conforms to the
:class:`~chaotic_systems.integrators._protocol.Integrator` protocol.

When the caller supplies ``n_points``, the integrator returns a uniformly
sampled trajectory using scipy's dense output (cheaper than rerunning).
When only ``dt`` is supplied, we evaluate at ``arange(t0, t1+dt, dt)``.
Otherwise we hand back scipy's native step grid (``sol.t`` and ``sol.y``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.integrate import solve_ivp

from chaotic_systems.core.base import FloatArray, Trajectory
from chaotic_systems.integrators._protocol import RHS


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
        # Pick the sample grid.
        t_eval: FloatArray | None
        if n_points is not None:
            t_eval = np.linspace(t0, t1, int(n_points), dtype=np.float64)
        elif dt is not None:
            n_steps = int(np.floor((t1 - t0) / dt))
            t_eval = t0 + dt * np.arange(n_steps + 1, dtype=np.float64)
            # Clip to t_span end (rounding can push us 1 ulp past t1).
            t_eval = t_eval[t_eval <= t1 + 1e-12]
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
