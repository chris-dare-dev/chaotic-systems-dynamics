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
    """Wall-clock pacing advances the playhead by elapsed * rate.

    Under the iteration-4 wall-clock pacing, the per-tick advance is
    derived from ``elapsed = now - _play_wall_start`` rather than from
    a fixed stride. Synthetic 200-frame trajectory is below the
    prerender threshold (500), so the legacy integer-frame branch runs.
    """

    import time

    window = _make_window(qtbot)
    window._on_sim_finished(_synthetic_trajectory(200))  # noqa: SLF001
    window._pause()  # noqa: SLF001
    window._seek_to(0)  # noqa: SLF001

    # Simulate that playback started 100 ms ago. At the default
    # ``_frames_per_tick_base`` cadence, 100 ms of wall time should
    # advance the playhead by a measurable, deterministic amount.
    window._speed_multiplier = 1.0  # noqa: SLF001
    window._play_position_start = 0.0  # noqa: SLF001
    window._play_wall_start = time.perf_counter() - 0.1  # noqa: SLF001
    window._is_playing = True  # noqa: SLF001

    window._on_anim_tick()  # noqa: SLF001
    # Position advanced past start, didn't snap to the end.
    assert 0 < window._current_frame_index < 199  # noqa: SLF001
    window._is_playing = False  # noqa: SLF001


def test_anim_tick_snaps_to_end_after_full_playback(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Wall-clock pacing self-corrects: elapsed > playback duration snaps to end.

    Replaces the legacy ``test_anim_tick_caps_stride`` from the
    stride-based model. Under wall-clock pacing there is no
    per-tick stride cap; instead, an elapsed time greater than
    ``target_playback_seconds`` lands the playhead at the final
    frame and pauses.
    """

    import time

    window = _make_window(qtbot)
    window._on_sim_finished(_synthetic_trajectory(200))  # noqa: SLF001
    window._pause()  # noqa: SLF001
    window._seek_to(0)  # noqa: SLF001
    window._speed_multiplier = 1.0  # noqa: SLF001
    # Pretend playback started before the dawn of time — elapsed is
    # effectively infinite, so the tick should snap to the last frame
    # and stop the timer.
    window._play_position_start = 0.0  # noqa: SLF001
    window._play_wall_start = time.perf_counter() - 1e6  # noqa: SLF001
    window._is_playing = True  # noqa: SLF001

    window._on_anim_tick()  # noqa: SLF001
    assert window._current_frame_index == 199  # noqa: SLF001
    assert not window._is_playing  # noqa: SLF001 - auto-paused at end


def test_speed_change_changes_multiplier(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    # The presets are 0.25, 0.5, 1, 2, 4, 8.
    target_idx = window.speed_box.findData(4.0)
    assert target_idx >= 0
    window.speed_box.setCurrentIndex(target_idx)
    assert window._speed_multiplier == pytest.approx(4.0)  # noqa: SLF001
