"""Tests for the 2D phase-portrait GUI panel.

GUI tests inherit the ``CHAOTIC_GUI_TESTS_USE_DISPLAY`` gate from
``tests/gui/conftest.py``.

We pin:

- The panel constructs against a 2-D-or-higher trajectory and exposes
  axis combos / equal-aspect / plot button / status / canvas widgets.
- The combos are seeded with one entry per state-vector component
  carrying the corresponding label.
- Re-selecting axes triggers a re-plot via ``_refresh``.
- The panel rejects state_dim < 2.
- The dialog wraps the panel and is constructed by the toolbar slot.
- The main-window toolbar exposes ``action_phase_portrait`` and it
  starts disabled until a trajectory exists.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")


def _make_trajectory(state_dim: int = 3, n: int = 50) -> object:
    """Build a duck-typed trajectory sufficient for the phase panel."""

    class _Stub:
        pass

    stub = _Stub()
    t = np.linspace(0.0, 1.0, n)
    # Sinusoidal columns so the (x, y) projection is non-degenerate.
    cols = [np.sin(t + i * 0.5) for i in range(state_dim)]
    stub.y = np.column_stack(cols)
    stub.t = t
    stub.system = "Stub"
    stub.state_dim = state_dim
    return stub


def _panel_cls():
    from chaotic_systems.gui.phase_panel import PhasePanel

    return PhasePanel


def _make_panel(qtbot, state_dim: int = 3):  # type: ignore[no-untyped-def]
    Panel = _panel_cls()
    panel = Panel(_make_trajectory(state_dim=state_dim))
    qtbot.addWidget(panel)
    return panel


def test_panel_controls_exist(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    assert panel.x_axis_box.objectName() == "phase_x_axis"
    assert panel.y_axis_box.objectName() == "phase_y_axis"
    assert panel.equal_aspect_box.objectName() == "phase_equal_aspect"
    assert panel.plot_button.objectName() == "phase_plot_button"
    assert panel.status_label.objectName() == "phase_status"
    assert panel.canvas.objectName() == "phase_canvas"


def test_axis_combos_carry_one_entry_per_state_component(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot, state_dim=4)
    assert panel.x_axis_box.count() == 4
    assert panel.y_axis_box.count() == 4
    # Default selection is (0, 1).
    assert panel.x_axis_box.currentData() == 0
    assert panel.y_axis_box.currentData() == 1


def test_panel_uses_supplied_axes_labels(qtbot) -> None:  # type: ignore[no-untyped-def]
    Panel = _panel_cls()
    panel = Panel(
        _make_trajectory(state_dim=3),
        axes_labels=("x", "y", "z"),
    )
    qtbot.addWidget(panel)
    assert "x" in panel.x_axis_box.itemText(0)
    assert "y" in panel.x_axis_box.itemText(1)
    assert "z" in panel.x_axis_box.itemText(2)


def test_changing_axes_triggers_refresh(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot, state_dim=3)
    canvas_before = panel.canvas
    panel.y_axis_box.setCurrentIndex(2)  # switch from y[1] to y[2]
    # The canvas widget is recreated on every refresh; the new one
    # should not be the same Python object.
    assert panel.canvas is not canvas_before
    # Status label echoes the new axis pair.
    assert "y[0]" in panel.status_label.text()
    assert "y[2]" in panel.status_label.text()


def test_same_axis_pair_surfaces_status_message(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot, state_dim=3)
    canvas_before = panel.canvas
    # Force both combos to the same index.
    panel.y_axis_box.setCurrentIndex(0)
    assert "must differ" in panel.status_label.text()
    # The canvas was *not* swapped (the refresh aborted).
    assert panel.canvas is canvas_before


def test_panel_rejects_1d_trajectory() -> None:
    Panel = _panel_cls()

    class _Stub1D:
        state_dim = 1
        y = np.zeros((10, 1))
        system = "stub-1d"

    with pytest.raises(ValueError, match="state_dim >= 2"):
        Panel(_Stub1D())


def test_set_trajectory_swaps_snapshot(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot, state_dim=3)
    new = _make_trajectory(state_dim=3, n=20)
    new.system = "Replaced"  # type: ignore[attr-defined]
    canvas_before = panel.canvas
    panel.set_trajectory(new, system_name="Replaced")
    assert panel.canvas is not canvas_before


def test_set_trajectory_rebuilds_combos_when_dim_changes(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot, state_dim=3)
    assert panel.x_axis_box.count() == 3
    panel.set_trajectory(_make_trajectory(state_dim=4))
    assert panel.x_axis_box.count() == 4
    assert panel.state_dim == 4


def test_dialog_wraps_panel(qtbot) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtWidgets import QWidget

    from chaotic_systems.gui.phase_panel import build_phase_dialog

    dialog = build_phase_dialog(
        _make_trajectory(state_dim=3), axes_labels=("x", "y", "z")
    )
    qtbot.addWidget(dialog)
    assert dialog.objectName() == "phase_dialog"
    # Embedded canvas is discoverable.
    canvas = dialog.findChild(QWidget, "phase_canvas")
    assert canvas is not None
    # Panel handle is exposed for scripted callers.
    assert dialog.phase_panel is not None


def test_main_window_exposes_disabled_phase_action_initially(qtbot) -> None:  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)
    actions = window.transport_actions()
    assert "action_phase_portrait" in actions
    action = actions["action_phase_portrait"]
    # Disabled until a simulation has run and produced a trajectory.
    assert action.isEnabled() is False
    assert "Phase portrait" in action.text()


def test_phase_action_enables_after_sim_finished(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Drive the same path the simulate-worker takes — the action lights up."""
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)
    traj = _make_trajectory(state_dim=3)
    window._on_sim_finished(traj)  # noqa: SLF001
    action = window.transport_actions()["action_phase_portrait"]
    assert action.isEnabled() is True


def test_phase_action_stays_disabled_for_1d_trajectory(qtbot) -> None:  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)

    class _Stub1D:
        state_dim = 1
        y = np.zeros((10, 1))
        t = np.arange(10, dtype=float)
        system = "stub"

    window._on_sim_finished(_Stub1D())  # noqa: SLF001
    action = window.transport_actions()["action_phase_portrait"]
    assert action.isEnabled() is False
