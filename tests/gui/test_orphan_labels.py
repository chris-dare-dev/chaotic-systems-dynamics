"""Tests for FU-009 — move orphan labels into Diagnostics card.

Pre-FU-009 the left-panel cards rail ended with two orphan
``QLabel`` widgets sitting directly in ``cards_layout``, *not*
inside any card:

- ``status_label`` (empty default text) duplicated the
  ``QStatusBar`` chips at the bottom of the window
  (current-state-critic DV-02).
- ``state_label`` (``y(t_end) = (no simulation yet)``) was a
  diagnostics readout living outside any container —
  inconsistent card-rail rhythm (visual-brief F-03 / F-12).

Post-FU-009:

- ``state_label`` is inside the Diagnostics card as a
  "Last state" row, keeping the canonical
  ``y(t={t_last:.3f}) = [...]`` format
  ``_update_state_label`` already writes. The label gains an
  ``objectName="state_label"`` (was empty pre-FU-009) so the
  FU-014 command palette + ``docs/ui_design.md`` can resolve
  it.
- ``status_label`` is preserved as a Python attribute on the
  window (challenger §7 MAJOR mitigation: 6 test sites in
  ``test_live_preview.py`` + ``test_compare_setting.py`` call
  ``window.status_label.text()``), but it is hidden and *not*
  added to the layout. The QStatusBar at the bottom is the
  authoritative status surface.

Coverage:

- ``window.status_label`` still exists and is a ``QLabel``
  (preserves 6 test sites).
- ``status_label`` is hidden (``isHidden() == True``) so the
  visual orphan-text strip is gone.
- ``status_label`` is *not* a child of the cards-layout column
  (it was removed from the layout, not just hidden).
- ``window.state_label`` still exists and now carries
  ``objectName == "state_label"``.
- ``state_label`` is a descendant of the Diagnostics card —
  ``findChild`` from the diag card resolves it.
- The terminal-state text format is preserved: setting a
  trajectory still produces ``y(t={...}) = [...]`` text via
  ``_update_state_label``.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")


@pytest.fixture
def window(qtbot):  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    win = Window()
    qtbot.addWidget(win)
    yield win
    win.close()


# ---------------------------------------------------------------------------
# status_label — attribute survives but hidden
# ---------------------------------------------------------------------------


def test_status_label_attribute_survives(window) -> None:  # type: ignore[no-untyped-def]
    """``window.status_label`` is still a ``QLabel`` (challenger mitigation).

    6 test sites depend on ``window.status_label.text()``:
    ``test_live_preview.py:62,129`` +
    ``test_compare_setting.py:56,105,121,128``. The attribute
    must survive the visual orphan-label fix.
    """

    from PySide6.QtWidgets import QLabel

    assert hasattr(window, "status_label")
    assert isinstance(window.status_label, QLabel)


def test_status_label_is_hidden(window) -> None:  # type: ignore[no-untyped-def]
    """``status_label`` is hidden so the orphan-text strip is gone.

    Visual scout F-03 / F-12: pre-FU-009 the empty ``status_label``
    rendered as a thin orphan band below the Diagnostics card.
    Post-FU-009 it should not be visible in the layout.
    """

    # ``isHidden()`` works even before the window is shown, which
    # ``isVisible()`` does not. The widget should be explicitly
    # set hidden in the constructor.
    assert window.status_label.isHidden(), (
        "FU-009 — status_label must be hidden so the orphan-text "
        "strip below the cards is gone (visual scout F-03 / F-12)"
    )


def test_status_label_not_in_cards_layout(window) -> None:  # type: ignore[no-untyped-def]
    """``status_label`` is removed from the cards-layout column.

    Just hiding the widget would still leave it in the
    layout's child enumeration; for a clean removal it must
    have been omitted from ``cards_layout.addWidget`` entirely.
    We verify by walking the cards layout (the parent of the
    Parameters / Integrator / Time-range / Diagnostics cards)
    and asserting the status_label is not among its direct
    children.
    """

    # ``status_label`` is parented to ``left_inner`` but never
    # added to a layout. Walking the widget tree up from
    # status_label should not encounter a layout containing
    # the Diagnostics card.
    label = window.status_label
    parent = label.parentWidget()
    # The parent's layout is ``cards_layout``; status_label
    # should not be inside it.
    if parent is not None and parent.layout() is not None:
        layout = parent.layout()
        idx = layout.indexOf(label)
        assert idx < 0, (
            f"FU-009 — status_label must not be in cards_layout "
            f"(found at index {idx})"
        )


# ---------------------------------------------------------------------------
# state_label — now lives inside the Diagnostics card
# ---------------------------------------------------------------------------


def test_state_label_attribute_survives(window) -> None:  # type: ignore[no-untyped-def]
    """``window.state_label`` is still accessible as a Python attribute."""

    from PySide6.QtWidgets import QLabel

    assert hasattr(window, "state_label")
    assert isinstance(window.state_label, QLabel)


def test_state_label_has_object_name(window) -> None:  # type: ignore[no-untyped-def]
    """``state_label`` gained ``objectName="state_label"`` (was empty pre-FU-009).

    FU-014's command palette + ``docs/ui_design.md`` layout-spec
    assertions both look widgets up by ``objectName``; the
    relocation is a good moment to backfill it.
    """

    assert window.state_label.objectName() == "state_label"


def test_state_label_findable_via_object_name(window) -> None:  # type: ignore[no-untyped-def]
    """``window.findChild(QLabel, "state_label")`` resolves it."""

    from PySide6.QtWidgets import QLabel

    label = window.findChild(QLabel, "state_label")
    assert label is window.state_label


def test_state_label_initial_text_preserved(window) -> None:  # type: ignore[no-untyped-def]
    """The terminal-state placeholder format is unchanged."""

    assert window.state_label.text() == "y(t_end) = (no simulation yet)"


def test_state_label_lives_inside_diagnostics_card(window) -> None:  # type: ignore[no-untyped-def]
    """``state_label`` is a descendant of the Diagnostics card.

    The synthesis prescribes "a 'Last state' row inside the
    Diagnostics card". Cards are built via ``_make_card`` as
    :class:`QGroupBox`-es with ``variant="card"``; the title
    text is the groupbox's native :meth:`title` property. We
    walk the ancestor chain upward from ``state_label`` until
    we find a ``QGroupBox`` whose title is ``"Diagnostics"``.
    """

    from PySide6.QtWidgets import QGroupBox

    found_diagnostics_ancestor = False
    widget = window.state_label.parentWidget()
    while widget is not None:
        if isinstance(widget, QGroupBox) and widget.title() == "Diagnostics":
            found_diagnostics_ancestor = True
            break
        widget = widget.parentWidget()
    assert found_diagnostics_ancestor, (
        "FU-009 — state_label must live inside a QGroupBox "
        "whose title is 'Diagnostics' (the Diagnostics card "
        "built by _make_card)"
    )


# ---------------------------------------------------------------------------
# Behavioural regression — _update_state_label still works
# ---------------------------------------------------------------------------


def test_update_state_label_writes_terminal_state(window) -> None:  # type: ignore[no-untyped-def]
    """``_update_state_label(traj)`` still produces the y(t)=[...] text."""

    import types

    import numpy as np

    traj = types.SimpleNamespace(
        t=np.array([0.0, 0.5, 1.0]),
        y=np.array([[1.0, 2.0, 3.0], [1.1, 2.1, 3.1], [1.2, 2.2, 3.2]]),
    )
    window._update_state_label(traj)  # noqa: SLF001
    text = window.state_label.text()
    assert "y(t=" in text and "1.2" in text and "3.2" in text, (
        f"FU-009 — _update_state_label must still produce "
        f"y(t={{...}}) = [v0, ..., vN] text; got {text!r}"
    )
