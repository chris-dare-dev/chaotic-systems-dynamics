"""The Kuramoto N-oscillator network.

.. math::

    \\dot\\theta_i = \\omega_i + \\frac{K}{N} \\sum_{j=1}^{N}
    \\sin(\\theta_j - \\theta_i), \\qquad i = 1, \\dots, N.

A swarm of phase oscillators with quenched random natural frequencies
:math:`\\omega_i`, globally coupled with strength :math:`K`. Kuramoto
(1975) showed that as :math:`K` crosses a *critical coupling*
:math:`K_c`, the population undergoes a continuous phase transition
from incoherence to partial synchronization. The order parameter

.. math::

    r\\,e^{i\\psi} = \\frac{1}{N} \\sum_{j=1}^{N} e^{i\\theta_j}

measures how phase-locked the population is: ``|r| = 0`` for fully
incoherent dynamics, ``|r| → 1`` as the oscillators lock in step. The
classical Kuramoto result is :math:`K_c = 2 / (\\pi g(0))` for a
symmetric unimodal frequency distribution ``g(ω)``; for a Lorentzian
of half-width :math:`\\gamma` that's :math:`K_c = 2\\gamma`.

Why N4 ships this
-----------------
The capability roadmap lists *network dynamics* as a target
phenomenology the project doesn't yet have. Kuramoto is the canonical
one-equation model. With ``N = 10`` the renderer's
``(θ_1, θ_2, θ_3)`` projection is enough to read *visual*
phase-locking — the user pulls the K slider and watches three
otherwise-uncorrelated oscillators march in lockstep past
:math:`K_c`.

Implementation notes
--------------------
- **N is per-instance**, not a tunable :class:`Parameter` (the
  state dimension can't be slid live — changing N would require
  rebuilding the whole solver pipeline). The registry instantiates
  the default ``Kuramoto(n=10)``; library callers can construct
  their own ``Kuramoto(n=...)`` for batched / sweep workflows.
- **Natural frequencies are seeded**. The default ``freq_seed=0``
  + Lorentzian (Cauchy) distribution of scale ``freq_scale=0.5``
  puts :math:`K_c = 2 \\cdot 0.5 = 1.0`. Reproducibility is the
  whole point — tests can pin a numerical synchronization
  threshold.
- **The RHS uses the mean-field reformulation**, which is
  exact (trig identity) and ``O(N)`` instead of ``O(N²)``:

  .. math::

      \\dot\\theta_i = \\omega_i + K\\,r\\,\\sin(\\psi - \\theta_i).

References
----------
- Y. Kuramoto, *Self-entrainment of a population of coupled
  non-linear oscillators*, in *International Symposium on
  Mathematical Problems in Theoretical Physics* (Springer,
  1975), 420-422.
- S. H. Strogatz, *From Kuramoto to Crawford: exploring the
  onset of synchronization in populations of coupled
  oscillators*, Physica D 143 (2000), 1-20 — the modern review.
- J. A. Acebrón et al., *The Kuramoto model: A simple paradigm
  for synchronization phenomena*, Rev. Mod. Phys. 77 (2005),
  137-185 — the definitive parameter-zoo treatment.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from chaotic_systems.core.base import DynamicalSystem, FloatArray, Parameter

# Canonical defaults. ``freq_scale = 0.5`` puts the Lorentzian
# critical coupling at K_c = 2 * gamma = 1.0; subcritical K = 0.1
# leaves the oscillators effectively independent, supercritical
# K = 5 drives |r| ~ 0.95+.
_DEFAULT_N: int = 10
_DEFAULT_K: float = 1.5
_DEFAULT_FREQ_SCALE: float = 0.5
_DEFAULT_FREQ_SEED: int = 0
# A small noise floor in the initial phases so the order parameter
# starts well below 1 (otherwise an all-aligned IC trivially fakes
# perfect synchronization).
_IC_SEED_OFFSET: int = 1


class Kuramoto(DynamicalSystem):
    """The Kuramoto N-oscillator network.

    The state vector is the phase angles :math:`(\\theta_1, \\dots, \\theta_N)`.
    Natural frequencies :math:`\\omega_i` are sampled once at
    construction time from a Lorentzian distribution and frozen on
    the instance — they're *quenched* disorder, not a parameter the
    user dials live.
    """

    name = "Kuramoto"
    latex = (
        r"\dot\theta_i = \omega_i + \frac{K}{N} \sum_{j=1}^{N}"
        r" \sin(\theta_j - \theta_i)"
    )
    lagrangian_latex: str | None = None

    # Class-level defaults — overridden per-instance in __init__ once N
    # is known. Stored here so the abstract base's class-attribute
    # access patterns don't blow up on cls() instantiation.
    state_dim = _DEFAULT_N
    parameters = {
        "K": Parameter(
            "K",
            _DEFAULT_K,
            0.0,
            10.0,
            "global coupling strength (K_c = 1.0 at default freq_scale)",
        ),
    }
    default_initial_state = np.zeros(_DEFAULT_N, dtype=np.float64)

    def __init__(
        self,
        n: int = _DEFAULT_N,
        *,
        freq_seed: int = _DEFAULT_FREQ_SEED,
        freq_scale: float = _DEFAULT_FREQ_SCALE,
    ) -> None:
        super().__init__()
        if int(n) < 2:
            raise ValueError(
                f"Kuramoto requires n >= 2 oscillators; got n={n!r}"
            )
        if float(freq_scale) <= 0.0:
            raise ValueError(
                f"freq_scale must be positive (got {freq_scale!r})"
            )
        self.n = int(n)
        # Quenched natural frequencies — Lorentzian / Cauchy with
        # the given scale, centered at zero. The Kuramoto critical
        # coupling for a Lorentzian g(ω) is K_c = 2 * scale.
        rng = np.random.default_rng(int(freq_seed))
        self._omega = (rng.standard_cauchy(self.n) * float(freq_scale)).astype(
            np.float64
        )
        # Per-instance shadow of the class attributes — every reference
        # to ``self.state_dim`` / ``self.default_initial_state`` now
        # picks up the actual N.
        self.state_dim = self.n
        # Initial phases: uniform in [-π, π) so the initial order
        # parameter sits at the ~1/√N noise floor for incoherent
        # dynamics. Different seed offset from the frequency RNG so
        # ICs and frequencies are uncorrelated draws.
        ic_rng = np.random.default_rng(int(freq_seed) + _IC_SEED_OFFSET)
        self.default_initial_state = ic_rng.uniform(
            -np.pi, np.pi, size=self.n
        ).astype(np.float64)

    educational_notes = """\
