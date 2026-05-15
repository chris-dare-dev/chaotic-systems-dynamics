"""Interface contract assumed of the math agent's backend.

This module is the *only* place the visualization and GUI layers depend on
the shape of the backend. If the math agent's actual API ends up different,
update the adapters here — not the renderer or GUI.

Assumed backend surface (importable):

    from chaotic_systems.systems.registry import list_systems, get_system

``list_systems()`` returns ready-to-use *instances* of
:class:`~chaotic_systems.core.DynamicalSystem`. Each such instance
advertises:

    name: str                              # human-readable
    latex: str                             # LaTeX of the ODE system (no $$)
    lagrangian_latex: str | None           # LaTeX of L (or H) if applicable
    parameters: dict[str, Parameter]       # named parameters
    initial_state: np.ndarray              # default initial condition, shape (state_dim,)
    state_dim: int                         # dimension of the state vector
    rhs(t, y, **params) -> np.ndarray      # vector field f(t, y; params)
    simulate(t_span, y0, params, integrator='RK45', dt=0.01) -> Trajectory

The visualization-side ``ParameterSpec`` mirrors the core
:class:`chaotic_systems.core.Parameter` (it carries
``name`` / ``default`` / ``min`` / ``max`` / ``description``). When the
backend exposes the real ``Parameter`` we read its fields directly; for
duck-typed objects we coerce via :func:`_coerce_parameter`.

A ``Trajectory`` carries at least:
    .t: np.ndarray, shape (N,)
    .y: np.ndarray, shape (N, state_dim)

If the math agent uses ``(state_dim, N)`` instead of ``(N, state_dim)`` for
``Trajectory.y``, the adapter in :func:`as_points` uses the system's
declared ``state_dim`` (or the trajectory's ``.t`` length) to pick the
right axis rather than guessing from shape.

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
    "ParameterSpec",
    "Trajectory",
    "SystemLike",
    "as_points",
    "default_params",
    "list_systems_safe",
    "get_system_safe",
]


@dataclass(frozen=True)
class ParameterSpec:
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


# Back-compat alias. Older callers / tests use the bare ``Parameter`` name.
# Prefer ``ParameterSpec`` in new code so it's distinct from
# ``chaotic_systems.core.Parameter`` (which carries an extra ``units``
# field).
Parameter = ParameterSpec


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


def _project_to_3d(
    arr: np.ndarray,
    *,
    t_axis: np.ndarray | None,
    projection: tuple[int, int, int] | None,
) -> np.ndarray:
    """Project a ``(N, d)`` trajectory to a ``(N, 3)`` array of XYZ points."""

    n, d = arr.shape
    if d >= 3:
        if projection is None:
            return np.ascontiguousarray(arr[:, :3])
        for axis in projection:
            if not 0 <= axis < d:
                raise ValueError(
                    f"projection axis {axis} out of range for state_dim={d}"
                )
        return np.ascontiguousarray(arr[:, list(projection)])
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


def _orient_trajectory(
    traj: Any,
) -> tuple[np.ndarray, np.ndarray | None]:
    """Return ``(arr, t_axis)`` with ``arr`` shaped ``(N, state_dim)``.

    Uses the trajectory's declared ``state_dim`` (or ``.t`` length) to
    pick the time axis rather than a shape heuristic — which would
    silently mis-transpose short trajectories like ``(2, 3)`` or
    ``(3, 4)``.
    """

    arr = np.asarray(traj.y, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"trajectory y must be 2-D; got shape {arr.shape!r}")

    t_axis = (
        np.asarray(traj.t, dtype=float)
        if hasattr(traj, "t") and traj.t is not None
        else None
    )

    # 1. If the trajectory carries `state_dim`, use it as the source of truth.
    state_dim = getattr(traj, "state_dim", None)
    if state_dim is None:
        # 2. Fall back to t.shape[0] vs y.shape[i].
        if t_axis is not None and t_axis.ndim == 1:
            n_t = int(t_axis.shape[0])
            if arr.shape[0] == n_t and arr.shape[1] != n_t:
                return arr, t_axis
            if arr.shape[1] == n_t and arr.shape[0] != n_t:
                return arr.T, t_axis
            if arr.shape[0] == n_t and arr.shape[1] == n_t:
                # Ambiguous (square). Trust the convention `(N, state_dim)`.
                return arr, t_axis
        # 3. No info at all — assume the contract `(N, state_dim)`.
        return arr, t_axis

    state_dim_i = int(state_dim)
    if arr.shape[1] == state_dim_i:
        return arr, t_axis
    if arr.shape[0] == state_dim_i:
        return arr.T, t_axis
    raise ValueError(
        f"trajectory y has shape {arr.shape!r}; "
        f"neither axis matches state_dim={state_dim_i}"
    )


def _screen_non_finite(arr: np.ndarray) -> tuple[np.ndarray, int]:
    """Clip trailing non-finite rows. Returns ``(clipped, n_dropped)``.

    If the trajectory diverged at some step ``k``, every subsequent row
    will be NaN/Inf. We keep the prefix up to the last all-finite row.
    """

    if arr.size == 0:
        return arr, 0
    finite_mask = np.all(np.isfinite(arr), axis=1)
    if finite_mask.all():
        return arr, 0
    # Find the last finite row.
    finite_indices = np.flatnonzero(finite_mask)
    if finite_indices.size == 0:
        # Every row is bad — caller can decide what to do.
        return arr[:0], int(arr.shape[0])
    last_good = int(finite_indices[-1]) + 1
    n_dropped = int(arr.shape[0] - last_good)
    return arr[:last_good], n_dropped


def as_points(
    traj: Trajectory | np.ndarray,
    *,
    projection: tuple[int, int, int] | None = None,
    on_non_finite: str = "clip",
) -> np.ndarray:
    """Normalize a trajectory to a contiguous ``(N, 3)`` array of XYZ points.

    Rules:

    - If ``traj`` is already an ndarray, use it directly. For raw
      arrays, axis orientation is inferred only when unambiguous
      (long-axis ratio > 3); otherwise we trust ``(N, state_dim)``.
    - Otherwise read ``traj.y`` and orient it using ``state_dim``
      (if the trajectory advertises one) or ``len(traj.t)``.
    - For ``state_dim > 3``, by default return the first three
      components. Pass ``projection=(i, j, k)`` to pick a different
      ordered triple — useful for Hénon-Heiles ``[x, y, px, py]`` where
      ``projection=(0, 1, 3)`` gives a ``(x, y, py)`` view.
    - For ``state_dim == 2``, pad a zero z-column.
    - For ``state_dim == 1``, return ``(N, 3)`` with x = t, y = value, z = 0.

    Non-finite handling
    -------------------
    Trajectories that blow up to ``NaN`` / ``Inf`` would otherwise
    propagate through bounding-box math and segfault VTK. By default
    (``on_non_finite="clip"``) we drop trailing non-finite rows and
    return the prefix; ``"raise"`` raises ``ValueError`` instead.

    Raises
    ------
    ValueError
        If the trajectory cannot be coerced to a 2-D array, or if every
        row is non-finite.
    """

    if isinstance(traj, np.ndarray):
        arr = np.asarray(traj, dtype=float)
        t_axis: np.ndarray | None = None
        if arr.ndim != 2:
            raise ValueError(f"trajectory must be 2-D; got shape {arr.shape!r}")
        # Heuristic only for raw arrays without a `t` axis: only transpose
        # when the long axis is unambiguously longer than the short.
        if arr.shape[0] < arr.shape[1] and arr.shape[1] >= 3 * arr.shape[0]:
            arr = arr.T
    else:
        arr, t_axis = _orient_trajectory(traj)

    # Screen non-finite rows.
    arr, n_dropped = _screen_non_finite(arr)
    if arr.shape[0] == 0:
        if on_non_finite == "raise":
            raise ValueError("trajectory is entirely non-finite")
        # Fall through with an empty array; caller will surface this.
    if n_dropped and on_non_finite == "raise":
        raise ValueError(
            f"trajectory has {n_dropped} non-finite trailing row(s); "
            "the integration diverged"
        )

    return _project_to_3d(arr, t_axis=t_axis, projection=projection)


def _coerce_parameter(name: str, raw: Any) -> ParameterSpec:
    """Best-effort coercion of an arbitrary parameter descriptor."""

    if isinstance(raw, ParameterSpec):
        return raw
    # Treat any object with the right attributes as a Parameter.
    default = float(getattr(raw, "default", getattr(raw, "value", 0.0)))
    lo = float(getattr(raw, "min", default - 1.0))
    hi = float(getattr(raw, "max", default + 1.0))
    desc = str(getattr(raw, "description", "") or "")
    return ParameterSpec(name=name, default=default, min=lo, max=hi, description=desc)


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

    Only an ``ImportError`` is swallowed — a broken system module
    (typo, attribute error) propagates so the developer sees it. If you
    want belt-and-braces no-fail behavior, wrap the call yourself.
    """

    try:
        from chaotic_systems.systems import registry
    except ImportError:
        return []
    list_fn = getattr(registry, "list_systems", None)
    if list_fn is None:
        return []
    return list(list_fn())


def get_system_safe(name: str) -> SystemLike | None:
    """Look up a system by name; return ``None`` only if the backend is missing.

    ``KeyError`` for an unknown name propagates as ``None`` (the common
    "not in the registry" case), but anything else — a syntax error in
    a system module, a missing attribute — surfaces normally.
    """

    try:
        from chaotic_systems.systems import registry
    except ImportError:
        return None
    get_fn = getattr(registry, "get_system", None)
    if get_fn is not None:
        try:
            return get_fn(name)  # type: ignore[no-any-return]
        except KeyError:
            return None
    for sys_obj in list_systems_safe():
        if getattr(sys_obj, "name", None) == name:
            return sys_obj
    return None
