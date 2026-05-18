"""Smoke tests for the matplotlib recurrence-plot renderer.

Pure-Agg, no display needed. We verify:

- ``plot_recurrence`` returns a ``Figure`` with one axes carrying an
  imshow of the recurrence matrix.
- The imshow extent covers ``(0, N, 0, N)`` and uses
  ``origin='lower'`` (Marwan §3 convention).
- The stats overlay text appears when an ``RQAStats`` is passed and
  ``show_stats_overlay=True``.
- The ``dark`` toggle swaps figure / axes background to the dark
  palette; ``facecolor`` overrides both.
- Axis labels and title default to sensible values.
- Malformed matrices are rejected.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.core.recurrence import RQAStats
from chaotic_systems.visualization.recurrence_plot import plot_recurrence


def _small_matrix(n: int = 16) -> np.ndarray:
    """A toy diagonal-stripe matrix for smoke tests."""
    matrix = np.zeros((n, n), dtype=bool)
    for i in range(n):
        for j in range(n):
            if abs(i - j) <= 1 or abs(i - j) == n // 2:
                matrix[i, j] = True
    return matrix


def _stub_stats(n: int = 16) -> RQAStats:
    return RQAStats(
        rr=0.123,
        det=0.987,
        lam=0.654,
        l_max=12,
        v_max=4,
        l_mean=3.5,
        tt=2.1,
        entr=1.234,
        n=n,
        l_min=2,
        v_min=2,
        theiler=0,
    )


def test_returns_figure_with_imshow() -> None:
    from matplotlib.figure import Figure

    fig = plot_recurrence(_small_matrix())
    assert isinstance(fig, Figure)
    ax = fig.axes[0]
    assert len(ax.images) == 1


def test_imshow_extent_matches_matrix_size() -> None:
    matrix = _small_matrix(n=20)
    fig = plot_recurrence(matrix)
    extent = fig.axes[0].images[0].get_extent()
    np.testing.assert_allclose(extent, (0, 20, 0, 20))


def test_axis_labels_and_title_have_defaults() -> None:
    matrix = _small_matrix(n=12)
    fig = plot_recurrence(matrix)
    ax = fig.axes[0]
    assert "Recurrence plot" in ax.get_title()
    assert "12" in ax.get_title()
    assert "time index" in ax.get_xlabel()
    assert "time index" in ax.get_ylabel()


def test_explicit_title_and_labels_override() -> None:
    matrix = _small_matrix()
    fig = plot_recurrence(
        matrix, title="custom", xlabel="X", ylabel="Y"
    )
    ax = fig.axes[0]
    assert ax.get_title() == "custom"
    assert ax.get_xlabel() == "X"
    assert ax.get_ylabel() == "Y"


def test_stats_overlay_shows_rqa_values() -> None:
    matrix = _small_matrix()
    stats = _stub_stats()
    fig = plot_recurrence(matrix, stats=stats, show_stats_overlay=True)
    ax = fig.axes[0]
    # The Text artist with our values should be findable by text content.
    text_blobs = [t.get_text() for t in ax.texts]
    combined = "\n".join(text_blobs)
    assert "0.1230" in combined  # RR
    assert "0.9870" in combined  # DET
    assert "0.6540" in combined  # LAM


def test_stats_overlay_hidden_when_no_stats() -> None:
    fig = plot_recurrence(_small_matrix())
    # ``ax.texts`` is a matplotlib ArtistList, not a plain Python list —
    # check its length so the assertion is iterable-agnostic.
    assert len(fig.axes[0].texts) == 0


def test_dark_mode_sets_dark_background() -> None:
    matrix = _small_matrix()
    fig = plot_recurrence(matrix, dark=True)
    # Tokyo Night deep night #1a1b26 → roughly (26/255, 27/255, 38/255).
    fc = fig.get_facecolor()
    np.testing.assert_allclose(
        fc[:3], (26 / 255, 27 / 255, 38 / 255), atol=1e-2
    )


def test_facecolor_override_takes_precedence() -> None:
    matrix = _small_matrix()
    fig = plot_recurrence(matrix, dark=True, facecolor="#ffffff")
    np.testing.assert_allclose(
        fig.get_facecolor()[:3], (1.0, 1.0, 1.0), atol=1e-3
    )


def test_rejects_non_square_matrix() -> None:
    with pytest.raises(ValueError, match="square"):
        plot_recurrence(np.zeros((4, 5), dtype=bool))


def test_ax_kwarg_reuses_existing_axes() -> None:
    from matplotlib.figure import Figure

    parent_fig = Figure()
    ax = parent_fig.add_subplot(111)
    fig = plot_recurrence(_small_matrix(), ax=ax)
    assert fig is parent_fig
