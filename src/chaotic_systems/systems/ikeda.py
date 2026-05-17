"""The Ikeda map.

.. math::

    t_n &= 0.4 - \\frac{6}{1 + x_n^2 + y_n^2}, \\\\
    x_{n+1} &= 1 + u\\,(x_n \\cos t_n - y_n \\sin t_n), \\\\
    y_{n+1} &= u\\,(x_n \\sin t_n + y_n \\cos t_n).

Ikeda's 1979 model arose from a *laser pulse propagating round a
nonlinear ring cavity*. The complex amplitude obeys
``E_{n+1} = A + B E_n exp(i phi(|E_n|^2))``; the real form above is the
standard two-real-coordinate reduction (Hammel, Jones & Moloney 1985).

The single parameter ``u`` is the dissipation × gain product. The map
is contracting (Jacobian magnitude ``u``); for ``u >= ~0.6`` the
attractor is the famous *Ikeda spiral* — a self-similar set of nested
arcs. The canonical demo value ``u = 0.9`` yields a strange attractor;
``u = 1`` is area-preserving.

References
----------
- K. Ikeda, *Multiple-valued stationary state and its instability of
  the transmitted light by a ring cavity system*, Optics Comm. 30
  (1979), 257-261.
- S. M. Hammel, C. K. R. T. Jones and J. V. Moloney, *Global dynamical
  behavior of the optical field in a ring cavity*, J. Opt. Soc. Am. B
  2 (1985), 552-564.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from chaotic_systems.core.base import FloatArray, Parameter
from chaotic_systems.core.discrete import DiscreteSystem

# Canonical "Ikeda spiral" demo value (Hammel et al. 1985).
_DEFAULT_U: float = 0.9

# Phase-function constants baked into the standard reduction
# (Wikipedia "Ikeda map"; Hammel et al. 1985). Treated as project
# constants rather than tunable parameters to match the textbook
# single-knob presentation.
_PHASE_OFFSET: float = 0.4
_PHASE_DENOM_SCALE: float = 6.0


class Ikeda(DiscreteSystem):
    """The Ikeda map — single dissipation/gain knob ``u``."""

    name = "Ikeda"
    latex = (
        r"\begin{aligned}"
        r"t_n &= 0.4 - \tfrac{6}{1 + x_n^2 + y_n^2}\\"
        r"x_{n+1} &= 1 + u\,(x_n \cos t_n - y_n \sin t_n)\\"
        r"y_{n+1} &= u\,(x_n \sin t_n + y_n \cos t_n)"
        r"\end{aligned}"
    )
    state_dim = 2
    parameters = {
        "u": Parameter(
            "u",
            _DEFAULT_U,
            0.0,
            1.0,
            "dissipation × gain (strange attractor for u ≳ 0.6)",
        ),
    }
    default_initial_state = np.array([0.1, 0.1], dtype=np.float64)

    def _step(self, y: FloatArray, params: Mapping[str, float]) -> FloatArray:
        x, yv = y[0], y[1]
        u = params["u"]
        t = _PHASE_OFFSET - _PHASE_DENOM_SCALE / (1.0 + x * x + yv * yv)
        cos_t = float(np.cos(t))
        sin_t = float(np.sin(t))
        return np.array(
            [
                1.0 + u * (x * cos_t - yv * sin_t),
                u * (x * sin_t + yv * cos_t),
            ],
            dtype=np.float64,
        )


__all__ = ["Ikeda"]
