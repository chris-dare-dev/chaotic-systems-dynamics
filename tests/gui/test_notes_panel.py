"""Tests for the educational-notes GUI panel (E1).

GUI tests inherit the ``CHAOTIC_GUI_TESTS_USE_DISPLAY`` gate from
``tests/gui/conftest.py``.

We pin:

- The ``notes_widget`` (``QTextBrowser``) and ``_notes_section``
  (collapsible wrapper) are constructed and addressable by name.
- After ``_rebuild_for_current_system`` runs, the panel carries the
  current system's notes — verified by checking a Lorenz-specific
  keyword shows up.
- Switching systems re-renders the panel with the new notes.
- An empty-notes system surfaces the friendly placeholder rather
  than a blank panel.
- External links open in the OS browser (``setOpenExternalLinks``
  is on).
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


def test_notes_widget_constructs_with_expected_object_names(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    assert window.notes_widget is not None
    assert window.notes_widget.objectName() == "educational_notes"
    # The collapsible section wrapper is the addressable parent.
    assert window._notes_section is not None  # noqa: SLF001
    # External links open in the OS browser, not inside the read-only
    # QTextBrowser (which can't actually navigate anyway).
    assert window.notes_widget.openExternalLinks() is True
    assert window.notes_widget.isReadOnly() is True


def test_panel_carries_current_system_notes_at_startup(qtbot) -> None:  # type: ignore[no-untyped-def]
    """First-system render must reach the panel via _rebuild_for_current_system."""
    window = _make_window(qtbot)
    # The default registered system is Lorenz, whose notes mention
    # the canonical λ₁ ≈ 0.9056 — a hard-to-fake giveaway.
    text = window.notes_widget.toPlainText()
    assert "Lorenz" in text or "0.9056" in text or "Strogatz" in text


def test_panel_re_renders_on_system_change(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Switching to a different system swaps the visible notes."""
    window = _make_window(qtbot)
    if window.system_box.count() < 2:
        pytest.skip("only one system registered; cycling is a no-op")
    before = window.notes_widget.toPlainText()
    # Find a system that isn't currently selected and switch to it.
    other_idx = (window.system_box.currentIndex() + 1) % window.system_box.count()
    window.system_box.setCurrentIndex(other_idx)
    after = window.notes_widget.toPlainText()
    assert after != before, "notes panel did not refresh on system change"
    assert after.strip() != "", "notes panel went empty after system change"


def test_empty_notes_falls_back_to_placeholder(qtbot) -> None:  # type: ignore[no-untyped-def]
    """A blank-notes system shows a friendly placeholder, not an empty panel."""
    window = _make_window(qtbot)
    window._set_educational_notes("")  # noqa: SLF001
    text = window.notes_widget.toPlainText().lower()
    assert "no educational notes" in text


def test_set_educational_notes_renders_markdown_headings(qtbot) -> None:  # type: ignore[no-untyped-def]
    """``setMarkdown`` round-trips headings into the plain-text view."""
    window = _make_window(qtbot)
    window._set_educational_notes(  # noqa: SLF001
        "# Heading One\n\nSome paragraph text mentioning Strogatz.\n"
    )
    plain = window.notes_widget.toPlainText()
    # QTextBrowser's plain-text view strips the leading '#' but keeps
    # the heading text.
    assert "Heading One" in plain
    assert "Strogatz" in plain


def test_set_educational_notes_handles_none_safely(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Defensive: ``None`` is treated like an empty string, not a crash."""
    window = _make_window(qtbot)
    window._set_educational_notes(None)  # type: ignore[arg-type]  # noqa: SLF001
    assert "no educational notes" in window.notes_widget.toPlainText().lower()
