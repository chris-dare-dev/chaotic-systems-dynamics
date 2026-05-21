"""Tests for the conservation-overlay GUI panel (V3).

GUI tests inherit the ``CHAOTIC_GUI_TESTS_USE_DISPLAY`` gate from
``tests/gui/conftest.py``.

We pin:

- Panel controls exist with stable object names.
- Constructing a panel against a HenonHeiles yoshida4 trajectory
  records a tight (|ΔE|_max < 1e-5) drift number that the tests can
  introspect via ``last_max_drift``.
- ``system_has_energy`` returns True for the three Hamiltonian /
  Lagrangian systems and False for others.
- The main-window toolbar exposes ``action_conservation``, disabled
  at startup; it enables after a Run if the current system has an
  ``.energy`` method.
- The dialog wraps the panel.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")


def _hh_yoshida_traj(t_end: float = 10.0, dt: float = 0.05):
    from chaotic_systems.systems import HenonHeiles

    hh = HenonHeiles()
    return hh.simulate((0.0, t_end), dt=dt, integrator="yoshida4")


def _make_panel(qtbot, traj=None, energy_fn=None):  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.conservation_panel import ConservationPanel
    from chaotic_systems.systems import HenonHeiles

    if traj is None:
        traj = _hh_yoshida_traj()
    if energy_fn is None:
        hh = HenonHeiles()
        energy_fn = hh.energy
    panel = ConservationPanel(traj, energy_fn)
    qtbot.addWidget(panel)
    return panel


def test_panel_controls_exist(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    assert panel.title_label.objectName() == "conservation_title"
    assert panel.canvas.objectName() == "conservation_canvas"
    assert panel.status_label.objectName() == "conservation_status"


def test_panel_records_tight_drift_for_yoshida4_on_henon_heiles(qtbot) -> None:  # type: ignore[no-untyped-def]
    """The GUI surface of the headline observable."""
    panel = _make_panel(qtbot, traj=_hh_yoshida_traj(t_end=20.0, dt=0.05))
    assert panel.max_drift() < 1e-6


def test_panel_status_label_shows_e0_and_drift(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    text = panel.status_label.text()
    assert "E(0)" in text
    assert "|ΔE|_max" in text


def test_system_has_energy_for_canonical_systems() -> None:
    from chaotic_systems.gui.conservation_panel import system_has_energy
    from chaotic_systems.systems import (
        DoublePendulum,
        Duffing,
        HenonHeiles,
        Logistic,
        Lorenz,
    )

    assert system_has_energy(HenonHeiles()) is True
    assert system_has_energy(DoublePendulum()) is True
    assert system_has_energy(Duffing()) is True
    # Lorenz / Logistic / etc. do not carry an energy method.
    assert system_has_energy(Lorenz()) is False
    assert system_has_energy(Logistic()) is False


def test_panel_rejects_input_without_t_or_y() -> None:
    from chaotic_systems.gui.conservation_panel import ConservationPanel

    class _NoTraj:
        pass

    with pytest.raises(TypeError, match=".t and .y"):
        ConservationPanel(_NoTraj(), lambda y: 0.0)


def test_panel_rejects_short_trajectory() -> None:
    from chaotic_systems.gui.conservation_panel import ConservationPanel

    class _Stub:
        t = np.array([0.0])
        y = np.zeros((1, 2))
        system = "stub"

    with pytest.raises(ValueError, match="N>=2"):
        ConservationPanel(_Stub(), lambda y: 0.0)


def test_panel_subsamples_long_trajectories(qtbot) -> None:  # type: ignore[no-untyped-def]
    """N > _MAX_PLOT_N → uniformly subsampled to the cap."""
    from chaotic_systems.gui.conservation_panel import _MAX_PLOT_N

    class _Stub:
        pass

    n = _MAX_PLOT_N * 3
    stub = _Stub()
    stub.t = np.linspace(0.0, 10.0, n)
    stub.y = np.column_stack([np.sin(stub.t), np.cos(stub.t)])
    stub.system = "Subsample-test"
    panel = _make_panel(
        qtbot,
        traj=stub,
        energy_fn=lambda y: float(0.5 * (y[0] ** 2 + y[1] ** 2)),
    )
    # The subsampled trajectory exposed on the panel has at most
    # _MAX_PLOT_N rows.
    assert panel._traj.y.shape[0] <= _MAX_PLOT_N  # noqa: SLF001


def test_dialog_wraps_panel(qtbot) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtWidgets import QWidget

    from chaotic_systems.gui.conservation_panel import build_conservation_dialog
    from chaotic_systems.systems import HenonHeiles

    hh = HenonHeiles()
    dialog = build_conservation_dialog(_hh_yoshida_traj(t_end=5.0), hh.energy)
    qtbot.addWidget(dialog)
    assert dialog.objectName() == "conservation_dialog"
    canvas = dialog.findChild(QWidget, "conservation_canvas")
    assert canvas is not None
    assert dialog.conservation_panel is not None


def test_main_window_exposes_disabled_conservation_action_initially(qtbot) -> None:  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)
    actions = window.transport_actions()
    assert "action_conservation" in actions
    action = actions["action_conservation"]
    # Disabled at startup — no trajectory yet, and gating also checks
    # for .energy() on the system.
    assert action.isEnabled() is False
    assert "Conservation" in action.text() or "conservation" in action.text().lower()


def test_conservation_action_enables_for_hamiltonian_system(qtbot) -> None:  # type: ignore[no-untyped-def]
    """When current_system has .energy(), the action lights up post-Run."""
    from chaotic_systems.gui.main_window import _build_window_class
    from chaotic_systems.systems import HenonHeiles

    Window = _build_window_class()
    # Restrict the GUI's registered systems to a single Hamiltonian
    # entry so current_system is reliably one we know.
    hh = HenonHeiles()
    window = Window(systems=[hh])
    qtbot.addWidget(window)
    traj = hh.simulate((0.0, 5.0), dt=0.05, integrator="yoshida4")
    window._on_sim_finished(traj)  # noqa: SLF001
    action = window.transport_actions()["action_conservation"]
    assert action.isEnabled() is True


def test_conservation_action_disabled_for_non_energy_system(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Lorenz has no .energy() → the action must stay disabled even
    after a successful Run."""
    from chaotic_systems.gui.main_window import _build_window_class
    from chaotic_systems.systems import Lorenz

    Window = _build_window_class()
    lor = Lorenz()
    window = Window(systems=[lor])
    qtbot.addWidget(window)
    traj = lor.simulate((0.0, 2.0), n_points=50, integrator="DOP853")
    window._on_sim_finished(traj)  # noqa: SLF001
    action = window.transport_actions()["action_conservation"]
    assert action.isEnabled() is False
