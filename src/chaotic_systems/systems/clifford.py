r"""The Clifford attractor — a second density-art map preset (CSC-008).

.. math::

    x_{n+1} &= \sin(a\,y_n) + c\,\cos(a\,x_n), \\
    y_{n+1} &= \sin(b\,x_n) + d\,\cos(b\,y_n).

Clifford Pickover's attractor: a four-parameter trigonometric map that, like
Simone Conradi's ``z^2`` map, produces lacy multi-lobe density art when a dense
lattice of initial conditions is iterated and accumulated. Adding it proves the
CSC-002 render / CSC-005 animate / CSC-004 screen pipeline generalizes beyond the
Conradi map for the cost of one small subclass.

Two structural facts:

- **Bounded** (contrary to the polynomial Hénon / Clifford-*polynomial* maps).
  Because ``sin, cos in [-1, 1]``, every iterate satisfies
  ``|x| <= 1 + |c|`` and ``|y| <= 1 + |d|`` — so the render window is the fixed
  ``(c, d)``-derived box returned by :func:`clifford_extent`, not an
  orbit-dependent auto-fit. (The proposal's "unbounded" note refers to
  polynomial-affine attractors; this sin/cos form cannot diverge.)
- **Four parameters** ``(a, b, c, d)`` versus the Conradi map's two, giving a
  richer family of shapes from Paul Bourke's reference parameter sets.

Canonical parameters ``(a, b, c, d) = (-1.4, 1.6, 1.0, 0.7)`` are one of Paul
Bourke's reference sets (a recognizable four-lobe figure).

References
----------
- Paul Bourke, "Clifford Attractors",
  http://paulbourke.net/fractals/clifford/ (the canonical map
  ``x' = sin(a y) + c cos(a x)``, ``y' = sin(b x) + d cos(b y)`` and its
  reference parameter sets). The ``dysts`` software catalog is intentionally
  NOT used as the primary source (per CLAUDE.md "Mathematical correctness").
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from chaotic_systems.core.base import FloatArray, Parameter
from chaotic_systems.core.discrete import DiscreteSystem

# Canonical regime, one of Paul Bourke's reference Clifford parameter sets.
_DEFAULT_A: float = -1.4
_DEFAULT_B: float = 1.6
_DEFAULT_C: float = 1.0
_DEFAULT_D: float = 0.7

# Parameter sweep range. Bourke's reference sets all live within [-3, 3].
_PARAM_LO: float = -3.0
_PARAM_HI: float = 3.0

#: Curated named Clifford parameter sets, each ``(label, a, b, c, d)`` (CMP-005).
#: All are reference sets from Paul Bourke's "Clifford Attractors" page
#: (http://paulbourke.net/fractals/clifford/) and lie within the
#: ``[-3, 3]`` parameter range above; each renders a recognizable multi-lobe
#: figure through ``visualization.attractor_density``. The map-preset picker
#: (a later item) populates a "Preset" dropdown from this list.
CLIFFORD_PRESETS: list[tuple[str, float, float, float, float]] = [
    ("Bourke I (four-lobe)", -1.4, 1.6, 1.0, 0.7),
    ("Bourke II", 1.7, 1.7, 0.6, 1.2),
    ("Bourke III", -1.7, 1.3, -0.1, -1.21),
    ("Bourke IV", 1.5, -1.8, 1.6, 0.9),
    ("Bourke V", -1.8, -2.0, -0.5, -0.9),
]


def clifford_map(
    x: FloatArray,
    y: FloatArray,
    a: float,
    b: float,
    c: float,
    d: float,
) -> tuple[FloatArray, FloatArray]:
    """Vectorized Clifford step ``(x, y) -> (x', y')`` over arrays of seeds."""
    return (
        np.sin(a * y) + c * np.cos(a * x),
        np.sin(b * x) + d * np.cos(b * y),
    )


def make_clifford_map_fn(
    c: float = _DEFAULT_C, d: float = _DEFAULT_D
):
    """Return a 2-parameter ``map_fn(x, y, a, b)`` with ``c``/``d`` fixed.

    The density renderer (:func:`chaotic_systems.visualization.attractor_density.render`)
    sweeps a 2-parameter ``map_fn(x, y, a, b)``; Clifford has four parameters, so
    this closes over ``(c, d)`` and exposes ``(a, b)`` as the swept pair. Pair it
    with :func:`clifford_extent` for the render window::

        from chaotic_systems.visualization import attractor_density
        rgba = attractor_density.render(
            a, b,
            map_fn=make_clifford_map_fn(c, d),
            extent=clifford_extent(c, d),
        )

    The returned closure carries two tags the density renderer's JIT dispatch
    reads (CMP-003): ``_map_id = "clifford"`` selects the Clifford ``@njit``
    accumulation kernel, and ``_map_params = (c, d)`` passes the fixed
    parameters to it. Tagging the closure (rather than relying on object
    identity) is what lets a freshly-built closure still take the fast path.
    These are plain attributes — no ``visualization`` import here.
    """

    def map_fn(
        x: FloatArray, y: FloatArray, a: float, b: float
    ) -> tuple[FloatArray, FloatArray]:
        return clifford_map(x, y, a, b, c, d)

    map_fn._map_id = "clifford"  # type: ignore[attr-defined]
    map_fn._map_params = (float(c), float(d))  # type: ignore[attr-defined]
    return map_fn


def clifford_extent(
    c: float = _DEFAULT_C, d: float = _DEFAULT_D
) -> tuple[float, float, float, float]:
    """Exact bounding box ``(xmin, xmax, ymin, ymax)`` of the Clifford attractor.

    Since ``sin, cos in [-1, 1]``, ``|x| <= 1 + |c|`` and ``|y| <= 1 + |d|``.
    """
    x_half = 1.0 + abs(c)
    y_half = 1.0 + abs(d)
    return (-x_half, x_half, -y_half, y_half)


class CliffordMap(DiscreteSystem):
    r"""The Clifford attractor :math:`(x,y)\mapsto(\sin(ay)+c\cos(ax),\ \sin(bx)+d\cos(by))`."""

    name = "CliffordMap"
    latex = (
        r"\begin{aligned}x_{n+1} &= \sin(a\,y_n) + c\,\cos(a\,x_n)\\"
        r"y_{n+1} &= \sin(b\,x_n) + d\,\cos(b\,y_n)\end{aligned}"
    )
    state_dim = 2
    parameters = {
        "a": Parameter("a", _DEFAULT_A, _PARAM_LO, _PARAM_HI, "y-coupling / x-frequency"),
        "b": Parameter("b", _DEFAULT_B, _PARAM_LO, _PARAM_HI, "x-coupling / y-frequency"),
        "c": Parameter("c", _DEFAULT_C, _PARAM_LO, _PARAM_HI, "x cosine amplitude"),
        "d": Parameter("d", _DEFAULT_D, _PARAM_LO, _PARAM_HI, "y cosine amplitude"),
    }
    # Generic interior seed; the attractor is reached from almost any start.
    default_initial_state = np.array([0.1, 0.1], dtype=np.float64)
    educational_notes = """\
