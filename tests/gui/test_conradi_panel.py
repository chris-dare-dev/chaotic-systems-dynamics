"""Tests for the Conradi attractor GUI panel (CSC-007).

GUI tests inherit the ``CHAOTIC_GUI_TESTS_USE_DISPLAY`` gate from
``tests/gui/conftest.py``.

We pin:

- Panel controls exist with stable object names and the documented defaults.
- Construction does not crash and the placeholder canvas renders.
- The worker-finished handler stores the RGBA image, re-enables Render, and
  updates the status label.
- The error handler re-enables Render and surfaces the message.
- A real (small) render flows through the worker's render call and the canvas
  swap without crashing.
- The dialog wraps the panel with the stable object name + attribute.
- The main-window toolbar exposes ``action_conradi`` enabled by default.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")


def _make_panel(qtbot):  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.conradi_panel import ConradiPanel

    panel = ConradiPanel()
    qtbot.addWidget(panel)
    return panel


def test_panel_controls_exist(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    assert panel.a_spin.objectName() == "conradi_a"
    assert panel.b_spin.objectName() == "conradi_b"
    assert panel.n_points_spin.objectName() == "conradi_n_points"
    assert panel.n_iter_spin.objectName() == "conradi_n_iter"
    assert panel.bins_spin.objectName() == "conradi_bins"
    assert panel.cmap_box.objectName() == "conradi_cmap"
    assert panel.tone_box.objectName() == "conradi_tone"
    assert panel.bloom_check.objectName() == "conradi_bloom"
    assert panel.render_button.objectName() == "conradi_render"
    assert panel.progress_bar.objectName() == "conradi_progress"
    assert panel.status_label.objectName() == "conradi_status"
    assert panel.canvas.objectName() == "conradi_canvas"
    # Render starts enabled; progress hidden.
    assert panel.render_button.isEnabled() is True
    assert panel.progress_bar.isVisible() is False or not panel.isVisible()


def test_panel_defaults(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    assert panel.a_spin.value() == pytest.approx(5.46)
    assert panel.b_spin.value() == pytest.approx(4.55)
    assert panel.cmap_box.currentText() == "magma"
    assert panel.tone_box.currentText() == "log"
    # The colormap picker is populated from the registry.
    from chaotic_systems.visualization import colormaps

    names = [panel.cmap_box.itemText(i) for i in range(panel.cmap_box.count())]
    assert names == colormaps.available()


def test_last_rgba_starts_none(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    assert panel.last_rgba() is None


def test_finished_handler_stores_rgba_and_updates_status(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    panel.render_button.setEnabled(False)
    panel.progress_bar.setVisible(True)

    rgba = np.zeros((16, 16, 4), dtype=np.uint8)
    rgba[4:8, 4:8, :3] = 200  # a lit block
    rgba[..., 3] = 255
    panel._on_finished(rgba)  # noqa: SLF001
    assert panel.last_rgba() is rgba
    assert panel.render_button.isEnabled() is True
    assert "16" in panel.status_label.text()
    assert "lit" in panel.status_label.text()


def test_cancelled_finish_does_not_set_rgba(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    panel._on_finished(None)  # noqa: SLF001
    assert panel.last_rgba() is None
    assert "ancel" in panel.status_label.text().lower()


def test_error_handler_surfaces_message(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    panel.render_button.setEnabled(False)
    panel._on_error("ValueError", "bad tone")  # noqa: SLF001
    text = panel.status_label.text()
    assert "bad tone" in text
    assert "ValueError" in text
    assert panel.render_button.isEnabled() is True


def test_cleanup_thread_resets_state(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    panel._worker = MagicMock()  # noqa: SLF001
    panel._thread = MagicMock()  # noqa: SLF001
    panel._cleanup_thread()  # noqa: SLF001
    assert panel._worker is None  # noqa: SLF001
    assert panel._thread is None  # noqa: SLF001


def test_small_render_flows_to_canvas(qtbot) -> None:  # type: ignore[no-untyped-def]
    """A real (small) render reaches the canvas-swap path without crashing."""
    from chaotic_systems.visualization import attractor_density

    panel = _make_panel(qtbot)
    rgba = attractor_density.render(5.46, 4.55, n_points=40, n_iter=40, bins=48)
    panel._on_finished(rgba)  # noqa: SLF001
    assert panel.last_rgba() is not None
    assert panel.canvas.objectName() == "conradi_canvas"


def test_screen_button_exists(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    assert panel.screen_button.objectName() == "conradi_screen"
    assert panel.last_lle() is None
    assert panel._screen_mode is False  # noqa: SLF001


def test_screen_finished_stores_lle_and_enters_screen_mode(qtbot) -> None:  # type: ignore[no-untyped-def]
    """A real small screening grid flows through to the heatmap + screen mode."""
    from chaotic_systems.visualization import attractor_screen

    panel = _make_panel(qtbot)
    panel.render_button.setEnabled(False)
    panel.screen_button.setEnabled(False)
    lle, _ = attractor_screen.lyapunov_grid(16, n=120, n_transient=40)
    panel._on_screen_finished(lle)  # noqa: SLF001
    assert panel.last_lle() is lle
    assert panel._screen_mode is True  # noqa: SLF001
    assert panel.render_button.isEnabled() is True
    assert panel.screen_button.isEnabled() is True
    assert "chaotic" in panel.status_label.text()


def test_canvas_click_in_screen_mode_sets_ab(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Clicking the heatmap in screen mode sets the a/b spinboxes."""
    from types import SimpleNamespace

    from chaotic_systems.visualization import attractor_screen

    panel = _make_panel(qtbot)
    lle, _ = attractor_screen.lyapunov_grid(16, n=120, n_transient=40)
    panel._on_screen_finished(lle)  # noqa: SLF001 - enter screen mode
    # A fake matplotlib button-press event over the axes.
    event = SimpleNamespace(inaxes=object(), xdata=2.0, ydata=3.0)
    panel._on_canvas_click(event)  # noqa: SLF001
    assert panel.a_spin.value() == pytest.approx(2.0, abs=1e-6)
    assert panel.b_spin.value() == pytest.approx(3.0, abs=1e-6)


