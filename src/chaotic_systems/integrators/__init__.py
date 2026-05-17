"""Numerical integrators (adaptive, fixed-step, symplectic).

This package exposes a single registry-style lookup, :func:`get_integrator`,
that returns an :class:`Integrator` instance by name. Names are
case-sensitive and match the scipy methods one-to-one
(``"RK45"``, ``"RK23"``, ``"DOP853"``, ``"Radau"``, ``"BDF"``,
``"LSODA"``) plus our hand-rolled methods (``"RK4"``, ``"Euler"``,
``"leapfrog"``, ``"velocity_verlet"``, ``"yoshida4"``).
"""

from __future__ import annotations

from chaotic_systems.integrators._protocol import (
    RHS,
    Integrator,
    IntegratorDivergedError,
)
from chaotic_systems.integrators.adaptive import (
    BDF,
    DOP853,
    LSODA,
    RK23,
    RK45,
    Radau,
)
from chaotic_systems.integrators.fixed_step import RK4, Euler
from chaotic_systems.integrators.symplectic import (
    from_hamiltonian,
    leapfrog,
    velocity_verlet,
    yoshida4,
)

_REGISTRY: dict[str, Integrator] = {
    "RK45": RK45,
    "RK23": RK23,
    "DOP853": DOP853,
    "Radau": Radau,
    "BDF": BDF,
    "LSODA": LSODA,
    "RK4": RK4,
    "Euler": Euler,
    "leapfrog": leapfrog,
    "velocity_verlet": velocity_verlet,
    "yoshida4": yoshida4,
}


def get_integrator(name: str) -> Integrator:
    """Return the integrator with the given name.

    Raises
    ------
    KeyError
        If ``name`` is not a known integrator.
    """
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(
            f"unknown integrator {name!r}; known: {sorted(_REGISTRY)}"
        ) from exc


def list_integrators() -> list[str]:
    """Return the names of all registered integrators (sorted)."""
    return sorted(_REGISTRY)


#: Registry-key set for integrators that require a separable Hamiltonian
#: (i.e. ``grad_T(p)`` and ``grad_V(q)`` callbacks). Consumers like the
#: GUI use this to gate the integrator picker — for a non-Hamiltonian
#: system (Lorenz, Rossler, Chua, Duffing, ...) these methods cannot be
#: applied and the picker should disable them rather than letting the
#: user trigger a cryptic ``grad_t_fn`` / ``grad_v_fn`` error mid-Run.
SYMPLECTIC_INTEGRATORS: frozenset[str] = frozenset(
    {"leapfrog", "velocity_verlet", "yoshida4"}
)


__all__ = [
    "BDF",
    "DOP853",
    "Euler",
    "Integrator",
    "IntegratorDivergedError",
    "LSODA",
    "RHS",
    "RK23",
    "RK4",
    "RK45",
    "Radau",
    "SYMPLECTIC_INTEGRATORS",
    "from_hamiltonian",
    "get_integrator",
    "leapfrog",
    "list_integrators",
    "velocity_verlet",
    "yoshida4",
]
