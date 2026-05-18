"""Smoke tests for the matplotlib bifurcation-plot helper.

Pure-Agg rendering, no display required. We verify:

- ``plot_bifurcation`` returns a ``matplotlib.figure.Figure`` with one
  axes carrying a single scatter collection.
- The scatter holds ``M * n_record`` points (the full sweep).
- Axes labels are set from the diagram's metadata.
- Passing an existing ``ax=`` reuses it instead of building a new figure.
- ``facecolor=`` applies to the figure / axes backgrounds.
"""

from __future__ import annotations

import numpy as np

from chaotic_systems.core.bifurcation import bifurcation_diagram
from chaotic_systems.systems import HenonMap, Logistic
from chaotic_systems.visualization.bifurcation_plot import plot_bifurcation


def _logistic_diagram(m: int = 6, n_record: int = 8):
    sys = Logistic()
    rs = np.linspace(3.0, 4.0, m)
    return bifurcation_diagram(sys, "r", rs, n_record=n_record, n_transient=30)


def test_returns_figure_with_scatter() -> None:
    from matplotlib.figure import Figure

    diag = _logistic_diagram()
    fig = plot_bifurcation(diag)
    assert isinstance(fig, Figure)
    assert len(fig.axes) == 1
    ax = fig.axes[0]
    # One scatter collection.
    assert len(ax.collections) == 1
    pts = ax.collections[0].get_offsets()
    assert pts.shape == (diag.n_values * diag.n_record, 2)


def test_axes_labels_carry_diagram_metadata() -> None:
    diag = _logistic_diagram()
    fig = plot_bifurcation(diag)
    ax = fig.axes[0]
    assert ax.get_xlabel() == "r"
    # state_dim == 1 → ylabel is "x"
    assert ax.get_ylabel() == "x"
    assert "Logistic" in ax.get_title()


def test_2d_map_default_projection_labels_y0() -> None:
    sys = HenonMap()
    diag = bifurcation_diagram(
        sys, "a", np.linspace(1.0, 1.4, 4), n_record=5, n_transient=20
    )
    fig = plot_bifurcation(diag, projection=1)
    ax = fig.axes[0]
    assert ax.get_ylabel() == "y[1]"


def test_ax_kwarg_reuses_existing_axes() -> None:
    from matplotlib.figure import Figure

    diag = _logistic_diagram()
    parent_fig = Figure()
    ax = parent_fig.add_subplot(111)
    fig = plot_bifurcation(diag, ax=ax)
    # We reused the parent figure, not built a new one.
    assert fig is parent_fig
    assert len(parent_fig.axes) == 1


def test_facecolor_applied_to_figure_and_axes() -> None:
    diag = _logistic_diagram()
    fig = plot_bifurcation(diag, facecolor="#24283b")
    ax = fig.axes[0]
    # matplotlib returns RGBA tuples in 0-1 range.
    fc = fig.get_facecolor()
    ac = ax.get_facecolor()
    # Tokyo Night background ≈ (36/255, 40/255, 59/255, 1).
    np.testing.assert_allclose(fc[:3], (36 / 255, 40 / 255, 59 / 255), atol=1e-2)
    np.testing.assert_allclose(ac[:3], (36 / 255, 40 / 255, 59 / 255), atol=1e-2)
