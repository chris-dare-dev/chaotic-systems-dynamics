"""Tests for the recurrence-plot GUI panel (D5).

GUI tests inherit the ``CHAOTIC_GUI_TESTS_USE_DISPLAY`` gate from
``tests/gui/conftest.py``.

We pin:

- Panel controls exist with stable object names.
- Construction with a trajectory runs the initial recurrence compute
  and populates ``last_stats`` / ``last_matrix``.
- Re-pressing Compute with a different epsilon updates the cached
  stats.
- The dialog wraps the panel and is discoverable.
- The main-window toolbar exposes the ``action_recurrence`` QAction
  disabled by default; it lights up after a sim finishes.
- Long trajectories are subsampled to ``_MAX_PLOT_N``.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")


def _make_trajectory(n: int = 100, state_dim: int = 2) -> object:
    """Periodic sinusoidal trajectory — gives a non-trivial recurrence plot."""

    class _Stub:
        pass

    stub = _Stub()
    t = np.linspace(0, 4 * np.pi, n)
    stub.y = np.column_stack(
        [np.cos(t + i * 0.5) for i in range(state_dim)]
    )
    stub.t = t
    stub.system = "Stub"
    stub.state_dim = state_dim
    return stub


def _panel_cls():
    from chaotic_systems.gui.recurrence_panel import RecurrencePanel

    return RecurrencePanel


def _make_panel(qtbot, n: int = 100):  # type: ignore[no-untyped-def]
    Panel = _panel_cls()
    panel = Panel(_make_trajectory(n=n))
    qtbot.addWidget(panel)
    return panel


def test_panel_controls_exist(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    assert panel.epsilon_spin.objectName() == "recurrence_epsilon"
    assert panel.l_min_spin.objectName() == "recurrence_l_min"
    assert panel.v_min_spin.objectName() == "recurrence_v_min"
    assert panel.compute_button.objectName() == "recurrence_compute"
    assert panel.status_label.objectName() == "recurrence_status"
    assert panel.canvas.objectName() == "recurrence_canvas"


def test_initial_render_populates_stats(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot, n=80)
    stats = panel.last_stats()
    assert stats is not None
    assert stats.n == 80
    matrix = panel.last_matrix()
    assert matrix is not None
    assert matrix.shape == (80, 80)


def test_recompute_updates_stats(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot, n=80)
    initial_stats = panel.last_stats()
    assert initial_stats is not None
    # Bump epsilon way up; recurrence rate must grow.
    panel.epsilon_spin.setValue(initial_stats.rr * 1000 + 5.0)
    panel._on_compute()  # noqa: SLF001
    new_stats = panel.last_stats()
    assert new_stats is not None
    assert new_stats.rr > initial_stats.rr


def test_recompute_with_bad_epsilon_surfaces_status(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot, n=40)
    # Spinbox has a positive minimum; bypass with attribute assignment
    # via the _on_compute path by directly stubbing the spinbox.
    panel.epsilon_spin.setRange(-10.0, 10.0)
    panel.epsilon_spin.setValue(-1.0)
    panel._on_compute()  # noqa: SLF001
    text = panel.status_label.text().lower()
    assert "epsilon" in text or "positive" in text


def test_long_trajectory_is_subsampled(qtbot) -> None:  # type: ignore[no-untyped-def]
    """N > _MAX_PLOT_N must be subsampled to the cap."""
    from chaotic_systems.gui.recurrence_panel import _MAX_PLOT_N

    panel = _make_panel(qtbot, n=_MAX_PLOT_N * 3)
    stats = panel.last_stats()
    assert stats is not None
    assert stats.n == _MAX_PLOT_N


def test_panel_rejects_input_without_y() -> None:
    Panel = _panel_cls()

    class _NoY:
        state_dim = 2

    with pytest.raises(TypeError, match=".y attribute"):
        Panel(_NoY())


def test_dialog_wraps_panel(qtbot) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtWidgets import QWidget

    from chaotic_systems.gui.recurrence_panel import build_recurrence_dialog

    dialog = build_recurrence_dialog(_make_trajectory())
    qtbot.addWidget(dialog)
    assert dialog.objectName() == "recurrence_dialog"
    canvas = dialog.findChild(QWidget, "recurrence_canvas")
    assert canvas is not None
    assert dialog.recurrence_panel is not None


def test_main_window_exposes_disabled_recurrence_action_initially(qtbot) -> None:  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)
    actions = window.transport_actions()
    assert "action_recurrence" in actions
    action = actions["action_recurrence"]
    assert action.isEnabled() is False
    assert "Recurrence" in action.text() or "recurrence" in action.text().lower()


def test_recurrence_action_enables_after_sim_finished(qtbot) -> None:  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)
    window._on_sim_finished(_make_trajectory(n=50))  # noqa: SLF001
    action = window.transport_actions()["action_recurrence"]
    assert action.isEnabled() is True
