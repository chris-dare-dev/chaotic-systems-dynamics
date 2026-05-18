"""Discrete-time dynamical systems (maps).

A *discrete* dynamical system is governed by an iterated map
:math:`x_{n+1} = F(x_n;\\theta)` rather than a vector field
:math:`\\dot y = f(t, y;\\theta)`. The two settings share enough surface
(named parameters, LaTeX representation, initial state, trajectory
output) to feel unified to the GUI / visualization layer, but the
runtime semantics are different:

- there is no time-step ``dt`` — the natural index ``n`` is the only time;
- there is no integrator pick — iteration *is* the algorithm;
- there is no notion of "step error" — the map is its own ground truth.

This module ships:

- :class:`DiscreteSystem` — abstract base for maps. Mirrors
  :class:`~chaotic_systems.core.base.DynamicalSystem` on metadata
  (``name``, ``latex``, ``parameters``, ``default_initial_state``,
  ``state_dim``) so a single GUI parameter form drives either kind. The
  difference is :meth:`_step` (one iterate) instead of ``_rhs`` (a
  vector field), and :meth:`iterate` (return an N-step trajectory)
  instead of ``simulate`` (call an integrator).

- A ``kind`` class attribute distinguishes the two: ``"map"`` here,
  ``"ode"`` on :class:`DynamicalSystem`. The registry exposes the
  discriminator so the GUI can disable integrator pickers when a map
  is selected.

The output is still a :class:`~chaotic_systems.core.base.Trajectory`,
with ``t`` set to the integer iterate index cast to float and
``integrator`` set to ``"map"``. That keeps the visualization /
contract layer unchanged.

References
----------
- Strogatz, *Nonlinear Dynamics and Chaos* (2nd ed., 2015), §10:
  one-dimensional maps and the logistic family.
- Ott, *Chaos in Dynamical Systems* (2nd ed., 2002), §2: discrete-time
  systems.
- Sales et al., *pynamicalsys: A Python toolkit for discrete dynamical
  systems analysis*, Chaos, Solitons & Fractals 201 (2025) — the
  pedagogical canon for the logistic / Hénon / Ikeda / standard map set
  this module enables.
"""

from __future__ import annotations

import abc
from collections.abc import Mapping
from typing import Any

import numpy as np

from chaotic_systems.core.base import (
    _EMPTY_INITIAL_STATE,
    _EMPTY_PARAMS,
    FloatArray,
    Parameter,
    Trajectory,
)


