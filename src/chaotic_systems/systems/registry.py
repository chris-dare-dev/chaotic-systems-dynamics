"""Registry of all concrete dynamical systems.

This is the **public entry point for GUI / visualization layers** —
:func:`list_systems` enumerates every continuous-time chaotic system
the project ships (as ready-to-use *instances*), :func:`list_maps`
does the same for discrete-time maps, and :func:`list_all_systems`
returns the union. :func:`get_system` and :func:`get_map` resolve a
single instance by name; :func:`get_any_system` resolves either kind.

To add a new system:

1. Create ``src/chaotic_systems/systems/<name>.py`` exporting either a
   :class:`~chaotic_systems.core.DynamicalSystem` subclass (ODE flow) or
   a :class:`~chaotic_systems.core.DiscreteSystem` subclass (iterated map).
2. Register it below by adding a line to :data:`_SYSTEM_CLASSES` (for
   ODE systems) or :data:`_MAP_CLASSES` (for maps).
3. Add a row to ``docs/systems.md``.

That's it. No magic auto-import — the explicit list is what gives us
deterministic ordering and clear errors if a system fails to import.

Why instances and not classes?
------------------------------
The GUI and visualization layers consume ``SystemLike`` instances (see
:mod:`chaotic_systems.visualization.contract`). Returning bare classes
forces every caller to re-instantiate, and tempts subtle bugs like
``getattr(cls, "initial_state")`` returning the ``@property`` descriptor
instead of a ``(state_dim,)`` ndarray. We instantiate each registered
system **once at import time** and hand out those instances directly.

Concrete systems are stateless w.r.t. simulation — instance state is
limited to cached symbolic derivations (e.g. the ``DoublePendulum``'s
``_lsys`` cached property), which is exactly what we want to share
across GUI runs.

ODE vs. map discrimination
--------------------------
Continuous systems and discrete maps share enough metadata surface
(``name`` / ``latex`` / ``parameters`` / ``state_dim`` /
``initial_state``) to flow through the same GUI parameter form, but
their runtime semantics differ — one has integrators and a ``dt``,
the other only has an iterate index. Each instance carries a
``kind`` class attribute (``"ode"`` or ``"map"``) the GUI / consumers
read at runtime to pick the right control surface. Existing callers
that only know ``list_systems()`` continue to see ODE flows only and
need no changes.
"""

from __future__ import annotations

from chaotic_systems.core.base import DynamicalSystem
from chaotic_systems.core.discrete import DiscreteSystem
from chaotic_systems.systems.chua import Chua
from chaotic_systems.systems.double_pendulum import DoublePendulum
from chaotic_systems.systems.duffing import Duffing
from chaotic_systems.systems.henon_heiles import HenonHeiles
from chaotic_systems.systems.henon_map import HenonMap
from chaotic_systems.systems.ikeda import Ikeda
from chaotic_systems.systems.logistic import Logistic
from chaotic_systems.systems.lorenz import Lorenz
from chaotic_systems.systems.mackey_glass import MackeyGlass
from chaotic_systems.systems.rossler import Rossler
from chaotic_systems.systems.rossler_hyper import RosslerHyper
from chaotic_systems.systems.standard_map import StandardMap

# Ordered tuple of ODE-flow classes — defines the GUI display order.
# MackeyGlass is a DDE rather than an ODE but inherits DynamicalSystem
# and overrides ``simulate`` to dispatch to BellenRK4 internally, so it
# slots into the same registry surface the GUI consumes.
_SYSTEM_CLASSES: tuple[type[DynamicalSystem], ...] = (
    Lorenz,
    Rossler,
    RosslerHyper,
    DoublePendulum,
    Chua,
    HenonHeiles,
    Duffing,
    MackeyGlass,
)

# Ordered tuple of discrete-map classes. Listed in pedagogical order
# (Strogatz §10 traversal): 1D logistic → 2D Hénon → 2D Ikeda
# (dissipative) → 2D area-preserving standard map.
_MAP_CLASSES: tuple[type[DiscreteSystem], ...] = (
    Logistic,
    HenonMap,
    Ikeda,
    StandardMap,
)


def _instantiate_systems() -> tuple[DynamicalSystem, ...]:
    """Instantiate every registered ODE system once, with uniqueness check."""

    instances: list[DynamicalSystem] = []
    seen: dict[str, type[DynamicalSystem]] = {}
    for cls in _SYSTEM_CLASSES:
        if cls.name in seen:
            raise RuntimeError(
                f"duplicate system name {cls.name!r}: "
                f"{seen[cls.name].__module__}.{seen[cls.name].__name__} "
                f"vs {cls.__module__}.{cls.__name__}"
            )
        seen[cls.name] = cls
        instances.append(cls())
    return tuple(instances)


