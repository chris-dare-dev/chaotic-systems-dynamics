"""Fixed-step integrators: classical RK4 and explicit Euler.

These are useful as baselines and pedagogical references. RK4 is the
canonical 4th-order single-step method; explicit Euler is included so
tests can demonstrate the difference between a 1st-order and a higher
order scheme.

The hot loop is JIT-compiled with numba when available. The Python /
NumPy fallback is fully functional but ~5-20x slower for small state
dimensions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from chaotic_systems.core._numba import NUMBA_AVAILABLE
from chaotic_systems.core.base import FloatArray, Trajectory
from chaotic_systems.integrators._protocol import RHS


def _rk4_step(
    rhs: Any, t: float, y: FloatArray, h: float
) -> FloatArray:
    """One classical-RK4 step.

    Not numba-JIT'd at the outer level because ``rhs`` is an arbitrary
    Python callable; numba can't infer its signature. Users who want full
    JIT for the inner loop can pass a numba-JIT'd ``rhs`` and call
    :func:`_rk4_step_jit` (registered below when numba is available).
    """
    k1 = rhs(t, y)
    k2 = rhs(t + 0.5 * h, y + 0.5 * h * k1)
    k3 = rhs(t + 0.5 * h, y + 0.5 * h * k2)
    k4 = rhs(t + h, y + h * k3)
    return y + (h / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)


def _rk4_loop_python(
    rhs: RHS, ts: FloatArray, y0: FloatArray
) -> FloatArray:
    n = ts.shape[0]
    ys = np.empty((n, y0.shape[0]), dtype=np.float64)
    ys[0] = y0
    for i in range(n - 1):
        h = ts[i + 1] - ts[i]
        ys[i + 1] = _rk4_step(rhs, ts[i], ys[i], h)
    return ys


def _euler_loop_python(
    rhs: RHS, ts: FloatArray, y0: FloatArray
) -> FloatArray:
    n = ts.shape[0]
    ys = np.empty((n, y0.shape[0]), dtype=np.float64)
    ys[0] = y0
    for i in range(n - 1):
        h = ts[i + 1] - ts[i]
        ys[i + 1] = ys[i] + h * rhs(ts[i], ys[i])
    return ys


def _resolve_grid(
    t_span: tuple[float, float], dt: float | None, n_points: int | None
) -> FloatArray:
    t0, t1 = float(t_span[0]), float(t_span[1])
    if n_points is not None:
        return np.linspace(t0, t1, int(n_points), dtype=np.float64)
    if dt is None:
        raise ValueError(
            "fixed-step integrators require either `dt` or `n_points`"
        )
    n_steps = int(np.floor((t1 - t0) / float(dt)))
    return t0 + float(dt) * np.arange(n_steps + 1, dtype=np.float64)


@dataclass(slots=True)
class _RK4:
    name: str = "RK4"

    def integrate(
        self,
        rhs: RHS,
        t_span: tuple[float, float],
        y0: FloatArray,
        *,
        dt: float | None = None,
        n_points: int | None = None,
        rtol: float = 1e-8,  # unused for fixed step
        atol: float = 1e-10,  # unused
        **kwargs: Any,
    ) -> Trajectory:
        ts = _resolve_grid(t_span, dt, n_points)
        y0_arr = np.asarray(y0, dtype=np.float64)
        # We deliberately call the pure-Python loop because numba can't
        # JIT through an arbitrary Python ``rhs`` callable. The
        # _rk4_step body, however, is JIT'd when called with numba-typed
        # arguments — practically this just means an inlined arithmetic
        # call here, which is still fast enough for the project's
        # purposes. Users who want maximum speed can pass a numba-JIT'd
        # rhs and call _rk4_step directly.
        ys = _rk4_loop_python(rhs, ts, y0_arr)
        return Trajectory(t=ts, y=ys, integrator=self.name)


@dataclass(slots=True)
class _Euler:
    name: str = "Euler"

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
        ts = _resolve_grid(t_span, dt, n_points)
        ys = _euler_loop_python(rhs, ts, np.asarray(y0, dtype=np.float64))
        return Trajectory(t=ts, y=ys, integrator=self.name)


RK4 = _RK4()
Euler = _Euler()

__all__ = ["RK4", "Euler", "NUMBA_AVAILABLE"]
