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
    educational_notes = """\
**Chaos in a 1-DOF driven oscillator.** The Duffing equation (1918)
is a textbook nonlinear oscillator with a double-well potential
V(x) = ½αx² + ¼βx⁴, periodically driven. The 2D autonomous state
*(x, v)* lifts to a 3D non-autonomous one once you fold in the
driving phase ωt — and that's exactly where chaos lives (the
Poincaré-Bendixson theorem rules it out in 2D autonomous).

**Where to read about it:** Guckenheimer & Holmes, *Nonlinear
Oscillations, Dynamical Systems, and Bifurcations of Vector
Fields* (1983), §2.2; Strogatz §12.5; Moon, *Chaotic Vibrations*
(1987), §3.

**The route to chaos:** vary the drive amplitude γ at fixed
ω = 1, δ = 0.2:

- γ = 0.10: damped oscillation in one well, no jumps.
- γ = 0.20: regular cross-well jumps every drive period.
- γ = 0.28: period-doubled jumps.
- γ = 0.30: chaotic cross-well jumps — the canonical regime.
- γ = 0.50: period-1 again — chaos has a *finite* parameter
  window.

**Pair with the V1 phase portrait** on (y[0], y[1]) = (x, v) —
the cross-well jumps are visually unmistakable, and the strange
attractor in the Poincaré section (sampled once per drive period)
is the chunky "Duffing fractal" Moon's 1987 book opens with.
"""

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
                -delta * v - alpha * x - beta * x * x * x + gamma * np.cos(omega * t),
            ],
            dtype=np.float64,
        )


__all__ = ["Duffing"]
