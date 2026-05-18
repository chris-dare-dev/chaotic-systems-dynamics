"""Base abstractions for dynamical systems and the simulation pipeline.

The two key types here are:

- :class:`Parameter` — a typed, validated description of a single scalar
  parameter of a dynamical system. The GUI uses ``min`` / ``max`` to bound
  slider widgets; tests use ``default`` for canonical-value checks.
- :class:`DynamicalSystem` — an abstract base class. A concrete chaotic
  system subclasses it and supplies a name, a LaTeX representation, the
  parameter table, the default initial state, the state dimension, and a
  right-hand-side ``rhs(t, y, **params)`` that returns :math:`\\dot y`.

A :class:`Trajectory` is the standard output type: time grid, state
matrix, and bookkeeping about which system / parameters produced it.

The GUI agent depends on this exact public surface — do not rename
attributes or change return types lightly. See the module docstring of
:mod:`chaotic_systems.systems.registry` for the contract.
"""

from __future__ import annotations

import abc
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]

# Module-level empty defaults shared by every ``DynamicalSystem`` subclass.
# Kept as read-only / size-zero so an accidental write surfaces immediately.
_EMPTY_PARAMS: Mapping[str, Parameter] = MappingProxyType({})
_EMPTY_INITIAL_STATE: NDArray[np.float64] = np.empty(0, dtype=np.float64)


@dataclass(frozen=True, slots=True)
class Parameter:
    """A single scalar parameter of a dynamical system.

    Attributes
    ----------
    name
        Short identifier, used as the keyword argument name in
        :meth:`DynamicalSystem.rhs`.
    default
        Canonical default value.
    min, max
        Inclusive bounds used by GUI slider widgets. If unbounded
        physically, pick a sensible exploration range.
    description
        Human-readable description for tooltips / docs.
    units
        Optional unit string (``"s^-1"``, ``"m"``, ``""`` for dimensionless).
    """

    name: str
    default: float
    min: float
    max: float
    description: str = ""
    units: str = ""

    def __post_init__(self) -> None:
        if not (self.min <= self.default <= self.max):
            raise ValueError(
                f"Parameter {self.name!r}: default={self.default} not in "
                f"[{self.min}, {self.max}]"
            )


@dataclass(slots=True)
class Trajectory:
    """A simulated trajectory of a dynamical system.

    Attributes
    ----------
    t
        Time grid of shape ``(N,)``.
    y
        State matrix of shape ``(N, state_dim)``. ``y[i]`` is the state at
        ``t[i]``.
    system
        Name of the system that produced this trajectory.
    params
        Parameter values used (a copy — mutating this won't affect the
        trajectory).
    integrator
        Name of the integrator used (``"RK45"``, ``"yoshida4"``, ...).
    """

    t: FloatArray
    y: FloatArray
    system: str = ""
    params: dict[str, float] = field(default_factory=dict)
    integrator: str = ""

    def __post_init__(self) -> None:
        if self.t.ndim != 1:
            raise ValueError(f"t must be 1-D, got shape {self.t.shape}")
        if self.y.ndim != 2:
            raise ValueError(f"y must be 2-D, got shape {self.y.shape}")
        if self.t.shape[0] != self.y.shape[0]:
            raise ValueError(
                f"t and y disagree on N: t has {self.t.shape[0]}, "
                f"y has {self.y.shape[0]}"
            )

    @property
    def state_dim(self) -> int:
        """Dimension of the state space."""
        return int(self.y.shape[1])

    @property
    def n_steps(self) -> int:
        """Number of stored samples (``N``)."""
        return int(self.t.shape[0])

    @property
    def duration(self) -> float:
        """``t[-1] - t[0]``."""
        return float(self.t[-1] - self.t[0])


