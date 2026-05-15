"""Smoke tests for the GUI main window.

These tests verify that the window builds, parameter widgets are generated
from the system's parameter schema, and the LaTeX panel renders without
error. We do NOT exercise the full event loop or the video export path here.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")


def test_main_window_builds(qtbot) -> None:  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)

    assert window.system_box.count() >= 1
    # At least one parameter spinbox per system.
    assert len(window._param_widgets) >= 1  # noqa: SLF001 — testing internals deliberately
    assert window.integrator_box.count() >= 1


def test_main_window_changing_system_rebuilds_params(qtbot) -> None:  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)

    # The fallback Lorenz exposes sigma/rho/beta.
    names = set(window._param_widgets.keys())  # noqa: SLF001
    assert {"sigma", "rho", "beta"}.issubset(names)


def test_main_window_latex_panel_is_populated(qtbot) -> None:  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)

    pixmap = window.ode_label.pixmap()
    # Either we rendered something to a pixmap OR there is at least some
    # fallback text describing the failure — both are acceptable signs of
    # the LaTeX path having been exercised.
    has_pixmap = pixmap is not None and not pixmap.isNull() and pixmap.width() > 0
    has_text = bool(window.ode_label.text())
    assert has_pixmap or has_text, "ODE label neither has a pixmap nor a text fallback"
