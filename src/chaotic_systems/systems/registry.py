"""Registry of all concrete dynamical systems.

This is the **public entry point for GUI / visualization layers** —
:func:`list_systems` enumerates every chaotic system the project ships,
and :func:`get_system` resolves one by name.

To add a new system:

1. Create ``src/chaotic_systems/systems/<name>.py`` exporting a
   :class:`~chaotic_systems.core.DynamicalSystem` subclass.
2. Register it below by adding a line to :data:`_SYSTEMS`.
3. Add a row to ``docs/systems.md``.

That's it. No magic auto-import — the explicit list is what gives us
deterministic ordering and clear errors if a system fails to import.
"""

from __future__ import annotations

from chaotic_systems.core.base import DynamicalSystem
from chaotic_systems.systems.chua import Chua
from chaotic_systems.systems.double_pendulum import DoublePendulum
from chaotic_systems.systems.duffing import Duffing
from chaotic_systems.systems.henon_heiles import HenonHeiles
from chaotic_systems.systems.lorenz import Lorenz
from chaotic_systems.systems.rossler import Rossler

# Ordered tuple so the GUI gets a stable display order.
_SYSTEMS: tuple[type[DynamicalSystem], ...] = (
    Lorenz,
    Rossler,
    DoublePendulum,
    Chua,
    HenonHeiles,
    Duffing,
)

_BY_NAME: dict[str, type[DynamicalSystem]] = {cls.name: cls for cls in _SYSTEMS}


def list_systems() -> list[type[DynamicalSystem]]:
    """Return the list of all registered system classes (stable order)."""
    return list(_SYSTEMS)


def list_system_names() -> list[str]:
    """Return the names of all registered systems in display order."""
    return [cls.name for cls in _SYSTEMS]


def get_system(name: str) -> DynamicalSystem:
    """Instantiate the system with the given :attr:`~DynamicalSystem.name`.

    Raises
    ------
    KeyError
        If ``name`` is not a registered system.
    """
    try:
        cls = _BY_NAME[name]
    except KeyError as exc:
        raise KeyError(
            f"unknown system {name!r}; known: {sorted(_BY_NAME)}"
        ) from exc
    return cls()


__all__ = ["get_system", "list_system_names", "list_systems"]
