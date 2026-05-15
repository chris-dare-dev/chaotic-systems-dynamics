"""Smoke tests for the QSS theme module.

These tests verify the theme loads, ``apply_theme`` doesn't raise, and
the QSS string actually reaches the running ``QApplication``. They do
NOT verify pixel-perfect appearance — that's reviewed manually via the
before/after screenshots referenced in ``docs/ui_design.md``.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")


def test_palette_is_internally_consistent() -> None:
    """Palette hex strings should all parse as 6-digit ``#rrggbb``."""

    from chaotic_systems.gui.theme import PALETTE

    for field_name in PALETTE.__dataclass_fields__:
        value = getattr(PALETTE, field_name)
        assert isinstance(value, str), f"{field_name}: not a string"
        assert value.startswith("#"), f"{field_name}: missing leading '#'"
        assert len(value) == 7, f"{field_name}: not #rrggbb"
        int(value[1:], 16)  # raises ValueError if non-hex


def test_apply_theme_installs_stylesheet(qapp) -> None:  # type: ignore[no-untyped-def]
    """``apply_theme("dark")`` should populate ``QApplication.styleSheet``."""

    from chaotic_systems.gui.theme import (
        PALETTE,
        apply_theme,
        current_theme,
        viewport_background,
    )

    apply_theme(qapp, "dark")
    css = qapp.styleSheet()
    assert css, "expected a non-empty stylesheet after apply_theme"
    # A few load-bearing palette tokens should appear in the CSS so a
    # stale install (e.g. mismatched dark.qss) is caught.
    for token in (
        PALETTE.bg_window,
        PALETTE.bg_panel,
        PALETTE.accent,
        PALETTE.text_primary,
    ):
        assert token.lower() in css.lower(), f"missing token {token} in QSS"

    assert current_theme() == "dark"
    assert viewport_background() == PALETTE.bg_viewport


def test_apply_theme_unknown_mode_falls_back_to_dark(qapp) -> None:  # type: ignore[no-untyped-def]
    """Unknown theme names should fall back to dark rather than raising."""

    from chaotic_systems.gui.theme import apply_theme, current_theme

    apply_theme(qapp, "nope-not-a-theme")
    assert current_theme() == "dark"
    assert qapp.styleSheet(), "stylesheet should still be installed"


def test_build_application_applies_dark_by_default() -> None:
    """The main-window factory should install the dark QSS automatically."""

    from PySide6.QtWidgets import QApplication

    from chaotic_systems.gui.main_window import build_application
    from chaotic_systems.gui.theme import PALETTE

    # If an app already exists from a previous test we still want the theme
    # applied — build_application calls apply_theme unconditionally.
    app, window = build_application([])
    assert isinstance(app, QApplication)
    css = app.styleSheet()
    assert PALETTE.bg_window.lower() in css.lower()
    window.close()


def test_main_window_exposes_transport_actions() -> None:
    """The toolbar exposes the documented transport-action object names."""

    from chaotic_systems.gui.main_window import build_application

    app, window = build_application([])
    actions = window.transport_actions()
    expected = {
        "transport_run",
        "transport_pause",
        "transport_stop",
        "transport_jump_end",
        "action_export",
        "action_reset_view",
        "action_toggle_theme",
    }
    assert expected.issubset(set(actions.keys()))
    # Every action should carry the expected objectName so external agents
    # can find them via QApplication.findChild() as well.
    for name, action in actions.items():
        assert action.objectName() == name
    # Use app so static analysis doesn't flag it as unused; it must be
    # alive while the window exists.
    assert app is not None
    window.close()
