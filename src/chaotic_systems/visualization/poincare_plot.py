"""Matplotlib 2D renderer for Poincaré-section crossings.

A Poincaré section is the intersection of a trajectory with a
codimension-1 hyperplane in phase space. The crossings form a discrete
2D scatter that exposes the section topology directly — KAM tori
appear as nested closed curves, chaotic seas as area-filling clouds,
period-N orbits as N isolated dots. For Hénon-Heiles at energy
:math:`E \\approx 0.125` the section through :math:`x = 0` with
:math:`p_x > 0`, projected onto :math:`(y, p_y)`, reproduces the
canonical "islands of stability in a chaotic sea" picture of Hénon &
Heiles 1964 Fig. 4.

This module is the pure-matplotlib side of the W1 / CSC-029 wire-up;
the companion :mod:`chaotic_systems.gui.poincare_panel` embeds the
result in a PySide6 panel. The compute-side
:func:`~chaotic_systems.core.poincare.poincare_section` has shipped
since day one (``core/poincare.py:42``); this renderer + panel are the
GUI surface that internal-adversary brief W1 identified as the next
"D1"-class wire-up.

The rendering follows the same Agg-safe pattern as
:mod:`chaotic_systems.visualization.phase_plot` and
:mod:`chaotic_systems.visualization.basin_plot`: a non-interactive Agg
canvas is bound to the figure so this module is safe to call from a
worker thread that runs before any Qt event loop has spun up.

References
----------
- M. Hénon, C. Heiles, *The applicability of the third integral of
  motion: some numerical experiments*, Astron. J. 69 (1964), 73-79
  — Fig. 4 is the canonical reference image this module reproduces
  for the Hénon-Heiles default IC.
- S. H. Strogatz, *Nonlinear Dynamics and Chaos* (2nd ed., 2015),
  §12.5 — Poincaré-section construction; §8.5 covers the
  stroboscopic-section specialisation used in forced systems.
- E. Ott, *Chaos in Dynamical Systems* (2nd ed., 2002), §6.5 — the
  Hénon-Heiles section as a window into mixed phase space.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:  # pragma: no cover - import only for type hints
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

# Tokyo-Night accent shared across panels. The basin plot uses ``#7aa2f7``
# for its label background; we use the same hex for crossings so the
# section + basin + phase panels feel like one family.
_DEFAULT_COLOR: str = "#7aa2f7"
_DEFAULT_FIGSIZE: tuple[float, float] = (6.5, 6.0)
_DEFAULT_DPI: int = 120
_DEFAULT_MARKER_SIZE: float = 4.0
_DEFAULT_ALPHA: float = 0.75
# Tokyo-Night foreground for axis decorations on a dark facecolor.
_DARK_LABEL_COLOR: str = "#c0caf5"
_DARK_SPINE_COLOR: str = "#a9b1d6"


def _extract_y(crossings: Any) -> np.ndarray:
    """Read ``crossings.y`` and coerce to a ``(N, state_dim)`` array.

    Accepts a :class:`~chaotic_systems.core.Trajectory` or any
    duck-typed object exposing ``.y``. For an empty
    Poincaré-section result (no crossings within the integration
    window), returns a ``(0, state_dim)`` array.
    """
    if not hasattr(crossings, "y"):
        raise TypeError(
            "poincare-plot input must have a .y attribute; got "
            f"{type(crossings).__name__}"
        )
    arr = np.asarray(crossings.y, dtype=np.float64)
    if arr.ndim != 2:
        raise ValueError(
            f"crossings.y must be 2-D; got shape {arr.shape!r}"
        )
    return arr


def plot_poincare_section(
    crossings: Any,
    *,
    ix: int = 0,
    iy: int = 1,
    ax: Axes | None = None,
    color: str = _DEFAULT_COLOR,
    marker_size: float = _DEFAULT_MARKER_SIZE,
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
    """Render a 2D scatter of Poincaré-section crossings.

    Parameters
    ----------
    crossings
        Any object exposing ``.y`` of shape ``(N, state_dim)`` — typically
        a :class:`~chaotic_systems.core.Trajectory` returned by
        :func:`~chaotic_systems.core.poincare.poincare_section`. Each
        row is the full state at one section crossing.
    ix, iy
        State-vector indices to project onto. Must be distinct and in
        ``[0, state_dim)``. By convention the section-axis index is
        *excluded* (its value is constant by construction); for
        Hénon-Heiles with normal ``e_x``, ``(ix, iy) = (1, 3)`` gives
        the canonical ``(y, p_y)`` view.
    ax
        Optional pre-existing :class:`matplotlib.axes.Axes`. If ``None``
        a fresh figure + axes pair is built (Agg backend, thread-safe).
    color, marker_size, alpha
        Scatter styling. Defaults match the Tokyo-Night palette used
        elsewhere in the GUI.
    figsize, dpi
        Used only when ``ax is None``.
    title
        Plot title. Defaults to ``"<system> Poincaré section"`` when
        ``crossings.system`` is set.
    xlabel, ylabel
        Axis labels. If not supplied, default to ``axes_labels[ix]``
        / ``axes_labels[iy]`` when provided, otherwise to
        ``"y[ix]"`` / ``"y[iy]"``.
    axes_labels
        Optional per-state-component labels (length ``state_dim``).
        E.g. ``("x", "y", "p_x", "p_y")`` for Hénon-Heiles.
    facecolor
        Optional figure / axes background colour. Pass a dark hex
        string to match the embedded Tokyo-Night panel; leave as
        ``None`` for saved figures.
    equal_aspect
        If ``True``, force ``ax.set_aspect("equal")``. Useful when
        the two projected axes carry comparable physical meaning
        (Hénon-Heiles ``(y, p_y)``, area-preserving maps); off by
        default so wide-range chaotic seas stay readable.

    Returns
    -------
    Figure
        The matplotlib figure carrying the rendered scatter.

    Raises
    ------
    TypeError
        If ``crossings`` does not expose ``.y``.
    ValueError
        If ``ix == iy``, or either index is out of range, or
        ``crossings.y`` is not 2-D.
    """
    if int(ix) == int(iy):
        raise ValueError(
            f"ix and iy must be distinct (got ix={ix!r}, iy={iy!r})"
        )

    arr = _extract_y(crossings)
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

    # Same Agg-default rationale as phase_plot.py / basin_plot.py: this
    # routine is safe to call from a worker thread before any Qt event
    # loop has spun up. The GUI panel re-binds a Qt canvas afterwards.
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
            spine.set_edgecolor(_DARK_SPINE_COLOR)
        ax_local.tick_params(colors=_DARK_SPINE_COLOR)
        ax_local.xaxis.label.set_color(_DARK_LABEL_COLOR)
        ax_local.yaxis.label.set_color(_DARK_LABEL_COLOR)
        ax_local.title.set_color(_DARK_LABEL_COLOR)

    if n > 0:
        ax_local.scatter(
            xs,
            ys,
            s=marker_size,
            c=color,
            alpha=alpha,
            edgecolors="none",
        )
    else:
        # Empty-result safety: render an explicit annotation so the user
        # sees why the canvas is blank rather than guessing.
        ax_local.text(
            0.5,
            0.5,
            "no crossings within t_span",
            transform=ax_local.transAxes,
            ha="center",
            va="center",
            color=_DARK_LABEL_COLOR if facecolor is not None else "0.3",
        )

    def _resolve_label(explicit: str | None, idx: int) -> str:
        if explicit is not None:
            return explicit
        if axes_labels is not None and 0 <= idx < len(axes_labels):
            return str(axes_labels[idx])
        return f"y[{idx}]"

    ax_local.set_xlabel(_resolve_label(xlabel, int(ix)))
    ax_local.set_ylabel(_resolve_label(ylabel, int(iy)))

    system_name = getattr(crossings, "system", "") or "trajectory"
    ax_local.set_title(
        title if title is not None else f"{system_name} Poincaré section"
    )
    ax_local.grid(True, alpha=0.15, linewidth=0.5)
    if equal_aspect:
        ax_local.set_aspect("equal", adjustable="datalim")
    fig.tight_layout()
    return fig


__all__ = ["plot_poincare_section"]
