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


__all__ = ["Integrator", "RHS"]
