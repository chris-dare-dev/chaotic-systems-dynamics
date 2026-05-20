"""Tests for FU-003 — theme-aware Notes-panel document stylesheet.

Pre-FU-003 the Notes ``QTextBrowser`` document stylesheet was set
once at construction with the dark-theme PALETTE values. Toggling
to light theme left the Notes panel rendering dark-grey paragraphs
against the light system chrome (visual-scout F-05). FU-003 adds a
``_notes_document_stylesheet(mode)`` static helper that branches on
mode, and ``_on_toggle_theme`` re-applies the helper output between
the theme swap and the LaTeX / Notes re-render.

Coverage:

- ``_notes_document_stylesheet("dark")`` and ``("light")`` return
  different strings (the contract: light branch must produce
  light-mode legible defaults).
- Dark branch uses the canonical ``PALETTE`` tokens
  (continues FU-002's token discipline).
- Light branch uses near-black text on cream-background colours,
  avoiding the dark-text-on-white legibility regression.
- ``_on_toggle_theme`` re-applies the document stylesheet on every
  toggle (verified by spying on the QTextDocument's
  ``setDefaultStyleSheet`` calls).
- The dark branch matches the live-shipped CSS — no drift between
  the helper and the construction-time stylesheet.
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


# ---------------------------------------------------------------------------
# Helper contract
# ---------------------------------------------------------------------------


def test_notes_stylesheet_helper_branches_on_mode(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Light and dark branches return different stylesheets.

    The headline FU-003 contract: a single mode-specific entry
    point. Returning the same string for both modes would mean the
    theme toggle is a no-op for the Notes panel — exactly the F-05
    regression FU-003 is closing.
    """

    from chaotic_systems.gui.main_window import _build_window_class

    cls = _build_window_class()
    dark = cls._notes_document_stylesheet("dark")  # noqa: SLF001
    light = cls._notes_document_stylesheet("light")  # noqa: SLF001
    assert dark != light, (
        "FU-003 — light and dark branches must produce different stylesheets"
    )


def test_dark_branch_uses_palette_tokens() -> None:
    """Dark branch routes every load-bearing colour through ``PALETTE``.

    Continues the FU-002 token discipline. A future palette change
    that doesn't update this branch is caught by the substring
    check below.
    """

    from chaotic_systems.gui.main_window import _build_window_class
    from chaotic_systems.gui.theme import PALETTE

    cls = _build_window_class()
    dark = cls._notes_document_stylesheet("dark")  # noqa: SLF001
    # Every load-bearing token must appear verbatim.
    for token in (
        PALETTE.text_primary,
        PALETTE.text_secondary,
        PALETTE.success,
        PALETTE.bg_deep,
        PALETTE.warning,
        PALETTE.lyapunov,
        PALETTE.accent,
    ):
        assert token in dark, (
            f"FU-003 — dark Notes stylesheet missing PALETTE token {token!r}"
        )


def test_light_branch_uses_dark_text_on_light_background() -> None:
    """Light branch ships legible colours for the Notes panel.

    Without `light.qss` in place, the document stylesheet alone
    must produce a readable rendering. We assert near-black text
    colours (#1a1b26 for headings, #3b4261 for paragraphs) and a
    light code background — the visual contract.
    """

    from chaotic_systems.gui.main_window import _build_window_class

    cls = _build_window_class()
    light = cls._notes_document_stylesheet("light")  # noqa: SLF001
    # Near-black heading + dark-grey paragraph + light-cream code bg.
    assert "#1a1b26" in light, "light h1/h2/h3 must be near-black"
    assert "#3b4261" in light, "light paragraph must be dark grey"
    # Code background must be a light cream, not a dark one
    # (regression: pre-FU-003 the code background was #1a1b26
    # which on a light theme renders as black-on-near-black).
    assert "#e8e4d8" in light, (
        "FU-003 — light branch must use a cream code background"
    )
    # The chromatic accents stay PALETTE-sourced; the dark text
    # tokens DO NOT appear (no #c0caf5 = text-primary, no
    # #9aa5ce = text-secondary, no #1a1b26 as a *background*).
    assert "#c0caf5" not in light, (
        "light branch shouldn't carry the dark text_primary"
    )