def test_canvas_click_ignored_outside_screen_mode(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Clicks do nothing when a density render (not the heatmap) is shown."""
    from types import SimpleNamespace

    panel = _make_panel(qtbot)
    assert panel._screen_mode is False  # noqa: SLF001
    a0, b0 = panel.a_spin.value(), panel.b_spin.value()
    event = SimpleNamespace(inaxes=object(), xdata=1.0, ydata=1.0)
    panel._on_canvas_click(event)  # noqa: SLF001
    assert panel.a_spin.value() == pytest.approx(a0)
    assert panel.b_spin.value() == pytest.approx(b0)


def test_render_after_screen_leaves_screen_mode(qtbot) -> None:  # type: ignore[no-untyped-def]
    """A density render after screening clears screen mode (clicks go inert)."""
    from chaotic_systems.visualization import attractor_density, attractor_screen

    panel = _make_panel(qtbot)
    lle, _ = attractor_screen.lyapunov_grid(16, n=120, n_transient=40)
    panel._on_screen_finished(lle)  # noqa: SLF001
    assert panel._screen_mode is True  # noqa: SLF001
    rgba = attractor_density.render(5.46, 4.55, n_points=40, n_iter=40, bins=48)
    panel._on_finished(rgba)  # noqa: SLF001
    assert panel._screen_mode is False  # noqa: SLF001


def test_dialog_wraps_panel(qtbot) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtWidgets import QWidget

    from chaotic_systems.gui.conradi_panel import build_conradi_dialog

    dialog = build_conradi_dialog()
    qtbot.addWidget(dialog)
    assert dialog.objectName() == "conradi_dialog"
    canvas = dialog.findChild(QWidget, "conradi_canvas")
    assert canvas is not None
    assert dialog.conradi_panel is not None


def test_main_window_exposes_conradi_action(qtbot) -> None:  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)
    actions = window.transport_actions()
    assert "action_conradi" in actions
    action = actions["action_conradi"]
    assert action.isEnabled() is True
    assert "Conradi" in action.text() or "conradi" in action.text().lower()
