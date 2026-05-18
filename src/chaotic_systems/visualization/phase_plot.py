"""Matplotlib 2D phase-portrait renderer.

A *phase portrait* — a plot of one state coordinate against another —
is the canonical first picture of any dynamical system, and is how
chaos is *taught* before the 3D strange-attractor render takes over
(Strogatz §6.1 "Phase Portraits"). For the Duffing oscillator the
portrait of ``(x, dx/dt)`` shows the cross-well jumping behaviour
explicitly; for the Hénon-Heiles section ``(x, p_x)`` exposes the KAM
tori; for Lorenz the ``(x, z)`` projection shows the famous twin-lobe
recurrence even without a third dimension.

This module is the pure-matplotlib side of the V1 feature: given a
:class:`~chaotic_systems.core.Trajectory` (or any object exposing
``.y``), render a 2D projection on the chosen axes. The companion
:mod:`chaotic_systems.gui.phase_panel` embeds the result in a
PySide6 panel.

The rendering follows the same Agg-safe pattern as
:mod:`chaotic_systems.visualization.bifurcation_plot`: a non-
interactive Agg canvas is bound to the figure so this module is safe
to call from a worker thread that runs before any Qt event loop has
spun up.

References
----------
- S. Strogatz, *Nonlinear Dynamics and Chaos* (2nd ed., 2015), §6.1
  "Phase Portraits" and §12.1 "The Lorenz Equations" — Figs. 6.1.1,
  12.1.1, 12.3.2 are the canonical reference figures this module
  reproduces.
- E. Ott, *Chaos in Dynamical Systems* (2nd ed., 2002), §1.5 — same
  phase-portrait language for higher-dimensional flows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:  # pragma: no cover - import only for type hints
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

# Default Tokyo-Night accent. The bifurcation plot uses the same hex
# (``#7aa2f7``) so the two panels feel like one family even though
# the renderers are independent.
_DEFAULT_COLOR: str = "#7aa2f7"
_DEFAULT_FIGSIZE: tuple[float, float] = (6.5, 6.0)
_DEFAULT_DPI: int = 120
_DEFAULT_LINE_WIDTH: float = 0.9
_DEFAULT_ALPHA: float = 0.85


def _extract_y(trajectory: Any) -> np.ndarray:
    """Read ``trajectory.y`` and coerce it to a ``(N, state_dim)`` array.

    Accepts either a :class:`~chaotic_systems.core.Trajectory` or any
    duck-typed object with a ``.y`` attribute shaped ``(N, state_dim)``
    or ``(state_dim, N)`` — the visualization contract layer's
    convention. We prefer the ``(N, state_dim)`` orientation since it's
    what :class:`Trajectory` ships.
    """
    if not hasattr(trajectory, "y"):
        raise TypeError(
            "phase-plot input must have a .y attribute; got "
            f"{type(trajectory).__name__}"
        )
    arr = np.ascontiguousarray(trajectory.y, dtype=np.float64)
    if arr.ndim != 2:
        raise ValueError(
            f"trajectory.y must be 2-D; got shape {arr.shape!r}"
        )
    # If the second axis matches a declared state_dim, we trust the
    # (N, state_dim) orientation. Otherwise fall back to the same
    # heuristic the contract layer uses: the shorter axis is state_dim.
    state_dim = getattr(trajectory, "state_dim", None)
    if state_dim is not None and arr.shape[0] == int(state_dim) and arr.shape[1] != int(
        state_dim
    ):
        return arr.T
    return arr


def plot_phase_portrait(
    trajectory: Any,
    *,
    ix: int = 0,
    iy: int = 1,
    ax: Axes | None = None,
    color: str = _DEFAULT_COLOR,
    line_width: float = _DEFAULT_LINE_WIDTH,
    alpha: float = _DEFAULT_ALPHA,
    figsize: tuple[float, float] = _DEFAULT_FIGSIZE,
    dpi: int = _DEFAULT_DPI,
    title: str | None = None,
    xlabel: str | None = None,
    ylabel: str | None = None,
    axes_labels: tuple[str, ...] | None = None,
    facecolor: str | None = None,
    equal_aspect: bool = False,
) -> Figure:
    """Render a 2D phase portrait of ``trajectory.y[:, ix]`` vs ``y[:, iy]``.

    Parameters
    ----------
    trajectory
        Any object exposing ``.y`` of shape ``(N, state_dim)``. The
        framework's :class:`~chaotic_systems.core.Trajectory` is the
        canonical input but duck-typed inputs (e.g. the fallback
        Lorenz used by the GUI in isolation) also work.
    ix, iy
        State-vector indices to use as the x- and y-axis. Must be
        distinct and in ``[0, state_dim)``. Defaults are ``(0, 1)`` —
        the standard ``(x, y)`` projection for 2-D and 3-D systems.
    ax
        Optional pre-existing :class:`matplotlib.axes.Axes`. If ``None``
        a fresh figure + axes pair is built.
    color, line_width, alpha
        Trajectory styling. Defaults match the Tokyo-Night palette
        used elsewhere in the GUI.
    figsize, dpi
        Used only when ``ax is None``.
    title
        Plot title. Defaults to ``"<system> phase portrait"``.
    xlabel, ylabel
        Axis labels. If not supplied, default to ``axes_labels[ix]``
        / ``axes_labels[iy]`` when provided, otherwise to
        ``"y[ix]"`` / ``"y[iy]"``.
    axes_labels
        Optional tuple of per-state-component labels (length
        ``state_dim``), e.g. ``("x", "y", "z")`` for Lorenz or
        ``("theta1", "theta2", "p1", "p2")`` for the double
        pendulum. The GUI passes this in from
        ``MainWindow._axes_labels_for``.
    facecolor
        Optional figure / axes background colour. ``None`` leaves the
        matplotlib default in place (best for saved figures); pass a
        dark hex string to match the embedded Tokyo-Night panel.
    equal_aspect
        If ``True``, force ``ax.set_aspect("equal")``. Useful for
        portraits where the ``(x, y)`` aspect ratio carries physical
        meaning (closed orbits in conservative systems, the Hénon
        attractor, etc.). Off by default since for chaotic flows the
        natural span of each axis differs by an order of magnitude.

    Returns
    -------
    Figure
        The matplotlib figure carrying the rendered portrait.

    Raises
    ------
    TypeError
        If ``trajectory`` does not expose ``.y``.
    ValueError
        If ``ix == iy``, or either index is out of range, or
        ``trajectory.y`` is not 2-D.
    """
    if int(ix) == int(iy):
        raise ValueError(
            f"ix and iy must be distinct (got ix={ix!r}, iy={iy!r})"
        )

    arr = _extract_y(trajectory)
    n, state_dim = arr.shape
    if not 0 <= int(ix) < state_dim:
        raise ValueError(
            f"ix={ix!r} out of range for state_dim={state_dim}"
        )
    if not 0 <= int(iy) < state_dim:
        raise ValueError(
            f"iy={iy!r} out of range for state_dim={state_dim}"
        )

    xs = arr[:, int(ix)]
    ys = arr[:, int(iy)]

    import matplotlib

    # Same Agg-default rationale as the bifurcation plot: this routine
    # is safe to call from a worker thread before any Qt event loop
    # has spun up. The GUI panel re-binds a Qt canvas afterwards.
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
        for spine in ax_local.spines.values():
            spine.set_edgecolor("#a9b1d6")
        ax_local.tick_params(colors="#a9b1d6")
        ax_local.xaxis.label.set_color("#c0caf5")
        ax_local.yaxis.label.set_color("#c0caf5")
        ax_local.title.set_color("#c0caf5")

    ax_local.plot(
        xs,
        ys,
        color=color,
        linewidth=line_width,
        alpha=alpha,
    )

    # Mark the starting point with a small filled circle so the user
    # can read the orbit direction by following the line away from it.
    if n > 0:
        ax_local.plot(
            [xs[0]],
            [ys[0]],
            marker="o",
            markersize=4,
            color=color,
            alpha=1.0,
        )

    # Axis labels: explicit > axes_labels tuple > generic y[i].
    def _resolve_label(explicit: str | None, idx: int) -> str:
        if explicit is not None:
            return explicit
        if axes_labels is not None and 0 <= idx < len(axes_labels):
            return str(axes_labels[idx])
        return f"y[{idx}]"

    ax_local.set_xlabel(_resolve_label(xlabel, int(ix)))
    ax_local.set_ylabel(_resolve_label(ylabel, int(iy)))

    system_name = getattr(trajectory, "system", "") or "trajectory"
    ax_local.set_title(
        title if title is not None else f"{system_name} phase portrait"
    )
    ax_local.grid(True, alpha=0.15, linewidth=0.5)
    if equal_aspect:
        ax_local.set_aspect("equal", adjustable="datalim")
    fig.tight_layout()
    return fig


__all__ = ["plot_phase_portrait"]