def test_light_branch_chromatic_accents_match_palette() -> None:
    """Light branch keeps chromatic tokens (accent / warning / etc.) PALETTE-sourced.

    The chromatic colours read well on both backgrounds, so
    keeping them PALETTE-sourced means a future palette change
    propagates to both dark and light Notes rendering.
    """

    from chaotic_systems.gui.main_window import _build_window_class
    from chaotic_systems.gui.theme import PALETTE

    cls = _build_window_class()
    light = cls._notes_document_stylesheet("light")  # noqa: SLF001
    for chromatic in (PALETTE.warning, PALETTE.lyapunov, PALETTE.accent):
        assert chromatic in light, (
            f"FU-003 — light branch missing chromatic token {chromatic!r}"
        )


# ---------------------------------------------------------------------------
# Construction-time wiring
# ---------------------------------------------------------------------------


def test_notes_widget_uses_helper_at_construction(qtbot) -> None:  # type: ignore[no-untyped-def]
    """The construction-time stylesheet matches ``_notes_document_stylesheet``.

    Pre-FU-003 the construction-time stylesheet was an inline
    f-string; post-FU-003 it routes through the helper. Asserting
    they match ensures the live widget actually consumes the
    helper output (vs. a stale duplicate left behind).
    """

    from chaotic_systems.gui.main_window import _build_window_class
    from chaotic_systems.gui.theme import current_theme

    window = _make_window(qtbot)
    actual = window.notes_widget.document().defaultStyleSheet()
    cls = _build_window_class()
    expected = cls._notes_document_stylesheet(current_theme())  # noqa: SLF001
    assert actual == expected, (
        "FU-003 — Notes widget's default stylesheet must match the "
        "helper output at construction time"
    )


# ---------------------------------------------------------------------------
# Theme-toggle re-apply
# ---------------------------------------------------------------------------


def test_on_toggle_theme_reapplies_notes_stylesheet(qtbot) -> None:  # type: ignore[no-untyped-def]
    """``_on_toggle_theme`` swaps the document stylesheet to the new mode.

    The headline behavioural contract: after the toggle, the Notes
    document's default stylesheet matches the helper's output for
    the new mode. Pre-FU-003 the toggle didn't touch the document
    stylesheet at all — the F-05 regression.
    """

    from chaotic_systems.gui.main_window import _build_window_class

    window = _make_window(qtbot)
    cls = _build_window_class()

    # Capture the dark stylesheet first.
    before = window.notes_widget.document().defaultStyleSheet()
    expected_dark = cls._notes_document_stylesheet("dark")  # noqa: SLF001
    assert before == expected_dark

    # Toggle to light.
    window._on_toggle_theme()  # noqa: SLF001

    after = window.notes_widget.document().defaultStyleSheet()
    expected_light = cls._notes_document_stylesheet("light")  # noqa: SLF001
    assert after == expected_light, (
        "FU-003 — _on_toggle_theme didn't re-apply the light stylesheet"
    )
    assert after != before, (
        "FU-003 — the document stylesheet must change on theme toggle"
    )


def test_toggle_back_to_dark_restores_dark_stylesheet(qtbot) -> None:  # type: ignore[no-untyped-def]
    """A round-trip toggle (dark -> light -> dark) restores the dark stylesheet."""

    from chaotic_systems.gui.main_window import _build_window_class

    window = _make_window(qtbot)
    cls = _build_window_class()
    expected_dark = cls._notes_document_stylesheet("dark")  # noqa: SLF001

    window._on_toggle_theme()  # -> light  # noqa: SLF001
    window._on_toggle_theme()  # -> dark  # noqa: SLF001
    final = window.notes_widget.document().defaultStyleSheet()
    assert final == expected_dark, (
        "FU-003 — round-trip toggle must restore dark stylesheet"
    )


# ---------------------------------------------------------------------------
# Mode fallback
# ---------------------------------------------------------------------------


def test_unknown_mode_falls_back_to_dark() -> None:
    """Unknown ``mode`` values default to the dark branch.

    Defensive: the helper should never raise on an unexpected
    string. The fallback matches Qt's general "unknown theme name
    falls back to dark" convention (theme.apply_theme has the
    same behavior).
    """

    from chaotic_systems.gui.main_window import _build_window_class

    cls = _build_window_class()
    dark = cls._notes_document_stylesheet("dark")  # noqa: SLF001
    unknown = cls._notes_document_stylesheet("bogus-theme-name")  # noqa: SLF001
    assert unknown == dark, (
        "FU-003 — unknown mode should fall back to the dark branch"
    )
