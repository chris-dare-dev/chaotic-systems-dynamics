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
from chaotic_systems.core.basins import (
    UNCLASSIFIED_LABEL,
    BasinDiagram,
    basin_diagram,
    double_well_rhs,
)
from chaotic_systems.core.bifurcation import (
    BifurcationDiagram,
    as_scatter,
    bifurcation_diagram,
)
from chaotic_systems.core.discrete import DiscreteSystem
from chaotic_systems.core.hamiltonian import HamiltonianSystem
from chaotic_systems.core.lagrangian import LagrangianSystem
from chaotic_systems.core.lyapunov import (
    largest_lyapunov_two_trajectory,
    lyapunov_spectrum,
)
from chaotic_systems.core.poincare import poincare_section
from chaotic_systems.core.recurrence import (
    RQAStats,
    recurrence_matrix,
    rqa,
    suggest_epsilon,
)

__all__ = [
    "BasinDiagram",
    "BifurcationDiagram",
    "DiscreteSystem",
    "DynamicalSystem",
    "FloatArray",
    "HamiltonianSystem",
    "LagrangianSystem",
    "Parameter",
    "RQAStats",
    "Trajectory",
    "UNCLASSIFIED_LABEL",
    "as_scatter",
    "basin_diagram",
    "bifurcation_diagram",
    "double_well_rhs",
    "largest_lyapunov_two_trajectory",
    "lyapunov_spectrum",
    "poincare_section",
    "recurrence_matrix",
    "rqa",
    "suggest_epsilon",
]
