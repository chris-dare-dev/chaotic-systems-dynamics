"""The 4D Rössler hyperchaos system.

.. math::

    \\dot x &= -y - z, \\\\
    \\dot y &= x + a y + w, \\\\
    \\dot z &= b + x z, \\\\
    \\dot w &= -c z + d w.

This is Rössler's 1979 four-dimensional extension of his 1976 chaotic
attractor. Adding the ``w`` coordinate and the linear feedback
``-cz + dw`` produces a system with **two positive Lyapunov
exponents** — the defining feature of *hyperchaos*. The canonical
parameter set ``(a, b, c, d) = (0.25, 3.0, 0.5, 0.05)`` yields a
spectrum approximately ``(+0.112, +0.019, 0.000, -25.59)``.

The system was the first hyperchaotic flow discovered and remains the
textbook exemplar; pair it with the Diagnostics card's Lyapunov
spectrum to see the ``(+, +, 0, -)`` signature directly.

References
----------
- O. E. Rössler, *An equation for hyperchaos*, Physics Letters A 71
  (1979), 155-157.
- T. Stankevich and D. Wilczak, *Computer-assisted proofs of existence
  of hyperchaotic dynamics*, Physics Letters A 379 (2015).
- Scholarpedia, "Hyperchaos" entry (Letellier & Rössler).
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from chaotic_systems.core.base import DynamicalSystem, FloatArray, Parameter

# Canonical hyperchaotic regime (Rössler 1979).
_DEFAULT_A: float = 0.25
_DEFAULT_B: float = 3.0
_DEFAULT_C: float = 0.5
_DEFAULT_D: float = 0.05


class RosslerHyper(DynamicalSystem):
    """4D Rössler hyperchaos — two positive Lyapunov exponents."""

    name = "RosslerHyper"
    latex = (
        r"\begin{aligned}\dot x &= -y - z\\"
        r"\dot y &= x + a y + w\\"
        r"\dot z &= b + x z\\"
        r"\dot w &= -c z + d w\end{aligned}"
    )
    state_dim = 4
    parameters = {
        "a": Parameter("a", _DEFAULT_A, 0.0, 1.0, "y-coupling"),
        "b": Parameter("b", _DEFAULT_B, 0.0, 10.0, "drive"),
        "c": Parameter("c", _DEFAULT_C, 0.0, 5.0, "w-z coupling"),
        "d": Parameter(
            "d", _DEFAULT_D, 0.0, 0.5, "w self-feedback (small positive => hyperchaos)"
        ),
    }
    default_initial_state = np.array(
        [-10.0, -6.0, 0.0, 10.0], dtype=np.float64
    )
    educational_notes = """\
**The first hyperchaotic flow.** Rössler (1979) extended his 3D
chaotic attractor with a fourth state variable and discovered
something genuinely new: a system with *two* positive Lyapunov
exponents. That had been considered impossible in low dimensions.

**Where to read about it:** Stankevich & Wilczak, *Computer-assisted
proofs of existence of hyperchaotic dynamics*, Phys. Lett. A 379
(2015) — rigorous treatment; Scholarpedia "Hyperchaos" entry —
intuition.

**Why it matters:** hyperchaos is the qualitative regime past
ordinary chaos. With two positive exponents the dynamics expand in
two directions simultaneously; trajectories scatter on a
*hyperchaotic attractor* (not a strange attractor in the strict
3D sense). It's the simplest exemplar of how chaos scales with
dimension.

**Pair with the Diagnostics card.** Click *Compute Lyapunov
spectrum* — you'll see the (+, +, 0, -) signature:

- λ₁ ≈ +0.112  (chaotic stretching #1)
- λ₂ ≈ +0.019  (chaotic stretching #2 — the hyperchaos signature)
- λ₃ ≈  0      (flow direction)
- λ₄ ≈ -25.59  (strong dissipation)

The card classifies the system as *Hyperchaotic (2 positive
exponents)*. No 3D-or-lower attractor can produce that label.
"""

    def _rhs(
        self, t: float, y: FloatArray, params: Mapping[str, float]
    ) -> FloatArray:
        x, y_, z, w = y[0], y[1], y[2], y[3]
        a = params["a"]
        b = params["b"]
        c = params["c"]
        d = params["d"]
        return np.array(
            [
                -y_ - z,
                x + a * y_ + w,
                b + x * z,
                -c * z + d * w,
            ],
            dtype=np.float64,
        )


__all__ = ["RosslerHyper"]
