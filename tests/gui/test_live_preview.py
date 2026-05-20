"""Tests for the E2 live parameter-slider preview (+ FU-017 promotion).

GUI tests inherit the ``CHAOTIC_GUI_TESTS_USE_DISPLAY`` gate from
``tests/gui/conftest.py``.

We pin:

- The main toolbar carries a checkable ``action_live_preview``
  QAction with ``text="Auto"``, an ``mdi6.flash`` icon, and a
  position adjacent to Run (FU-017 — the Settings menu still hosts
  the same QAction as a secondary discoverability path).
- Toggling the action flips ``_setting_live_preview`` and the
  status label echoes the armed/disarmed message.
- With the setting off, a parameter spinbox change does NOT start
  the debounce timer.
- With the setting on, a parameter spinbox change DOES start the
  debounce timer.
- ``_on_preview_finished`` attaches the trajectory but leaves
  ``_last_trajectory`` untouched (the export / diagnostics
  contract is preserved).
- ``_on_preview_error`` surfaces the message in the status bar
  without raising.
- ``_cancel_preview_in_flight`` disconnects the worker's signals
  so a stale result can't paint over a newer preview.
- ``_cleanup_preview_thread`` resets the thread/worker references.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")


def _make_window(qtbot):  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)
    return window


def test_live_preview_action_exists_and_defaults_off(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    assert hasattr(window, "action_live_preview")
    action = window.action_live_preview
    assert action.objectName() == "action_live_preview"
    assert action.isCheckable() is True
    assert action.isChecked() is False
    assert window._setting_live_preview is False  # noqa: SLF001


def test_toggle_flips_setting_and_updates_status(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    window.action_live_preview.setChecked(True)
    assert window._setting_live_preview is True  # noqa: SLF001
    text = window.status_label.text().lower()
    assert "preview" in text or "live" in text
    window.action_live_preview.setChecked(False)
    assert window._setting_live_preview is False  # noqa: SLF001


def test_preview_timer_initial_state(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    # Single-shot at the documented debounce interval.
    assert window._preview_timer.isSingleShot() is True  # noqa: SLF001
    assert window._preview_timer.interval() == window._preview_debounce_ms  # noqa: SLF001
    # Inactive until a param change fires it.
    assert window._preview_timer.isActive() is False  # noqa: SLF001


def test_param_change_with_setting_off_does_not_start_timer(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    window._setting_live_preview = False  # noqa: SLF001
    # Pick any registered parameter and fire its valueChanged via
    # the spinbox setValue (slightly different from the current value
    # to ensure the signal actually emits).
    if not window._param_widgets:  # noqa: SLF001
        pytest.skip("current system has no parameters to tweak")
    key = next(iter(window._param_widgets))  # noqa: SLF001
    pw = window._param_widgets[key]  # noqa: SLF001
    new_val = pw.value() + 0.1
    pw._spin.setValue(new_val)  # noqa: SLF001
    assert window._preview_timer.isActive() is False  # noqa: SLF001


def test_param_change_with_setting_on_starts_timer(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    window._setting_live_preview = True  # noqa: SLF001
    if not window._param_widgets:  # noqa: SLF001
        pytest.skip("current system has no parameters to tweak")
    key = next(iter(window._param_widgets))  # noqa: SLF001
    pw = window._param_widgets[key]  # noqa: SLF001
    pw._spin.setValue(pw.value() + 0.1)  # noqa: SLF001
    assert window._preview_timer.isActive() is True  # noqa: SLF001
    # Don't let the timer actually fire during the test — we already
    # validated debounce arming.
    window._preview_timer.stop()  # noqa: SLF001


def test_preview_finished_does_not_update_last_trajectory(qtbot) -> None:  # type: ignore[no-untyped-def]
    """The export / diagnostics contract: only explicit Runs persist."""
    window = _make_window(qtbot)
    # Pin a sentinel trajectory as the user's "last full run".
    sentinel = object()
    window._last_trajectory = sentinel  # noqa: SLF001

    # Build a duck-typed preview trajectory.
    class _Stub:
        state_dim = 3
        system = "Stub"
        t = np.linspace(0.0, 1.0, 30)
        y = np.zeros((30, 3))

    window._on_preview_finished(_Stub())  # noqa: SLF001
    # _last_trajectory must still be the sentinel — preview does not
    # overwrite the user's explicit Run output.
    assert window._last_trajectory is sentinel  # noqa: SLF001


def test_preview_error_surfaces_in_status_bar(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    window._on_preview_error("RuntimeError", "diverged")  # noqa: SLF001
    text = window.status_label.text()
    assert "diverged" in text
    assert "RuntimeError" in text


def test_cleanup_preview_thread_resets_state(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    window._preview_worker = MagicMock()  # noqa: SLF001
    window._preview_thread = MagicMock()  # noqa: SLF001
    window._cleanup_preview_thread()  # noqa: SLF001
    assert window._preview_worker is None  # noqa: SLF001
    assert window._preview_thread is None  # noqa: SLF001


def test_cancel_preview_in_flight_disconnects_signals(qtbot) -> None:  # type: ignore[no-untyped-def]
    """A stale preview's signals must be unwired so the result is dropped."""
    window = _make_window(qtbot)
    worker = MagicMock()
    window._preview_worker = worker  # noqa: SLF001
    window._cancel_preview_in_flight()  # noqa: SLF001
    # Disconnect must have been attempted for both signals.
    worker.finished.disconnect.assert_called_once_with(
        window._on_preview_finished  # noqa: SLF001
    )
    worker.error.disconnect.assert_called_once_with(
        window._on_preview_error  # noqa: SLF001
    )


