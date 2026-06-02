r"""The Conradi trigonometric attractor map.

.. math::

    x_{n+1} &= \sin(x_n^2 - y_n^2 + a), \\
    y_{n+1} &= \cos(2 x_n y_n + b).

This is the iterated map behind Simone Conradi's "trigonometric attractor"
art (``Nice_orbits.ipynb`` in github.com/profConradi/Python_Simulations). The
two arguments are exactly the real and imaginary parts of :math:`z^2` for
:math:`z = x + i y` (``x^2 - y^2 = Re z^2``, ``2 x y = Im z^2``): the map
squares the complex number, shifts by the complex constant ``(a, b)``, then
applies ``sin`` to the real channel and ``cos`` to the imaginary channel. The
componentwise ``sin`` / ``cos`` breaks holomorphy and folds the plane.

Two structural facts make this map distinctive:

- **Automatically bounded.** ``sin, cos in [-1, 1]``, so every iterate after the
  first lives in ``[-1, 1] x [-1, 1]``. No blow-up is possible (unlike the
  polynomial Hénon / Clifford maps, which can diverge); the only "boring"
  failure mode is collapse to a fixed point or short cycle.
- **Dissipative.** With ``u = x^2 - y^2 + a`` and ``v = 2 x y + b`` the Jacobian
  is ``J = [[2x cos u, -2y cos u], [-2y sin v, -2x sin v]]`` and
  ``det J = -4 (x^2 + y^2) cos u sin v``, which contracts area on average, so
  the attracting set is measure-zero.

Canonical parameters ``(a, b) = (5.46, 4.55)`` are taken verbatim from
Conradi's notebook (a point in the upper-right ``[0, 2*pi]^2`` quadrant that
produces a richly folded attractor).

This module ships only the ``z^2`` member of the family. A ``z^k`` (k>2)
generalization is mathematically natural (``Re z^k`` / ``Im z^k`` via the
binomial expansion) but is **not present in Conradi's primary source**, so it
is deliberately not shipped here — adding it would attach the map's name to a
parameterization the cited reference does not contain.

References
----------
- Simone Conradi, ``Nice_orbits.ipynb``,
  https://github.com/profConradi/Python_Simulations (the exact map and the
  canonical ``(a, b) = (5.46, 4.55)`` / ``(1.7, 2.3)`` parameter pairs).
- Paul Bourke, "Simone attractor",
  https://paulbourke.net/fractals/simone_orbits/ (independent confirmation of
  the ``[-1, 1]`` boundedness of this sin/cos family).
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from chaotic_systems.core.base import FloatArray, Parameter
from chaotic_systems.core.discrete import DiscreteSystem

# Canonical regime, verbatim from Conradi's ``Nice_orbits.ipynb``.
_DEFAULT_A: float = 5.46
_DEFAULT_B: float = 4.55

# The map's two phase shifts ``a, b`` are angles; the full sweep range is
# ``[0, 2*pi]`` (the parameter-space inset in Conradi's animations spans
# exactly this square). Stored as a named constant rather than a magic number.
_TWO_PI: float = 2.0 * np.pi

#: Curated named Conradi parameter sets, each ``(label, a, b)`` (CMP-005). Both
#: are the canonical stills from Conradi's ``Nice_orbits.ipynb`` and lie within
#: ``[0, 2*pi]``. The map-preset picker (a later item) populates a "Preset"
#: dropdown from this list.
CONRADI_PRESETS: list[tuple[str, float, float]] = [
    ("Canonical (5.46, 4.55)", _DEFAULT_A, _DEFAULT_B),
    ("Alternate (1.7, 2.3)", 1.7, 2.3),
]


class ConradiMap(DiscreteSystem):
    r"""The Conradi trigonometric map :math:`(x, y) \mapsto (\sin(x^2 - y^2 + a),\ \cos(2xy + b))`."""

    name = "ConradiMap"
    latex = (
        r"\begin{aligned}x_{n+1} &= \sin(x_n^2 - y_n^2 + a)\\"
        r"y_{n+1} &= \cos(2\,x_n y_n + b)\end{aligned}"
    )
    state_dim = 2
    parameters = {
        "a": Parameter("a", _DEFAULT_A, 0.0, _TWO_PI, "real-channel phase shift"),
        "b": Parameter("b", _DEFAULT_B, 0.0, _TWO_PI, "imag-channel phase shift"),
    }
    # The map self-bounds to [-1, 1]^2 after one step; (0.1, 0.1) is a generic
    # interior seed that lands on the attractor quickly.
    default_initial_state = np.array([0.1, 0.1], dtype=np.float64)
    educational_notes = """\
