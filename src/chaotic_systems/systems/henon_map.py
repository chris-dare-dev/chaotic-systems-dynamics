"""The Hénon map.

.. math::

    x_{n+1} &= 1 - a\\,x_n^2 + y_n, \\\\
    y_{n+1} &= b\\,x_n.

Hénon's 1976 two-dimensional map is the canonical "stretch and fold"
illustration of how a fractal strange attractor arises from a simple
polynomial transformation. At the textbook parameters ``a = 1.4``,
``b = 0.3`` the iterates fill out a thin Cantor-set-cross-arc
attractor.

The Jacobian determinant is the constant ``-b``, so the map contracts
area uniformly by ``|b|`` per iterate. With ``b = 0.3`` the long-time
volume contraction matches a strange attractor in the strict sense
(positive λ_1, λ_1 + λ_2 < 0). Hénon (1976) reports
``λ_1 ≈ 0.42`` and ``λ_2 ≈ -1.62``.

References
----------
- M. Hénon, *A two-dimensional mapping with a strange attractor*,
  Commun. Math. Phys. 50 (1976), 69-77.
- E. Ott, *Chaos in Dynamical Systems* (2nd ed., 2002), §4.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from chaotic_systems.core.base import FloatArray, Parameter
from chaotic_systems.core.discrete import DiscreteSystem

# Canonical "strange attractor" regime (Hénon 1976).
_DEFAULT_A: float = 1.4
_DEFAULT_B: float = 0.3


class HenonMap(DiscreteSystem):
    """The Hénon map :math:`(x, y) \\mapsto (1 - a x^2 + y,\\, b x)`."""

    name = "HenonMap"
    latex = (
        r"\begin{aligned}x_{n+1} &= 1 - a\,x_n^2 + y_n\\"
        r"y_{n+1} &= b\,x_n\end{aligned}"
    )
    state_dim = 2
    parameters = {
        "a": Parameter("a", _DEFAULT_A, 0.0, 2.0, "nonlinearity"),
        "b": Parameter("b", _DEFAULT_B, -1.0, 1.0, "area contraction factor"),
    }
    default_initial_state = np.array([0.0, 0.0], dtype=np.float64)
    educational_notes = """\
**Stretch and fold, in 30 characters of code.** The Hénon map
(1976) is the smallest interesting 2D map with a *strange
attractor*. Its iterates trace out a thin Cantor-set-cross-arc
that's the textbook illustration of how fractal structure arises
from a smooth polynomial.

**Where to read about it:** Hénon, *A two-dimensional mapping with
a strange attractor*, Commun. Math. Phys. 50 (1976); Ott, *Chaos
in Dynamical Systems* 2e, §4.

**Area contraction.** The Jacobian determinant is identically −b,
so every iterate shrinks the area by |b|. With b = 0.3 the orbit
is dissipative; with b = 1 it would be area-preserving (and the
attractor would not be strange — pick the standard map for that
instead).

**The route to chaos** (sweep a at fixed b = 0.3):

- a = 0.5: period-1 fixed point.
- a = 1.06: period-doubling begins.
- a = 1.22: period-4.
- a = 1.40: chaos (the canonical "Hénon attractor" figure).
- a ≈ 1.06 to ≈ 1.40 in the Bifurcation explorer shows the
  full cascade.

Largest Lyapunov exponent at canonical (1.4, 0.3): λ₁ ≈ 0.42
(Hénon 1976), λ₂ ≈ −1.62 — sum is ln|−b| = ln 0.3 ≈ −1.20
(matches λ₁ + λ₂ within ~10⁻²).
"""

    def _step(self, y: FloatArray, params: Mapping[str, float]) -> FloatArray:
        x, yv = y[0], y[1]
        a = params["a"]
        b = params["b"]
        return np.array([1.0 - a * x * x + yv, b * x], dtype=np.float64)


__all__ = ["HenonMap"]
