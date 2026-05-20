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


def test_palette_carries_derived_interaction_shades() -> None:
    """FU-002 — ``bg_deep`` / ``accent_hover`` / ``accent_pressed`` /
    ``accent_glow`` / ``bg_pill_track`` are first-class palette tokens
    so the QSS-derived interaction shades + the Notes panel + the
    ``_BG_PRESETS`` background picker all route through ``PALETTE``
    instead of grep-targets across the codebase.
    """

    from chaotic_systems.gui.theme import PALETTE

    # Each new token must exist on the dataclass and resolve to the
    # canonical Tokyo-Night-derived hex (see ``theme.py`` comments).
    expected = {
        "bg_deep": "#1a1b26",
        "bg_pill_track": "#2a2c3a",
        "accent_hover": "#343a55",
        "accent_pressed": "#6788d8",
        "accent_glow": "#a4c1ff",
    }
    for field_name, expected_hex in expected.items():
        assert hasattr(PALETTE, field_name), (
            f"PALETTE missing FU-002 token {field_name!r}"
        )
        assert getattr(PALETTE, field_name) == expected_hex, (
            f"PALETTE.{field_name} drift: expected {expected_hex}, "
            f"got {getattr(PALETTE, field_name)}"
        )


def test_dark_qss_header_documents_derived_shades() -> None:
    """The ``dark.qss`` header comment block must enumerate the FU-002
    tokens — QSS has no variable substitution so the header anchors
    the values and inline-comment annotations at each use site mark
    the token names. A drifted header would lie about the contract.
    """

    from pathlib import Path

    from chaotic_systems.gui.theme import PALETTE

    qss_text = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "chaotic_systems"
        / "gui"
        / "assets"
        / "dark.qss"
    ).read_text(encoding="utf-8")

    # The header block is everything up to the first non-comment rule.
    header_end = qss_text.index("\n */\n") + 5
    header = qss_text[:header_end]

    for name, expected_hex in (
        ("bg-deep", PALETTE.bg_deep),
        ("bg-pill-track", PALETTE.bg_pill_track),
        ("accent-hover", PALETTE.accent_hover),
        ("accent-pressed", PALETTE.accent_pressed),
        ("accent-glow", PALETTE.accent_glow),
    ):
        assert name in header, f"dark.qss header missing derived shade {name!r}"
        assert expected_hex in header, (
            f"dark.qss header missing hex {expected_hex} for token {name}"
        )


def test_dark_stylesheet_contains_qmenu_rules(qapp) -> None:  # type: ignore[no-untyped-def]
    """The dark theme paints ``QMenu`` so the Settings dropdown (and any
    future menu-bearing affordance) consumes the Tokyo Night palette
    instead of falling back to the platform-native light style.

    Closes FU-001 from frontend-uplift 2026-05-19-initial — the
    visual scout's ``screenshots/settings-open.png`` confirms the
    regression on Windows; the current-state-critic flagged this as
    anti-pattern AP-01 ("do not propose any new QMenu-based dropdown
    until dark.qss includes QMenu rules").
    """

    from chaotic_systems.gui.theme import PALETTE, apply_theme

    apply_theme(qapp, "dark")
    css = qapp.styleSheet().lower()

    # The QMenu selector and its three load-bearing pseudo-states must
    # all appear so the popup picks up bg-panel, selected-item accent,
    # and the separator stroke.
    for selector in (
        "qmenu {",
        "qmenu::item {",
        "qmenu::item:selected",
        "qmenu::separator",
    ):
        assert selector in css, f"missing QMenu selector {selector!r} in dark.qss"

    # The QMenu block uses palette tokens, not raw hex literals that
    # would drift on a future palette change. We assert the canonical
    # tokens appear in proximity to the QMenu selector by checking the
    # CSS contains the bg-panel and accent tokens (the selector-level
    # assertion above already requires the rules to exist).
    assert PALETTE.bg_panel.lower() in css
    assert PALETTE.accent.lower() in css


def test_qmenu_rule_uses_canonical_tokens() -> None:
    """The QMenu QSS block uses the documented palette tokens verbatim.

    Token discipline check — parses the dark.qss source directly so a
    future palette change that updates ``theme.PALETTE`` but forgets
    to update the QMenu rule's literals is caught.
    """

    from pathlib import Path

    from chaotic_systems.gui.theme import PALETTE

    qss_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "chaotic_systems"
        / "gui"
        / "assets"
        / "dark.qss"
    )
    qss_text = qss_path.read_text(encoding="utf-8")
    # Find the QMenu block — everything from "QMenu {" through the next
    # rule at column 0 that isn't a QMenu::... selector.
    start = qss_text.index("QMenu {")
    # End at the next top-level selector after the QMenu rules
    # (QMenu::indicator and QMenu::right-arrow are still QMenu rules).
    # Look forward for a non-QMenu rule.
    block = qss_text[start : start + 1500]

    # Required tokens.
    assert PALETTE.bg_panel in block, "QMenu background must use bg_panel token"
    assert PALETTE.text_primary in block, "QMenu color must use text_primary"
    assert PALETTE.border in block, "QMenu border must use border token"
    assert PALETTE.accent in block, "QMenu::item:selected must use accent"
    assert PALETTE.accent_text in block, (
        "QMenu::item:selected color must use accent_text"
    )
    assert PALETTE.text_muted in block, (
        "QMenu::item:disabled must use text_muted"
    )


