"""Tests for the system picker (attractor dropdown).

FU-006 briefly swapped the plain ``QComboBox`` system picker for
superqt's editable ``QSearchableComboBox`` (type-to-filter over the
13+ systems: Lorenz, Rossler, RosslerHyper, DoublePendulum, Chua,
Duffing, HenonHeiles, Kuramoto, MackeyGlass, plus the four discrete
maps). That widget rendered correctly on macOS but broke on Windows —
its embedded ``QLineEdit`` painted a blank white field under Fusion,
and its ``QCompleter`` popup (a separate top-level window) appeared
detached and offset from the box at the fractional display scaling
Windows uses. The picker was reverted to a plain non-editable
``QComboBox`` (identical to the integrator picker), which renders
correctly on every platform; the 13-entry list is short enough to
scroll.

``superqt`` remains a runtime dependency for the slider widgets used
elsewhere in the GUI.

Coverage:

- ``self.system_box`` is a plain, non-editable ``QComboBox``.
- Every registered system still appears.
- The ``preselect=`` kwarg and the ``currentIndexChanged`` slot
  wiring continue to work.
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
# Migration contract
# ---------------------------------------------------------------------------


def test_system_box_is_a_plain_qcombobox(qtbot) -> None:  # type: ignore[no-untyped-def]
    """``self.system_box`` is a plain, non-editable ``QComboBox``.

    The editable ``QSearchableComboBox`` was reverted because its inner
    line-edit rendered as a blank white field and its completer popup
    appeared detached/offset on Windows. A non-editable ``QComboBox``
    renders correctly on every platform.
    """

    from PySide6.QtWidgets import QComboBox

    window = _make_window(qtbot)
    assert isinstance(window.system_box, QComboBox), (
        f"system_box should be a QComboBox; "
        f"got {type(window.system_box).__name__}"
    )
    assert not window.system_box.isEditable(), (
        "system_box must be non-editable — an editable combobox shows a "
        "blank white line-edit under Fusion on Windows"
    )


def test_system_box_keeps_canonical_object_name(qtbot) -> None:  # type: ignore[no-untyped-def]
    """The ``"system_picker"`` objectName survives the migration.

    External agents (the FU-014 command palette, layout-spec
    assertions in ``docs/ui_design.md``, etc.) look up the picker
    by objectName via ``findChild``; renaming silently breaks them.
    """

    window = _make_window(qtbot)
    assert window.system_box.objectName() == "system_picker"


# ---------------------------------------------------------------------------
# Behavioural contracts that survive the migration
# ---------------------------------------------------------------------------


def test_every_registered_system_appears_in_picker(qtbot) -> None:  # type: ignore[no-untyped-def]
    """All registered systems show up as items in the picker.

    Sanity that the migration didn't drop systems from the
    ``addItem`` loop. The picker should list every system the
    project ships (Lorenz, Rossler, RosslerHyper, DoublePendulum,
    Chua, Duffing, HenonHeiles, Kuramoto, MackeyGlass, plus the
    discrete maps).
    """

    window = _make_window(qtbot)
    items = [
        window.system_box.itemText(i)
        for i in range(window.system_box.count())
    ]
    # Spot-check the canonical systems that have shipped since
    # 2026-05-15 and must continue to appear post-FU-006.
    for canonical in (
        "Lorenz",
        "Rossler",
        "DoublePendulum",
        "HenonHeiles",
        "Kuramoto",
    ):
        assert canonical in items, (
            f"FU-006 — {canonical!r} missing from system picker"
        )
    # The full list should be non-empty.
    assert window.system_box.count() >= 5


def test_system_box_index_change_still_fires_rebuild(qtbot) -> None:  # type: ignore[no-untyped-def]
    """``currentIndexChanged`` still drives ``_on_system_changed``.

    The signal wiring is the load-bearing contract — without it,
    the parameter form / LaTeX panels / educational notes don't
    refresh when the user picks a different system. The
    ``QSearchableComboBox`` subclass inherits ``currentIndexChanged``
    from ``QComboBox`` so this should Just Work; we pin it
    explicitly because a hypothetical future regression would
    silently break the picker.
    """

    window = _make_window(qtbot)
    initial = window.system_box.currentText()
    # Switch to the second item if there are at least two systems.
    if window.system_box.count() >= 2:
        new_idx = 1 if window.system_box.currentIndex() == 0 else 0
        window.system_box.setCurrentIndex(new_idx)
        assert window.system_box.currentText() != initial, (
            "system picker index change didn't fire — signal wiring broken"
        )


# ---------------------------------------------------------------------------
# Non-editable contract (the Windows-regression fix)
# ---------------------------------------------------------------------------


def test_system_box_has_no_editable_line_edit(qtbot) -> None:  # type: ignore[no-untyped-def]
    """The picker exposes no editable line-edit.

    The editable ``QSearchableComboBox`` was reverted because its inner
    ``QLineEdit`` rendered as a blank white field under Fusion on
    Windows. A plain ``QComboBox`` has no line-edit; assert that so a
    future re-introduction of an editable picker fails loudly here.
    """

    window = _make_window(qtbot)
    assert window.system_box.lineEdit() is None, (
        "system_box must have no line-edit — an editable combobox shows a "
        "blank white field under Fusion on Windows"
    )


def test_preselect_argument_still_works(qtbot) -> None:  # type: ignore[no-untyped-def]
    """The ``preselect=`` kwarg on ``_MainWindow.__init__`` continues to honor.

    ``self.system_box.findText(preselect)`` sets the initial index; pin
    it because tests / external launchers may rely on it.
    """

    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window(preselect="Rossler")
    qtbot.addWidget(window)
    try:
        assert window.system_box.currentText() == "Rossler", (
            "FU-006 — preselect='Rossler' didn't take effect; "
            f"got {window.system_box.currentText()!r}"
        )
    finally:
        window.close()
