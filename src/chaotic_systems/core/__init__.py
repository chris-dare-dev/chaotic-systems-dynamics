"""Core abstractions: ``DynamicalSystem``, integrator base types, etc.

The public surface here is the contract the GUI and visualization layers
consume. Importing from submodules is fine, but the symbols re-exported
at this package level are the supported ones.
"""

from chaotic_systems.core._numba import (
    NUMBA_AVAILABLE,
    CompiledRHS,
    compile_rhs,
    maybe_njit,
)
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
from chaotic_systems.core.diagnostics_protocol import (
    PostSimDiagnosticProvider,
    format_post_sim_diagnostics,
)
from chaotic_systems.core.discrete import DiscreteSystem
from chaotic_systems.core.hamiltonian import HamiltonianSystem
from chaotic_systems.core.lagrangian import LagrangianSystem
from chaotic_systems.core.lyapunov import (
    kaplan_yorke_dimension,
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
    "CompiledRHS",
    "DiscreteSystem",
    "DynamicalSystem",
    "FloatArray",
    "HamiltonianSystem",
    "LagrangianSystem",
    "NUMBA_AVAILABLE",
    "Parameter",
    "PostSimDiagnosticProvider",
    "RQAStats",
    "Trajectory",
    "UNCLASSIFIED_LABEL",
    "as_scatter",
    "basin_diagram",
    "bifurcation_diagram",
    "compile_rhs",
    "double_well_rhs",
    "format_post_sim_diagnostics",
    "kaplan_yorke_dimension",
    "largest_lyapunov_two_trajectory",
    "lyapunov_spectrum",
    "maybe_njit",
    "poincare_section",
    "recurrence_matrix",
    "rqa",
    "suggest_epsilon",
]
