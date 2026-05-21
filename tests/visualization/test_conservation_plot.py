"""Tests for the conservation-overlay plot helper (V3).

Headline observable: integrating Hénon-Heiles at its canonical IC
with the **symplectic** ``yoshida4`` integrator at ``dt = 0.05``
over ``t = 50`` keeps the relative energy drift ``|ΔE| / |E₀|``
below 1e-5 — the textbook payoff of symplectic methods
(Hairer-Lubich-Wanner 2006 §V).

The remaining tests pin the plot's contract: Figure shape, axis
labels, reference-line at ΔE = 0, drift annotation, Tokyo Night
facecolor, custom-color override, and validation of malformed
inputs.
"""

from __future__ import annotations

import numpy as np
import pytest

from chaotic_systems.systems import DoublePendulum, Duffing, HenonHeiles
from chaotic_systems.visualization.conservation_plot import plot_conservation


def _hh_yoshida_traj(t_end: float = 50.0, dt: float = 0.05):
    """Symplectic-integrator Hénon-Heiles trajectory."""
    hh = HenonHeiles()
    return hh.simulate((0.0, t_end), dt=dt, integrator="yoshida4")


# --- Reference observable: yoshida4 preserves HH energy ---------------


def test_yoshida4_holds_henon_heiles_energy_drift_below_1e_minus_5() -> None:
    """The signature observable. Hairer-Lubich-Wanner §V: symplectic
    integrators bound the energy error uniformly in time."""
    hh = HenonHeiles()
    traj = _hh_yoshida_traj(t_end=50.0, dt=0.05)
    e0 = hh.energy(traj.y[0])
    drift = max(abs(hh.energy(y) - e0) for y in traj.y)
    rel = drift / abs(e0)
    assert rel < 1e-5, (
        f"expected |ΔE/E₀| < 1e-5 with yoshida4 on HH over t=50; "
        f"got {rel:.4e}"
    )


def test_duffing_undriven_undamped_is_conservative() -> None:
    """With gamma = delta = 0 the Duffing oscillator is a conservative
    Hamiltonian system: E = ½v² + V(x). Any decent integrator should
    keep the drift small over moderate t."""
    duf = Duffing()
    traj = duf.simulate(
        (0.0, 50.0),
        dt=0.05,
        integrator="RK45",
        params={"gamma": 0.0, "delta": 0.0},
    )
    params = {"alpha": -1.0, "beta": 1.0, "delta": 0.0, "gamma": 0.0, "omega": 1.0}
    e0 = duf.energy(traj.y[0], params)
    drift = max(abs(duf.energy(y, params) - e0) for y in traj.y)
    denom = abs(e0) if abs(e0) > 1e-12 else 1.0
    rel = drift / denom
    assert rel < 1e-3, (
        f"expected |ΔE/E₀| < 1e-3 on undriven undamped Duffing; "
        f"got {rel:.4e}"
    )


def test_duffing_driven_shows_visible_energy_change() -> None:
    """With the default driven parameters, the energy must NOT be
    conserved — measurable drift is the whole point of the demo
    contrast vs. the undriven case."""
    duf = Duffing()
    traj = duf.simulate((0.0, 30.0), dt=0.05, integrator="RK45")
    # Use the trajectory's recorded params if present.
    params = traj.params if hasattr(traj, "params") and traj.params else duf.default_params()
    e0 = duf.energy(traj.y[0], params)
    drift = max(abs(duf.energy(y, params) - e0) for y in traj.y)
    denom = abs(e0) if abs(e0) > 1e-3 else 1.0
    rel = drift / denom
    # Any reasonable threshold above 1e-3 suffices to distinguish
    # "actively driven" from "conservative".
    assert rel > 1e-2, (
        f"expected driven Duffing to show measurable energy change; "
        f"got rel drift {rel:.4e}"
    )


# --- Plot shape contract ----------------------------------------------


def test_plot_returns_figure_with_axes() -> None:
    from matplotlib.figure import Figure

    hh = HenonHeiles()
    traj = _hh_yoshida_traj(t_end=10.0, dt=0.05)
    fig = plot_conservation(traj, hh.energy)
    assert isinstance(fig, Figure)
    assert len(fig.axes) == 1


