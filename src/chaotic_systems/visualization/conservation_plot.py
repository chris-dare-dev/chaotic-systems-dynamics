"""Matplotlib renderer for the conservation-overlay plot (V3).

For a trajectory ``y_i = y(t_i)`` of a system with a (claimed)
conserved quantity ``E(y)``, the plot shows

    ΔE(t) = E(y(t)) − E(y(0))

against ``t``. For a perfectly conservative integrator the curve is
flat at zero; non-symplectic methods (RK4, RK45, DOP853, ...) drift
linearly (or worse) over long times, and the drift makes the
symplectic-family pitch (yoshida4 / velocity_verlet / leapfrog)
visually concrete.

This is V3 from ``docs/proposals/capability-roadmap-2026-05-17.md``:
the headline argument for why the project ships symplectic
integrators in the first place. The mathematical reference is the
Hairer-Lubich-Wanner *Geometric Numerical Integration* monograph
(2006), §I.1 and §V.

Implementation notes
--------------------
- Pure-matplotlib, Agg-safe (callable from a worker thread before
  any Qt event loop has spun up). The GUI panel rebinds a Qt canvas
  after the worker returns — same pattern as V1 / D2 / D4 / D5.
- The energy callable is plugged from the caller: it accepts the
  raw state vector ``y_i`` (no time argument; conservative systems
  the project ships have no explicit-time dependence in the
  Hamiltonian) and returns a scalar. The DoublePendulum, HenonHeiles,
  and Duffing systems all expose ``.energy(y, params)`` directly.
- The annotation in the corner shows ``|ΔE|_max`` and the relative
  drift ``|ΔE|_max / |E_0|`` so the user reads the integrator's
  conservation quality at a glance.

References
----------
- E. Hairer, C. Lubich, G. Wanner, *Geometric Numerical Integration*
  (2nd ed., Springer 2006), §I.1.1 "Conservation of total energy"
  and §V "Symplectic Integration of Hamiltonian Systems".
- B. Leimkuhler & S. Reich, *Simulating Hamiltonian Dynamics*
  (Cambridge 2004), §3 — the canonical conservation-error plot.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import numpy as np

from chaotic_systems.core.base import FloatArray

if TYPE_CHECKING:  # pragma: no cover - import only for type hints
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

# Tokyo Night palette accents — same hexes used by V1 / D5 so the
# overlay reads as part of the family.
_DEFAULT_COLOR: str = "#7aa2f7"  # blue (matches phase-portrait / recurrence)
_DEFAULT_FIGSIZE: tuple[float, float] = (7.0, 3.5)
_DEFAULT_DPI: int = 120

#: Tolerance below which we round ``|E_0|`` to 1.0 in the relative-drift
#: denominator. Near-zero starting energies (HenonHeiles default IC at
#: E≈0.125 is the only system that lands here, harmlessly above the
#: floor) would otherwise produce absurd-looking relative drifts.
_REL_DRIFT_ZERO_FLOOR: float = 1e-12


def plot_conservation(
    trajectory: Any,
    energy_fn: Callable[[FloatArray], float],
    *,
    ax: Axes | None = None,
    color: str = _DEFAULT_COLOR,
    figsize: tuple[float, float] = _DEFAULT_FIGSIZE,
    dpi: int = _DEFAULT_DPI,
    title: str | None = None,
    xlabel: str = "t",
    ylabel: str = r"$\Delta E(t) = E(t) - E(0)$",
    facecolor: str | None = None,
    line_width: float = 1.2,
    show_drift_annotation: bool = True,
) -> Figure:
    """Plot the energy drift ``E(t) - E(0)`` for a trajectory.

    Parameters
    ----------
    trajectory
        Any object with ``.t`` (shape ``(N,)``) and ``.y`` (shape
        ``(N, state_dim)``) attributes — typically a
        :class:`~chaotic_systems.core.Trajectory`.
    energy_fn
        Callable ``E(y) -> float``. For the systems this project
        ships, ``system.energy`` is the natural choice; users with
        non-default parameters should bind those via ``functools.partial``
        before passing in (since the systems' ``energy`` typically
        accepts a ``params`` second argument).
    ax
        Optional pre-existing axes; default builds a fresh figure.
    color
        Trajectory line color. Defaults to the Tokyo Night accent.
    figsize, dpi
        Used when ``ax is None``.
    title
        Plot title. Defaults to ``"<system> energy drift"`` when the
        trajectory exposes a ``.system`` attribute, else just
        ``"Energy drift"``.
    xlabel, ylabel
        Axis labels.
    facecolor
        Optional figure / axes background hex (e.g. Tokyo Night
        ``#24283b``).
    line_width
        Line width in logical pixels.
    show_drift_annotation
        Render a corner overlay reporting ``|ΔE|_max`` and the
        relative drift ``|ΔE|_max / max(|E_0|, floor)``.

    Returns
    -------
    Figure
        The matplotlib figure carrying the rendered overlay.

    Raises
    ------
    TypeError
        If ``trajectory`` doesn't expose ``.t`` / ``.y``.
    ValueError
        If ``.y`` is malformed or has fewer than 2 samples.
    """
    ts, ys = _coerce_trajectory(trajectory)
    # Evaluate the energy at every sample. The list-comp is fine for
    # the GUI-typical N ≤ 4000; vectorized energy callables would let
    # us batch this but most system.energy methods take a single y
    # at a time, so we don't paper over that asymmetry.
    energies = np.fromiter(
        (float(energy_fn(np.asarray(y, dtype=np.float64))) for y in ys),
        dtype=np.float64,
        count=int(ys.shape[0]),
    )
    e0 = float(energies[0])
    delta = energies - e0

    import matplotlib

    matplotlib.use("Agg", force=False)
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    fig: Figure
    if ax is None:
        fig = Figure(figsize=figsize, dpi=dpi)
        FigureCanvasAgg(fig)
        ax_local: Any = fig.add_subplot(111)
    else:
        ax_local = ax
        fig = ax_local.figure

    if facecolor is not None:
        fig.patch.set_facecolor(facecolor)
        ax_local.set_facecolor(facecolor)
        text_color = "#c0caf5"
        for spine in ax_local.spines.values():
            spine.set_edgecolor("#a9b1d6")
        ax_local.tick_params(colors="#a9b1d6")
        ax_local.xaxis.label.set_color(text_color)
        ax_local.yaxis.label.set_color(text_color)
        ax_local.title.set_color(text_color)
    else:
        text_color = "#1a1b26"

    ax_local.plot(ts, delta, color=color, linewidth=line_width)
    # A horizontal reference line at ΔE = 0 — exactly where a perfect
    # symplectic run would sit. Drawn faint so it doesn't dominate.
    ax_local.axhline(0.0, color="#a9b1d6", linewidth=0.6, alpha=0.4)

    ax_local.set_xlabel(xlabel)
    ax_local.set_ylabel(ylabel)
    system_name = getattr(trajectory, "system", None)
    ax_local.set_title(
        title
        if title is not None
        else (f"{system_name} energy drift" if system_name else "Energy drift")
    )

    if show_drift_annotation:
        max_drift = float(np.max(np.abs(delta)))
        denom = abs(e0) if abs(e0) > _REL_DRIFT_ZERO_FLOOR else 1.0
        rel_drift = max_drift / denom
        annotation = (
            f"E(0) = {e0:+.4g}\n"
            f"|ΔE|_max = {max_drift:.3e}\n"
            f"|ΔE|/|E₀| = {rel_drift:.3e}"
        )
        # Pin to the upper-right axes corner; same anchor as the
        # D5 recurrence-plot RQA-stats overlay.
        bbox = dict(
            facecolor=facecolor if facecolor is not None else "white",
            edgecolor=text_color,
            alpha=0.85,
            boxstyle="round,pad=0.3",
        )
        ax_local.text(
            0.98,
            0.97,
            annotation,
            transform=ax_local.transAxes,
            ha="right",
            va="top",
            color=text_color,
            fontfamily="monospace",
            fontsize=8,
            bbox=bbox,
            zorder=5,
        )

    ax_local.grid(True, alpha=0.15, linewidth=0.5)
    fig.tight_layout()
    return fig


def _coerce_trajectory(trajectory: Any) -> tuple[FloatArray, FloatArray]:
    """Pull ``(t, y)`` arrays out of a Trajectory-like object."""
    if not hasattr(trajectory, "t") or not hasattr(trajectory, "y"):
        raise TypeError(
            "conservation plot needs an object with .t and .y attributes; "
            f"got {type(trajectory).__name__}"
        )
    ts = np.ascontiguousarray(trajectory.t, dtype=np.float64)
    ys = np.ascontiguousarray(trajectory.y, dtype=np.float64)
    if ts.ndim != 1:
        raise ValueError(f"trajectory.t must be 1-D; got shape {ts.shape}")
    if ys.ndim != 2:
        raise ValueError(
            f"trajectory.y must be 2-D (N, state_dim); got shape {ys.shape}"
        )
    if ts.shape[0] != ys.shape[0]:
        raise ValueError(
            f"trajectory.t length {ts.shape[0]} != trajectory.y first axis "
            f"{ys.shape[0]}"
        )
    if ts.shape[0] < 2:
        raise ValueError("conservation plot requires at least 2 samples")
    return ts, ys


__all__ = ["plot_conservation"]
