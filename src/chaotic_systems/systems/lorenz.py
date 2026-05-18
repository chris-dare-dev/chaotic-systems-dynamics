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
    educational_notes = """\
**The original chaotic flow.** Lorenz (1963) derived this 3-mode
truncation as a toy model of Rayleigh-Bénard convection — fluid
heated from below. It's the system that put "sensitive dependence on
initial conditions" on the map.

**Where to read about it:** Strogatz, *Nonlinear Dynamics and Chaos*
2e, §9.3–9.5; Sparrow, *The Lorenz Equations* (1982) for the full
treatment.

**Why it matters:** the *strange attractor* is here in its purest
form — a fractal of Hausdorff dimension ≈ 2.06 living inside a 3D
state space. The largest Lyapunov exponent at the canonical
parameters is λ₁ ≈ 0.9056 (Wolf et al. 1985); the Diagnostics card
recovers it to within 1%.

**Try these excursions:**

- ρ = 23: the two non-zero fixed points are stable; trajectories
  spiral into them.
- ρ = 24.06: just past the *homoclinic explosion*; the strange
  invariant set appears but is not yet attracting.
- ρ = 24.74: Hopf bifurcation — the fixed points lose stability.
- ρ = 28: the canonical chaos.
- ρ = 100.5 / 160 / 350: three different windows of stable
  *periodic* orbits embedded in the chaotic regime (Strogatz §9.5,
  Fig 9.5.5).
"""
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
