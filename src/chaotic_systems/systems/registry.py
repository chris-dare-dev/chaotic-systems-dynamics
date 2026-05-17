"""Registry of all concrete dynamical systems.

This is the **public entry point for GUI / visualization layers** —
:func:`list_systems` enumerates every chaotic system the project ships
(as ready-to-use *instances*), and :func:`get_system` resolves one by
name.

To add a new system:

1. Create ``src/chaotic_systems/systems/<name>.py`` exporting a
   :class:`~chaotic_systems.core.DynamicalSystem` subclass.
2. Register it below by adding a line to :data:`_SYSTEM_CLASSES`.
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
"""

from __future__ import annotations

from chaotic_systems.core.base import DynamicalSystem
from chaotic_systems.systems.chua import Chua
from chaotic_systems.systems.double_pendulum import DoublePendulum
from chaotic_systems.systems.duffing import Duffing
from chaotic_systems.systems.henon_heiles import HenonHeiles
from chaotic_systems.systems.lorenz import Lorenz
from chaotic_systems.systems.rossler import Rossler
from chaotic_systems.systems.rossler_hyper import RosslerHyper

# Ordered tuple of classes — defines the GUI display order.
_SYSTEM_CLASSES: tuple[type[DynamicalSystem], ...] = (
    Lorenz,
    Rossler,
    RosslerHyper,
    DoublePendulum,
    Chua,
    HenonHeiles,
    Duffing,
)


def _instantiate() -> tuple[DynamicalSystem, ...]:
    """Instantiate every registered system once, with uniqueness check."""

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


_SYSTEMS: tuple[DynamicalSystem, ...] = _instantiate()
_BY_NAME: dict[str, DynamicalSystem] = {sys.name: sys for sys in _SYSTEMS}


def list_systems() -> list[DynamicalSystem]:
    """Return the list of all registered system *instances* (stable order)."""
    return list(_SYSTEMS)


def list_system_names() -> list[str]:
    """Return the names of all registered systems in display order."""
    return [sys.name for sys in _SYSTEMS]


def get_system(name: str) -> DynamicalSystem:
    """Return the registered system instance with the given ``name``.

    The returned object is the singleton instance held by the registry.
    Concrete systems are designed to be stateless w.r.t. simulation, so
    sharing is safe. Callers who need an independent copy can construct
    one directly via the system class.

    Raises
    ------
    KeyError
        If ``name`` is not a registered system.
    """
    try:
        return _BY_NAME[name]
    except KeyError as exc:
        raise KeyError(
            f"unknown system {name!r}; known: {sorted(_BY_NAME)}"
        ) from exc


__all__ = ["get_system", "list_system_names", "list_systems"]
