"""Tests for FU-008 — "Analyse…" toolbar submenu.

Pre-FU-008 the five analytics actions (Bifurcation / Phase
portrait / Recurrence / Basins / Poincaré) lived as flat
``QAction``s on the main toolbar, consuming ~300 px of horizontal
real estate at 1400 px and *truncating off entirely* at 900 px
(visual-brief F-08).

Post-FU-008 they're nested under a single ``QToolButton``
("Analyse…") with a popup ``QMenu``. ParaView's "Filters" menu /
napari's "Plugins" menu vocabulary.

Coverage:

- The ``button_analyse`` ``QToolButton`` exists on the toolbar.
- Its popup mode is ``InstantPopup`` (one-click opens menu) and
  its focus policy is ``StrongFocus`` (challenger MINOR a11y
  mitigation — Tab-reachable).
- The popup menu holds exactly the 5 analytics actions, in the
  spec order.
- **CC-01 mitigation** — all 5 analytics actions remain in
  ``window.transport_actions()`` under their canonical keys
  (``action_bifurcation``, ``action_phase_portrait``,
  ``action_recurrence``, ``action_basins``, ``action_poincare``).
  Five panel test files depend on this resolution path; breaking
  it would cascade across the suite.
- The analytics actions are *not* on the top-level toolbar
  (otherwise FU-008 would be no-op).
- The toolbar still surfaces the non-analytics actions
  (Run / Pause / Stop / Jump-end / Export / Reset view /
  Theme / Auto) at top level.
- The Analyse… button carries an icon (the FU-005 contract — no
  bare-text toolbar buttons).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")


_ANALYSE_KEYS = (
    "action_bifurcation",
    "action_phase_portrait",
    "action_recurrence",
    "action_basins",
    "action_poincare",
)


@pytest.fixture
def window(qtbot):  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    win = Window()
    qtbot.addWidget(win)
    yield win
    win.close()


# ---------------------------------------------------------------------------
# Button exists + a11y contract
# ---------------------------------------------------------------------------


def test_analyse_button_exists_on_toolbar(window) -> None:  # type: ignore[no-untyped-def]
    """The FU-008 ``button_analyse`` ``QToolButton`` is on the main toolbar."""

    from PySide6.QtWidgets import QToolBar, QToolButton

    toolbar = window.findChild(QToolBar, "toolbar_main")
    assert toolbar is not None, "toolbar_main missing from window"

    btn = toolbar.findChild(QToolButton, "button_analyse")
    assert btn is not None, (
        "FU-008 — button_analyse QToolButton missing from toolbar_main"
    )
    assert btn.text() == "Analyse…"


def test_analyse_button_popup_mode_is_instant(window) -> None:  # type: ignore[no-untyped-def]
    """A single click opens the popup (``InstantPopup``)."""

    from PySide6.QtWidgets import QToolButton

    btn = window.findChild(QToolButton, "button_analyse")
    assert btn is not None
    assert btn.popupMode() == QToolButton.ToolButtonPopupMode.InstantPopup, (
        "FU-008 — Analyse button must use InstantPopup so a single "
        "click opens the menu (no separate arrow). "
        "Challenger §6 MINOR a11y note."
    )


def test_analyse_button_is_keyboard_focusable(window) -> None:  # type: ignore[no-untyped-def]
    """Tab navigation reaches the Analyse button (``StrongFocus``)."""

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QToolButton

    btn = window.findChild(QToolButton, "button_analyse")
    assert btn is not None
    assert btn.focusPolicy() == Qt.FocusPolicy.StrongFocus, (
        "FU-008 — Analyse button must be Tab-reachable. "
        "Challenger §6 MINOR a11y note."
    )


def test_analyse_button_carries_an_icon(window) -> None:  # type: ignore[no-untyped-def]
    """The Analyse… button has a non-null icon (FU-005 / AP-04 contract)."""

    from PySide6.QtWidgets import QToolButton

    btn = window.findChild(QToolButton, "button_analyse")
    assert btn is not None
    assert not btn.icon().isNull(), (
        "FU-008 — Analyse… button must ship an icon. AP-04: no "
        "toolbar action without an icon."
    )


# ---------------------------------------------------------------------------
# Menu contents
# ---------------------------------------------------------------------------


def test_analyse_menu_has_five_analytics_actions(window) -> None:  # type: ignore[no-untyped-def]
    """The popup menu holds exactly the 5 analytics actions, in spec order."""

    from PySide6.QtWidgets import QMenu, QToolButton

    btn = window.findChild(QToolButton, "button_analyse")
    assert btn is not None
    menu = btn.menu()
    assert isinstance(menu, QMenu), "FU-008 — button_analyse must carry a QMenu"
    assert menu.objectName() == "menu_analyse"

    object_names = [act.objectName() for act in menu.actions()]
    assert object_names == list(_ANALYSE_KEYS), (
        f"FU-008 — Analyse menu actions must be exactly "
        f"{_ANALYSE_KEYS!r} in order; got {object_names!r}"
    )


# ---------------------------------------------------------------------------
# CC-01 mitigation: actions remain in transport_actions() dict
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("action_key", _ANALYSE_KEYS)
def test_analytics_actions_remain_in_transport_actions(window, action_key) -> None:  # type: ignore[no-untyped-def]
    """CC-01 — every analytics action is still in ``transport_actions()``.

    Five panel test files (test_phase_panel.py:163,
    test_basin_panel.py:144, test_recurrence_panel.py:140,
    test_poincare_panel.py:338, test_bifurcation_panel.py:143)
    resolve their open-dialog action via
    ``window.transport_actions()[<key>]``. Breaking the key
    cascade-breaks all five.
    """

    actions = window.transport_actions()
    assert action_key in actions, (
        f"FU-008 / CC-01 — {action_key!r} must remain in "
        f"transport_actions() even though it now lives under the "
        f"Analyse… submenu. Pre-existing panel tests depend on this key."
    )
    assert actions[action_key].objectName() == action_key


# ---------------------------------------------------------------------------
# Actions are NOT on the top-level toolbar
# ---------------------------------------------------------------------------


def test_analytics_actions_not_on_top_level_toolbar(window) -> None:  # type: ignore[no-untyped-def]
    """The 5 analytics actions are removed from the top-level toolbar.

    Otherwise FU-008 would be a no-op — both the dropdown and the
    flat buttons would be visible.
    """

    from PySide6.QtWidgets import QToolBar

    toolbar = window.findChild(QToolBar, "toolbar_main")
    assert toolbar is not None

    toolbar_action_names = {
        act.objectName() for act in toolbar.actions() if act.objectName()
    }
    for key in _ANALYSE_KEYS:
        assert key not in toolbar_action_names, (
            f"FU-008 — {key!r} should no longer be a direct toolbar "
            f"action; it's now nested under Analyse… submenu."
        )


def test_non_analytics_actions_still_on_toolbar(window) -> None:  # type: ignore[no-untyped-def]
    """The remaining transport actions still surface at the top level."""

    from PySide6.QtWidgets import QToolBar

    toolbar = window.findChild(QToolBar, "toolbar_main")
    assert toolbar is not None

    toolbar_action_names = {
        act.objectName() for act in toolbar.actions() if act.objectName()
    }
    expected = {
        "transport_run",
        "transport_pause",
        "transport_stop",
        "transport_jump_end",
        "action_export",
        "action_reset_view",
        "action_toggle_theme",
        "action_live_preview",
    }
    missing = expected - toolbar_action_names
    assert not missing, (
        f"FU-008 — non-analytics toolbar actions must survive the "
        f"submenu refactor; missing {missing!r}"
    )
