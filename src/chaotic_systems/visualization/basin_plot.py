"""Matplotlib renderer for basin-of-attraction diagrams.

Companion to :mod:`chaotic_systems.core.basins`. Given a
:class:`~chaotic_systems.core.basins.BasinDiagram`, produces a
:class:`matplotlib.figure.Figure` with the basin imshow + a legend
of per-attractor swatches. Follows the same Agg-safe pattern as
:mod:`chaotic_systems.visualization.bifurcation_plot` /
:mod:`chaotic_systems.visualization.phase_plot` so the renderer is
callable from a worker thread before any Qt event loop has spun up.

References
----------
- E. Ott, *Chaos in Dynamical Systems* (2nd ed., 2002), §5.3, Figure
  5.5 (driven Duffing basin) — the canonical reference picture this
  module reproduces.
- G. Datseris & A. Wagemakers, *Effortless estimation of basins of
  attraction*, Chaos 32 (2022) 023104, Figs. 1-3 for the modern
  colormap conventions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from chaotic_systems.core.basins import UNCLASSIFIED_LABEL, BasinDiagram

if TYPE_CHECKING:  # pragma: no cover - import only for type hints
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

# Tokyo-Night palette accents — distinct, color-blind-friendly enough
# for up to ~6 attractors. Beyond that the caller should pick their
# own ``cmap``; the basin plot accepts a matplotlib ``Colormap`` or
# any list of color hex strings.
_DEFAULT_PALETTE: tuple[str, ...] = (
    "#7aa2f7",  # blue
    "#f7768e",  # red-pink
    "#9ece6a",  # green
    "#e0af68",  # orange-yellow
    "#bb9af7",  # purple
    "#73daca",  # teal
)
_UNCLASSIFIED_COLOR: str = "#414868"  # Tokyo Night surface gray

_DEFAULT_FIGSIZE: tuple[float, float] = (6.5, 6.0)
_DEFAULT_DPI: int = 120


def plot_basin(
    diagram: BasinDiagram,
    *,
    ax: Axes | None = None,
    palette: list[str] | tuple[str, ...] | None = None,
    figsize: tuple[float, float] = _DEFAULT_FIGSIZE,
    dpi: int = _DEFAULT_DPI,
    title: str | None = None,
    xlabel: str | None = None,
    ylabel: str | None = None,
    axes_labels: tuple[str, ...] | None = None,
    facecolor: str | None = None,
    show_attractor_markers: bool = True,
    show_legend: bool = True,
) -> Figure:
    """Render a basin-of-attraction map.

    The basin matrix is drawn with :meth:`matplotlib.axes.Axes.imshow`
    using a categorical colormap built from ``palette`` (one color per
    attractor; unclassified pixels use a neutral gray). Attractor
    centers can be marked with stars on top of the basin so the
    viewer can read off the attractor's location.

    Parameters
    ----------
    diagram
        The :class:`BasinDiagram` to render.
    ax
        Optional pre-existing axes to draw into.
    palette
        Per-attractor colors. Defaults to a 6-entry Tokyo-Night-aligned
        palette; if more attractors than palette entries are present,
        colors cycle.
    figsize, dpi
        Used when ``ax is None``.
    title
        Plot title. Defaults to ``"<system> basins"``.
    xlabel, ylabel
        Axis labels. Default to ``axes_labels[ix]`` / ``axes_labels[iy]``
        when supplied, otherwise to ``y[ix]`` / ``y[iy]``.
    axes_labels
        Optional per-state-component label tuple (length ``state_dim``).
    facecolor
        Optional background hex (e.g. Tokyo Night ``#24283b``) for
        the figure + axes.
    show_attractor_markers
        Draw a small star at the (x, y) projection of each attractor
        center.
    show_legend
        Render a legend with one entry per attractor + an entry for
        unclassified pixels (if any).

    Returns
    -------
    Figure
        The matplotlib figure carrying the rendered basin.
    """
    import matplotlib

    matplotlib.use("Agg", force=False)
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.colors import ListedColormap
    from matplotlib.figure import Figure
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    colors = list(palette) if palette is not None else list(_DEFAULT_PALETTE)
    if not colors:
        raise ValueError("palette must contain at least one color")
    n_attr = diagram.n_attractors
    # Cycle through palette if there are more attractors than colors.
    attractor_colors = [colors[i % len(colors)] for i in range(n_attr)]

    # Build a colormap whose lookup-table order is:
    #   index 0 = unclassified (gray)
    #   indices 1..n_attr = attractor 0..n_attr-1
    # We then shift the label matrix by +1 so the imshow indices line up.
    cmap_colors = [_UNCLASSIFIED_COLOR, *attractor_colors]
    cmap = ListedColormap(cmap_colors)

    # Shift labels: UNCLASSIFIED_LABEL (-1) → 0, attractor i → i + 1.
    shifted = diagram.labels.astype(np.int64) + 1
    shifted[diagram.labels == UNCLASSIFIED_LABEL] = 0
    # Clip to the palette range so cycling out-of-range labels stays sane.
    shifted = np.clip(shifted, 0, n_attr)

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

    _, x_lo, x_hi = diagram.x_axis
    _, y_lo, y_hi = diagram.y_axis
    ax_local.imshow(
        shifted,
        cmap=cmap,
        origin="lower",
        extent=(x_lo, x_hi, y_lo, y_hi),
        aspect="auto",
        interpolation="nearest",
        vmin=0,
        vmax=n_attr,
    )

    # Axis labels: explicit > axes_labels[ix/iy] > "y[i]".
    ix = int(diagram.x_axis[0])
    iy = int(diagram.y_axis[0])

    def _resolve_label(explicit: str | None, idx: int) -> str:
        if explicit is not None:
            return explicit
        if axes_labels is not None and 0 <= idx < len(axes_labels):
            return str(axes_labels[idx])
        return f"y[{idx}]"

    ax_local.set_xlabel(_resolve_label(xlabel, ix))
    ax_local.set_ylabel(_resolve_label(ylabel, iy))
    ax_local.set_title(
        title
        if title is not None
        else f"{diagram.system_name or 'system'} basins"
    )

    # Attractor markers — small stars on top of the imshow.
    if show_attractor_markers and n_attr > 0:
        for i in range(n_attr):
            pt = diagram.attractor_points[i]
            ax_local.scatter(
                pt[ix],
                pt[iy],
                marker="*",
                s=140,
                color="white",
                edgecolors="black",
                linewidths=0.8,
                zorder=5,
            )

    if show_legend and n_attr > 0:
        handles: list[Any] = [
            Patch(facecolor=attractor_colors[i], label=diagram.attractor_labels[i])
            for i in range(n_attr)
        ]
        # Only show the unclassified swatch if some pixels actually
        # landed there — otherwise the legend reads misleadingly busy.
        if (diagram.labels == UNCLASSIFIED_LABEL).any():
            handles.append(
                Patch(facecolor=_UNCLASSIFIED_COLOR, label="unclassified")
            )
        if show_attractor_markers:
            handles.append(
                Line2D(
                    [],
                    [],
                    marker="*",
                    color="white",
                    markeredgecolor="black",
                    linestyle="None",
                    markersize=10,
                    label="attractor",
                )
            )
        ax_local.legend(handles=handles, loc="upper right", framealpha=0.85)

    fig.tight_layout()
    return fig


__all__ = ["plot_basin"]
