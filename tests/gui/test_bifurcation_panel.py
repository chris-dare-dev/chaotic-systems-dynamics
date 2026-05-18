"""Tests for the bifurcation GUI panel.

GUI tests are gated by the ``CHAOTIC_GUI_TESTS_USE_DISPLAY`` env var
in ``tests/gui/conftest.py``; this file inherits that behaviour
automatically.

We pin:

- The panel constructs against a discrete map and exposes the
  controls (parameter combobox, range spinboxes, n_values / transient
  / record spinboxes, projection, compute + cancel buttons, canvas).
- The compute path: a fast in-thread sweep that finishes triggers
  ``_on_finished`` and stores the diagram on the panel.
- The error path: a worker error surfaces in the status label and
  re-enables the Compute button.
- The dialog wraps a map picker and embeds the panel.
- ``BifurcationPanel`` rejects non-DiscreteSystem arguments.
- The main-window toolbar exposes the ``action_bifurcation`` QAction.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")


def _panel_cls():
    from chaotic_systems.gui.bifurcation_panel import BifurcationPanel

    return BifurcationPanel


def _make_panel(qtbot):  # type: ignore[no-untyped-def]
    from chaotic_systems.systems import Logistic

    Panel = _panel_cls()
    panel = Panel(Logistic())
    qtbot.addWidget(panel)
    return panel


def test_panel_controls_exist(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    assert panel.param_box.objectName() == "bifurcation_param_box"
    assert panel.min_spin.objectName() == "bifurcation_min"
    assert panel.max_spin.objectName() == "bifurcation_max"
    assert panel.n_values_spin.objectName() == "bifurcation_n_values"
    assert panel.n_transient_spin.objectName() == "bifurcation_n_transient"
    assert panel.n_record_spin.objectName() == "bifurcation_n_record"
    assert panel.projection_spin.objectName() == "bifurcation_projection"
    assert panel.compute_button.objectName() == "bifurcation_compute"
    assert panel.cancel_button.objectName() == "bifurcation_cancel"
    assert panel.progress_bar.objectName() == "bifurcation_progress"
    assert panel.canvas.objectName() == "bifurcation_canvas"


def test_panel_seeds_range_from_parameter_bounds(qtbot) -> None:  # type: ignore[no-untyped-def]
    """When the panel opens, range fields reflect the swept parameter's [min, max]."""
    panel = _make_panel(qtbot)
    # Logistic's only parameter is r ∈ [0, 4].
    assert panel.min_spin.value() == pytest.approx(0.0)
    assert panel.max_spin.value() == pytest.approx(4.0)
    # Single-component state: projection spin is disabled.
    assert panel.projection_spin.isEnabled() is False


def test_panel_rejects_continuous_system() -> None:
    from chaotic_systems.systems import Lorenz

    Panel = _panel_cls()
    with pytest.raises(TypeError, match="DiscreteSystem only"):
        Panel(Lorenz())


def test_finished_signal_updates_canvas_and_diagram(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Simulating a worker-finished call swaps the canvas and stores the diagram."""
    from chaotic_systems.core.bifurcation import bifurcation_diagram

    panel = _make_panel(qtbot)
    # Build a small diagram and hand it to the panel as if the worker had
    # finished, then check the panel records it and re-enables the button.
    from chaotic_systems.systems import Logistic

    diag = bifurcation_diagram(
        Logistic(), "r", np.linspace(3.0, 4.0, 5), n_record=8, n_transient=20
    )
    panel.compute_button.setEnabled(False)
    panel.cancel_button.setEnabled(True)
    panel.progress_bar.setVisible(True)
    panel._on_finished(diag)  # noqa: SLF001
    assert panel.last_diagram() is diag
    assert panel.compute_button.isEnabled() is True
    assert panel.cancel_button.isEnabled() is False
    assert "Done" in panel.status_label.text()


def test_cancelled_finish_does_not_set_diagram(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    panel._on_finished(None)  # noqa: SLF001
    assert panel.last_diagram() is None
    assert "ancel" in panel.status_label.text().lower()


def test_error_path_surfaces_message(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    panel.compute_button.setEnabled(False)
    panel._on_error("KeyError", "bogus param")  # noqa: SLF001
    assert "bogus param" in panel.status_label.text()
    assert "KeyError" in panel.status_label.text()
    assert panel.compute_button.isEnabled() is True


def test_dialog_bundles_map_picker_and_panel(qtbot) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtWidgets import QComboBox, QWidget

    from chaotic_systems.gui.bifurcation_panel import build_bifurcation_dialog

    dialog = build_bifurcation_dialog()
    qtbot.addWidget(dialog)
    assert dialog.objectName() == "bifurcation_dialog"
    picker = dialog.findChild(QComboBox, "bifurcation_map_picker")
    assert picker is not None
    # All four maps from N1 are present.
    items = [picker.itemText(i) for i in range(picker.count())]
    for expected in ("Logistic", "HenonMap", "Ikeda", "StandardMap"):
        assert expected in items
    # The dialog wraps a BifurcationPanel that has the right controls.
    panel_host = dialog.findChild(QWidget, "bifurcation_panel_host")
    assert panel_host is not None
    canvas = dialog.findChild(QWidget, "bifurcation_canvas")
    assert canvas is not None


def test_main_window_exposes_bifurcation_action(qtbot) -> None:  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)
    actions = window.transport_actions()
    assert "action_bifurcation" in actions
    action = actions["action_bifurcation"]
    assert action.isEnabled()
    assert "Bifurcation" in action.text()
