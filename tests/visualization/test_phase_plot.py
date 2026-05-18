"""Smoke + reference tests for the 2D phase-portrait helper.

Reference observable
--------------------
For a harmonic oscillator ``y_dot = [v, -omega^2 x]`` with
``omega = 1``, IC ``(1, 0)``, the trajectory is ``(cos t, -sin t)``
and the ``(x, v)`` phase portrait is a unit circle (Strogatz §6.1,
Fig 6.1.1). After many periods every sampled point satisfies
``x^2 + v^2 = 1`` to integrator tolerance — the test below pins
``max(|r - 1|) < 5e-4`` on a default RK45 run.

The remaining tests pin axis validation, custom labels, the
``equal_aspect`` toggle, and the Tokyo-Night facecolor.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.core import DynamicalSystem, Parameter
from chaotic_systems.visualization.phase_plot import plot_phase_portrait


class _Harmonic(DynamicalSystem):
    """y_dot = [v, -omega^2 x] — classical harmonic oscillator."""

    name = "Harmonic"
    latex = r"\dot y = A y"
    state_dim = 2
    parameters = {"omega": Parameter("omega", 1.0, 0.0, 10.0)}
    default_initial_state = np.array([1.0, 0.0], dtype=np.float64)

    def _rhs(self, t, y, params):
        w = params["omega"]
        return np.array([y[1], -w * w * y[0]], dtype=np.float64)


def _harmonic_traj():
    return _Harmonic().simulate(
        (0.0, 4.0 * np.pi),
        n_points=400,
        integrator="RK45",
        rtol=1e-9,
        atol=1e-12,
    )


def test_harmonic_phase_portrait_is_a_unit_circle() -> None:
    """``x^2 + v^2 = 1`` along every sample — the canonical Strogatz Fig 6.1.1."""
    traj = _harmonic_traj()
    radii = np.sqrt(traj.y[:, 0] ** 2 + traj.y[:, 1] ** 2)
    assert np.max(np.abs(radii - 1.0)) < 5e-4


def test_returns_figure_with_line_and_marker() -> None:
    from matplotlib.figure import Figure

    traj = _harmonic_traj()
    fig = plot_phase_portrait(traj, ix=0, iy=1)
    assert isinstance(fig, Figure)
    ax = fig.axes[0]
    # The trajectory line + the start marker = 2 Line2D entries.
    assert len(ax.lines) == 2
    # The line's data length matches the trajectory.
    xs, ys = ax.lines[0].get_data()
    assert xs.shape == traj.y[:, 0].shape
    np.testing.assert_array_equal(xs, traj.y[:, 0])
    np.testing.assert_array_equal(ys, traj.y[:, 1])


def test_axes_labels_default_to_index_strings() -> None:
    traj = _harmonic_traj()
    fig = plot_phase_portrait(traj, ix=0, iy=1)
    ax = fig.axes[0]
    assert ax.get_xlabel() == "y[0]"
    assert ax.get_ylabel() == "y[1]"
    assert "Harmonic phase portrait" in ax.get_title()


def test_axes_labels_pulled_from_tuple() -> None:
    traj = _harmonic_traj()
    fig = plot_phase_portrait(
        traj, ix=0, iy=1, axes_labels=("x", "v"),
    )
    ax = fig.axes[0]
    assert ax.get_xlabel() == "x"
    assert ax.get_ylabel() == "v"


def test_explicit_xlabel_ylabel_override_tuple() -> None:
    traj = _harmonic_traj()
    fig = plot_phase_portrait(
        traj,
        ix=0,
        iy=1,
        axes_labels=("x", "v"),
        xlabel="position",
        ylabel="velocity",
    )
    ax = fig.axes[0]
    assert ax.get_xlabel() == "position"
    assert ax.get_ylabel() == "velocity"


def test_equal_aspect_sets_aspect_to_equal() -> None:
    traj = _harmonic_traj()
    fig = plot_phase_portrait(traj, ix=0, iy=1, equal_aspect=True)
    ax = fig.axes[0]
    assert ax.get_aspect() == 1.0  # matplotlib stores "equal" as 1.0


def test_facecolor_applied_to_figure_and_axes() -> None:
    traj = _harmonic_traj()
    fig = plot_phase_portrait(traj, ix=0, iy=1, facecolor="#24283b")
    ax = fig.axes[0]
    np.testing.assert_allclose(
        fig.get_facecolor()[:3], (36 / 255, 40 / 255, 59 / 255), atol=1e-2
    )
    np.testing.assert_allclose(
        ax.get_facecolor()[:3], (36 / 255, 40 / 255, 59 / 255), atol=1e-2
    )


def test_rejects_duplicate_axes() -> None:
    traj = _harmonic_traj()
    with pytest.raises(ValueError, match="distinct"):
        plot_phase_portrait(traj, ix=0, iy=0)


def test_rejects_out_of_range_index() -> None:
    traj = _harmonic_traj()
    with pytest.raises(ValueError, match="out of range"):
        plot_phase_portrait(traj, ix=0, iy=5)
    with pytest.raises(ValueError, match="out of range"):
        plot_phase_portrait(traj, ix=-1, iy=0)


def test_rejects_object_without_y() -> None:
    class _NoY:
        state = "I have no y"

    with pytest.raises(TypeError, match=".y attribute"):
        plot_phase_portrait(_NoY())


def test_accepts_raw_duck_typed_trajectory() -> None:
    """Anything with .y of shape (N, state_dim) is acceptable input."""

    class _Stub:
        state_dim = 2
        system = "Stub"
        y = np.array([[0.0, 1.0], [1.0, 0.0], [0.0, -1.0], [-1.0, 0.0]])

    fig = plot_phase_portrait(_Stub(), ix=0, iy=1)
    assert "Stub" in fig.axes[0].get_title()


def test_2d_array_transposed_when_state_dim_matches_first_axis() -> None:
    """The contract layer convention: ``(state_dim, N)`` is also accepted."""

    class _Stub:
        state_dim = 2
        system = "stub"
        # First axis matches state_dim → contract layer treats this as (state_dim, N).
        y = np.array([[0.0, 1.0, 0.0, -1.0], [1.0, 0.0, -1.0, 0.0]])

    fig = plot_phase_portrait(_Stub(), ix=0, iy=1)
    ax = fig.axes[0]
    xs, _ = ax.lines[0].get_data()
    # After auto-transpose, x-axis is the first row (0, 1, 0, -1).
    np.testing.assert_array_equal(xs, np.array([0.0, 1.0, 0.0, -1.0]))


def test_ax_kwarg_reuses_existing_axes() -> None:
    from matplotlib.figure import Figure

    traj = _harmonic_traj()
    parent_fig = Figure()
    ax = parent_fig.add_subplot(111)
    fig = plot_phase_portrait(traj, ax=ax, ix=0, iy=1)
    assert fig is parent_fig
