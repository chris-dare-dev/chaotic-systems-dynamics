"""Integrator protocol shared by adaptive, fixed-step, and symplectic methods.

All integrators expose a single :meth:`integrate` method with the same
signature, so :meth:`chaotic_systems.core.DynamicalSystem.simulate` and
downstream code can swap integrators without touching the call site.

We use :class:`typing.Protocol` rather than an ABC because some
integrators are stateful (caching numba-compiled functions) while others
are lightweight wrappers — a structural type is the cleaner contract.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from chaotic_systems.core.base import FloatArray, Trajectory

RHS = Callable[[float, FloatArray], FloatArray]


class IntegratorDivergedError(RuntimeError):
    """The integrator produced a non-finite state and cannot continue.

    Raised by fixed-step methods (Euler, RK4) when local truncation error
    grows fast enough that the state overflows to ``±inf`` or becomes
    ``nan``. The classic trigger is explicit Euler on a chaotic /
    stiff system at too coarse a ``dt`` — Euler on the Lorenz attractor
    at ``dt = 0.01`` is the canonical example.

    Attributes
    ----------
    integrator
        Name of the integrator that diverged (e.g. ``"Euler"``).
    step_index
        Index ``i`` into the time grid at which the *next* state
        (``ys[i + 1]``) was first detected as non-finite. ``ys[: i + 1]``
        is still finite; everything after is invalid.
    t
        Wall-time on the integration grid at the failing step
        (``ts[step_index]``).
    """

    def __init__(self, integrator: str, step_index: int, t: float) -> None:
        self.integrator = integrator
        self.step_index = int(step_index)
        self.t = float(t)
        super().__init__(
            f"{integrator} diverged at step {self.step_index} (t≈{self.t:.4g}): "
            "state became non-finite. Try a smaller dt or a higher-order "
            "integrator (RK4, RK45, DOP853)."
        )


@runtime_checkable
class Integrator(Protocol):
    """Structural type for an ODE integrator.

    Any integrator we ship satisfies this protocol; user code can pass a
    custom integrator too. The required ``name`` attribute is what shows
    up in :class:`~chaotic_systems.core.Trajectory.integrator`.
    """

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
    ) -> Trajectory: ...


__all__ = ["Integrator", "IntegratorDivergedError", "RHS"]