def test_setting_off_stops_timer_and_cancels_in_flight(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Toggling the setting off mid-debounce must drop the pending preview."""
    window = _make_window(qtbot)
    window._setting_live_preview = True  # noqa: SLF001
    window._preview_timer.start(window._preview_debounce_ms)  # noqa: SLF001
    assert window._preview_timer.isActive()  # noqa: SLF001
    # Also pin a fake in-flight worker so we can confirm cancellation.
    fake_worker = MagicMock()
    window._preview_worker = fake_worker  # noqa: SLF001
    window._on_setting_live_preview(False)  # noqa: SLF001
    assert window._preview_timer.isActive() is False  # noqa: SLF001
    fake_worker.finished.disconnect.assert_called_once()


def test_fire_preview_suppressed_when_full_sim_in_flight(qtbot) -> None:  # type: ignore[no-untyped-def]
    """A real Run takes precedence — preview must skip."""
    window = _make_window(qtbot)
    window._setting_live_preview = True  # noqa: SLF001
    # Stub a fake live sim thread.
    window._sim_thread = MagicMock()  # noqa: SLF001
    # The pre-fire worker count.
    window._preview_worker = None  # noqa: SLF001
    window._fire_preview()  # noqa: SLF001
    # No worker should have been built.
    assert window._preview_worker is None  # noqa: SLF001
    # Clean up so other tests don't see a fake thread reference.
    window._sim_thread = None  # noqa: SLF001


# ---------------------------------------------------------------------------
# FU-017 — toolbar promotion
# ---------------------------------------------------------------------------


def test_live_preview_is_on_the_main_toolbar(qtbot) -> None:  # type: ignore[no-untyped-def]
    """FU-017 — the Auto pill lands on the main toolbar.

    Promoting the toggle to a top-level affordance is the headline
    change. The QAction must appear in the toolbar's ``actions()``
    list so users see the pill at startup instead of needing two
    clicks into the Settings dropdown.
    """
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)

    toolbar = window.findChild(object, "toolbar_main")
    assert toolbar is not None, "main toolbar must exist"
    toolbar_actions = list(toolbar.actions())
    assert window.action_live_preview in toolbar_actions, (
        "FU-017 — action_live_preview must appear in the main "
        "toolbar's actions() list (was Settings-menu-only pre-FU-017)"
    )


def test_live_preview_pill_text_is_auto(qtbot) -> None:  # type: ignore[no-untyped-def]
    """FU-017 — the pill's display text is "Auto".

    Synthesis-prescribed label. The pre-FU-017 menu entry's text
    was "Live preview (slider drag re-simulates)" — too long for a
    toolbar pill.
    """
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)

    assert window.action_live_preview.text() == "Auto", (
        f"FU-017 — action text should be 'Auto', got "
        f"{window.action_live_preview.text()!r}"
    )


def test_live_preview_pill_has_lightning_icon(qtbot) -> None:  # type: ignore[no-untyped-def]
    """FU-017 — the pill carries the mdi6.flash glyph from qtawesome.

    The icon mapping is centralised in ``icons.STEM_TO_GLYPH``
    (FU-005); ``"live-preview"`` resolves to ``mdi6.flash``. The
    icon must be non-null and rasterisable at toolbar size.
    """
    from PySide6.QtCore import QSize

    from chaotic_systems.gui.icons import STEM_TO_GLYPH
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)

    assert STEM_TO_GLYPH["live-preview"] == "mdi6.flash"
    icon = window.action_live_preview.icon()
    assert not icon.isNull(), "FU-017 — Auto pill must carry an icon"
    pix = icon.pixmap(QSize(18, 18))
    assert not pix.isNull(), (
        "FU-017 — Auto pill icon must rasterise at toolbar size (18 px)"
    )


def test_live_preview_pill_sits_adjacent_to_run(qtbot) -> None:  # type: ignore[no-untyped-def]
    """FU-017 — synthesis-prescribed position: directly after Run.

    The explicit Run action and the Auto-Apply pill read as a unit
    ("run on demand" vs "run on every parameter change"), so they
    sit next to each other in the toolbar's action order.
    """
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)

    toolbar = window.findChild(object, "toolbar_main")
    actions = list(toolbar.actions())
    # Filter out separators / widget-actions; we only care about
    # the action objects that have an objectName.
    named = [a for a in actions if a.objectName()]
    object_names = [a.objectName() for a in named]
    assert "transport_run" in object_names, (
        "sanity — Run action must be on the toolbar"
    )
    assert "action_live_preview" in object_names, (
        "FU-017 — Auto pill must be on the toolbar"
    )
    run_idx = object_names.index("transport_run")
    auto_idx = object_names.index("action_live_preview")
    assert auto_idx == run_idx + 1, (
        f"FU-017 — Auto pill must sit directly after Run; got "
        f"run at index {run_idx}, auto at index {auto_idx}"
    )
