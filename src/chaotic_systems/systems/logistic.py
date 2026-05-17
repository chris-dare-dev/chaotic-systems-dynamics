"""The logistic map.

.. math::

    x_{n+1} = r\\,x_n (1 - x_n), \\qquad x_n \\in [0, 1].

The single-parameter logistic map is the simplest system that exhibits
the *period-doubling cascade to chaos* (Feigenbaum 1978). As ``r``
increases through ``[0, 4]``:

- ``0 < r < 1``: the only attractor is ``x* = 0``;
- ``1 < r < 3``: a single non-zero fixed point ``x* = 1 - 1/r``;
- ``3 < r < 1 + sqrt(6) ≈ 3.449``: period-2 orbit;
- successive period doublings accumulate at
  ``r_∞ ≈ 3.5699456``;
- beyond ``r_∞`` the orbit is chaotic, with periodic windows
  (the period-3 window at ``r ≈ 3.828`` is the most visible).

This is the canonical pedagogical entry point to discrete-time chaos
(Strogatz §10.2). It is also the natural smoke test for proposal N1's
:class:`~chaotic_systems.core.discrete.DiscreteSystem` machinery:
``state_dim = 1`` and the map is a one-liner.

References
----------
- R. May, *Simple mathematical models with very complicated dynamics*,
  Nature 261 (1976), 459-467.
- M. J. Feigenbaum, *Quantitative universality for a class of nonlinear
  transformations*, J. Stat. Phys. 19 (1978), 25-52.
- S. Strogatz, *Nonlinear Dynamics and Chaos* (2nd ed., 2015), §10.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from chaotic_systems.core.base import FloatArray, Parameter
from chaotic_systems.core.discrete import DiscreteSystem

# Canonical "deep chaos" regime past the period-doubling accumulation
# point r_inf ≈ 3.5699 and past the period-3 window at r ≈ 3.828.
_DEFAULT_R: float = 3.9


class Logistic(DiscreteSystem):
    """One-dimensional logistic map :math:`x_{n+1} = r x_n (1 - x_n)`."""

    name = "Logistic"
    latex = r"x_{n+1} = r\,x_n (1 - x_n)"
    state_dim = 1
    parameters = {
        "r": Parameter(
            "r",
            _DEFAULT_R,
            0.0,
            4.0,
            "growth rate; chaotic beyond the Feigenbaum point r_inf ≈ 3.5699",
        ),
    }
    default_initial_state = np.array([0.5], dtype=np.float64)

    def _step(self, y: FloatArray, params: Mapping[str, float]) -> FloatArray:
        x = y[0]
        r = params["r"]
        return np.array([r * x * (1.0 - x)], dtype=np.float64)


__all__ = ["Logistic"]