**The simplest model of synchronization.** Kuramoto (1975)
introduced this swarm of phase oscillators with quenched random
natural frequencies and showed that as the global coupling ``K``
crosses a critical value :math:`K_c`, the population undergoes a
continuous phase transition from *incoherence* (every oscillator
running at its own frequency) to *partial synchronization* (a
macroscopic fraction locked into a common phase).

**Where to read about it:** Kuramoto, *International Symposium on
Mathematical Problems in Theoretical Physics* (Springer, 1975);
Strogatz, *Physica D* 143 (2000) — the modern review; Acebrón et
al., *Rev. Mod. Phys.* 77 (2005) — the parameter-zoo treatment.

**The order parameter** ``r * exp(i ψ) = (1/N) Σ exp(i θ_j)``
measures synchronization:

- ``|r| ≈ 1/√N``: incoherent (random phases).
- ``|r| → 1``: fully phase-locked.

**The transition.** With Lorentzian natural-frequency
distribution of half-width γ, the critical coupling is
``K_c = 2γ`` (Kuramoto 1975). At the project's default
``freq_scale = 0.5``, that's ``K_c = 1.0``.

**Try these K excursions** (default N = 10, freq_seed = 0):

- K = 0.1: subcritical — oscillators drift independently;
  ``|r|`` stays near the ``1/√N`` noise floor.
- K = 0.9: just below K_c — partial coherence, ``|r|`` ~ 0.4-0.6.
- K = 1.5: supercritical — fast convergence to ``|r|`` > 0.85.
- K = 5.0: deep lock — ``|r|`` ~ 0.95+.

**Pair with the V1 phase portrait** on any two ``(θ_i, θ_j)``
pair: at low K they trace out a Lissajous-like cloud (independent
rotations); at high K they collapse to a thin line near
``θ_j = θ_i + const`` (locked).
"""

    def _rhs(
        self, t: float, y: FloatArray, params: Mapping[str, float]
    ) -> FloatArray:
        """Mean-field Kuramoto RHS — exact via trig identity, O(N) per call.

        ``(1/N) Σ_j sin(θ_j - θ_i) ≡ r sin(ψ - θ_i)`` where
        ``r e^(iψ) = (1/N) Σ_j e^(iθ_j)`` (expand the sin in
        exponentials and pull the i-dependent factor out). So the
        full ``O(N²)`` all-pairs sum reduces to a single complex mean
        plus a per-oscillator scalar update.
        """
        k = params["K"]
        z = np.exp(1j * y).mean()
        r = float(abs(z))
        psi = float(np.angle(z))
        return self._omega + k * r * np.sin(psi - y)

    # ------------------------------------------------------------ helpers

    @property
    def omega(self) -> FloatArray:
        """The quenched natural-frequency vector. Read-only copy."""
        return self._omega.copy()

    @staticmethod
    def order_parameter(theta: FloatArray) -> tuple[float, float]:
        """Return ``(|r|, ψ)`` for a phase configuration.

        ``|r|`` is the Kuramoto order parameter (synchronization
        magnitude in ``[0, 1]``); ``ψ`` is the mean phase.
        """
        z = np.exp(1j * np.asarray(theta, dtype=np.float64)).mean()
        return float(abs(z)), float(np.angle(z))

    # ------------------------------------------------------------------
    # CSC-033 / T3 — PostSimDiagnosticProvider implementation.
    # The Diagnostics card calls this after each Run if the system is
    # an isinstance of
    # :class:`~chaotic_systems.core.diagnostics_protocol.PostSimDiagnosticProvider`.
    # ------------------------------------------------------------------
    def post_sim_diagnostics(self, trajectory: Any) -> Mapping[str, str]:
        """Return the late-time Kuramoto order parameter as display chips.

        Computes :meth:`order_parameter` on the **last** frame of the
        trajectory — once the population has had time to lock or
        decohere, that single snapshot is the meaningful diagnostic
        (cf. Strogatz, *From Kuramoto to Crawford*, Physica D 143
        (2000) 1-20, where late-time ``|r|`` is the headline scalar).
        For sub-critical ``K < K_c`` returns ``|r| → 0`` modulo
        finite-N fluctuations; for supercritical ``K > K_c`` returns
        ``|r|`` approaching 1.
        """
        y = np.asarray(getattr(trajectory, "y", []), dtype=np.float64)
        if y.ndim != 2 or y.shape[0] == 0:
            return {}
        theta_last = y[-1]
        r, psi = self.order_parameter(theta_last)
        return {
            "|r|": f"{r:.4f}",
            "ψ": f"{psi:+.4f}",
        }


__all__ = ["Kuramoto"]
