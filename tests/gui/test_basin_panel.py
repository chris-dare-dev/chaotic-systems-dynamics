"""Tests for the basin-of-attraction GUI panel (D4).

GUI tests inherit the ``CHAOTIC_GUI_TESTS_USE_DISPLAY`` gate from
``tests/gui/conftest.py``.

We pin:

- Panel controls exist with stable object names.
- Construction with the bundled Duffing demo doesn't crash and the
  placeholder canvas is rendered.
- The worker-finished handler stores the diagram and updates the
  status label with the basin counts.
- The cancelled handler surfaces the cancellation message.
- The worker-error handler re-enables the Compute button and shows
  the error.
- The main-window toolbar exposes the ``action_basins`` QAction
  enabled by default.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")


def _make_panel(qtbot):  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.basin_panel import BasinPanel

    panel = BasinPanel()
    qtbot.addWidget(panel)
    return panel


def test_panel_controls_exist(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    assert panel.n_grid_spin.objectName() == "basin_n_grid"
    assert panel.t_end_spin.objectName() == "basin_t_end"
    assert panel.compute_button.objectName() == "basin_compute"
    assert panel.cancel_button.objectName() == "basin_cancel"
    assert panel.progress_bar.objectName() == "basin_progress"
    assert panel.status_label.objectName() == "basin_status"
    assert panel.canvas.objectName() == "basin_canvas"
    # Cancel starts disabled; Compute starts enabled.
    assert panel.cancel_button.isEnabled() is False
    assert panel.compute_button.isEnabled() is True
    # Progress bar starts hidden.
    assert panel.progress_bar.isVisible() is False or not panel.isVisible()


def test_panel_defaults_match_demo_constants(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    assert panel.n_grid_spin.value() == 32
    assert panel.t_end_spin.value() == pytest.approx(50.0)


def test_panel_last_diagram_starts_none(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    assert panel.last_diagram() is None


def test_finished_handler_stores_diagram_and_updates_status(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Drive ``_on_finished`` directly with a stub diagram."""
    from chaotic_systems.core import BasinDiagram

    panel = _make_panel(qtbot)
    # Disable button as if a compute had been in flight.
    panel.compute_button.setEnabled(False)
    panel.cancel_button.setEnabled(True)
    panel.progress_bar.setVisible(True)

    # 4x4 toy diagram: half left, half right.
    labels = np.empty((4, 4), dtype=np.int64)
    labels[:, :2] = 0
    labels[:, 2:] = 1
    diag = BasinDiagram(
        x_axis=(0, -2.0, 2.0),
        y_axis=(1, -2.0, 2.0),
        n_grid=(4, 4),
        labels=labels,
        attractor_labels=["left", "right"],
        attractor_points=np.array([[-1.0, 0.0], [1.0, 0.0]]),
        fixed_state=np.array([0.0, 0.0]),
        system_name="Duffing (double-well)",
    )
    panel._on_finished(diag)  # noqa: SLF001
    assert panel.last_diagram() is diag
    assert panel.compute_button.isEnabled() is True
    assert panel.cancel_button.isEnabled() is False
    text = panel.status_label.text()
    # Status should report 8/16 left, 8/16 right.
    assert "8/16" in text


def test_cancelled_finish_does_not_set_diagram(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    panel._on_finished(None)  # noqa: SLF001
    assert panel.last_diagram() is None
    assert "ancel" in panel.status_label.text().lower()


def test_error_handler_surfaces_message(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    panel.compute_button.setEnabled(False)
    panel._on_error("RuntimeError", "boom")  # noqa: SLF001
    text = panel.status_label.text()
    assert "boom" in text
    assert "RuntimeError" in text
    assert panel.compute_button.isEnabled() is True


def test_cleanup_thread_resets_state(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    panel._worker = MagicMock()  # noqa: SLF001
    panel._thread = MagicMock()  # noqa: SLF001
    panel._cleanup_thread()  # noqa: SLF001
    assert panel._worker is None  # noqa: SLF001
    assert panel._thread is None  # noqa: SLF001


def test_dialog_wraps_panel(qtbot) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtWidgets import QWidget

    from chaotic_systems.gui.basin_panel import build_basin_dialog

    dialog = build_basin_dialog()
    qtbot.addWidget(dialog)
    assert dialog.objectName() == "basin_dialog"
    canvas = dialog.findChild(QWidget, "basin_canvas")
    assert canvas is not None
    assert dialog.basin_panel is not None


def test_main_window_exposes_basin_action(qtbot) -> None:  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)
    actions = window.transport_actions()
    assert "action_basins" in actions
    action = actions["action_basins"]
    assert action.isEnabled() is True
    assert "Basin" in action.text() or "basin" in action.text().lower()
