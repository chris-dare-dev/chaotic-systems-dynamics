"""Smoke tests for the transport controls.

We exercise the play / pause / stop / jump-end / scrubber wiring against a
freshly-built ``MainWindow`` with a synthetic trajectory injected directly
into ``_on_sim_finished``. These tests are gated behind
``CHAOTIC_GUI_TESTS_USE_DISPLAY=1`` (see ``tests/gui/conftest.py``).
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")


def _synthetic_trajectory(n: int = 60) -> SimpleNamespace:
    t = np.linspace(0.0, 5.0, n)
    y = np.column_stack(
        [np.cos(t), np.sin(t), 0.1 * t]
    )
    return SimpleNamespace(t=t, y=y, state_dim=3)


def _make_window(qtbot):  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)
    return window


def test_transport_panel_exists(qtbot) -> None:  # type: ignore[no-untyped-def]
    """All five transport widgets are present and start disabled."""

    window = _make_window(qtbot)
    assert window.play_button is not None
    assert window.stop_button is not None
    assert window.jump_end_button is not None
    assert window.speed_box is not None
    assert window.frame_scrubber is not None
    assert window.time_label is not None
    # Before any trajectory lands, transport is disabled.
    assert not window.play_button.isEnabled()
    assert not window.stop_button.isEnabled()
    assert not window.jump_end_button.isEnabled()
    assert not window.frame_scrubber.isEnabled()


def test_transport_enables_after_sim_finished(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    traj = _synthetic_trajectory(60)

    # Pause / disable the timer immediately afterwards so the test isn't racy.
    window._on_sim_finished(traj)  # noqa: SLF001 — testing internals deliberately
    window._pause()  # noqa: SLF001

    assert window.play_button.isEnabled()
    assert window.stop_button.isEnabled()
    assert window.jump_end_button.isEnabled()
    assert window.frame_scrubber.isEnabled()
    # Scrubber range matches the trajectory frame count - 1.
    assert window.frame_scrubber.minimum() == 0
    assert window.frame_scrubber.maximum() == 59


def test_jump_to_end_seeks_renderer(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    window._on_sim_finished(_synthetic_trajectory(40))  # noqa: SLF001
    window._pause()  # noqa: SLF001

    window._on_jump_to_end()  # noqa: SLF001
    assert window._current_frame_index == 39  # noqa: SLF001
    assert window.frame_scrubber.value() == 39
    assert window._current_renderer.current_frame == 40  # noqa: SLF001


def test_stop_rewinds_to_zero(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    window._on_sim_finished(_synthetic_trajectory(40))  # noqa: SLF001
    window._pause()  # noqa: SLF001

    window._seek_to(20)  # noqa: SLF001
    assert window._current_frame_index == 20  # noqa: SLF001
    window._on_stop()  # noqa: SLF001
    assert window._current_frame_index == 0  # noqa: SLF001
    assert window.frame_scrubber.value() == 0
    assert not window._is_playing  # noqa: SLF001


def test_scrubber_value_seeks_renderer(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    window._on_sim_finished(_synthetic_trajectory(50))  # noqa: SLF001
    window._pause()  # noqa: SLF001

    window.frame_scrubber.setValue(25)
    assert window._current_frame_index == 25  # noqa: SLF001
    # Underlying renderer also advanced.
    assert window._current_renderer.current_frame == 26  # noqa: SLF001


def test_anim_tick_advances_frame(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    window._on_sim_finished(_synthetic_trajectory(200))  # noqa: SLF001
    window._pause()  # noqa: SLF001

    window._seek_to(0)  # noqa: SLF001
    start = window._current_frame_index  # noqa: SLF001
    # Force a non-trivial stride EQUAL TO the per-tick cap so the test
    # is deterministic regardless of how the cap is configured. (The
    # cap exists so dense trajectories never teleport — see
    # ``_MAX_STRIDE``; the previous version of this test pinned a
    # stride > cap, but the cap shrank as sub-frame interpolation
    # landed.)
    window._frames_per_tick_base = float(window._MAX_STRIDE)  # noqa: SLF001
    window._speed_multiplier = 1.0  # noqa: SLF001
    window._is_playing = True  # noqa: SLF001
    window._on_anim_tick()  # noqa: SLF001
    assert window._current_frame_index == start + window._MAX_STRIDE  # noqa: SLF001
    window._is_playing = False  # noqa: SLF001


def test_anim_tick_caps_stride(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Per-tick stride is clamped to ``_MAX_STRIDE`` regardless of base."""

    window = _make_window(qtbot)
    window._on_sim_finished(_synthetic_trajectory(200))  # noqa: SLF001
    window._pause()  # noqa: SLF001
    window._seek_to(0)  # noqa: SLF001
    start = window._current_frame_index  # noqa: SLF001
    window._frames_per_tick_base = 1000.0  # absurd; should be capped  # noqa: SLF001
    window._speed_multiplier = 1.0  # noqa: SLF001
    window._is_playing = True  # noqa: SLF001
    window._on_anim_tick()  # noqa: SLF001
    cap = window._MAX_STRIDE  # noqa: SLF001
    assert window._current_frame_index == start + cap  # noqa: SLF001
    window._is_playing = False  # noqa: SLF001


def test_speed_change_changes_multiplier(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    # The presets are 0.25, 0.5, 1, 2, 4, 8.
    target_idx = window.speed_box.findData(4.0)
    assert target_idx >= 0
    window.speed_box.setCurrentIndex(target_idx)
    assert window._speed_multiplier == pytest.approx(4.0)  # noqa: SLF001
