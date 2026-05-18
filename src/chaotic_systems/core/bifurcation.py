"""Bifurcation diagrams for discrete-time dynamical systems.

The *bifurcation diagram* — the long-time orbit plotted as a function of
a control parameter — is the canonical visualization of how dynamical
behaviour reorganizes itself as a parameter is varied. The
Feigenbaum logistic-map figure (``r`` on the x-axis, attractor on the
y-axis, period-doubling cascade visible as the ``r``-window
``[3.0, 1 + sqrt(6) ≈ 3.449]`` of period-2 orbits, then period-4, ...,
into the chaotic regime past ``r_inf ≈ 3.5699``) is the most famous
single image in nonlinear dynamics (May 1976; Feigenbaum 1978).

This module ships the compute side. The companion module
:mod:`chaotic_systems.visualization.bifurcation_plot` renders the
result with matplotlib; :mod:`chaotic_systems.gui.bifurcation_panel`
embeds the plot in a PySide6 panel.

Scope (v1)
----------
Only **discrete maps** (:class:`~chaotic_systems.core.DiscreteSystem`)
are supported. For each value ``v`` of the swept parameter the routine
iterates the map ``n_transient + n_record - 1`` times from a seed
state and records the final ``n_record`` iterates. The resulting
``(M, n_record, state_dim)`` block is the bifurcation diagram; helper
:func:`as_scatter` flattens a chosen projection axis to ``(xs, ys)``
arrays for plotting.

ODE-flow bifurcation diagrams (via a Poincaré section + parameter
sweep) need extra choices a future iteration will surface — which
Poincaré plane, which projection, how many sections to sample — and
are intentionally out of scope here.

References
----------
- R. May, *Simple mathematical models with very complicated dynamics*,
  Nature 261 (1976), 459-467 — the original logistic-map bifurcation
  figure.
- M. J. Feigenbaum, *Quantitative universality for a class of nonlinear
  transformations*, J. Stat. Phys. 19 (1978), 25-52 — the universal
  scaling constants.
- S. Strogatz, *Nonlinear Dynamics and Chaos* (2nd ed., 2015), §10.6 —
  the canonical pedagogical presentation.
- L. R. Sales et al., *pynamicalsys: A Python toolkit for discrete
  dynamical systems analysis*, Chaos, Solitons & Fractals 201 (2025) —
  the 2025 reference implementation; their
  ``DiscreteDynamicalSystem.bifurcation_diagram`` exposes the same
  ``(param_range, n_values, n_transient, n_record)`` knobs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np

from chaotic_systems.core.base import FloatArray
from chaotic_systems.core.discrete import DiscreteSystem

# Default sweep settings tuned to feel "Feigenbaum-like" on the logistic
# map without paying too much compute up front. 800 parameter values is
# enough to make the period-doubling cascade visually crisp; 200 recorded
# iterates per value resolves period-8 cycles cleanly; 1000 burn-in
# iterates is well past the Feigenbaum transient for r > 3.5.
DEFAULT_N_VALUES: int = 800
DEFAULT_N_RECORD: int = 200
DEFAULT_N_TRANSIENT: int = 1000


@dataclass(frozen=True, slots=True)
class BifurcationDiagram:
    """The result of a parameter sweep over a discrete map.

    Attributes
    ----------
    system_name
        Name of the swept system (for the plot title / file name).
    param_name
        Which parameter was swept (e.g. ``"r"`` for the logistic map).
    param_values
        Shape ``(M,)``. The parameter values, in sweep order.
    samples
        Shape ``(M, n_record, state_dim)``. ``samples[i]`` is the
        recorded orbit for ``param_values[i]`` after the transient has
        been discarded.
    state_dim
        Echoed from the system for convenience.
    fixed_params
        The non-swept parameters held constant during the sweep
        (defaults to the system's :meth:`default_params`).
    """

    system_name: str
    param_name: str
    param_values: FloatArray
    samples: FloatArray
    state_dim: int
    fixed_params: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.param_values.ndim != 1:
            raise ValueError(
                f"param_values must be 1-D, got shape {self.param_values.shape}"
            )
        if self.samples.ndim != 3:
            raise ValueError(
                f"samples must be 3-D (M, n_record, state_dim); "
                f"got shape {self.samples.shape}"
            )
        m, _, d = self.samples.shape
        if self.param_values.shape[0] != m:
            raise ValueError(
                f"param_values length {self.param_values.shape[0]} does not "
                f"match samples first axis {m}"
            )
        if d != self.state_dim:
            raise ValueError(
                f"samples last axis {d} does not match state_dim {self.state_dim}"
            )

    @property
    def n_values(self) -> int:
        """Number of parameter values swept (``M``)."""
        return int(self.param_values.shape[0])

    @property
    def n_record(self) -> int:
        """Number of recorded iterates per parameter value."""
        return int(self.samples.shape[1])


def bifurcation_diagram(
    system: DiscreteSystem,
    param_name: str,
    param_values: FloatArray,
    *,
    n_record: int = DEFAULT_N_RECORD,
    n_transient: int = DEFAULT_N_TRANSIENT,
    y0: FloatArray | None = None,
    fixed_params: Mapping[str, float] | None = None,
) -> BifurcationDiagram:
    """Sweep ``param_name`` over ``param_values`` and record the long-time orbit.

    For each value ``v`` of the swept parameter:

    1. The map is iterated ``n_transient`` times from ``y0`` (or the
       system's default initial state) to let transients decay.
    2. The next ``n_record`` iterates are recorded.

    The state after the previous parameter's run is **not** carried
    over — each parameter value starts from the same fixed ``y0``. That
    keeps the diagram reproducible and lets pathological intermediate
    parameter values (e.g. ones inside the period-3 window) not pollute
    later values' transients.

    Parameters
    ----------
    system
        The discrete map to sweep. Must expose the named parameter.
    param_name
        Name of the parameter to vary; must be a key in
        ``system.parameters``.
    param_values
        Shape ``(M,)``. The values to evaluate, in sweep order. Need
        not be sorted; the diagram preserves the user's ordering.
    n_record
        Number of iterates to record per parameter value (after the
        transient). Higher values resolve longer cycles.
    n_transient
        Number of iterates to discard per parameter value before
        recording. Must be long enough that the orbit has settled onto
        the attractor.
    y0
        Initial condition for every sub-sweep (defaults to
        :attr:`DiscreteSystem.initial_state`). The same seed is used
        for every value of the swept parameter.
    fixed_params
        Values for the non-swept parameters. Defaults to the system's
        :meth:`default_params`; the swept parameter's entry, if
        supplied here, is overridden by ``param_values``.

    Returns
    -------
    BifurcationDiagram
        The sweep result. See :class:`BifurcationDiagram`.

    Raises
    ------
    KeyError
        If ``param_name`` is not a parameter of ``system``.
    ValueError
        If ``param_values`` is not 1-D, or ``n_record`` / ``n_transient``
        are out of range, or ``y0`` is the wrong shape / non-finite.
    """
    if not isinstance(system, DiscreteSystem):
        raise TypeError(
            f"bifurcation_diagram currently supports DiscreteSystem only; "
            f"got {type(system).__name__}. ODE-flow bifurcation via Poincaré "
            f"sampling is a planned future extension."
        )
    if param_name not in system.parameters:
        raise KeyError(
            f"unknown parameter {param_name!r} for map {system.name!r}; "
            f"known: {sorted(system.parameters)}"
        )
    pv = np.ascontiguousarray(param_values, dtype=np.float64)
    if pv.ndim != 1:
        raise ValueError(f"param_values must be 1-D, got shape {pv.shape}")
    if pv.shape[0] < 1:
        raise ValueError("param_values must contain at least one value")
    if int(n_record) < 1:
        raise ValueError(f"n_record must be >= 1 (got {n_record!r})")
    if int(n_transient) < 0:
        raise ValueError(f"n_transient must be >= 0 (got {n_transient!r})")

    # Seed and fixed-parameter dict resolution.
    if y0 is None:
        seed = system.initial_state
    else:
        seed = np.ascontiguousarray(y0, dtype=np.float64)
        if seed.shape != (system.state_dim,):
            raise ValueError(
                f"y0 has shape {seed.shape}, expected ({system.state_dim},)"
            )
        if not np.isfinite(seed).all():
            raise ValueError("y0 contains non-finite entries")

    base_params = dict(system.default_params())
    if fixed_params is not None:
        for key, val in fixed_params.items():
            if key not in base_params:
                raise KeyError(
                    f"fixed_params has unknown key {key!r} for map "
                    f"{system.name!r}; known: {sorted(base_params)}"
                )
            base_params[key] = float(val)

    m = pv.shape[0]
    samples = np.empty((m, int(n_record), system.state_dim), dtype=np.float64)
    for i in range(m):
        params = dict(base_params)
        params[param_name] = float(pv[i])
        # ``iterate`` already discards the transient internally and
        # returns ``n_record + 1`` samples — we slice off the seed row
        # so the recorded block is exactly ``(n_record, state_dim)``.
        traj = system.iterate(
            n_steps=int(n_record),
            y0=seed,
            params=params,
            n_transient=int(n_transient),
        )
        samples[i] = traj.y[1:]

    return BifurcationDiagram(
        system_name=system.name,
        param_name=param_name,
        param_values=pv,
        samples=samples,
        state_dim=system.state_dim,
        fixed_params=dict(base_params),
    )


def as_scatter(
    diagram: BifurcationDiagram,
    *,
    projection: int = 0,
) -> tuple[FloatArray, FloatArray]:
    """Flatten a bifurcation diagram to ``(xs, ys)`` plot-ready arrays.

    Parameters
    ----------
    diagram
        The :class:`BifurcationDiagram` to project.
    projection
        Which state-vector axis to use as the y-coordinate.
        ``0`` for the first state component (the conventional choice
        for the logistic / Hénon / Ikeda / standard map). Must satisfy
        ``0 <= projection < diagram.state_dim``.

    Returns
    -------
    xs, ys
        Each shape ``(M * n_record,)``. ``xs[i]`` is the parameter
        value, ``ys[i]`` is the corresponding sampled state component.
    """
    if not 0 <= int(projection) < diagram.state_dim:
        raise ValueError(
            f"projection axis {projection} out of range for "
            f"state_dim={diagram.state_dim}"
        )
    m, n_record, _ = diagram.samples.shape
    xs = np.repeat(diagram.param_values, n_record)
    ys = diagram.samples[:, :, int(projection)].reshape(m * n_record)
    return xs, ys


__all__ = [
    "BifurcationDiagram",
    "DEFAULT_N_RECORD",
    "DEFAULT_N_TRANSIENT",
    "DEFAULT_N_VALUES",
    "as_scatter",
    "bifurcation_diagram",
]
