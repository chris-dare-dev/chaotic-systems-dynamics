"""Matplotlib renderer for bifurcation diagrams.

This module is the *pure-matplotlib* side of the bifurcation feature:
given a :class:`~chaotic_systems.core.bifurcation.BifurcationDiagram`,
return a :class:`matplotlib.figure.Figure` that can be either embedded
in the GUI (:class:`~chaotic_systems.gui.bifurcation_panel.BifurcationPanel`
uses :class:`matplotlib.backends.backend_qtagg.FigureCanvasQTAgg`)
or saved to disk for a paper figure.

The plot is a dense scatter of ``(param_value, state_component)``
points with tiny markers and low opacity — the conventional rendering
since May 1976. We default to ``marker="."`` / ``s=0.5`` / ``alpha=0.6``
which makes the period-doubling cascade visually crisp at the
``800 × 200`` default sweep size without needing per-orbit color coding.

A non-interactive Agg canvas is bound to the figure so this module is
safe to call from a worker thread that runs before any Qt event loop
has spun up. The GUI panel re-binds a Qt canvas after the worker
returns — see :mod:`chaotic_systems.gui.bifurcation_panel`.

References
----------
- R. May, *Simple mathematical models with very complicated dynamics*,
  Nature 261 (1976), 459-467 — the original logistic-map figure this
  module reproduces.
- S. Strogatz, *Nonlinear Dynamics and Chaos* (2nd ed., 2015), §10.6,
  Figs 10.6.2-10.6.4 — the textbook presentation of the diagram.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from chaotic_systems.core.bifurcation import BifurcationDiagram, as_scatter

if TYPE_CHECKING:  # pragma: no cover - import only for type hints
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

# Matplotlib defaults tuned for the canonical Feigenbaum-style render.
# - marker "." is the smallest visible point at standard DPI.
# - s=0.5 keeps individual iterates from blurring together inside cycles.
# - alpha=0.6 softens the chaotic band so periodic windows pop visually.
_DEFAULT_MARKER: str = "."
_DEFAULT_MARKER_SIZE: float = 0.5
_DEFAULT_ALPHA: float = 0.6
_DEFAULT_COLOR: str = "#7aa2f7"
_DEFAULT_FIGSIZE: tuple[float, float] = (8.0, 5.0)
_DEFAULT_DPI: int = 120


def plot_bifurcation(
    diagram: BifurcationDiagram,
    *,
    projection: int = 0,
    ax: Axes | None = None,
    marker: str = _DEFAULT_MARKER,
    marker_size: float = _DEFAULT_MARKER_SIZE,
    alpha: float = _DEFAULT_ALPHA,
    color: str = _DEFAULT_COLOR,
    figsize: tuple[float, float] = _DEFAULT_FIGSIZE,
    dpi: int = _DEFAULT_DPI,
    title: str | None = None,
    ylabel: str | None = None,
    facecolor: str | None = None,
) -> Figure:
    """Render a bifurcation diagram as a dense scatter plot.

    Parameters
    ----------
    diagram
        The :class:`BifurcationDiagram` to render.
    projection
        Which state-vector component to plot on the y-axis. Defaults
        to ``0`` (the first component — the conventional choice for
        the logistic / Hénon / Ikeda / standard map).
    ax
        Optional pre-existing :class:`matplotlib.axes.Axes` to draw
        into. If ``None`` a fresh ``Figure`` + ``Axes`` are built.
    marker, marker_size, alpha, color
        Scatter styling. The defaults reproduce the Feigenbaum look.
    figsize, dpi
        Used only when ``ax is None``.
    title
        Plot title. Defaults to ``"<system_name> bifurcation diagram"``.
    ylabel
        Y-axis label. Defaults to ``y[<projection>]``.
    facecolor
        Optional figure / axes background color. ``None`` leaves the
        matplotlib default (white) untouched, which is what most
        papers expect; pass a dark hex string to match the GUI's
        Tokyo Night palette.

    Returns
    -------
    Figure
        The matplotlib figure. The caller owns it; the GUI panel
        replaces its canvas before showing it.
    """
    import matplotlib

    # Keep the same Agg-default rationale as ``visualization.latex``:
    # this module needs to be safe to call from a worker thread before
    # any Qt event loop has spun up. The GUI re-binds a Qt canvas later.
    matplotlib.use("Agg", force=False)
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    xs, ys = as_scatter(diagram, projection=projection)

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
        # Light text against a dark background.
        for spine in ax_local.spines.values():
            spine.set_edgecolor("#a9b1d6")
        ax_local.tick_params(colors="#a9b1d6")
        ax_local.xaxis.label.set_color("#c0caf5")
        ax_local.yaxis.label.set_color("#c0caf5")
        ax_local.title.set_color("#c0caf5")

    ax_local.scatter(
        xs,
        ys,
        s=marker_size,
        marker=marker,
        c=color,
        alpha=alpha,
        linewidths=0.0,
    )

    ax_local.set_xlabel(diagram.param_name)
    ax_local.set_ylabel(
        ylabel
        if ylabel is not None
        else (f"y[{projection}]" if diagram.state_dim > 1 else "x")
    )
    ax_local.set_title(
        title
        if title is not None
        else f"{diagram.system_name} bifurcation diagram"
    )
    ax_local.grid(True, alpha=0.15, linewidth=0.5)
    fig.tight_layout()
    return fig


__all__ = ["plot_bifurcation"]