**A four-knob trigonometric attractor.** Clifford Pickover's map wraps
two sine/cosine mixtures back on themselves; iterating a dense grid of
seeds and accumulating every visit traces a lacy multi-lobe figure — the
same density-art idea as the Conradi map, with four parameters instead of
two for a wider family of shapes.

**Where to read about it:** Paul Bourke, "Clifford Attractors"
(paulbourke.net/fractals/clifford/), with reference parameter sets.

**Automatically bounded.** Because sin and cos live in [-1, 1], every
iterate stays in [-(1+|c|), 1+|c|] x [-(1+|d|), 1+|d|] — the map cannot
diverge, so the render window is fixed by (c, d), not the orbit.

**Try these (Bourke's sets):** (a,b,c,d) = (-1.4, 1.6, 1.0, 0.7) is the
default four-lobe figure; (1.7, 1.7, 0.6, 1.2) and (-1.7, 1.3, -0.1,
-1.21) give very different lacework. Render through the Conradi panel's
density pipeline (the lattice-transient ink-drop method).
"""

    def _step(self, y: FloatArray, params: Mapping[str, float]) -> FloatArray:
        x, yv = y[0], y[1]
        a = params["a"]
        b = params["b"]
        c = params["c"]
        d = params["d"]
        return np.array(
            [
                np.sin(a * yv) + c * np.cos(a * x),
                np.sin(b * x) + d * np.cos(b * yv),
            ],
            dtype=np.float64,
        )

    def jacobian(self, y: FloatArray, **params: float) -> FloatArray:
        r"""Analytic Jacobian :math:`\partial F / \partial (x, y)` at state ``y``.

        .. math::

            J = \begin{pmatrix}
                  -c\,a\,\sin(a x) & a\,\cos(a y) \\
                  b\,\cos(b x) & -d\,b\,\sin(b y)
                \end{pmatrix}.

        Missing parameters default to :meth:`default_params`. Returned as a
        ``(2, 2)`` array. Like ``ConradiMap``, this is a map-specific method
        (the ``DiscreteSystem`` base has no ``jacobian`` hook); the discrete
        Lyapunov estimator (CSC-003) takes it as a callable.
        """
        merged = self.merged_params(params)
        x, yv = float(y[0]), float(y[1])
        a = merged["a"]
        b = merged["b"]
        c = merged["c"]
        d = merged["d"]
        return np.array(
            [
                [-c * a * np.sin(a * x), a * np.cos(a * yv)],
                [b * np.cos(b * x), -d * b * np.sin(b * yv)],
            ],
            dtype=np.float64,
        )


__all__ = [
    "CLIFFORD_PRESETS",
    "CliffordMap",
    "clifford_extent",
    "clifford_map",
    "make_clifford_map_fn",
]