def _instantiate_maps() -> tuple[DiscreteSystem, ...]:
    """Instantiate every registered discrete map once, with uniqueness check."""

    instances: list[DiscreteSystem] = []
    seen: dict[str, type[DiscreteSystem]] = {}
    for cls in _MAP_CLASSES:
        if cls.name in seen:
            raise RuntimeError(
                f"duplicate map name {cls.name!r}: "
                f"{seen[cls.name].__module__}.{seen[cls.name].__name__} "
                f"vs {cls.__module__}.{cls.__name__}"
            )
        seen[cls.name] = cls
        instances.append(cls())
    return tuple(instances)


_SYSTEMS: tuple[DynamicalSystem, ...] = _instantiate_systems()
_MAPS: tuple[DiscreteSystem, ...] = _instantiate_maps()

# Guard against accidental name collisions across the ODE and map registries.
_ode_names: set[str] = {sys.name for sys in _SYSTEMS}
_map_names: set[str] = {m.name for m in _MAPS}
_collision = _ode_names & _map_names
if _collision:
    raise RuntimeError(
        f"name collision between ODE systems and discrete maps: {sorted(_collision)}"
    )

_BY_NAME: dict[str, DynamicalSystem] = {sys.name: sys for sys in _SYSTEMS}
_MAPS_BY_NAME: dict[str, DiscreteSystem] = {m.name: m for m in _MAPS}


# ---- ODE-flow API (unchanged contract) ---------------------------------


def list_systems() -> list[DynamicalSystem]:
    """Return the list of all registered ODE system *instances* (stable order)."""
    return list(_SYSTEMS)


def list_system_names() -> list[str]:
    """Return the names of all registered ODE systems in display order."""
    return [sys.name for sys in _SYSTEMS]


def get_system(name: str) -> DynamicalSystem:
    """Return the registered ODE system instance with the given ``name``.

    The returned object is the singleton instance held by the registry.
    Concrete systems are designed to be stateless w.r.t. simulation, so
    sharing is safe. Callers who need an independent copy can construct
    one directly via the system class.

    Raises
    ------
    KeyError
        If ``name`` is not a registered ODE system. Discrete maps are
        deliberately *not* searched here — use :func:`get_map` or
        :func:`get_any_system` if you want either kind.
    """
    try:
        return _BY_NAME[name]
    except KeyError as exc:
        raise KeyError(
            f"unknown system {name!r}; known: {sorted(_BY_NAME)}"
        ) from exc


# ---- Discrete-map API --------------------------------------------------


def list_maps() -> list[DiscreteSystem]:
    """Return the list of all registered discrete map *instances*."""
    return list(_MAPS)


def list_map_names() -> list[str]:
    """Return the names of all registered maps in display order."""
    return [m.name for m in _MAPS]


def get_map(name: str) -> DiscreteSystem:
    """Return the registered map instance with the given ``name``.

    Raises
    ------
    KeyError
        If ``name`` is not a registered map.
    """
    try:
        return _MAPS_BY_NAME[name]
    except KeyError as exc:
        raise KeyError(
            f"unknown map {name!r}; known: {sorted(_MAPS_BY_NAME)}"
        ) from exc


# ---- Union API ---------------------------------------------------------


def list_all_systems() -> list[DynamicalSystem | DiscreteSystem]:
    """Return every registered system, both ODE flows and discrete maps.

    Ordering is ODE flows first (in :func:`list_systems` order), then
    discrete maps (in :func:`list_maps` order). Each instance carries
    a ``kind`` attribute (``"ode"`` or ``"map"``) the caller can
    switch on.
    """
    return [*_SYSTEMS, *_MAPS]


def get_any_system(name: str) -> DynamicalSystem | DiscreteSystem:
    """Resolve a system by name, looking up ODE flows then maps.

    Raises
    ------
    KeyError
        If ``name`` is not a registered ODE system or map.
    """
    if name in _BY_NAME:
        return _BY_NAME[name]
    if name in _MAPS_BY_NAME:
        return _MAPS_BY_NAME[name]
    raise KeyError(
        f"unknown system or map {name!r}; "
        f"known systems: {sorted(_BY_NAME)}; "
        f"known maps: {sorted(_MAPS_BY_NAME)}"
    )


__all__ = [
    "get_any_system",
    "get_map",
    "get_system",
    "list_all_systems",
    "list_map_names",
    "list_maps",
    "list_system_names",
    "list_systems",
]