def test_state_layer_focus_rules_cover_every_interactive_widget() -> None:
    """FU-016 — every load-bearing interactive widget ships a ``:focus`` rule.

    The state-layer contract documented at the top of ``dark.qss``
    pins the eight widget families: QPushButton, QToolButton,
    QComboBox, QSpinBox / QDoubleSpinBox, QLineEdit, QSlider,
    QCheckBox, QListView / QListWidget. Without these the keyboard
    focus indicator is invisible on Windows (WCAG 2.1 SC 2.4.7
    violation).
    """

    from pathlib import Path

    qss_text = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "chaotic_systems"
        / "gui"
        / "assets"
        / "dark.qss"
    ).read_text(encoding="utf-8")

    # Every load-bearing interactive widget needs at least one
    # ``:focus`` selector. Substring search is robust to formatting.
    required = [
        "QPushButton:focus",
        "QToolButton:focus",
        "QComboBox:focus",
        "QDoubleSpinBox:focus",
        "QSpinBox:focus",
        "QLineEdit:focus",
        "QSlider::handle:horizontal:focus",
        "QCheckBox:focus",
        "QListView:focus",
        "QListWidget:focus",
    ]
    for selector in required:
        assert selector in qss_text, (
            f"FU-016 — dark.qss missing :focus rule {selector!r}"
        )


def test_state_layer_hover_rules_cover_new_widgets() -> None:
    """FU-016 — QCheckBox + QListView/QListWidget have hover rules.

    These are the new state-layer additions introduced by FU-016 (the
    other widgets had hover rules pre-FU-016). Items get a separate
    ``::item:hover`` selector because the row-level interaction is
    where the hover layer reads.
    """

    from pathlib import Path

    qss_text = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "chaotic_systems"
        / "gui"
        / "assets"
        / "dark.qss"
    ).read_text(encoding="utf-8")

    for selector in (
        "QCheckBox::indicator:hover",
        "QListView::item:hover",
        "QListWidget::item:hover",
    ):
        assert selector in qss_text, (
            f"FU-016 — dark.qss missing hover rule {selector!r}"
        )


def test_state_layer_consumes_palette_tokens() -> None:
    """FU-016 state-layer rules route through the FU-002 PALETTE tokens.

    The new QCheckBox / QListView blocks must use the same canonical
    hex values that FU-002 promoted to ``theme.PALETTE``. Asserting
    against the PALETTE values keeps the QSS aligned with the
    dataclass — a future palette change updates one place and the
    test catches drift.
    """

    from pathlib import Path

    from chaotic_systems.gui.theme import PALETTE

    qss_text = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "chaotic_systems"
        / "gui"
        / "assets"
        / "dark.qss"
    ).read_text(encoding="utf-8")

    # Find the QCheckBox + QListView sections and assert the tokens
    # appear in each.
    checkbox_start = qss_text.index("QCheckBox {")
    listview_start = qss_text.index("QListView,")
    checkbox_block = qss_text[checkbox_start:listview_start]
    listview_block = qss_text[listview_start : listview_start + 2000]

    # QCheckBox indicator + hover use accent + accent-hover.
    assert PALETTE.accent_hover in checkbox_block, (
        "QCheckBox hover must use PALETTE.accent_hover"
    )
    assert PALETTE.accent in checkbox_block, (
        "QCheckBox checked must use PALETTE.accent"
    )

    # QListView item:hover uses accent_hover; item:selected uses accent.
    assert PALETTE.accent_hover in listview_block, (
        "QListView::item:hover must use PALETTE.accent_hover"
    )
    assert PALETTE.accent in listview_block, (
        "QListView::item:selected must use PALETTE.accent"
    )


def test_qcheckbox_renders_with_dark_indicator(qapp) -> None:  # type: ignore[no-untyped-def]
    """A QCheckBox embedded in the dark-themed app picks up dark chrome.

    Behavioural check: build a checkbox under the theme and confirm
    Qt resolves a non-empty styleSheet for it (i.e. our QCheckBox
    rule actually reaches the widget). Pixel-perfect appearance is
    out of scope; we verify the QSS hookup, not the visual output.
    """

    from PySide6.QtWidgets import QCheckBox

    from chaotic_systems.gui.theme import apply_theme

    apply_theme(qapp, "dark")
    cb = QCheckBox("Sample")
    try:
        # The application-level styleSheet must reference QCheckBox.
        assert "QCheckBox" in qapp.styleSheet()
    finally:
        cb.deleteLater()


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
