"""Smoke tests for the matplotlib basin-plot helper.

Pure-Agg rendering, no display needed. We verify:

- ``plot_basin`` returns a ``Figure`` with one axes carrying an
  ``imshow`` and (optionally) attractor-marker scatter / legend.
- Axes labels and title default to sensible values pulled from the
  diagram.
- The imshow's extent matches the diagram's axis ranges.
- ``facecolor`` styles figure + axes.
- Unclassified pixels render as the neutral gray; supplying a custom
  palette is honored.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.core.basins import UNCLASSIFIED_LABEL, BasinDiagram
from chaotic_systems.visualization.basin_plot import plot_basin


def _make_diagram(n_x: int = 6, n_y: int = 6) -> BasinDiagram:
    """A small toy diagram for shape tests."""
    labels = np.empty((n_y, n_x), dtype=np.int64)
    for i in range(n_y):
        for j in range(n_x):
            # Left half = 0, right half = 1, with a strip of unclassified
            # along the centre column.
            if j < n_x // 2 - 1:
                labels[i, j] = 0
            elif j > n_x // 2:
                labels[i, j] = 1
            else:
                labels[i, j] = UNCLASSIFIED_LABEL
    return BasinDiagram(
        x_axis=(0, -2.0, 2.0),
        y_axis=(1, -2.0, 2.0),
        n_grid=(n_x, n_y),
        labels=labels,
        attractor_labels=["left", "right"],
        attractor_points=np.array([[-1.0, 0.0], [1.0, 0.0]]),
        fixed_state=np.array([0.0, 0.0]),
        system_name="ToyWell",
    )


def test_returns_figure_with_imshow_and_markers() -> None:
    from matplotlib.figure import Figure

    diag = _make_diagram()
    fig = plot_basin(diag)
    assert isinstance(fig, Figure)
    ax = fig.axes[0]
    # imshow returns an AxesImage which lives in ax.images.
    assert len(ax.images) == 1
    # Two attractor stars on top.
    assert len(ax.collections) == 2


def test_imshow_extent_matches_axis_ranges() -> None:
    diag = _make_diagram()
    fig = plot_basin(diag)
    extent = fig.axes[0].images[0].get_extent()
    np.testing.assert_allclose(extent, (-2.0, 2.0, -2.0, 2.0))


def test_titles_and_labels_default_to_diagram_metadata() -> None:
    diag = _make_diagram()
    fig = plot_basin(diag)
    ax = fig.axes[0]
    assert "ToyWell" in ax.get_title()
    assert ax.get_xlabel() == "y[0]"
    assert ax.get_ylabel() == "y[1]"


def test_axes_labels_tuple_overrides_defaults() -> None:
    diag = _make_diagram()
    fig = plot_basin(diag, axes_labels=("x", "v"))
    ax = fig.axes[0]
    assert ax.get_xlabel() == "x"
    assert ax.get_ylabel() == "v"


def test_facecolor_applied_to_figure_and_axes() -> None:
    diag = _make_diagram()
    fig = plot_basin(diag, facecolor="#24283b")
    ax = fig.axes[0]
    np.testing.assert_allclose(
        fig.get_facecolor()[:3], (36 / 255, 40 / 255, 59 / 255), atol=1e-2
    )
    np.testing.assert_allclose(
        ax.get_facecolor()[:3], (36 / 255, 40 / 255, 59 / 255), atol=1e-2
    )


def test_custom_palette_honored() -> None:
    from matplotlib.colors import to_rgba

    diag = _make_diagram()
    fig = plot_basin(diag, palette=["#ff0000", "#00ff00"])
    # The colormap of the AxesImage should carry our custom hex. ListedColormap
    # stores colors as the strings the user passed in (or RGBA tuples); convert
    # via matplotlib.colors.to_rgba so the test is colorspec-agnostic.
    ax = fig.axes[0]
    cmap = ax.images[0].get_cmap()
    # Unclassified gray sits at index 0, our two attractor colors at 1 and 2.
    np.testing.assert_allclose(
        to_rgba(cmap.colors[1])[:3], (1.0, 0.0, 0.0), atol=1e-6
    )
    np.testing.assert_allclose(
        to_rgba(cmap.colors[2])[:3], (0.0, 1.0, 0.0), atol=1e-6
    )


def test_show_legend_can_be_disabled() -> None:
    diag = _make_diagram()
    fig = plot_basin(diag, show_legend=False)
    assert fig.axes[0].get_legend() is None


def test_show_attractor_markers_can_be_disabled() -> None:
    diag = _make_diagram()
    fig = plot_basin(diag, show_attractor_markers=False)
    assert len(fig.axes[0].collections) == 0


def test_empty_palette_rejected() -> None:
    diag = _make_diagram()
    with pytest.raises(ValueError, match="at least one color"):
        plot_basin(diag, palette=[])
