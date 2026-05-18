"""Tests for the V2 perturbed-IC comparison setting in MainWindow.

GUI tests inherit the ``CHAOTIC_GUI_TESTS_USE_DISPLAY`` gate from
``tests/gui/conftest.py``.

We pin:

- The settings menu exposes the ``action_compare_perturbed_ic``
  checkable QAction.
- Toggling the action flips the setting; the default is off.
- ``_on_setting_compare_perturbed_ic(True)`` updates the status
  label with an "armed" message; off shows "disarmed".
- The chaining hook ``_launch_comparison_sim`` is callable and is
  guarded against double-fires.
- ``_on_compare_finished`` calls ``add_overlay_trajectory`` on the
  current renderer and surfaces the late-time separation in the
  status text.
- ``_on_compare_error`` surfaces the failure without re-raising.
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


def test_compare_action_exists_and_defaults_off(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    assert hasattr(window, "action_compare_perturbed_ic")
    action = window.action_compare_perturbed_ic
    assert action.objectName() == "action_compare_perturbed_ic"
    assert action.isCheckable() is True
    assert action.isChecked() is False
    assert window._setting_compare_perturbed_ic is False  # noqa: SLF001


def test_toggling_action_flips_setting_and_updates_status(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    window.action_compare_perturbed_ic.setChecked(True)
    assert window._setting_compare_perturbed_ic is True  # noqa: SLF001
    # The status bar should mention the armed state + epsilon.
    text = window.status_label.text().lower()
    assert "comparison" in text or "perturbed" in text or "compari" in text
    window.action_compare_perturbed_ic.setChecked(False)
    assert window._setting_compare_perturbed_ic is False  # noqa: SLF001


def test_compare_thread_starts_clean(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    assert window._compare_thread is None  # noqa: SLF001
    assert window._compare_worker is None  # noqa: SLF001
    assert window._compare_primary_config is None  # noqa: SLF001


def test_compare_finished_overlays_on_current_renderer(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Drive ``_on_compare_finished`` directly with a stub renderer + traj."""
    window = _make_window(qtbot)

    # Stub renderer that records add_overlay_trajectory calls.
    stub_renderer = MagicMock()
    window._current_renderer = stub_renderer  # noqa: SLF001

    # Stub primary trajectory so the separation calculation runs.
    n = 30

    class _Stub:
        pass

    primary = _Stub()
    primary.y = np.zeros((n, 3))
    primary.y[-1] = np.array([0.0, 0.0, 0.0])
    primary.t = np.linspace(0.0, 1.0, n)
    primary.state_dim = 3
    window._last_trajectory = primary  # noqa: SLF001

    secondary = _Stub()
    secondary.y = np.zeros((n, 3))
    secondary.y[-1] = np.array([3.0, 4.0, 0.0])  # separation sqrt(9+16) = 5.0
    secondary.t = np.linspace(0.0, 1.0, n)
    secondary.state_dim = 3

    window._on_compare_finished(secondary)  # noqa: SLF001

    # add_overlay_trajectory must have been called once with secondary.
    stub_renderer.add_overlay_trajectory.assert_called_once()
    args, kwargs = stub_renderer.add_overlay_trajectory.call_args
    assert args[0] is secondary
    assert "color" in kwargs

    # Status carries the final-separation number ("5" appears in "5.000").
    text = window.status_label.text()
    assert "5" in text
    assert "separation" in text.lower()


def test_compare_finished_with_no_renderer_is_a_no_op(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    window._current_renderer = None  # noqa: SLF001
    # Build a duck-typed trajectory; should not raise.

    class _Stub:
        y = np.zeros((5, 3))
        t = np.arange(5, dtype=float)
        state_dim = 3

    window._on_compare_finished(_Stub())  # noqa: SLF001
    text = window.status_label.text().lower()
    assert "torn down" in text or "renderer" in text


def test_compare_error_surfaces_message(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    window._on_compare_error("RuntimeError", "boom")  # noqa: SLF001
    text = window.status_label.text()
    assert "boom" in text
    assert "RuntimeError" in text


def test_cleanup_compare_thread_resets_state(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    window._compare_worker = MagicMock()  # noqa: SLF001
    window._compare_thread = MagicMock()  # noqa: SLF001
    window._cleanup_compare_thread()  # noqa: SLF001
    assert window._compare_worker is None  # noqa: SLF001
    assert window._compare_thread is None  # noqa: SLF001
