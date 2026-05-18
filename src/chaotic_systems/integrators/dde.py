"""Delay-differential-equation integrator (Bellen-style continuous RK4).

A *delay differential equation* (DDE) takes the form

.. math::

    \\dot x(t) = f\\bigl(t, x(t), x(t - \\tau)\\bigr)

— the right-hand side depends on the state at one or more *past*
times. The phase space is therefore infinite-dimensional (the
"state" at any moment is the entire history segment on
:math:`[t - \\tau, t]`), and chaos can emerge in systems as simple
as a one-component scalar DDE. Mackey-Glass (Mackey & Glass, *Science*
197, 1977) is the canonical example.

This module ships :class:`BellenRK4`, a single-delay DDE integrator
modelled on the *continuous extension* idea of Bellen & Zennaro
(2003). The algorithm is just classical RK4 augmented with a
history buffer: at each substep where the RHS asks for
:math:`x(t - \\tau)`, the integrator looks the value up by linear
interpolation in the buffer of past samples. Linear interpolation
is one order lower than RK4's local truncation, which costs
accuracy at large ``dt`` but is plenty for the GUI's typical
``dt = 0.05`` on Mackey-Glass at canonical parameters
(``β, γ, n, τ = 0.2, 0.1, 10, 17``).

DDE integrators don't conform to the
:class:`~chaotic_systems.integrators._protocol.Integrator`
protocol — they need extra inputs (the history function, the delay
value) and a separate RHS signature
``rhs(t, x_current, x_delayed, params)``. The Mackey-Glass system
(:mod:`chaotic_systems.systems.mackey_glass`) overrides
:meth:`DynamicalSystem.simulate` to dispatch here, so callers see
the same surface as any other system.

References
----------
- M. C. Mackey & L. Glass, *Oscillation and chaos in physiological
  control systems*, Science 197 (1977), 287-289 — the canonical
  DDE chaotic system.
- A. Bellen & M. Zennaro, *Numerical Methods for Delay Differential
  Equations*, Oxford University Press (2003), §4 — the
  continuous-extension RK methodology this module reduces to.
- J. D. Farmer, *Chaotic attractors of an infinite-dimensional
  dynamical system*, Physica D 4 (1982), 366-393 — first
  computation of Mackey-Glass's chaotic attractor.
- E. M. Junges & J. A. C. Gallas, *Intricate routes to chaos in the
  Mackey-Glass delayed feedback system*, Phys. Lett. A 376 (2012),
  2109-2116 — the modern parameter-cascade reference.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

import numpy as np

from chaotic_systems.core.base import FloatArray, Trajectory

# RHS signature: ``f(t, x_current, x_delayed, params) -> dx/dt``.
# ``x_current`` and ``x_delayed`` are both shape ``(state_dim,)``;
# ``params`` is a frozen dict of the system's parameter values at
# the time of integration.
DDERhs = Callable[
    [float, FloatArray, FloatArray, Mapping[str, float]],
    FloatArray,
]


def _default_constant_history(y0: FloatArray) -> Callable[[float], FloatArray]:
    """Return a history function that's identically ``y0`` for all ``t``.

    The Heaviside-style extension. Most DDE papers (Mackey & Glass 1977
    included) use this; it's the right default unless the caller has
    a specific reason to prescribe a non-constant pre-history.
    """
    y0_const = np.ascontiguousarray(y0, dtype=np.float64).copy()

    def history(_t: float) -> FloatArray:
        return y0_const.copy()

    return history


@dataclass(slots=True)
class BellenRK4:
    """Bellen-style continuous RK4 integrator for single-delay DDEs.

    The :attr:`name` is what shows up in
    :attr:`Trajectory.integrator` for trajectories produced by this
    integrator (e.g. via :class:`~chaotic_systems.systems.MackeyGlass`).
    """

    name: str = "BellenRK4"

    def integrate_dde(
        self,
        dde_rhs: DDERhs,
        t_span: tuple[float, float],
        y0: FloatArray,
        *,
        delay: float,
        dt: float,
        params: Mapping[str, float] | None = None,
        history: Callable[[float], FloatArray] | None = None,
        n_points: int | None = None,
    ) -> Trajectory:
        """Integrate a single-delay DDE from ``t_span[0]`` to ``t_span[1]``.

        Parameters
        ----------
        dde_rhs
            The RHS callable, signature
            ``f(t, x_current, x_delayed, params) -> dx/dt``.
            ``x_current`` is the state at time ``t``;
            ``x_delayed`` is the state at time ``t - delay``,
            obtained by linear interpolation of the history buffer.
        t_span
            ``(t0, t1)`` time interval, ``t1 > t0``.
        y0
            Initial state at ``t0``. Shape ``(state_dim,)``.
        delay
            Constant delay value :math:`\\tau > 0`. Must be larger
            than ``dt`` so the integrator is querying *into* the
            history rather than into the present step.
        dt
            Integration step size. Bellen-Zennaro recommend
            ``dt ≤ delay / 10``; for the GUI's canonical Mackey-Glass
            run (``delay = 17``) ``dt = 0.05`` is comfortably below
            that.
        params
            Frozen parameter mapping forwarded to ``dde_rhs``.
            Defaults to an empty dict; the system's own
            ``simulate`` override is responsible for resolving
            defaults before calling here.
        history
            History function ``h(t) -> state``, defining the
            pre-history ``x(t)`` for ``t < t_span[0]``. Defaults to
            the constant ``y0`` (Heaviside extension).
        n_points
            If supplied, resample the trajectory onto a uniform
            grid of this many points. Defaults to keeping every
            integration step.

        Returns
        -------
        Trajectory
            ``t`` is the time grid (either the native step grid or
            the resampled one), ``y`` is the state matrix shape
            ``(N, state_dim)``, ``integrator = "BellenRK4"``.

        Raises
        ------
        ValueError
            On bad ``t_span``, non-positive ``delay`` / ``dt``,
            ``dt >= delay``, ``y0`` shape mismatch, or non-finite
            inputs.
        """
        t0, t1 = float(t_span[0]), float(t_span[1])
        if t1 <= t0:
            raise ValueError(
                f"t_span must be strictly increasing (got t0={t0!r}, t1={t1!r})"
            )
        if float(delay) <= 0.0:
            raise ValueError(f"delay must be positive (got {delay!r})")
        if float(dt) <= 0.0:
            raise ValueError(f"dt must be positive (got {dt!r})")
        if float(dt) >= float(delay):
            # The Bellen-Zennaro continuous-extension argument assumes
            # the integrator never asks for x(t - delay) at a t past
            # the most recent step's right endpoint. dt < delay
            # guarantees this for a single-delay problem.
            raise ValueError(
                f"dt ({dt!r}) must be less than delay ({delay!r}) for "
                f"the single-delay BellenRK4 scheme."
            )
        y0_arr = np.ascontiguousarray(y0, dtype=np.float64)
        if y0_arr.ndim != 1:
            raise ValueError(
                f"y0 must be 1-D (state_dim,); got shape {y0_arr.shape}"
            )
        if not np.isfinite(y0_arr).all():
            raise ValueError("y0 contains non-finite entries")

        state_dim = int(y0_arr.shape[0])
        merged_params: dict[str, float] = (
            {} if params is None else {k: float(v) for k, v in params.items()}
        )
        hist_fn = history if history is not None else _default_constant_history(y0_arr)

        # Pre-allocate the time grid + history-extended state buffer.
        # The buffer holds samples on ``[t0, t1]``; the pre-history
        # ``[t0 - delay, t0]`` is queried via ``hist_fn``.
        n_steps = int(round((t1 - t0) / float(dt)))
        if n_steps < 1:
            raise ValueError(
                f"step count ({n_steps}) is < 1; pick a smaller dt for "
                f"this t_span"
            )
        ts = t0 + float(dt) * np.arange(n_steps + 1, dtype=np.float64)
        # Snap the last sample to t1 to absorb rounding error.
        ts[-1] = t1
        ys = np.empty((n_steps + 1, state_dim), dtype=np.float64)
        ys[0] = y0_arr

        # Closure over the history buffer for interpolated lookups
        # at arbitrary t. Initial-history-aware: if the queried
        # time precedes t0 (or equals t0 exactly), defer to hist_fn;
        # otherwise linear-interpolate in the appended (ts, ys) buffer.
        appended_count = 1  # ys[0] is already populated

        def _query_history(t_query: float) -> FloatArray:
            if t_query <= t0:
                return hist_fn(t_query)
            # The appended buffer covers ts[: appended_count]; the
            # query t must lie in [t0, ts[appended_count - 1]].
            # Clamp to the upper end (defensive — shouldn't happen
            # under dt < delay).
            t_clamped = min(t_query, ts[appended_count - 1])
            # Find the bracketing index via uniform-grid arithmetic
            # (cheaper than np.searchsorted at every substep).
            offset = (t_clamped - t0) / float(dt)
            idx = int(offset)
            if idx >= appended_count - 1:
                return ys[appended_count - 1].copy()
            frac = offset - idx
            return ys[idx] * (1.0 - frac) + ys[idx + 1] * frac

        # The RK4 loop. ``f`` calls into ``dde_rhs`` with the
        # delayed-state lookup baked in.
        def _f(t_eval: float, x_eval: FloatArray) -> FloatArray:
            x_delayed = _query_history(t_eval - float(delay))
            out = dde_rhs(t_eval, x_eval, x_delayed, merged_params)
            arr = np.ascontiguousarray(out, dtype=np.float64)
            if arr.shape != (state_dim,):
                raise ValueError(
                    f"dde_rhs returned shape {arr.shape}; expected ({state_dim},)"
                )
            return arr

        for i in range(n_steps):
            t_i = float(ts[i])
            x_i = ys[i]
            h = float(ts[i + 1] - ts[i])
            k1 = _f(t_i, x_i)
            k2 = _f(t_i + 0.5 * h, x_i + 0.5 * h * k1)
            k3 = _f(t_i + 0.5 * h, x_i + 0.5 * h * k2)
            k4 = _f(t_i + h, x_i + h * k3)
            ys[i + 1] = x_i + (h / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
            appended_count = i + 2  # ys[: appended_count] is now valid

        # Optional resampling onto a uniform n_points grid.
        if n_points is not None:
            n_p = int(n_points)
            if n_p < 2:
                raise ValueError(f"n_points must be >= 2 (got {n_points!r})")
            target = np.linspace(t0, t1, n_p, dtype=np.float64)
            ys_resampled = np.empty((n_p, state_dim), dtype=np.float64)
            for d in range(state_dim):
                ys_resampled[:, d] = np.interp(target, ts, ys[:, d])
            return Trajectory(
                t=target, y=ys_resampled, integrator=self.name
            )

        return Trajectory(t=ts, y=ys, integrator=self.name)


__all__ = ["BellenRK4", "DDERhs"]
