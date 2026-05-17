"""Core abstractions: ``DynamicalSystem``, integrator base types, etc.

The public surface here is the contract the GUI and visualization layers
consume. Importing from submodules is fine, but the symbols re-exported
at this package level are the supported ones.
"""

from chaotic_systems.core.base import (
    DynamicalSystem,
    FloatArray,
    Parameter,
    Trajectory,
)
from chaotic_systems.core.discrete import DiscreteSystem
from chaotic_systems.core.hamiltonian import HamiltonianSystem
from chaotic_systems.core.lagrangian import LagrangianSystem
from chaotic_systems.core.lyapunov import (
    largest_lyapunov_two_trajectory,
    lyapunov_spectrum,
)
from chaotic_systems.core.poincare import poincare_section

__all__ = [
    "DiscreteSystem",
    "DynamicalSystem",
    "FloatArray",
    "HamiltonianSystem",
    "LagrangianSystem",
    "Parameter",
    "Trajectory",
    "largest_lyapunov_two_trajectory",
    "lyapunov_spectrum",
    "poincare_section",
]
