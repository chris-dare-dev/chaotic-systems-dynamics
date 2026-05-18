"""Chua's circuit (piecewise-linear chaotic circuit).

.. math::

    \\dot x &= \\alpha (y - x - h(x)), \\\\
    \\dot y &= x - y + z, \\\\
    \\dot z &= -\\beta y,

with the piecewise-linear nonlinearity (the so-called *Chua diode*)

.. math::

    h(x) = m_1 x + \\tfrac{1}{2} (m_0 - m_1) (|x + 1| - |x - 1|).

Canonical "double-scroll" parameters: :math:`\\alpha = 15.6`,
:math:`\\beta = 28`, :math:`m_0 = -1.143`, :math:`m_1 = -0.714`.

References
----------
- T. Matsumoto, L. O. Chua, M. Komuro, *The Double Scroll*,
  IEEE Trans. Circuits Syst. CAS-32 (1985), 798-818.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from chaotic_systems.core.base import DynamicalSystem, FloatArray, Parameter


class Chua(DynamicalSystem):
    """Chua's circuit with piecewise-linear diode."""

    name = "Chua"
    latex = (
        r"\begin{aligned}\dot x &= \alpha(y - x - h(x))\\"
        r"\dot y &= x - y + z\\"
        r"\dot z &= -\beta y\\"
        r"h(x) &= m_1 x + \tfrac{1}{2}(m_0 - m_1)(|x+1| - |x-1|)\end{aligned}"
    )
    state_dim = 3
    parameters = {
        "alpha": Parameter("alpha", 15.6, 0.0, 30.0, "circuit parameter"),
        "beta": Parameter("beta", 28.0, 0.0, 60.0, "circuit parameter"),
        "m0": Parameter("m0", -1.143, -2.0, 2.0, "inner slope of Chua diode"),
        "m1": Parameter("m1", -0.714, -2.0, 2.0, "outer slope of Chua diode"),
    }
    default_initial_state = np.array([0.7, 0.0, 0.0], dtype=np.float64)
    educational_notes = """\
**The chaos you can build on a breadboard.** Chua's circuit (1984)
is the only chaotic system whose chaos has been independently
confirmed in physical hardware *thousands of times* across labs
worldwide. The piecewise-linear nonlinearity h(x) — the
"Chua diode" — is what every textbook circuit is missing.

**Where to read about it:** Matsumoto, Chua & Komuro, *The Double
Scroll*, IEEE Trans. Circuits Syst. CAS-32 (1985); Madan (ed.),
*Chua's Circuit: A Paradigm for Chaos*, World Scientific (1993);
Sprott, *Chaos and Time-Series Analysis* (2003) §6.

**Why it matters:** the *double-scroll attractor* — two
interlocking spiral lobes joined by occasional jumps — is the
qualitative signature. It's chaos in three dimensions but with
a piecewise-linear vector field, which makes both rigorous proof
*and* hardware realization tractable.

**Try these excursions** (keep m₀ = -1.143, m₁ = -0.714):

- α = 8.5: single-scroll periodic orbit.
- α = 10.0: period-doubling into single-scroll chaos.
- α = 13.0: just past the double-scroll bifurcation.
- α = 15.6: canonical fully-developed double scroll.
- α = 20.0: chaos plus periodic windows.

Compute the Lyapunov spectrum — you should see one positive
exponent (~0.3 at α = 15.6) and one strongly negative one.
"""

    @staticmethod
    def _h(x: float, m0: float, m1: float) -> float:
        # ``np.abs`` works for both scalars and vectors; ``abs()`` would
        # silently break if a vectorized RHS evaluation ever reaches here.
        return m1 * x + 0.5 * (m0 - m1) * (np.abs(x + 1.0) - np.abs(x - 1.0))

    def _rhs(
        self, t: float, y: FloatArray, params: Mapping[str, float]
    ) -> FloatArray:
        x, y_, z = y[0], y[1], y[2]
        alpha = params["alpha"]
        beta = params["beta"]
        m0 = params["m0"]
        m1 = params["m1"]
        hx = self._h(x, m0, m1)
        return np.array(
            [
                alpha * (y_ - x - hx),
                x - y_ + z,
                -beta * y_,
            ],
            dtype=np.float64,
        )


__all__ = ["Chua"]
