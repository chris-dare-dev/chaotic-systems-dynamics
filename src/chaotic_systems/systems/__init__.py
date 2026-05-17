"""Concrete chaotic systems.

Each module here exports one :class:`~chaotic_systems.core.DynamicalSystem`
subclass. The registry at :mod:`chaotic_systems.systems.registry` is the
authoritative entry point used by the GUI / visualization.
"""

from chaotic_systems.systems.chua import Chua
from chaotic_systems.systems.double_pendulum import DoublePendulum
from chaotic_systems.systems.duffing import Duffing
from chaotic_systems.systems.henon_heiles import HenonHeiles
from chaotic_systems.systems.lorenz import Lorenz
from chaotic_systems.systems.registry import (
    get_system,
    list_system_names,
    list_systems,
)
from chaotic_systems.systems.rossler import Rossler
from chaotic_systems.systems.rossler_hyper import RosslerHyper

__all__ = [
    "Chua",
    "DoublePendulum",
    "Duffing",
    "HenonHeiles",
    "Lorenz",
    "Rossler",
    "RosslerHyper",
    "get_system",
    "list_system_names",
    "list_systems",
]
