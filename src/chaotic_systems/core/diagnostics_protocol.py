"""Protocol for per-system post-simulation observables (CSC-033 / T3).

Many of the systems in this project carry semantically meaningful
scalar observables that go beyond the universal "largest Lyapunov
exponent" / "Lyapunov spectrum" diagnostics surfaced by the
Diagnostics card:

- ``Kuramoto`` carries the order parameter :math:`r e^{i\\psi}` — *the*
  observable for synchronization studies (Strogatz, *From Kuramoto to
  Crawford*, Physica D 143 (2000) 1-20). Without ``|r|`` the GUI's
  3D-phase-angle render is illegible to the student who wants to see
  whether the population locked.
- ``HenonHeiles`` and ``DoublePendulum`` are conservative systems —
  energy is a known constant of motion. Surfacing the per-trajectory
  energy *drift* makes the symplectic-vs-RK45 integrator choice
  immediately visible (``|ΔE / E_0|`` is microscopic on Yoshida-4,
  grows linearly on RK45).

Both wants share one shape: take a finished trajectory, return a
small dict of formatted scalar labels for display. This module
defines the runtime-checkable Protocol the Diagnostics card uses to
discover whether a given system can supply such observables.

Why a Protocol, not an ABC method
---------------------------------
The challenger (Phase 3 of capability-scout 2026-q2-broadening)
explicitly recommended a ``runtime_checkable`` :class:`Protocol` over
adding an optional method to
:class:`~chaotic_systems.core.base.DynamicalSystem` because:

1. The base class is an ``abc.ABC`` — adding a concrete optional
   method changes the ABC contract in a way that ``mypy --strict``
   may flag on existing subclasses that don't implement it.
2. Every one of the 13 currently registered systems would inherit
   the method, even those for which it has no meaningful return
   (the 4 discrete maps, Lorenz / Rossler / Chua / RosslerHyper /
   Duffing / MackeyGlass have no system-specific scalar beyond
   λ₁ which the Diagnostics card already shows).
3. ``isinstance(system, PostSimDiagnosticProvider)`` at the call
   site is zero-impact on the rest of the project.

Concrete providers shipped with this milestone: :class:`Kuramoto`,
:class:`HenonHeiles`, :class:`DoublePendulum`. New systems opt in
by defining a ``post_sim_diagnostics(self, trajectory)`` method
with the matching signature; no inheritance change is required.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class PostSimDiagnosticProvider(Protocol):
    """A :class:`DynamicalSystem` that exposes per-system observables.

    Implementations return a :class:`~collections.abc.Mapping` of
    short label strings to pre-formatted display values. The
    Diagnostics card concatenates these into a status block under
    the Lyapunov spectrum readout.

    Convention
    ----------
    - Keys: human-readable scalar names (``"|r|"``, ``"E"``,
      ``"ΔE/E0"``, ``"ψ"`` — Unicode is fine; Qt's QLabel renders
      it correctly). Keep keys short — they appear inline.
    - Values: **pre-formatted** strings, e.g. ``f"{val:+.4f}"`` or
      ``f"{val:.3e}"``. The Protocol does no formatting itself so
      implementations control significant figures and notation.
    - The ``trajectory`` argument has the shape returned by
      :meth:`DynamicalSystem.simulate` — i.e.
      :class:`~chaotic_systems.core.base.Trajectory`. Implementations
      use ``trajectory.y`` (shape ``(N, state_dim)``) to extract
      first/last states and any per-state observable.

    Stability
    ---------
    A provider should not raise on a syntactically valid trajectory —
    Diagnostics-card consumers catch nothing and display whatever the
    method returns. If an observable is undefined for some inputs
    (e.g. ``DoublePendulum`` with missing params), return a key whose
    value is ``"n/a"`` or omit it from the dict; do not raise.
    """

    def post_sim_diagnostics(self, trajectory: Any) -> Mapping[str, str]:
        """Compute a dict of per-system observables for display.

        Parameters
        ----------
        trajectory
            The :class:`~chaotic_systems.core.base.Trajectory`
            produced by the simulation.

        Returns
        -------
        Mapping[str, str]
            Short label → formatted value pairs. May be empty.
        """
        ...


def format_post_sim_diagnostics(diagnostics: Mapping[str, str]) -> str:
    """Format a per-system observable dict as a single display string.

    Used by the GUI Diagnostics card. Returns a newline-separated
    ``"  key = value"`` block; empty dict returns ``""``. The leading
    two-space indent matches the spectrum/D_KY formatting in
    :func:`~chaotic_systems.gui.main_window._format_lyapunov_spectrum`
    so the two blocks stack visually.
    """
    if not diagnostics:
        return ""
    lines = [f"  {key} = {value}" for key, value in diagnostics.items()]
    return "\n".join(lines)


__all__ = [
    "PostSimDiagnosticProvider",
    "format_post_sim_diagnostics",
]
