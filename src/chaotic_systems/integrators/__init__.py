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

# N3 — DDE integrator. Exposed at package level so callers can
# instantiate / introspect it; *not* registered in ``_REGISTRY``
# below because BellenRK4 has a non-Integrator-protocol signature
# (the delay + history function don't fit the ODE shape).
from chaotic_systems.integrators.dde import BellenRK4
from chaotic_systems.integrators.fixed_step import RK4, Euler

# I1 — JAX backend. The ``jax_backend`` module itself imports cleanly
# *without* JAX / diffrax installed; only :meth:`integrate` actually
# pulls them in. That keeps the no-JAX import-cost story honest while
# letting the GUI's integrator picker advertise the JAX options
# uniformly. If the user picks one without the extra installed, the
# resulting ImportError surfaces on the first Run with a hint.
from chaotic_systems.integrators.jax_backend import JaxRK45, JaxTsit5

# I2 — numbalsoda backend. Like the JAX backend, the module imports
# cleanly without numbalsoda / numba installed; only :meth:`integrate`
# pulls them in. Listed in ``_REGISTRY`` so the GUI's integrator
# picker advertises it uniformly. If the user picks it without the
# ``[performance]`` extra installed, the resulting ImportError
# surfaces on the first Run with a hint.
from chaotic_systems.integrators.numbalsoda_backend import NumbaLSODA
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
    # I1 — JAX/diffrax-backed integrators. Listed last so the
    # picker's default selection (RK45) stays unchanged.
    "JAX-RK45": JaxRK45,
    "JAX-Tsit5": JaxTsit5,
    # I2 — numbalsoda-backed LSODA. Same optional-extra story as
    # the JAX entries above; gated on the ``[performance]`` extra.
    "NumbaLSODA": NumbaLSODA,
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
    "BellenRK4",
    "Euler",
    "Integrator",
    "IntegratorDivergedError",
    "JaxRK45",
    "JaxTsit5",
    "LSODA",
    "NumbaLSODA",
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