def test_plot_contains_main_line_and_zero_axhline() -> None:
    """Exactly one trajectory line + one axhline at ΔE = 0."""
    hh = HenonHeiles()
    traj = _hh_yoshida_traj(t_end=5.0, dt=0.05)
    fig = plot_conservation(traj, hh.energy)
    ax = fig.axes[0]
    # imshow() lives in ax.images; lines/axhline both register on ax.lines.
    # Two Line2D entries: the data trajectory and the reference axhline.
    assert len(ax.lines) == 2


def test_plot_drift_annotation_shows_values() -> None:
    """The corner overlay must include the three numbers we promise."""
    hh = HenonHeiles()
    traj = _hh_yoshida_traj(t_end=10.0, dt=0.05)
    fig = plot_conservation(traj, hh.energy, show_drift_annotation=True)
    text_blobs = [t.get_text() for t in fig.axes[0].texts]
    combined = "\n".join(text_blobs)
    assert "E(0)" in combined
    assert "|ΔE|_max" in combined
    assert "|ΔE|/|E₀|" in combined


def test_plot_drift_annotation_hidden_when_disabled() -> None:
    hh = HenonHeiles()
    traj = _hh_yoshida_traj(t_end=5.0, dt=0.05)
    fig = plot_conservation(traj, hh.energy, show_drift_annotation=False)
    assert len(fig.axes[0].texts) == 0


def test_plot_default_title_uses_system_name() -> None:
    hh = HenonHeiles()
    traj = _hh_yoshida_traj(t_end=5.0, dt=0.05)
    fig = plot_conservation(traj, hh.energy)
    assert "HenonHeiles" in fig.axes[0].get_title()


def test_plot_facecolor_applied_to_figure_and_axes() -> None:
    hh = HenonHeiles()
    traj = _hh_yoshida_traj(t_end=5.0, dt=0.05)
    fig = plot_conservation(traj, hh.energy, facecolor="#24283b")
    ax = fig.axes[0]
    np.testing.assert_allclose(
        fig.get_facecolor()[:3], (36 / 255, 40 / 255, 59 / 255), atol=1e-2
    )
    np.testing.assert_allclose(
        ax.get_facecolor()[:3], (36 / 255, 40 / 255, 59 / 255), atol=1e-2
    )


def test_plot_uses_double_pendulum_energy_method() -> None:
    """The plot helper accepts any system.energy method — DoublePendulum
    is the second canonical case after HenonHeiles."""
    dp = DoublePendulum()
    traj = dp.simulate((0.0, 5.0), dt=0.01, integrator="RK45")
    # Bind default params (DP energy needs them).
    fig = plot_conservation(
        traj, lambda y: dp.energy(y, dp.default_params())
    )
    assert len(fig.axes[0].lines) == 2


# --- Validation -------------------------------------------------------


def test_plot_rejects_object_without_t_and_y() -> None:
    class _NoFields:
        pass

    with pytest.raises(TypeError, match=".t and .y"):
        plot_conservation(_NoFields(), lambda y: 0.0)


def test_plot_rejects_short_trajectory() -> None:
    class _Stub:
        t = np.array([0.0])
        y = np.zeros((1, 2))
        system = "Stub"

    with pytest.raises(ValueError, match="at least 2 samples"):
        plot_conservation(_Stub(), lambda y: 0.0)


def test_plot_rejects_mismatched_t_y_lengths() -> None:
    class _Stub:
        t = np.array([0.0, 1.0, 2.0])
        y = np.zeros((4, 2))
        system = "Stub"

    with pytest.raises(ValueError, match="length"):
        plot_conservation(_Stub(), lambda y: 0.0)


def test_plot_rejects_1d_y() -> None:
    class _Stub:
        t = np.array([0.0, 1.0, 2.0])
        y = np.array([0.0, 1.0, 2.0])  # 1-D
        system = "Stub"

    with pytest.raises(ValueError, match="2-D"):
        plot_conservation(_Stub(), lambda y: 0.0)
