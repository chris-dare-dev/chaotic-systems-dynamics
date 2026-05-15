"""Driven Duffing oscillator (1-DOF chaotic forced oscillator).

.. math::

    \\ddot x + \\delta \\dot x + \\alpha x + \\beta x^3
    = \\gamma \\cos(\\omega t).

As a first-order system on :math:`(x, \\dot x) = (x, v)`:

.. math::

    \\dot x &= v,\\\\
    \\dot v &= -\\delta v - \\alpha x - \\beta x^3 + \\gamma \\cos(\\omega t).

Canonical chaotic regime: :math:`\\alpha = -1, \\beta = 1,
\\delta = 0.2, \\gamma = 0.3, \\omega = 1`.

References
----------
- F. C. Moon, *Chaotic Vibrations*, Wiley 1987 — see section 3.
- G. Duffing, *Erzwungene Schwingungen bei veränderlicher Eigenfrequenz*,
  Vieweg 1918.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np

from chaotic_systems.core.base import DynamicalSystem, FloatArray, Parameter


class Duffing(DynamicalSystem):
    """Periodically driven Duffing oscillator."""

    name = "Duffing"
    latex = (
        r"\begin{aligned}\dot x &= v\\"
        r"\dot v &= -\delta v - \alpha x - \beta x^3 + \gamma \cos(\omega t)\end{aligned}"
    )
    state_dim = 2
    parameters = {
        "alpha": Parameter("alpha", -1.0, -5.0, 5.0, "linear stiffness"),
        "beta": Parameter("beta", 1.0, -5.0, 5.0, "cubic stiffness"),
        "delta": Parameter("delta", 0.2, 0.0, 2.0, "damping"),
        "gamma": Parameter("gamma", 0.3, 0.0, 5.0, "drive amplitude"),
        "omega": Parameter("omega", 1.0, 0.1, 10.0, "drive angular frequency"),
    }
    default_initial_state = np.array([0.1, 0.0], dtype=np.float64)

    def _rhs(
        self, t: float, y: FloatArray, params: Mapping[str, float]
    ) -> FloatArray:
        x, v = y[0], y[1]
        alpha = params["alpha"]
        beta = params["beta"]
        delta = params["delta"]
        gamma = params["gamma"]
        omega = params["omega"]
        return np.array(
            [
                v,
                -delta * v - alpha * x - beta * x * x * x + gamma * math.cos(omega * t),
            ],
            dtype=np.float64,
        )


__all__ = ["Duffing"]
