"""3D rendering, animation, and video export.

Public surface
--------------
- :class:`Renderer3D` — animate a trajectory and export it to video.
- :func:`latex_to_array` / :func:`latex_to_qimage` — render LaTeX (mathtext) to
  an image or ``QImage`` suitable for embedding in the GUI.
- :func:`as_points` — normalize a ``Trajectory`` to an ``(N, 3)`` ndarray.

The :mod:`chaotic_systems.visualization.contract` module documents the
interface this layer expects of the math agent's backend.
"""

from __future__ import annotations

from .contract import Parameter, Trajectory, as_points, default_params
from .latex import latex_to_array, latex_to_qimage, sympy_to_latex
from .renderer import Renderer3D

__all__ = [
    "Parameter",
    "Renderer3D",
    "Trajectory",
    "as_points",
    "default_params",
    "latex_to_array",
    "latex_to_qimage",
    "sympy_to_latex",
]
