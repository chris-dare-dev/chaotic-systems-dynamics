"""The Chirikov standard map.

.. math::

    p_{n+1}     &= p_n + K \\sin\\theta_n
                   \\quad (\\mathrm{mod}\\ 2\\pi), \\\\
    \\theta_{n+1} &= \\theta_n + p_{n+1}
                   \\quad (\\mathrm{mod}\\ 2\\pi).

Chirikov's 1979 *standard map* is the universal local model for
near-integrable Hamiltonian dynamics in two degrees of freedom: it is
what a generic twist map looks like near a resonance. It is
**area-preserving** for every ``K`` — the Jacobian determinant is
identically ``1`` — and was the first system in which the
*last-KAM-torus breakup* was numerically observed (the *golden-mean
KAM curve* survives up to the critical value
``K_c ≈ 0.971635 4...``; above that, global stochasticity sets in).

The combination of integrable backbone (``K = 0``: rigid rotation),
mixed phase space (``K ≲ 1``: KAM tori coexisting with chaotic seas),
and global chaos (``K ≳ 1``) makes this the canonical sandbox for the
Kolmogorov-Arnold-Moser theorem and Hamiltonian-chaos pedagogy.

References
----------
- B. V. Chirikov, *A universal instability of many-dimensional
  oscillator systems*, Physics Reports 52 (1979), 263-379.
- J. M. Greene, *A method for determining a stochastic transition*,
  J. Math. Phys. 20 (1979), 1183-1201 — the analysis that fixes
  ``K_c``.
- A. J. Lichtenberg and M. A. Lieberman, *Regular and Chaotic
  Dynamics* (2nd ed., 1992), §4.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from chaotic_systems.core.base import FloatArray, Parameter
from chaotic_systems.core.discrete import DiscreteSystem

# Chirikov critical stochasticity parameter — the golden-mean KAM
# torus dissolves at this value (Greene 1979). At the canonical demo
# value of 0.971635, the map sits exactly at the last-torus breakup.
_K_CHIRIKOV_CRIT: float = 0.971635

_TWO_PI: float = 2.0 * np.pi


def _wrap(x: float) -> float:
    """Wrap a real number into ``[-pi, pi)``."""
    return float(((x + np.pi) % _TWO_PI) - np.pi)


class StandardMap(DiscreteSystem):
    """Chirikov standard map on the 2-torus, area-preserving for all ``K``."""

    name = "StandardMap"
    latex = (
        r"\begin{aligned}"
        r"p_{n+1} &= p_n + K \sin\theta_n\;(\bmod\,2\pi)\\"
        r"\theta_{n+1} &= \theta_n + p_{n+1}\;(\bmod\,2\pi)"
        r"\end{aligned}"
    )
    state_dim = 2
    parameters = {
        "K": Parameter(
            "K",
            _K_CHIRIKOV_CRIT,
            0.0,
            10.0,
            "stochasticity parameter; last KAM torus breaks at K ≈ 0.9716",
        ),
    }
    # State order is (theta, p) — angle first, action second.
    default_initial_state = np.array([0.5, 0.5], dtype=np.float64)

    def _step(self, y: FloatArray, params: Mapping[str, float]) -> FloatArray:
        theta, p = y[0], y[1]
        k = params["K"]
        p_new = _wrap(p + k * float(np.sin(theta)))
        theta_new = _wrap(theta + p_new)
        return np.array([theta_new, p_new], dtype=np.float64)


__all__ = ["StandardMap"]
