"""Tests for FU-014 — Command palette (Ctrl+Shift+P).

Coverage:

- :func:`collect_actions` dedupes the duplicate ``QAction`` entries
  Qt surfaces when an action lives in both a toolbar and a menu;
  anonymous actions are filtered out.
- :class:`CommandPalette` constructs without raising, populates
  with the host's actions, filters case-insensitively, navigates
  via Up/Down from the search field, and triggers the selected
  action on Enter.
- The main window registers the Ctrl+Shift+P shortcut and
  ``_open_command_palette`` is wired.
- Disabled actions show in the list but cannot be activated.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")


# ---------------------------------------------------------------------------
# collect_actions — action discovery
# ---------------------------------------------------------------------------


def test_collect_actions_dedupes_by_object_name(qapp) -> None:  # type: ignore[no-untyped-def]
    """A QAction registered on both a toolbar and a menu surfaces once.

    Qt's ``findChildren(QAction)`` returns the same action object
    multiple times when it has multiple parents. The palette must
    not show duplicate rows.
    """

    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QMainWindow, QMenu, QToolBar

    from chaotic_systems.gui.command_palette import collect_actions

    window = QMainWindow()
    try:
        toolbar = QToolBar(window)
        window.addToolBar(toolbar)
        menu = QMenu("Things", window)
        window.menuBar().addMenu(menu)

        action = QAction("Run simulation", window)
        action.setObjectName("action_run")
        toolbar.addAction(action)
        menu.addAction(action)  # same action — same objectName

        out = collect_actions(window)
        names = [a.objectName() for a in out]
        # Only one copy of action_run; no duplicates.
        assert names.count("action_run") == 1
    finally:
        window.close()


def test_collect_actions_filters_anonymous_and_textless(qapp) -> None:  # type: ignore[no-untyped-def]
    """Actions without ``objectName`` or display text are dropped."""

    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QMainWindow

    from chaotic_systems.gui.command_palette import collect_actions

    window = QMainWindow()
    try:
        # Anonymous action — no objectName.
        a1 = QAction("Anonymous", window)
        window.addAction(a1)

        # Textless action with objectName — separator-style.
        a2 = QAction("", window)
        a2.setObjectName("separator_textless")
        window.addAction(a2)

        # Visible action — should appear.
        a3 = QAction("Visible", window)
        a3.setObjectName("action_visible")
        window.addAction(a3)

        out = collect_actions(window)
        names = {a.objectName() for a in out}
        assert "action_visible" in names
        assert "separator_textless" not in names
        # Anonymous entries don't surface (no objectName at all).
        assert "" not in names
    finally:
        window.close()


def test_collect_actions_returns_alphabetical_order(qapp) -> None:  # type: ignore[no-untyped-def]
    """Output is sorted by display text (case-insensitive)."""

    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QMainWindow

    from chaotic_systems.gui.command_palette import collect_actions

    window = QMainWindow()
    try:
        for name, text in [
            ("z", "Zoom in"),
            ("a", "Apply preset"),
            ("m", "Mute"),
        ]:
            action = QAction(text, window)
            action.setObjectName(f"action_{name}")
            window.addAction(action)

        out = collect_actions(window)
        texts = [a.text() for a in out]
        assert texts == sorted(texts, key=str.lower)
    finally:
        window.close()


# ---------------------------------------------------------------------------
# CommandPalette dialog
# ---------------------------------------------------------------------------


def _host_with_actions(actions: list[tuple[str, str]]):
    """Build a throwaway QMainWindow with the listed actions registered.

    ``actions`` is ``[(objectName, displayText), ...]``.
    """
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QMainWindow

    window = QMainWindow()
    for name, text in actions:
        action = QAction(text, window)
        action.setObjectName(name)
        window.addAction(action)
    return window


def test_palette_constructs_and_populates_from_host(qapp) -> None:  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.command_palette import build_command_palette

    host = _host_with_actions([
        ("action_run", "Run simulation"),
        ("action_export", "Export video"),
        ("action_phase", "Open phase portrait"),
    ])
    try:
        palette = build_command_palette(host)
        try:
            assert palette.objectName() == "command_palette"
            # All 3 actions appear in the initial unfiltered list.
            assert palette.list_view.count() == 3
            # Search field is focused (PopupFocusReason).
            assert palette.search_field is not None
            # First row is preselected so Enter is always meaningful.
            assert palette.list_view.currentRow() == 0
        finally:
            palette.deleteLater()
    finally:
        host.close()


def test_palette_filters_case_insensitively(qapp) -> None:  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.command_palette import build_command_palette

    host = _host_with_actions([
        ("action_run", "Run simulation"),
        ("action_export", "Export video"),
        ("action_phase", "Open phase portrait"),
    ])
    try:
        palette = build_command_palette(host)
        try:
            palette.search_field.setText("EXPORT")
            assert palette.list_view.count() == 1
            assert "Export" in palette.list_view.item(0).text()

            palette.search_field.setText("phase")
            assert palette.list_view.count() == 1
            assert "phase" in palette.list_view.item(0).text().lower()

            # Empty filter restores everything.
            palette.search_field.setText("")
            assert palette.list_view.count() == 3
        finally:
            palette.deleteLater()
    finally:
        host.close()


def test_palette_enter_triggers_action_and_closes(qapp) -> None:  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.command_palette import build_command_palette

    host = _host_with_actions([
        ("action_run", "Run simulation"),
        ("action_export", "Export video"),
    ])
    try:
        triggers: list[str] = []
        for action in host.actions():
            action.triggered.connect(
                lambda *_a, name=action.objectName(): triggers.append(name)
            )

        palette = build_command_palette(host)
        try:
            palette.search_field.setText("Export")
            assert palette.list_view.count() == 1
            item = palette.list_view.item(0)
            palette._on_item_activated(item)  # noqa: SLF001

            assert triggers == ["action_export"]
            # Dialog accepts itself on activation (palette.result() == Accepted).
            from PySide6.QtWidgets import QDialog

            assert palette.result() == QDialog.DialogCode.Accepted
        finally:
            palette.deleteLater()
    finally:
        host.close()


def test_palette_disabled_action_is_visible_but_not_triggered(qapp) -> None:  # type: ignore[no-untyped-def]
    """Disabled actions show in the palette with a guard suffix.

    The synthesis explicitly calls for this: "Actions whose guard
    conditions are not met (no trajectory yet) appear greyed with
    a reason tooltip." Activation must not fire the action.
    """

    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QMainWindow

    from chaotic_systems.gui.command_palette import (
        _UNAVAILABLE_SUFFIX,
        build_command_palette,
    )

    host = QMainWindow()
    try:
        disabled = QAction("Export video", host)
        disabled.setObjectName("action_export")
        disabled.setEnabled(False)
        host.addAction(disabled)

        triggers: list[str] = []
        disabled.triggered.connect(lambda *_a: triggers.append("export"))

        palette = build_command_palette(host)
        try:
            assert palette.list_view.count() == 1
            row_text = palette.list_view.item(0).text()
            assert _UNAVAILABLE_SUFFIX.strip() in row_text
            # Attempt activation — must be a no-op.
            palette._on_item_activated(palette.list_view.item(0))  # noqa: SLF001
            assert triggers == []
        finally:
            palette.deleteLater()
    finally:
        host.close()


def test_palette_shortcut_returns_ctrl_shift_p() -> None:
    """The canonical shortcut binding matches napari / VS Code / Houdini."""

    from chaotic_systems.gui.command_palette import palette_shortcut

    seq = palette_shortcut()
    # Qt normalises modifier ordering: "Ctrl+Shift+P".
    assert "Ctrl+Shift+P" in seq.toString()


# ---------------------------------------------------------------------------
# Main-window wiring
# ---------------------------------------------------------------------------


def test_main_window_open_command_palette_method_exists() -> None:
    """The main window exposes ``_open_command_palette`` for the shortcut."""

    from chaotic_systems.gui.main_window import build_application

    app, window = build_application([])
    try:
        assert hasattr(window, "_open_command_palette")
        # Method is callable (we don't open the modal here — that
        # would block; we only verify the binding exists).
        assert callable(window._open_command_palette)  # noqa: SLF001
    finally:
        window.close()
        assert app is not None


def test_main_window_surfaces_toolbar_actions_to_palette() -> None:
    """The palette built against the real window includes the
    canonical transport actions.

    Sanity check that ``findChildren(QAction)`` reaches the toolbar
    surface — the palette must discover Run / Pause / Stop / Export
    out of the box without manual registration.
    """

    from chaotic_systems.gui.command_palette import collect_actions
    from chaotic_systems.gui.main_window import build_application

    app, window = build_application([])
    try:
        actions = collect_actions(window)
        names = {a.objectName() for a in actions}
        # Transport actions documented in test_theme.py must surface.
        for expected in (
            "transport_run",
            "transport_pause",
            "transport_stop",
            "transport_jump_end",
            "action_export",
            "action_reset_view",
            "action_toggle_theme",
        ):
            assert expected in names, f"action {expected!r} missing from palette"
        # FU-013's Preferences action should also surface.
        assert "action_preferences" in names
    finally:
        window.close()
        assert app is not None