class DiscreteSystem(abc.ABC):
    """Abstract base for a discrete-time dynamical system :math:`x_{n+1} = F(x_n)`.

    Subclasses must:

    1. Set the class attributes :attr:`name`, :attr:`latex`, and
       :attr:`state_dim`.
    2. Define :attr:`parameters` — a ``dict[str, Parameter]`` keyed by
       parameter name.
    3. Implement :meth:`_step` — the map, taking ``y, params`` and
       returning ``F(y;params)``. Pure NumPy.
    4. Set :attr:`default_initial_state` — a ``(state_dim,)`` array.
    """

    # ``kind`` is the discriminator the registry / GUI uses to decide
    # whether to show an integrator picker. Continuous systems carry
    # ``kind = "ode"`` (see :class:`DynamicalSystem`); maps carry
    # ``kind = "map"``.
    kind: str = "map"

    # Class-level metadata (override in subclasses). Defaults frozen / zero-sized
    # so an accidental write surfaces immediately.
    name: str = "unnamed-map"
    latex: str = ""
    state_dim: int = 0
    parameters: Mapping[str, Parameter] = _EMPTY_PARAMS
    default_initial_state: FloatArray = _EMPTY_INITIAL_STATE

    # Optional markdown blob rendered by the GUI's notes panel under the
    # LaTeX. Same convention as
    # :class:`chaotic_systems.core.base.DynamicalSystem.educational_notes` —
    # textbook references + parameter excursions worth trying.
    educational_notes: str = ""

    # ----- public metadata --------------------------------------------------

    @property
    def initial_state(self) -> FloatArray:
        """Default initial state (a copy — safe to mutate)."""
        return np.array(self.default_initial_state, dtype=np.float64, copy=True)

    def default_params(self) -> dict[str, float]:
        """Dictionary of default parameter values keyed by name."""
        return {name: float(p.default) for name, p in self.parameters.items()}

    def merged_params(self, overrides: Mapping[str, float] | None) -> dict[str, float]:
        """Merge user-supplied overrides over defaults, validating keys."""
        merged = self.default_params()
        if overrides:
            for key in overrides:
                if key not in merged:
                    raise KeyError(
                        f"Unknown parameter {key!r} for map {self.name!r}; "
                        f"known parameters: {sorted(merged)}"
                    )
            merged.update({k: float(v) for k, v in overrides.items()})
        return merged

    # ----- single-step evaluation -------------------------------------------

    def step(self, y: FloatArray, **params: float) -> FloatArray:
        """Evaluate :math:`F(y)` for one iterate.

        Missing keyword arguments are filled in from
        :meth:`default_params`. Returns the next state as a NumPy array
        of shape ``(state_dim,)``.
        """
        merged = self.merged_params(params)
        out = self._step(np.ascontiguousarray(y, dtype=np.float64), merged)
        result = np.ascontiguousarray(out, dtype=np.float64)
        if result.shape != (self.state_dim,):
            raise ValueError(
                f"{self.name}._step returned shape {result.shape}, "
                f"expected ({self.state_dim},)"
            )
        return result

    # ----- subclass hook ----------------------------------------------------

    @abc.abstractmethod
    def _step(self, y: FloatArray, params: Mapping[str, float]) -> FloatArray:
        """Compute :math:`F(y)`. Subclasses must implement.

        ``params`` is guaranteed to contain every key in :attr:`parameters`.
        """

    # ----- iteration --------------------------------------------------------

    def iterate(
        self,
        n_steps: int,
        y0: FloatArray | None = None,
        params: Mapping[str, float] | None = None,
        *,
        n_transient: int = 0,
    ) -> Trajectory:
        """Iterate the map and return an ``(n_steps + 1)``-sample :class:`Trajectory`.

        Parameters
        ----------
        n_steps
            Number of iterates to apply *after* the transient. The
            returned trajectory has ``n_steps + 1`` samples (the
            initial state plus ``n_steps`` iterates).
        y0
            Initial state. Defaults to :attr:`initial_state`.
        params
            Parameter overrides; defaults to :meth:`default_params`.
        n_transient
            Number of leading iterates to compute and discard before
            recording the trajectory. Useful for letting transients
            decay before sampling an attractor; defaults to 0.

        Returns
        -------
        Trajectory
            ``t = [0, 1, ..., n_steps]`` (the iterate index cast to
            float), ``y[i]`` is the state after ``i`` iterates from
            the post-transient starting point, ``integrator = "map"``.
        """
        if int(n_steps) < 1:
            raise ValueError(f"n_steps must be >= 1 (got n_steps={n_steps!r})")
        if int(n_transient) < 0:
            raise ValueError(
                f"n_transient must be >= 0 (got n_transient={n_transient!r})"
            )

        y0_arr = (
            self.initial_state
            if y0 is None
            else np.ascontiguousarray(y0, dtype=np.float64)
        )
        if y0_arr.shape != (self.state_dim,):
            raise ValueError(
                f"y0 has shape {y0_arr.shape}, expected ({self.state_dim},)"
            )
        if not np.isfinite(y0_arr).all():
            raise ValueError("y0 contains non-finite entries")

        merged_params = self.merged_params(params)

        state = y0_arr.copy()
        for _ in range(int(n_transient)):
            state = self._step(state, merged_params)
            state = np.ascontiguousarray(state, dtype=np.float64)
            if state.shape != (self.state_dim,):
                raise ValueError(
                    f"{self.name}._step returned shape {state.shape}, "
                    f"expected ({self.state_dim},)"
                )

        n_total = int(n_steps) + 1
        ys = np.empty((n_total, self.state_dim), dtype=np.float64)
        ys[0] = state
        for i in range(1, n_total):
            state = self._step(state, merged_params)
            state = np.ascontiguousarray(state, dtype=np.float64)
            if state.shape != (self.state_dim,):
                raise ValueError(
                    f"{self.name}._step returned shape {state.shape}, "
                    f"expected ({self.state_dim},)"
                )
            ys[i] = state

        ts = np.arange(n_total, dtype=np.float64)
        traj = Trajectory(
            t=ts,
            y=ys,
            system=self.name,
            params=dict(merged_params),
            integrator="map",
        )
        return traj

    # ----- compatibility shim with the contract layer ----------------------

    def simulate(self, *args: Any, **kwargs: Any) -> Trajectory:
        """Reject ``.simulate`` calls — maps are iterated, not integrated.

        Kept as an explicit error rather than silently aliasing
        :meth:`iterate` so a caller written for an ODE system fails
        loudly instead of producing a trajectory of unknown semantics.
        """
        raise TypeError(
            f"{self.name!r} is a discrete map (kind='map'); use .iterate(n_steps) "
            "instead of .simulate(t_span, ...)."
        )


__all__ = ["DiscreteSystem"]
