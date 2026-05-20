"""Command palette — keyboard-driven action search (FU-014).

A ``QDialog`` modal opened on Ctrl+Shift+P that lists every
:class:`~PySide6.QtGui.QAction` registered on the main window and
fuzzy-filters them by name. Trigger an action by typing part of
its name, navigating with up / down arrows, and pressing Enter.

The pattern is borrowed from three independent reference tools —
napari (PR #5483), VS Code (the original Ctrl+Shift+P palette),
and Houdini (operator-search shelf tool). The inspiration brief
catalogs this as **C3** in its convergent-pattern list ("any app
that outgrows its toolbar discovers that menus become a UX cliff;
the command palette is the standard answer"). The chaotic-systems
toolbar carries 12 actions today, putting it squarely in the
"needs a palette" regime.

Architecture
------------
Action collection: :meth:`QWidget.findChildren(QAction)` is the
canonical napari pattern — no bespoke registry. We dedupe by
``objectName`` (Qt makes a single :class:`QAction` discoverable as
a child of both the toolbar and the menu it appears in) and filter
out anonymous actions (``objectName() == ""``) so internal
helpers don't pollute the list. Disabled actions remain visible
but are tagged ``(unavailable)`` and their tooltip surfaces the
guard reason — the user can still see what exists without losing
discoverability.

Theme integration
-----------------
The dialog's container background routes through
``PALETTE.bg_panel`` so the popup matches the dark Tokyo Night
chrome on Windows, where Qt would otherwise default to the
system-native light frame. The challenger flagged this as the
single specific risk in this candidate's MAJOR rating; FU-002
(landed first) provides the tokens the container consumes.

References
----------
- napari PR #5483 — Command palette
  (https://github.com/napari/napari/pull/5483) — the canonical
  Python ``QAction``-discovery + fuzzy-filter implementation
  this module mirrors. License: BSD-3-Clause (pattern only;
  no code copied).
- Visual Studio Code — Ctrl+Shift+P palette (the keyboard binding
  convention).
- SideFX Houdini — shelf tool / operator-search palette
  (https://www.sidefx.com/docs/houdini/basics/panes.html).
- Frontend-uplift 2026-05-19-initial — inspiration-brief.md P01,
  C3 convergent pattern; final-report.md FU-014 (RICE 4.88).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:  # pragma: no cover - import only for type hints
    pass


#: Marker stored in each :class:`QListWidgetItem`'s ``UserRole`` data
#: so the activation slot can resolve a row back to its
#: :class:`QAction` without scanning the parent window again.
_ACTION_ROLE: int = Qt.ItemDataRole.UserRole

#: The "unavailable" suffix appended to row text for disabled actions.
#: The user can still see the row (so the palette doesn't appear to
#: "hide" features) but its row is non-interactive and the suffix
#: reads as the guard explanation.
_UNAVAILABLE_SUFFIX: str = "  (unavailable)"


def collect_actions(host: QWidget) -> list[QAction]:
    """Gather every named :class:`QAction` registered on ``host``.

    Uses ``host.findChildren(QAction)`` (the canonical napari pattern
    from PR #5483) and:

    - Filters out anonymous actions (``objectName() == ""``) so
      internal helpers / separators / shortcut-only handlers don't
      pollute the palette.
    - Dedupes by ``objectName``: a single :class:`QAction` is
      typically a child of both the toolbar AND the menu it appears
      in, so ``findChildren`` returns it twice.
    - Sorts by display text so the user sees a stable, alphabetical
      ordering before any filter is applied.

    Returns
    -------
    list[QAction]
        Deduped, alphabetised list of palette-eligible actions.
    """
    seen: dict[str, QAction] = {}
    for action in host.findChildren(QAction):
        name = action.objectName()
        if not name:
            continue
        # Skip actions with no display text (separators, internal
        # checkable toggles that only appear inside a parent action).
        if not action.text():
            continue
        # First-seen wins; duplicates from menu/toolbar reuse are
        # identical objects so this is order-stable.
        seen.setdefault(name, action)
    return sorted(seen.values(), key=lambda a: a.text().lower())


def _format_row(action: QAction) -> str:
    """Format the visible row text for ``action``.

    Includes the action's text, the keyboard shortcut (if any), and
    the ``(unavailable)`` suffix when the action is currently
    disabled. The shortcut is right-aligned via spaces so all rows
    line up roughly — Qt's ``QListWidget`` does not natively support
    multi-column layouts and this is the cheapest way to keep the
    palette legible at a glance.
    """
    text = action.text().replace("&", "")
    shortcut = action.shortcut().toString() if not action.shortcut().isEmpty() else ""
    if shortcut:
        text = f"{text}    [{shortcut}]"
    if not action.isEnabled():
        text = f"{text}{_UNAVAILABLE_SUFFIX}"
    return text


class CommandPalette(QDialog):
    """Modal command-palette dialog.

    Construction: pass the host window; the palette gathers actions
    via :func:`collect_actions` and presents them in a scrollable
    list filtered by the search field's contents.

    Activation: pressing Enter (or double-clicking a row) triggers
    the selected action and closes the palette. Disabled actions
    cannot be activated. Escape closes without triggering anything.

    Theming: the dialog's container has ``objectName`` set to
    ``"command_palette"`` so the QSS / inline styling can target it.
    The widget tree is rendered against a ``PALETTE.bg_panel``
    background to match the dark chrome — Qt's default on Windows
    is a system-light frame, which would look jarring over the
    dark window.
    """

    #: Emitted when the user activates an action (Enter / double-click).
    #: Carries the :class:`QAction` that was triggered.
    activated = Signal(object)

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self.setObjectName("command_palette")
        self.setWindowTitle("Command palette")
        # ``Dialog`` window flag keeps the palette modal but movable;
        # ``WindowStaysOnTopHint`` ensures it doesn't drop behind the
        # parent before the user can read it. Frameless would look
        # sleeker but loses the OS close button — preserve native
        # window chrome.
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setMinimumHeight(320)

        self._host = host
        self._actions: list[QAction] = collect_actions(host)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        prompt = QLabel(
            "Type to filter actions. Up/Down to navigate, Enter to run.",
            self,
        )
        prompt.setObjectName("command_palette_prompt")
        prompt.setProperty("role", "caption")
        layout.addWidget(prompt)

        self.search_field = QLineEdit(self)
        self.search_field.setObjectName("command_palette_search")
        self.search_field.setPlaceholderText("Search commands...")
        self.search_field.setClearButtonEnabled(True)
        self.search_field.textChanged.connect(self._on_filter_changed)
        layout.addWidget(self.search_field)

        self.list_view = QListWidget(self)
        self.list_view.setObjectName("command_palette_list")
        # Single-row selection; Enter triggers the selected row.
        self.list_view.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.list_view.itemActivated.connect(self._on_item_activated)
        layout.addWidget(self.list_view, 1)

        # Apply the dark-theme background to the dialog frame
        # explicitly. The QSS in dark.qss styles QDialog children
        # (QLineEdit / QListWidget) but the dialog itself defaults
        # to the system frame; FU-002 promoted bg_panel into PALETTE
        # so we read from there instead of baking a hex literal.
        from chaotic_systems.gui.theme import PALETTE

        self.setStyleSheet(
            f"QDialog#command_palette {{ background-color: {PALETTE.bg_panel}; }}"
        )

        self._populate_list("")

        # Up/Down inside the search field navigates the list (so the
        # user never has to leave the keyboard). Forward the key
        # events from the search field to the list.
        self.search_field.installEventFilter(self)

        # Initial focus on the search field — the user starts typing
        # immediately. Pre-select the first row so Enter without
        # filtering still triggers something.
        self.search_field.setFocus(Qt.FocusReason.PopupFocusReason)
        if self.list_view.count() > 0:
            self.list_view.setCurrentRow(0)

    # ------------------------------------------------------------ slots

    def _on_filter_changed(self, text: str) -> None:
        self._populate_list(text)
        # Re-select the first row after filtering so Enter is always
        # meaningful.
        if self.list_view.count() > 0:
            self.list_view.setCurrentRow(0)

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        action = item.data(_ACTION_ROLE)
        if not isinstance(action, QAction):
            return
        if not action.isEnabled():
            # Disabled rows: no-op activation (Qt blocks the trigger
            # but we also skip closing the palette so the user can
            # pick a different row).
            return
        self.activated.emit(action)
        # Trigger the action AFTER closing so any modal it opens
        # (e.g. Preferences dialog from FU-013) renders cleanly
        # without the palette covering it.
        self.accept()
        action.trigger()

    # ------------------------------------------------------------ helpers

    def _populate_list(self, filter_text: str) -> None:
        """Repopulate the list view with actions matching ``filter_text``.

        Case-insensitive substring match against the action's
        display text. Empty filter shows all actions.
        """
        self.list_view.clear()
        needle = filter_text.strip().lower()
        for action in self._actions:
            haystack = action.text().lower()
            if needle and needle not in haystack:
                continue
            item = QListWidgetItem(_format_row(action), self.list_view)
            item.setData(_ACTION_ROLE, action)
            # Tooltip surfaces extra context (the action's tooltip
            # carries the guard explanation for disabled actions in
            # most of this project's toolbar set).
            tt = action.toolTip() or action.text()
            item.setToolTip(tt)
            if not action.isEnabled():
                # Make the row visibly de-emphasized.
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)

    def eventFilter(  # type: ignore[override]
        self, watched: Any, event: Any
    ) -> bool:
        """Forward Up/Down/Enter from the search field to the list view.

        Lets the user navigate without taking focus off the text
        input — the canonical command-palette interaction.
        """
        from PySide6.QtCore import QEvent

        if watched is self.search_field and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                # Move list selection.
                row = self.list_view.currentRow()
                count = self.list_view.count()
                if count == 0:
                    return True
                if key == Qt.Key.Key_Down:
                    row = (row + 1) % count
                else:
                    row = (row - 1) % count
                self.list_view.setCurrentRow(row)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                item = self.list_view.currentItem()
                if item is not None:
                    self._on_item_activated(item)
                return True
        return super().eventFilter(watched, event)


def build_command_palette(host: QWidget) -> CommandPalette:
    """Factory matching the existing ``build_*_dialog`` family.

    Constructs a :class:`CommandPalette` parented to ``host`` and
    returns it without showing — callers invoke :meth:`exec`
    (modal) or :meth:`show` (non-modal).
    """
    return CommandPalette(host)


def palette_shortcut() -> QKeySequence:
    """Return the canonical Ctrl+Shift+P :class:`QKeySequence`.

    Externalised so tests can assert the binding without
    re-typing the string. The binding mirrors VS Code, napari
    (PR #5483), and Houdini's operator-search palette.
    """
    return QKeySequence("Ctrl+Shift+P")


__all__ = [
    "CommandPalette",
    "build_command_palette",
    "collect_actions",
    "palette_shortcut",
]
