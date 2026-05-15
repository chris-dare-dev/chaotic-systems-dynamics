"""Poincaré section computation.

A Poincaré section is the intersection of a trajectory with a
codimension-1 hyperplane :math:`\\Sigma = \\{y : \\langle n, y \\rangle = c\\}`,
optionally restricted to crossings in a fixed direction.

We use :func:`scipy.integrate.solve_ivp`'s event detection: define an
event function ``g(t, y) = n . y - c``; ``solve_ivp`` returns the
locations where ``g`` changes sign. The ``direction`` attribute of the
event lets us pick only crossings where :math:`n \\cdot \\dot y > 0`
("upward") or ``< 0`` ("downward").
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
from scipy.integrate import solve_ivp

from chaotic_systems.core.base import DynamicalSystem, FloatArray, Trajectory


def _make_event(
    normal: FloatArray, offset: float, direction: float
):
    """Build a scipy-compatible event callable with terminal / direction set.

    scipy.integrate.solve_ivp consumes ``event(t, y) -> float`` callables
    and looks at ``event.terminal`` and ``event.direction`` attributes. We
    set them on the closure object itself.
    """

    def event(t: float, y: FloatArray) -> float:
        return float(np.dot(normal, y) - offset)

    event.terminal = False  # type: ignore[attr-defined]
    event.direction = direction  # type: ignore[attr-defined]
    return event


def poincare_section(
    system: DynamicalSystem,
    normal: FloatArray,
    offset: float = 0.0,
    direction: int = 0,
    y0: FloatArray | None = None,
    params: Mapping[str, float] | None = None,
    t_span: tuple[float, float] = (0.0, 1000.0),
    t_transient: float = 50.0,
    rtol: float = 1e-9,
    atol: float = 1e-12,
    max_step: float | None = None,
) -> Trajectory:
    """Collect points where the trajectory crosses :math:`n \\cdot y = c`.

    Parameters
    ----------
    normal
        Normal vector :math:`n` of the hyperplane. Need not be unit.
    offset
        Constant :math:`c`.
    direction
        ``+1`` keep upward crossings (event function increasing),
        ``-1`` keep downward crossings, ``0`` keep both. Mirrors the
        semantics of ``scipy.integrate.solve_ivp`` event direction.
    t_span
        Total integration window.
    t_transient
        Discard crossings before this time (transient).

    Returns
    -------
    Trajectory
        ``t`` and ``y`` arrays containing only the section crossings
        (after the transient). ``y[k]`` is the full state at the
        :math:`k`-th crossing.
    """
    n_vec = np.asarray(normal, dtype=np.float64).ravel()
    if n_vec.shape != (system.state_dim,):
        raise ValueError(
            f"normal has shape {n_vec.shape}; expected ({system.state_dim},)"
        )

    y_start = system.initial_state if y0 is None else np.asarray(y0, dtype=np.float64)
    merged_params = system.merged_params(params)

    def fun(t: float, y: FloatArray) -> FloatArray:
        return system.rhs(t, y, **merged_params)

    event = _make_event(n_vec, float(offset), float(direction))

    solve_kwargs: dict[str, object] = {
        "method": "DOP853",
        "rtol": rtol,
        "atol": atol,
        "events": event,
        "dense_output": False,
    }
    if max_step is not None:
        solve_kwargs["max_step"] = max_step

    sol = solve_ivp(fun, t_span, y_start, **solve_kwargs)  # type: ignore[arg-type]
    if sol.t_events is None or len(sol.t_events) == 0:
        return Trajectory(
            t=np.array([], dtype=np.float64),
            y=np.zeros((0, system.state_dim), dtype=np.float64),
            system=system.name,
            params=dict(merged_params),
            integrator="poincare",
        )
    t_events = sol.t_events[0]
    y_events = sol.y_events[0]
    keep = t_events >= t_transient
    t_kept = t_events[keep]
    y_kept = y_events[keep]
    return Trajectory(
        t=np.asarray(t_kept, dtype=np.float64),
        y=np.asarray(y_kept, dtype=np.float64),
        system=system.name,
        params=dict(merged_params),
        integrator="poincare",
    )


__all__ = ["poincare_section"]
