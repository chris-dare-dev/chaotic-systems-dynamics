"""Matplotlib renderer for recurrence plots.

Given a boolean recurrence matrix from
:func:`chaotic_systems.core.recurrence.recurrence_matrix`, render it
as a black-and-white image. Recurrent points are dark; non-recurrent
points are light. Optionally overlay the RQA scalars (RR, DET, LAM,
L_max, ENTR) as text in the upper-right corner.

The viz module is intentionally thin — recurrence plots are
information-dense by construction; we keep the imshow plain so the
patterns the user actually wants to see (diagonal stripes, dot clouds,
laminar bars) are not visually competed-with by chart chrome.

References
----------
- N. Marwan, M. C. Romano, M. Thiel, J. Kurths, *Recurrence plots for
  the analysis of complex systems*, Phys. Rep. 438 (2007), 237-329 —
  Figs. 1-6 show the canonical patterns this module reproduces.
- T. Rawald, M. Sips, N. Marwan, *PyRQA — Conducting Recurrence
  Quantification Analysis on very long time series efficiently*,
  arXiv:2402.16853 (Jan 2024).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from chaotic_systems.core.recurrence import RQAStats

if TYPE_CHECKING:  # pragma: no cover - import only for type hints
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

_DEFAULT_FIGSIZE: tuple[float, float] = (6.0, 6.0)
_DEFAULT_DPI: int = 120

# Tokyo Night accent — recurrent points get the same blue the renderer
# uses for the primary trajectory, on a dark background.
_RECURRENT_COLOR_DARK: str = "#7aa2f7"
_BACKGROUND_DARK: str = "#1a1b26"
# Light variant (paper / publication mode): black on white.
_RECURRENT_COLOR_LIGHT: str = "#000000"
_BACKGROUND_LIGHT: str = "#ffffff"


def plot_recurrence(
    matrix: np.ndarray,
    *,
    ax: Axes | None = None,
    stats: RQAStats | None = None,
    figsize: tuple[float, float] = _DEFAULT_FIGSIZE,
    dpi: int = _DEFAULT_DPI,
    title: str | None = None,
    xlabel: str = "time index j",
    ylabel: str = "time index i",
    dark: bool = True,
    facecolor: str | None = None,
    show_stats_overlay: bool = True,
) -> Figure:
    """Render a recurrence matrix as a black-and-white square image.

    Parameters
    ----------
    matrix
        Boolean ``(N, N)`` recurrence matrix from
        :func:`chaotic_systems.core.recurrence.recurrence_matrix`.
    ax
        Optional pre-existing axes; default builds a fresh figure.
    stats
        Optional :class:`RQAStats` to overlay in the upper-right
        corner (RR / DET / LAM / L_max / ENTR). Pass ``None`` to
        suppress the overlay.
    figsize, dpi
        Used when ``ax is None``.
    title
        Plot title. Defaults to ``"Recurrence plot (N=...)"``.
    xlabel, ylabel
        Axis labels. Defaults are the conventional ``time index j`` /
        ``time index i``.
    dark
        If ``True`` (default), use the Tokyo Night palette
        (blue recurrent points on dark background); else paper /
        publication style (black on white).
    facecolor
        Optional explicit override for the figure / axes background.
        Takes precedence over the ``dark`` flag.
    show_stats_overlay
        Render the RQA scalars in the corner (only if ``stats`` is
        also provided).

    Returns
    -------
    Figure
        The matplotlib figure carrying the rendered plot.

    Raises
    ------
    ValueError
        If ``matrix`` is not a square 2-D array.
    """
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError(
            f"matrix must be square (N, N); got shape {matrix.shape}"
        )
    import matplotlib

    matplotlib.use("Agg", force=False)
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.colors import ListedColormap
    from matplotlib.figure import Figure

    n = int(matrix.shape[0])
    matrix_bool = matrix.astype(bool, copy=False)

    if dark:
        bg = facecolor if facecolor is not None else _BACKGROUND_DARK
        fg = _RECURRENT_COLOR_DARK
    else:
        bg = facecolor if facecolor is not None else _BACKGROUND_LIGHT
        fg = _RECURRENT_COLOR_LIGHT
    cmap = ListedColormap([bg, fg])

    fig: Figure
    if ax is None:
        fig = Figure(figsize=figsize, dpi=dpi)
        FigureCanvasAgg(fig)
        ax_local: Any = fig.add_subplot(111)
    else:
        ax_local = ax
        fig = ax_local.figure

    fig.patch.set_facecolor(bg)
    ax_local.set_facecolor(bg)
    text_color = "#c0caf5" if dark else "#1a1b26"
    for spine in ax_local.spines.values():
        spine.set_edgecolor(text_color)
    ax_local.tick_params(colors=text_color)
    ax_local.xaxis.label.set_color(text_color)
    ax_local.yaxis.label.set_color(text_color)
    ax_local.title.set_color(text_color)

    # ``origin="lower"`` so i increases upward (matches the convention
    # in Marwan §3 figures). Aspect "equal" keeps the matrix square
    # regardless of the surrounding window dimensions.
    ax_local.imshow(
        matrix_bool,
        cmap=cmap,
        origin="lower",
        interpolation="nearest",
        aspect="equal",
        vmin=0,
        vmax=1,
        extent=(0, n, 0, n),
    )

    ax_local.set_xlabel(xlabel)
    ax_local.set_ylabel(ylabel)
    ax_local.set_title(
        title if title is not None else f"Recurrence plot (N = {n})"
    )

    if show_stats_overlay and stats is not None:
        overlay = (
            f"RR     = {stats.rr:.4f}\n"
            f"DET    = {stats.det:.4f}\n"
            f"LAM    = {stats.lam:.4f}\n"
            f"L_max  = {stats.l_max:d}\n"
            f"V_max  = {stats.v_max:d}\n"
            f"ENTR   = {stats.entr:.4f}"
        )
        # Anchor the text box to the upper-right axes corner so it sits
        # on top of the (typically empty) corner of the plot rather
        # than over any structure.
        bbox = dict(
            facecolor=bg,
            edgecolor=text_color,
            alpha=0.85,
            boxstyle="round,pad=0.3",
        )
        ax_local.text(
            0.98,
            0.98,
            overlay,
            transform=ax_local.transAxes,
            ha="right",
            va="top",
            color=text_color,
            fontfamily="monospace",
            fontsize=8,
            bbox=bbox,
            zorder=5,
        )

    fig.tight_layout()
    return fig


__all__ = ["plot_recurrence"]