class DynamicalSystem(abc.ABC):
    """Abstract base for a continuous-time dynamical system :math:`\\dot y = f(t, y)`.

    Subclasses must:

    1. Set the class attributes :attr:`name`, :attr:`latex`,
       :attr:`state_dim`, and (optionally) :attr:`lagrangian_latex`.
    2. Define :attr:`parameters` — a ``dict[str, Parameter]`` keyed by
       parameter name.
    3. Implement :meth:`_rhs` — the vector field, taking ``t, y, params``
       and returning :math:`\\dot y`. Pure NumPy; the framework wraps it
       to make it callable from ``scipy.integrate.solve_ivp``.
    4. Set :attr:`default_initial_state` — a ``(state_dim,)`` array.
    """

    # ``kind`` is the discriminator the registry / GUI uses to decide
    # whether to show an integrator picker. Continuous-time ODE systems
    # carry ``"ode"``; discrete-time maps (see
    # :class:`chaotic_systems.core.discrete.DiscreteSystem`) carry
    # ``"map"``. Subclasses do not need to override this.
    kind: str = "ode"

    # Class-level metadata (override in subclasses). The defaults are
    # deliberately frozen / zero-sized so an accidental write would be loud.
    name: str = "unnamed"
    latex: str = ""
    lagrangian_latex: str | None = None
    state_dim: int = 0
    parameters: Mapping[str, Parameter] = _EMPTY_PARAMS
    default_initial_state: FloatArray = _EMPTY_INITIAL_STATE

    # Optional markdown blob rendered by the GUI's notes panel under the
    # LaTeX. Subclasses are encouraged to fill this with textbook
    # references (Strogatz / Ott / Sprott / Lichtenberg-Lieberman),
    # the chaotic-regime parameters worth trying, and a one-paragraph
    # summary of what the system is famous for. See
    # ``docs/proposals/capability-roadmap-2026-05-17.md`` E1.
    educational_notes: str = ""

    # ----- public API --------------------------------------------------

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
                        f"Unknown parameter {key!r} for system {self.name!r}; "
                        f"known parameters: {sorted(merged)}"
                    )
            merged.update({k: float(v) for k, v in overrides.items()})
        return merged

    def rhs(self, t: float, y: FloatArray, **params: float) -> FloatArray:
        """Evaluate the vector field at ``(t, y)``.

        Missing keyword arguments are filled in from
        :meth:`default_params`. Returns ``dy/dt`` as a NumPy array of shape
        ``(state_dim,)``.
        """
        merged = self.merged_params(params)
        out = self._rhs(t, y, merged)
        # Defensive: ensure float64 contiguous array of correct shape.
        result = np.ascontiguousarray(out, dtype=np.float64)
        if result.shape != (self.state_dim,):
            raise ValueError(
                f"{self.name}._rhs returned shape {result.shape}, "
                f"expected ({self.state_dim},)"
            )
        return result

    # ----- subclass hook -----------------------------------------------

    @abc.abstractmethod
    def _rhs(self, t: float, y: FloatArray, params: Mapping[str, float]) -> FloatArray:
        """Compute :math:`\\dot y`. Subclasses must implement.

        ``params`` is guaranteed to contain every key in :attr:`parameters`.
        """

    # ----- simulation --------------------------------------------------

    def simulate(
        self,
        t_span: tuple[float, float],
        y0: FloatArray | None = None,
        params: Mapping[str, float] | None = None,
        integrator: str = "RK45",
        dt: float | None = None,
        n_points: int | None = None,
        rtol: float = 1e-8,
        atol: float = 1e-10,
        **integrator_kwargs: Any,
    ) -> Trajectory:
        """Integrate this system over ``t_span`` and return a :class:`Trajectory`.

        Parameters
        ----------
        t_span
            ``(t0, t1)`` time interval.
        y0
            Initial state. Defaults to :attr:`initial_state`.
        params
            Parameter overrides; defaults to :meth:`default_params`.
        integrator
            One of the names exported by
            :mod:`chaotic_systems.integrators` — adaptive
            (``"RK45"``, ``"DOP853"``, ``"Radau"``, ``"BDF"``,
            ``"LSODA"``, ``"RK23"``), fixed-step (``"RK4"``), or
            symplectic (``"leapfrog"``, ``"velocity_verlet"``,
            ``"yoshida4"``).
        dt
            Step size for fixed-step / symplectic integrators (ignored by
            adaptive integrators if ``n_points`` is also given).
        n_points
            If given, the trajectory is evaluated at this many uniformly
            spaced points (uses dense output for adaptive integrators).
        rtol, atol
            Tolerances for adaptive integrators.
        integrator_kwargs
            Forwarded to the integrator.
        """
        # Local imports to avoid circular import at module load time.
        from chaotic_systems.integrators import get_integrator
        from chaotic_systems.integrators.symplectic import (
            _Symplectic,
            from_hamiltonian,
        )

        t0, t1 = float(t_span[0]), float(t_span[1])
        if t1 <= t0:
            raise ValueError(
                f"t_span must be strictly increasing (got t0={t0!r}, t1={t1!r})"
            )
        if dt is not None and float(dt) <= 0.0:
            raise ValueError(f"dt must be positive (got dt={dt!r})")
        if n_points is not None and int(n_points) < 2:
            raise ValueError(f"n_points must be >= 2 (got n_points={n_points!r})")

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

        # Bind params into a closure-style rhs the integrators can call.
        def bound_rhs(t: float, y: FloatArray) -> FloatArray:
            return self._rhs(t, y, merged_params)

        integ = get_integrator(integrator)

        # Symplectic integrators need (grad_T, grad_V) split. If `self`
        # exposes a separable `.hamiltonian`, build them automatically so
        # callers don't have to.
        if isinstance(integ, _Symplectic) and "grad_t_fn" not in integrator_kwargs:
            ham = getattr(self, "hamiltonian", None)
            if ham is not None and getattr(ham, "separable", False):
                grad_T, grad_V = from_hamiltonian(integ, ham)
                integrator_kwargs.setdefault("grad_t_fn", grad_T)
                integrator_kwargs.setdefault("grad_v_fn", grad_V)

        traj = integ.integrate(
            bound_rhs,
            (t0, t1),
            y0_arr,
            dt=dt,
            n_points=n_points,
            rtol=rtol,
            atol=atol,
            **integrator_kwargs,
        )
        # Annotate the trajectory with system / params metadata.
        traj.system = self.name
        traj.params = dict(merged_params)
        return traj


__all__ = ["Parameter", "Trajectory", "DynamicalSystem", "FloatArray"]
