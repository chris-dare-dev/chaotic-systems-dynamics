"""The Lorenz '63 system.

.. math::

    \\dot x &= \\sigma (y - x), \\\\
    \\dot y &= x (\\rho - z) - y, \\\\
    \\dot z &= x y - \\beta z.

Canonical chaotic regime: :math:`\\sigma = 10`, :math:`\\rho = 28`,
:math:`\\beta = 8/3`. Largest Lyapunov exponent
:math:`\\lambda_1 \\approx 0.9056` (Wolf et al. 1985).

References
----------
- E. N. Lorenz, *Deterministic Nonperiodic Flow*, J. Atmos. Sci. 20
  (1963), 130-141.
- A. Wolf et al., *Determining Lyapunov exponents from a time series*,
  Physica D 16 (1985), 285-317.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from chaotic_systems.core.base import DynamicalSystem, FloatArray, Parameter


class Lorenz(DynamicalSystem):
    """Lorenz '63 attractor."""

    name = "Lorenz"
    latex = (
        r"\begin{aligned}\dot x &= \sigma(y - x)\\"
        r"\dot y &= x(\rho - z) - y\\"
        r"\dot z &= xy - \beta z\end{aligned}"
    )
    lagrangian_latex: str | None = None
    state_dim = 3
    parameters = {
        "sigma": Parameter("sigma", 10.0, 0.1, 50.0, "Prandtl number", ""),
        "rho": Parameter("rho", 28.0, 0.1, 100.0, "Rayleigh number", ""),
        "beta": Parameter("beta", 8.0 / 3.0, 0.1, 10.0, "geometric factor", ""),
    }
    default_initial_state = np.array([1.0, 1.0, 1.0], dtype=np.float64)

    def _rhs(
        self, t: float, y: FloatArray, params: Mapping[str, float]
    ) -> FloatArray:
        x, y_, z = y[0], y[1], y[2]
        sigma = params["sigma"]
        rho = params["rho"]
        beta = params["beta"]
        return np.array(
            [
                sigma * (y_ - x),
                x * (rho - z) - y_,
                x * y_ - beta * z,
            ],
            dtype=np.float64,
        )


__all__ = ["Lorenz"]
