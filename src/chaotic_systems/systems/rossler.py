"""The Rössler attractor.

.. math::

    \\dot x &= -y - z, \\\\
    \\dot y &= x + a y, \\\\
    \\dot z &= b + z (x - c).

Canonical chaotic regime: :math:`a = 0.2, b = 0.2, c = 5.7`.
Largest Lyapunov exponent :math:`\\lambda_1 \\approx 0.071`.

References
----------
- O. E. Rössler, *An equation for continuous chaos*, Physics Letters A
  57 (1976), 397-398.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from chaotic_systems.core.base import DynamicalSystem, FloatArray, Parameter


class Rossler(DynamicalSystem):
    """Rössler attractor."""

    name = "Rossler"
    latex = (
        r"\begin{aligned}\dot x &= -y - z\\"
        r"\dot y &= x + a y\\"
        r"\dot z &= b + z(x - c)\end{aligned}"
    )
    state_dim = 3
    parameters = {
        "a": Parameter("a", 0.2, 0.0, 1.0, "coupling parameter"),
        "b": Parameter("b", 0.2, 0.0, 5.0, "drive parameter"),
        "c": Parameter("c", 5.7, 0.0, 30.0, "bifurcation parameter"),
    }
    default_initial_state = np.array([0.1, 0.0, 0.0], dtype=np.float64)

    def _rhs(
        self, t: float, y: FloatArray, params: Mapping[str, float]
    ) -> FloatArray:
        x, y_, z = y[0], y[1], y[2]
        a = params["a"]
        b = params["b"]
        c = params["c"]
        return np.array(
            [
                -y_ - z,
                x + a * y_,
                b + z * (x - c),
            ],
            dtype=np.float64,
        )


__all__ = ["Rossler"]
