"""Smoke tests for the Settings dropdown.

Verifies the gear button + popup menu surface the expected toggles,
defaults are sane, and toggling state flips the corresponding internal
flags. Live PyVista-side effects (axes show/hide, bg color) are not
asserted — those need a real display *and* the QtInteractor's GL
context, which the rest of the GUI tests already exercise.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")


def _make_window(qtbot):  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)
    return window


def test_settings_button_exists(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    assert window._settings_button is not None  # noqa: SLF001
    menu = window._settings_menu  # noqa: SLF001
    assert menu is not None
    actions = [a.text() for a in menu.actions()]
    # Spot-check: the three top-level toggles are all there.
    assert "Show axes" in actions
    assert "Show grid" in actions
    assert "Show vector field preview" in actions


def test_settings_defaults_are_on(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    assert window.action_show_axes.isChecked()
    assert window.action_show_grid.isChecked()
    # Vector-field preview is off by default — magnitude-scaled arrows
    # read as visual noise on systems like Lorenz.
    assert not window.action_show_vector_preview.isChecked()
    # Trajectory width default mirrors the renderer default (3.5 px).
    assert window._setting_trajectory_width == pytest.approx(3.5)  # noqa: SLF001


def test_toggling_axes_flips_setting(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    window.action_show_axes.setChecked(False)
    assert window._setting_show_axes is False  # noqa: SLF001
    window.action_show_axes.setChecked(True)
    assert window._setting_show_axes is True  # noqa: SLF001


def test_bg_preset_sets_color(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    window._on_setting_bg_color("#000000")  # noqa: SLF001
    assert window._setting_bg_color == "#000000"  # noqa: SLF001
    assert window._bg_actions["#000000"].isChecked()  # noqa: SLF001


def test_trajectory_width_slider_updates(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    # Slider is 1..6 px in 0.1 increments stored as int 10..60.
    window.trajectory_width_slider.setValue(50)
    assert window._setting_trajectory_width == pytest.approx(5.0)  # noqa: SLF001
    # And the value label tracks the slider.
    assert "5.0" in window.trajectory_width_value.text()
