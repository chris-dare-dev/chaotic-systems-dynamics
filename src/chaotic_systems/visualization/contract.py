"""Interface contract assumed of the math agent's backend.

This module is the *only* place the visualization and GUI layers depend on
the shape of the backend. If the math agent's actual API ends up different,
update the adapters here — not the renderer or GUI.

Assumed backend surface (importable):

    from chaotic_systems.systems.registry import list_systems, get_system

Each system instance produced by the registry advertises:

    name: str                              # human-readable
    latex: str                             # LaTeX of the ODE system (no $$)
    lagrangian_latex: str | None           # LaTeX of L (or H) if applicable
    parameters: dict[str, Parameter]       # named parameters
    initial_state: np.ndarray              # default initial condition, shape (state_dim,)
    state_dim: int                         # dimension of the state vector
    rhs(t, y, **params) -> np.ndarray      # vector field f(t, y; params)
    simulate(t_span, y0, params, integrator='RK45', dt=0.01) -> Trajectory

A ``Parameter`` carries: ``name: str``, ``default: float``, ``min: float``,
``max: float``, ``description: str``.

A ``Trajectory`` carries at least:
    .t: np.ndarray, shape (N,)
    .y: np.ndarray, shape (N, state_dim)

If the math agent uses ``(state_dim, N)`` instead of ``(N, state_dim)`` for
``Trajectory.y``, the adapter in :func:`as_points` normalizes that.

The functions in this module are deliberately tolerant: they accept
duck-typed objects and fail with informative errors rather than relying
on isinstance checks. That keeps the seam thin and easy to mend.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import numpy as np

__all__ = [
    "Parameter",
    "Trajectory",
    "SystemLike",
    "as_points",
    "default_params",
    "list_systems_safe",
    "get_system_safe",
]


@dataclass(frozen=True)
class Parameter:
    """Description of a tunable scalar parameter on a system.

    This is the *visualization-side* mirror of what we expect the backend
    to expose. If the backend uses a compatible class we read its fields
    directly; if not, the adapter in :func:`_coerce_parameter` rebuilds
    one of these from whatever is available.
    """

    name: str
    default: float
    min: float
    max: float
    description: str = ""


@runtime_checkable
class Trajectory(Protocol):
    """Duck-typed trajectory the math agent is expected to return."""

    t: np.ndarray
    y: np.ndarray


@runtime_checkable
class SystemLike(Protocol):
    """Duck-typed system object."""

    name: str
    latex: str
    parameters: dict[str, Any]
    initial_state: np.ndarray
    state_dim: int

    def rhs(self, t: float, y: np.ndarray, **params: float) -> np.ndarray: ...

    def simulate(
        self,
        t_span: tuple[float, float],
        y0: np.ndarray,
        params: dict[str, float],
        integrator: str = "RK45",
        dt: float = 0.01,
    ) -> Trajectory: ...


def as_points(traj: Trajectory | np.ndarray) -> np.ndarray:
    """Normalize a trajectory to a contiguous ``(N, 3)`` array of XYZ points.

    Rules:

    - If ``traj`` is already an ndarray, use it directly.
    - Otherwise read ``traj.y`` and orient it so the long axis is rows.
    - For ``state_dim > 3``, return the first three components (a
      conventional projection — callers wanting a different projection can
      slice themselves).
    - For ``state_dim == 2``, pad a zero z-column.
    - For ``state_dim == 1``, return ``(N, 3)`` with x = t, y = value, z = 0.

    Raises
    ------
    ValueError
        If the trajectory cannot be coerced to a 2-D array.
    """

    if isinstance(traj, np.ndarray):
        arr = np.asarray(traj, dtype=float)
        t_axis: np.ndarray | None = None
    else:
        arr = np.asarray(traj.y, dtype=float)
        t_axis = np.asarray(traj.t, dtype=float) if hasattr(traj, "t") else None

    if arr.ndim != 2:
        raise ValueError(
            f"trajectory must be 2-D; got shape {arr.shape!r}"
        )

    # Orient so the long axis (time) is rows.
    if arr.shape[0] < arr.shape[1]:
        arr = arr.T

    n, d = arr.shape
    if d >= 3:
        return np.ascontiguousarray(arr[:, :3])
    if d == 2:
        z = np.zeros((n, 1), dtype=float)
        return np.ascontiguousarray(np.hstack([arr, z]))
    # d == 1
    if t_axis is not None and t_axis.shape == (n,):
        x = t_axis.reshape(n, 1)
    else:
        x = np.arange(n, dtype=float).reshape(n, 1)
    z = np.zeros((n, 1), dtype=float)
    return np.ascontiguousarray(np.hstack([x, arr, z]))


def _coerce_parameter(name: str, raw: Any) -> Parameter:
    """Best-effort coercion of an arbitrary parameter descriptor."""

    if isinstance(raw, Parameter):
        return raw
    # Treat any object with the right attributes as a Parameter.
    default = float(getattr(raw, "default", getattr(raw, "value", 0.0)))
    lo = float(getattr(raw, "min", default - 1.0))
    hi = float(getattr(raw, "max", default + 1.0))
    desc = str(getattr(raw, "description", "") or "")
    return Parameter(name=name, default=default, min=lo, max=hi, description=desc)


def default_params(system: SystemLike) -> dict[str, float]:
    """Return a dict of default parameter values for ``system``."""

    out: dict[str, float] = {}
    raw = getattr(system, "parameters", {}) or {}
    for key, val in raw.items():
        p = _coerce_parameter(key, val)
        out[key] = p.default
    return out


def list_systems_safe() -> list[SystemLike]:
    """Return the registry's systems, or an empty list if the backend is missing.

    This makes the GUI and visualization layer importable and testable even
    before the math agent has landed a registry.
    """

    try:
        from chaotic_systems.systems import registry  # type: ignore[import-not-found]
    except Exception:
        return []
    list_fn = getattr(registry, "list_systems", None)
    if list_fn is None:
        return []
    try:
        return list(list_fn())
    except Exception:
        return []


def get_system_safe(name: str) -> SystemLike | None:
    """Look up a system by name; return ``None`` if backend or system is missing."""

    try:
        from chaotic_systems.systems import registry  # type: ignore[import-not-found]
    except Exception:
        return None
    get_fn = getattr(registry, "get_system", None)
    if get_fn is not None:
        try:
            return get_fn(name)  # type: ignore[no-any-return]
        except Exception:
            return None
    for sys_obj in list_systems_safe():
        if getattr(sys_obj, "name", None) == name:
            return sys_obj
    return None
