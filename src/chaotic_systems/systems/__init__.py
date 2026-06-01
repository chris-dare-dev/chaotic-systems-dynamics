"""Concrete chaotic systems — both continuous flows and discrete maps.

ODE flows subclass :class:`~chaotic_systems.core.DynamicalSystem`;
discrete-time maps subclass
:class:`~chaotic_systems.core.DiscreteSystem`. Each instance exposes a
``kind`` class attribute (``"ode"`` or ``"map"``) so the GUI can switch
on it.

The registry at :mod:`chaotic_systems.systems.registry` is the
authoritative entry point used by the GUI / visualization.
"""

from chaotic_systems.systems.chua import Chua
from chaotic_systems.systems.conradi import ConradiMap
from chaotic_systems.systems.double_pendulum import DoublePendulum
from chaotic_systems.systems.duffing import Duffing
from chaotic_systems.systems.henon_heiles import HenonHeiles
from chaotic_systems.systems.henon_map import HenonMap
from chaotic_systems.systems.ikeda import Ikeda
from chaotic_systems.systems.kuramoto import Kuramoto
from chaotic_systems.systems.logistic import Logistic
from chaotic_systems.systems.lorenz import Lorenz
from chaotic_systems.systems.mackey_glass import MackeyGlass
from chaotic_systems.systems.registry import (
    get_any_system,
    get_map,
    get_system,
    list_all_systems,
    list_map_names,
    list_maps,
    list_system_names,
    list_systems,
)
from chaotic_systems.systems.rossler import Rossler
from chaotic_systems.systems.rossler_hyper import RosslerHyper
from chaotic_systems.systems.standard_map import StandardMap

__all__ = [
    "Chua",
    "ConradiMap",
    "DoublePendulum",
    "Duffing",
    "HenonHeiles",
    "HenonMap",
    "Ikeda",
    "Kuramoto",
    "Logistic",
    "Lorenz",
    "MackeyGlass",
    "Rossler",
    "RosslerHyper",
    "StandardMap",
    "get_any_system",
    "get_map",
    "get_system",
    "list_all_systems",
    "list_map_names",
    "list_maps",
    "list_system_names",
    "list_systems",
]