**A strange attractor from one complex square.** The arguments
``x^2 - y^2`` and ``2xy`` are exactly ``Re(z^2)`` and ``Im(z^2)`` for
``z = x + iy``. So this map squares the complex number, shifts by the
constant ``(a, b)``, and wraps each channel through sin / cos. That
componentwise trig is what folds the plane into Simone Conradi's
trigonometric-attractor art.

**Where to read about it:** Simone Conradi, ``Nice_orbits.ipynb``
(github.com/profConradi/Python_Simulations); Paul Bourke, "Simone
attractor" (paulbourke.net/fractals/simone_orbits/).

**Automatically bounded.** Because sin and cos live in [-1, 1], every
iterate after the first stays in the unit square [-1, 1]^2 — this map
*cannot* diverge (contrast Hénon, which can). The only dull outcome is
collapse to a fixed point or short cycle, never escape to infinity.

**Dissipative.** det J = -4 (x^2 + y^2) cos(u) sin(v) with
u = x^2 - y^2 + a, v = 2xy + b. Area contracts on average, so the
attracting set is measure-zero — a strange attractor, rendered as a
density of many orbits rather than a single curve.

**Parameters are angles.** Both a and b are phase shifts in [0, 2*pi].
Sweeping (a, b) on a closed loop through that square morphs the
attractor continuously — the basis for the animated version. The
canonical still is (a, b) = (5.46, 4.55); (1.7, 2.3) is another rich
pair from the source notebook.
"""

    def _step(self, y: FloatArray, params: Mapping[str, float]) -> FloatArray:
        x, yv = y[0], y[1]
        a = params["a"]
        b = params["b"]
        return np.array(
            [np.sin(x * x - yv * yv + a), np.cos(2.0 * x * yv + b)],
            dtype=np.float64,
        )

    def jacobian(self, y: FloatArray, **params: float) -> FloatArray:
        r"""Analytic Jacobian :math:`\partial F / \partial (x, y)` at state ``y``.

        With ``u = x^2 - y^2 + a`` and ``v = 2 x y + b``,

        .. math::

            J = \begin{pmatrix}
                  2x \cos u & -2y \cos u \\
                  -2y \sin v & -2x \sin v
                \end{pmatrix}.

        Missing parameters default to :meth:`default_params`. Returned as a
        ``(2, 2)`` array. This is a ``ConradiMap``-specific method (the
        ``DiscreteSystem`` base intentionally has no ``jacobian`` hook); the
        discrete-Lyapunov estimator planned in CSC-003 takes such a callable as
        an argument rather than requiring it on the ABC.
        """
        merged = self.merged_params(params)
        x, yv = float(y[0]), float(y[1])
        a = merged["a"]
        b = merged["b"]
        cos_u = np.cos(x * x - yv * yv + a)
        sin_v = np.sin(2.0 * x * yv + b)
        return np.array(
            [
                [2.0 * x * cos_u, -2.0 * yv * cos_u],
                [-2.0 * yv * sin_v, -2.0 * x * sin_v],
            ],
            dtype=np.float64,
        )


__all__ = ["CONRADI_PRESETS", "ConradiMap"]
