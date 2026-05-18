"""Basin-of-attraction maps for multistable dynamical systems.

A *basin of attraction* is the set of initial conditions that asymptote
to a given attractor. For multistable systems — Duffing's double-well
potential, Lorenz with multiple coexisting fixed points / limit cycles,
the Hénon-Heiles section's KAM-island archipelago — coloring the
initial-condition plane by which attractor each orbit reaches produces
some of the most visually striking pictures in nonlinear dynamics.

This module computes the basin map on a 2D grid of initial conditions
holding the rest of the state vector (and all parameters) fixed.
**Classification is supervised**: the caller passes a list of
representative ``(label, point)`` attractors, and each orbit's
asymptotic state is assigned to the nearest one (with an unclassified
fallback when the orbit hasn't converged). The fully automatic
recurrence-based classifier from Datseris & Wagemakers (2022) is a
natural follow-up but lives outside v1's scope.

Two backends
------------
- **scipy** (default) — one ``solve_ivp`` per grid point. Always
  available; the right choice when the RHS is plain numpy or when the
  grid is small (≤ 32 × 32). Slow for large grids.
- **jax** (opt-in via the :mod:`chaotic_systems.integrators.jax_backend`)
  — a single :func:`~chaotic_systems.integrators.jax_backend.vmap_trajectories`
  call that fuses the whole grid into one XLA kernel. ~10-100× faster
  on a 64 × 64 grid. Requires the caller's RHS to be JAX-traceable
  (operations through ``jax.numpy``); the I1 milestone documents the
  pattern.

References
----------
- G. Datseris & A. Wagemakers, *Effortless estimation of basins of
  attraction*, Chaos 32 (2022) 023104. The recurrence-based
  classifier the abstract pushes is more sophisticated than what
  ships here; the supervised-classification path matches their
  ``AttractorMapper`` "fallback" mode.
- E. Ott, *Chaos in Dynamical Systems* (2nd ed., 2002), §5.3 —
  textbook treatment of basin structure for the driven Duffing
  oscillator, the canonical multistable example.

See also
--------
- :mod:`chaotic_systems.visualization.basin_plot` — matplotlib viz.
- :mod:`chaotic_systems.gui.basin_panel` — PySide6 explorer.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from scipy.integrate import solve_ivp

from chaotic_systems.core.base import FloatArray

# Sentinel label for grid points whose final state is far from every
# supplied attractor — i.e. the orbit hasn't converged within
# ``t_end``, has escaped to infinity, or has landed on an attractor
# the caller didn't register. Stored as ``-1`` in :attr:`labels` so
# it slots into a small integer enum cleanly. The visualization layer
# renders unclassified pixels as a neutral gray.
UNCLASSIFIED_LABEL: int = -1


@dataclass(frozen=True, slots=True)
class BasinDiagram:
    """A 2D basin-of-attraction map.

    Attributes
    ----------
    x_axis
        ``(state_idx, lo, hi)``. Which state component varies on the
        x-axis and over what range.
    y_axis
        ``(state_idx, lo, hi)``. Same for the y-axis.
    n_grid
        ``(n_x, n_y)`` — resolution of the basin map. The returned
        :attr:`labels` matrix is shaped ``(n_y, n_x)`` so it slots
        directly into ``imshow(origin="lower")``.
    labels
        Shape ``(n_y, n_x)``, ``int64``. ``labels[i, j]`` is the
        attractor index for the grid point ``(x_grid[j], y_grid[i])``,
        or :data:`UNCLASSIFIED_LABEL` (``-1``) if the orbit didn't
        converge to any registered attractor.
    attractor_labels
        Human-readable names for each attractor, matching the integer
        label indices ``0, 1, ..., n_attractors-1``.
    attractor_points
        Shape ``(n_attractors, state_dim)``. The representative state
        of each attractor — the classification reference points.
    fixed_state
        Shape ``(state_dim,)``. The non-swept components of the
        initial state, held constant across the grid.
    system_name
        Free-form label for the plot title.
    classify_tol
        The L2 distance threshold used during classification; saved
        on the diagram for reproducibility.
    backend
        ``"scipy"`` or ``"jax"`` — which integrator path produced
        this diagram.
    """

    x_axis: tuple[int, float, float]
    y_axis: tuple[int, float, float]
    n_grid: tuple[int, int]
    labels: FloatArray
    attractor_labels: list[str]
    attractor_points: FloatArray
    fixed_state: FloatArray
    system_name: str = ""
    classify_tol: float = 1.0
    backend: str = "scipy"

    def __post_init__(self) -> None:
        n_x, n_y = int(self.n_grid[0]), int(self.n_grid[1])
        if self.labels.shape != (n_y, n_x):
            raise ValueError(
                f"labels shape {self.labels.shape} does not match "
                f"(n_y, n_x) = ({n_y}, {n_x})"
            )
        if self.attractor_points.ndim != 2:
            raise ValueError(
                f"attractor_points must be 2-D (n_attractors, state_dim); "
                f"got shape {self.attractor_points.shape}"
            )
        if len(self.attractor_labels) != self.attractor_points.shape[0]:
            raise ValueError(
                f"attractor_labels has {len(self.attractor_labels)} entries "
                f"but attractor_points has {self.attractor_points.shape[0]} "
                f"rows; these must match."
            )
        if self.fixed_state.ndim != 1:
            raise ValueError(
                f"fixed_state must be 1-D; got shape {self.fixed_state.shape}"
            )

    @property
    def n_attractors(self) -> int:
        """Number of registered attractors (excluding the unclassified bucket)."""
        return int(self.attractor_points.shape[0])

    @property
    def state_dim(self) -> int:
        """Dimension of the state vector this basin lives in."""
        return int(self.fixed_state.shape[0])

    @property
    def x_grid(self) -> FloatArray:
        """``(n_x,)`` x-axis sample positions."""
        _, lo, hi = self.x_axis
        return np.linspace(float(lo), float(hi), int(self.n_grid[0]))

    @property
    def y_grid(self) -> FloatArray:
        """``(n_y,)`` y-axis sample positions."""
        _, lo, hi = self.y_axis
        return np.linspace(float(lo), float(hi), int(self.n_grid[1]))


# Type alias for the supervised-classification attractor list. Each
# entry is ``(label_name, point_in_state_space)`` — the point's shape
# must equal ``state_dim``.
AttractorSpec = tuple[str, np.ndarray]


def _classify_final_states(
    final_states: np.ndarray,
    attractor_points: np.ndarray,
    classify_tol: float,
) -> np.ndarray:
    """Assign each row of ``final_states`` to the nearest attractor.

    Returns an ``int64`` array of shape ``(N,)``. Entries equal to
    :data:`UNCLASSIFIED_LABEL` correspond to orbits whose nearest-
    attractor distance exceeds ``classify_tol``.
    """
    # Distance from every final state to every attractor — shape (N, K).
    diffs = (
        final_states[:, None, :] - attractor_points[None, :, :]
    )
    dists = np.linalg.norm(diffs, axis=2)
    nearest = np.argmin(dists, axis=1)
    min_dist = dists[np.arange(dists.shape[0]), nearest]
    labels = nearest.astype(np.int64)
    labels[min_dist > float(classify_tol)] = UNCLASSIFIED_LABEL
    return labels


def _build_y0_grid(
    x_axis: tuple[int, float, float],
    y_axis: tuple[int, float, float],
    n_grid: tuple[int, int],
    fixed_state: np.ndarray,
) -> np.ndarray:
    """Build the ``(n_x * n_y, state_dim)`` initial-condition matrix.

    Row order is row-major in ``(y, x)`` so the final reshape into the
    label matrix gives ``labels[i, j]`` for ``(y_grid[i], x_grid[j])``.
    """
    n_x, n_y = int(n_grid[0]), int(n_grid[1])
    ix, x_lo, x_hi = int(x_axis[0]), float(x_axis[1]), float(x_axis[2])
    iy, y_lo, y_hi = int(y_axis[0]), float(y_axis[1]), float(y_axis[2])
    if ix == iy:
        raise ValueError(
            f"x_axis and y_axis must differ; both refer to component {ix}"
        )
    state_dim = int(fixed_state.shape[0])
    if not 0 <= ix < state_dim:
        raise ValueError(f"x_axis state index {ix} out of range [0, {state_dim})")
    if not 0 <= iy < state_dim:
        raise ValueError(f"y_axis state index {iy} out of range [0, {state_dim})")
    if not x_hi > x_lo:
        raise ValueError(f"x_axis range must satisfy hi > lo; got ({x_lo}, {x_hi})")
    if not y_hi > y_lo:
        raise ValueError(f"y_axis range must satisfy hi > lo; got ({y_lo}, {y_hi})")

    xs = np.linspace(x_lo, x_hi, n_x)
    ys = np.linspace(y_lo, y_hi, n_y)
    # Row-major in (y, x): outer loop y, inner loop x.
    yy, xx = np.meshgrid(ys, xs, indexing="ij")  # shapes (n_y, n_x)
    template = np.broadcast_to(
        fixed_state, (n_y, n_x, state_dim)
    ).copy()
    template[..., ix] = xx
    template[..., iy] = yy
    return template.reshape(n_y * n_x, state_dim)


def _classify_attractors(
    attractors: Sequence[AttractorSpec],
    state_dim: int,
) -> tuple[list[str], np.ndarray]:
    """Validate + split the supervised-attractor specification."""
    if not attractors:
        raise ValueError("attractors must contain at least one (label, point) entry")
    labels: list[str] = []
    points: list[np.ndarray] = []
    for entry in attractors:
        try:
            label, point = entry
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"each attractor entry must be a (label, point) tuple; "
                f"got {entry!r}"
            ) from exc
        pt = np.ascontiguousarray(point, dtype=np.float64)
        if pt.shape != (state_dim,):
            raise ValueError(
                f"attractor {label!r} has shape {pt.shape}; expected "
                f"({state_dim},)"
            )
        if not np.isfinite(pt).all():
            raise ValueError(f"attractor {label!r} contains non-finite entries")
        labels.append(str(label))
        points.append(pt)
    return labels, np.stack(points)


def basin_diagram(
    rhs: Callable[..., Any],
    *,
    x_axis: tuple[int, float, float],
    y_axis: tuple[int, float, float],
    attractors: Sequence[AttractorSpec],
    fixed_state: FloatArray,
    n_grid: tuple[int, int] = (32, 32),
    t_end: float = 50.0,
    classify_tol: float = 1.0,
    backend: Literal["scipy", "jax"] = "scipy",
    system_name: str = "",
    rtol: float = 1e-6,
    atol: float = 1e-8,
    progress: Callable[[int, int], None] | None = None,
    scipy_method: str = "RK45",
    jax_solver: str = "Tsit5",
    jax_max_steps: int = 100_000,
) -> BasinDiagram:
    """Compute a 2D basin-of-attraction map.

    For every initial condition on the grid we integrate the system
    forward to ``t_end`` and classify the final state by nearest
    distance to one of the supplied attractor centers.

    Parameters
    ----------
    rhs
        Either a numpy ``rhs(t, y)`` or a JAX-traceable ``rhs(t, y)``
        / ``rhs(t, y, args)`` — pick the backend to match.
    x_axis, y_axis
        ``(state_idx, lo, hi)`` per axis. ``state_idx`` is which
        component of the state vector varies on that axis.
    attractors
        Sequence of ``(label, point)`` tuples. ``point`` is a
        ``(state_dim,)`` array — the representative location of one
        attractor.
    fixed_state
        Shape ``(state_dim,)``. Template for the non-swept
        components of every initial condition. The two swept
        components are overwritten per grid point.
    n_grid
        ``(n_x, n_y)`` resolution.
    t_end
        Integration time per orbit. Long enough that orbits settle
        onto their attractor; the canonical Duffing demo lands at
        t = 50 (about 15 oscillation periods at the natural
        frequency).
    classify_tol
        L2 distance threshold for the supervised classifier. Orbits
        farther than this from every attractor get
        :data:`UNCLASSIFIED_LABEL`.
    backend
        ``"scipy"`` (default; one ``solve_ivp`` per grid point) or
        ``"jax"`` (one vmapped diffrax call for the whole grid;
        requires a JAX-traceable rhs and the ``[jax]`` extra).
    system_name
        Free-form label saved on the returned diagram for plotting.
    rtol, atol
        Tolerances forwarded to the chosen integrator.
    progress
        Optional ``callback(done, total)`` invoked from the scipy
        backend after each grid point (or after each vmap batch for
        the JAX backend). The GUI worker uses this to drive a
        determinate progress bar.
    scipy_method
        scipy ``solve_ivp`` method when ``backend="scipy"``.
    jax_solver
        diffrax solver name when ``backend="jax"``. Forwarded to
        :func:`chaotic_systems.integrators.jax_backend.vmap_trajectories`.
    jax_max_steps
        diffrax ``max_steps`` cap when ``backend="jax"``.

    Returns
    -------
    BasinDiagram
        See :class:`BasinDiagram`.

    Raises
    ------
    ValueError
        On bad axis specs, attractor shapes, or grid sizes.
    ImportError
        If ``backend="jax"`` and the JAX extra is not installed.
    """
    fixed_arr = np.ascontiguousarray(fixed_state, dtype=np.float64)
    state_dim = int(fixed_arr.shape[0])
    attractor_labels_resolved, attractor_points = _classify_attractors(
        attractors, state_dim
    )
    y0_grid = _build_y0_grid(x_axis, y_axis, n_grid, fixed_arr)

    if backend == "scipy":
        final_states = _integrate_grid_scipy(
            rhs,
            y0_grid,
            t_end=t_end,
            rtol=rtol,
            atol=atol,
            method=scipy_method,
            progress=progress,
        )
    elif backend == "jax":
        final_states = _integrate_grid_jax(
            rhs,
            y0_grid,
            t_end=t_end,
            rtol=rtol,
            atol=atol,
            solver=jax_solver,
            max_steps=jax_max_steps,
            progress=progress,
        )
    else:
        raise ValueError(
            f"unknown backend {backend!r}; choose 'scipy' or 'jax'"
        )

    labels_flat = _classify_final_states(
        final_states, attractor_points, classify_tol
    )
    labels = labels_flat.reshape(int(n_grid[1]), int(n_grid[0]))

    return BasinDiagram(
        x_axis=(int(x_axis[0]), float(x_axis[1]), float(x_axis[2])),
        y_axis=(int(y_axis[0]), float(y_axis[1]), float(y_axis[2])),
        n_grid=(int(n_grid[0]), int(n_grid[1])),
        labels=labels,
        attractor_labels=attractor_labels_resolved,
        attractor_points=attractor_points,
        fixed_state=fixed_arr,
        system_name=str(system_name),
        classify_tol=float(classify_tol),
        backend=str(backend),
    )


def _integrate_grid_scipy(
    rhs: Callable[..., Any],
    y0_grid: np.ndarray,
    *,
    t_end: float,
    rtol: float,
    atol: float,
    method: str,
    progress: Callable[[int, int], None] | None,
) -> np.ndarray:
    """One ``solve_ivp`` per grid row. Returns ``(N, state_dim)`` final states."""
    n_total = int(y0_grid.shape[0])
    state_dim = int(y0_grid.shape[1])
    final_states = np.empty((n_total, state_dim), dtype=np.float64)
    # Progress tick at ~2% granularity, matching the bifurcation worker.
    tick_every = max(1, n_total // 50)
    for i in range(n_total):
        sol = solve_ivp(
            rhs,
            (0.0, float(t_end)),
            y0_grid[i],
            method=method,
            t_eval=[float(t_end)],
            rtol=rtol,
            atol=atol,
        )
        if sol.success and sol.y.shape[1] >= 1:
            final = sol.y[:, -1]
            # If the integrator silently produced NaN/Inf (rare with
            # adaptive methods on well-posed systems but possible on
            # divergent / stiff edge cases), mark this orbit as
            # unclassifiable by pushing the final state to infinity
            # — the classifier will then assign UNCLASSIFIED_LABEL.
            if not np.isfinite(final).all():
                final = np.full(state_dim, np.inf, dtype=np.float64)
            final_states[i] = final
        else:
            final_states[i] = np.full(state_dim, np.inf, dtype=np.float64)
        if progress is not None and ((i + 1) % tick_every == 0 or i == n_total - 1):
            progress(i + 1, n_total)
    return final_states


def _integrate_grid_jax(
    rhs: Callable[..., Any],
    y0_grid: np.ndarray,
    *,
    t_end: float,
    rtol: float,
    atol: float,
    solver: str,
    max_steps: int,
    progress: Callable[[int, int], None] | None,
) -> np.ndarray:
    """One ``vmap_trajectories`` call for the whole grid.

    Returns the final state per row, shape ``(N, state_dim)``. We ask
    diffrax for two saved time points (start and end) because the
    backend requires ``n_points >= 2`` even when we only care about
    the endpoint.
    """
    from chaotic_systems.integrators.jax_backend import vmap_trajectories

    _ts, ys = vmap_trajectories(
        rhs,
        (0.0, float(t_end)),
        y0_grid,
        n_points=2,
        solver=solver,
        rtol=rtol,
        atol=atol,
        max_steps=int(max_steps),
    )
    # ys shape: (N, 2, state_dim) — keep only the final row.
    final_states = np.ascontiguousarray(ys[:, -1, :], dtype=np.float64)
    # Replace any NaN/Inf with sentinel +inf so the classifier sends
    # them to the unclassified bucket rather than skewing the nearest-
    # attractor computation.
    bad = ~np.isfinite(final_states).all(axis=1)
    if bad.any():
        final_states[bad] = np.inf
    if progress is not None:
        progress(int(y0_grid.shape[0]), int(y0_grid.shape[0]))
    return final_states


# --------------------------------------------------------------------------
# Convenience: prebuilt scipy-side rhs for the undriven double-well
# Duffing oscillator (γ = 0). The two stable fixed points sit at
# (±1, 0); the basin boundary is the stable manifold of the saddle at
# the origin (a smooth curve, not yet fractal). This is the
# pedagogical pairing the proposal calls out and what the docstring of
# the basin panel references for the demo. Polynomial RHS so it
# trivially upgrades to JAX (replace ``np.array`` with ``jnp.array``).
# --------------------------------------------------------------------------


def double_well_rhs(
    alpha: float = -1.0, beta: float = 1.0, delta: float = 0.2
) -> Callable[[float, np.ndarray], np.ndarray]:
    """Return a scipy-style ``rhs(t, y)`` for the undriven Duffing oscillator.

    .. math::

        \\dot x &= v, \\\\
        \\dot v &= -\\delta v - \\alpha x - \\beta x^3.

    Canonical double-well: ``alpha = -1``, ``beta = 1`` puts stable
    fixed points at ``(±1, 0)`` and a saddle at ``(0, 0)``. ``delta``
    is light damping (the typical demo uses ``delta = 0.2``). With
    ``delta = 0`` the system is Hamiltonian and orbits don't decay
    onto the fixed points; a basin map then needs a different
    classification strategy. Default ``delta = 0.2`` keeps the
    supervised classifier honest.
    """

    def rhs(t: float, y: np.ndarray) -> np.ndarray:
        x, v = float(y[0]), float(y[1])
        return np.array(
            [v, -delta * v - alpha * x - beta * x * x * x],
            dtype=np.float64,
        )

    return rhs


__all__ = [
    "AttractorSpec",
    "BasinDiagram",
    "UNCLASSIFIED_LABEL",
    "basin_diagram",
    "double_well_rhs",
]
