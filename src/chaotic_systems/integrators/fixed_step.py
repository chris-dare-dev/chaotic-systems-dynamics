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
from chaotic_systems.integrators._protocol import RHS, IntegratorDivergedError


def rk4_step(
    rhs: Any, t: float, y: FloatArray, h: float
) -> FloatArray:
    """One classical-RK4 step.

    Not numba-JIT'd at the outer level because ``rhs`` is an arbitrary
    Python callable; numba can't infer its signature. Users who want full
    JIT for the inner loop can pass a numba-JIT'd ``rhs`` and call this
    function from a JIT-ed outer loop.
    """
    k1 = rhs(t, y)
    k2 = rhs(t + 0.5 * h, y + 0.5 * h * k1)
    k3 = rhs(t + 0.5 * h, y + 0.5 * h * k2)
    k4 = rhs(t + h, y + h * k3)
    return y + (h / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)


# Back-compat alias for callers that imported the private name.
_rk4_step = rk4_step


def _rk4_loop_python(
    rhs: RHS,
    ts: FloatArray,
    y0: FloatArray,
    h: float | None = None,
    name: str = "RK4",
) -> FloatArray:
    """RK4 outer loop. If ``h`` is given, use it for every step (uniform grid).

    Raises :class:`IntegratorDivergedError` if the state becomes
    non-finite (``inf`` / ``nan``). Overflow warnings inside the step
    are suppressed because we surface the failure as an explicit
    exception instead.
    """

    n = ts.shape[0]
    ys = np.empty((n, y0.shape[0]), dtype=np.float64)
    ys[0] = y0
    with np.errstate(over="ignore", invalid="ignore"):
        if h is not None:
            step = float(h)
            for i in range(n - 1):
                ys[i + 1] = rk4_step(rhs, ts[i], ys[i], step)
                if not np.isfinite(ys[i + 1]).all():
                    raise IntegratorDivergedError(name, i, float(ts[i]))
        else:
            for i in range(n - 1):
                ys[i + 1] = rk4_step(rhs, ts[i], ys[i], ts[i + 1] - ts[i])
                if not np.isfinite(ys[i + 1]).all():
                    raise IntegratorDivergedError(name, i, float(ts[i]))
    return ys


def _euler_loop_python(
    rhs: RHS,
    ts: FloatArray,
    y0: FloatArray,
    h: float | None = None,
    name: str = "Euler",
) -> FloatArray:
    """Explicit-Euler outer loop.

    Raises :class:`IntegratorDivergedError` if the state becomes
    non-finite. Euler is conditionally stable; on chaotic / stiff
    systems (Lorenz being the canonical example) it will diverge
    for any ``dt`` above a problem-dependent threshold.
    """

    n = ts.shape[0]
    ys = np.empty((n, y0.shape[0]), dtype=np.float64)
    ys[0] = y0
    with np.errstate(over="ignore", invalid="ignore"):
        if h is not None:
            step = float(h)
            for i in range(n - 1):
                ys[i + 1] = ys[i] + step * rhs(ts[i], ys[i])
                if not np.isfinite(ys[i + 1]).all():
                    raise IntegratorDivergedError(name, i, float(ts[i]))
        else:
            for i in range(n - 1):
                ys[i + 1] = ys[i] + (ts[i + 1] - ts[i]) * rhs(ts[i], ys[i])
                if not np.isfinite(ys[i + 1]).all():
                    raise IntegratorDivergedError(name, i, float(ts[i]))
    return ys


def _resolve_grid(
    t_span: tuple[float, float], dt: float | None, n_points: int | None
) -> tuple[FloatArray, float | None]:
    """Return ``(grid, h_or_none)``. ``h`` is set when the grid is uniform."""

    t0, t1 = float(t_span[0]), float(t_span[1])
    if t1 <= t0:
        raise ValueError(
            f"t_span must be strictly increasing (got t0={t0!r}, t1={t1!r})"
        )
    if n_points is not None:
        n_p = int(n_points)
        if n_p < 2:
            raise ValueError(f"n_points must be >= 2 (got n_points={n_points!r})")
        grid = np.linspace(t0, t1, n_p, dtype=np.float64)
        return grid, float((t1 - t0) / (n_p - 1))
    if dt is None:
        raise ValueError(
            "fixed-step integrators require either `dt` or `n_points`"
        )
    if float(dt) <= 0.0:
        raise ValueError(f"dt must be positive (got dt={dt!r})")
    h = float(dt)
    n_steps = max(1, int(np.floor((t1 - t0) / h)))
    grid = t0 + h * np.arange(n_steps + 1, dtype=np.float64)
    return grid, h


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
        rtol: float = 1e-8,
        atol: float = 1e-10,
        **kwargs: Any,
    ) -> Trajectory:
        del rtol, atol, kwargs  # Fixed-step methods don't use tolerances.
        ts, h = _resolve_grid(t_span, dt, n_points)
        y0_arr = np.asarray(y0, dtype=np.float64)
        ys = _rk4_loop_python(rhs, ts, y0_arr, h, self.name)
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
        del rtol, atol, kwargs
        ts, h = _resolve_grid(t_span, dt, n_points)
        ys = _euler_loop_python(
            rhs, ts, np.asarray(y0, dtype=np.float64), h, self.name
        )
        return Trajectory(t=ts, y=ys, integrator=self.name)


RK4 = _RK4()
Euler = _Euler()

__all__ = ["RK4", "Euler", "NUMBA_AVAILABLE", "rk4_step"]
