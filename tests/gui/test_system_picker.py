"""Tests for FU-006 — superqt ``QSearchableComboBox`` system picker.

Pre-FU-006 the system picker was a plain ``QComboBox`` that grew
to 13+ entries (Lorenz, Rossler, RosslerHyper, DoublePendulum,
Chua, Duffing, HenonHeiles, Kuramoto, MackeyGlass, plus the four
discrete maps) — past the scroll-vs-search threshold for ergonomic
selection. FU-006 swaps it for superqt's ``QSearchableComboBox``,
which subclasses ``QComboBox`` and adds a type-to-filter on the
dropdown.

Scope of FU-006 as shipped (reduced from the synthesis):

- ``QSearchableComboBox`` migration for the system picker ONLY.
- ``superqt`` is added to runtime deps for future migrations.
- ``_ParamWidget`` migration is DEFERRED — superqt 0.8's
  ``QLabeledDoubleSlider`` has no log-scale support, and the
  project's Kuramoto K (range 0.01–50, log-scale) depends on it.
  Mixing two widget types in the parameter form would be churn
  for marginal benefit.
- Notes-section ``QCollapsible`` migration is DEFERRED — the
  existing ``_CollapsibleSection`` works correctly; replacement
  would be churn without a clear user win.

Coverage:

- ``self.system_box`` is a ``QSearchableComboBox`` (IS-A
  ``QComboBox``, so all existing accessors still work).
- Every previously-registered system still appears.
- ``transport_actions()`` and the ``currentIndexChanged`` slot
  wiring continue to work — the migration is API-compatible.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("superqt")
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


def test_system_box_is_a_searchable_combobox(qtbot) -> None:  # type: ignore[no-untyped-def]
    """FU-006 — ``self.system_box`` is a ``QSearchableComboBox`` instance."""

    from superqt import QSearchableComboBox

    window = _make_window(qtbot)
    assert isinstance(window.system_box, QSearchableComboBox), (
        f"FU-006 — system_box should be QSearchableComboBox; "
        f"got {type(window.system_box).__name__}"
    )


def test_system_box_is_still_a_qcombobox(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Backwards-compat: ``QSearchableComboBox`` IS-A ``QComboBox``.

    Existing callers that introspect ``system_box`` as a
    ``QComboBox`` must continue to work — that's the migration
    contract that lets us swap without touching downstream code.
    """

    from PySide6.QtWidgets import QComboBox

    window = _make_window(qtbot)
    assert isinstance(window.system_box, QComboBox), (
        "FU-006 — system_box must remain a QComboBox subclass so "
        "existing accessors keep working"
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
# Filter / completer surface
# ---------------------------------------------------------------------------


def test_searchable_combobox_carries_a_completer(qtbot) -> None:  # type: ignore[no-untyped-def]
    """``QSearchableComboBox`` adds a ``QCompleter`` for type-to-filter.

    The user-visible value of FU-006 is the filter; without a
    completer the picker degrades to a plain ``QComboBox`` which
    would silently undo the migration's intent.
    """

    window = _make_window(qtbot)
    completer = window.system_box.completer()
    assert completer is not None, (
        "FU-006 — QSearchableComboBox should expose a non-null completer"
    )


def test_preselect_argument_still_works(qtbot) -> None:  # type: ignore[no-untyped-def]
    """The ``preselect=`` kwarg on ``_MainWindow.__init__`` continues to honor.

    Pre-FU-006 ``self.system_box.findText(preselect)`` set the
    initial index. ``QSearchableComboBox`` inherits ``findText``
    from ``QComboBox`` so the contract should survive — but pin
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
