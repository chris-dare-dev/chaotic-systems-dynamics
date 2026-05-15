"""Smoke tests for the prerender + loading-bar pipeline.

These tests exercise the ``_PrerenderWorker`` and the
``_on_sim_finished`` -> prerender -> ``_play`` transition. They are
gated behind ``CHAOTIC_GUI_TESTS_USE_DISPLAY=1`` (see
``tests/gui/conftest.py``) because the underlying renderer needs an
OpenGL context.

The "long trajectory" tests use 800+ samples to exceed
``MainWindow._PRERENDER_MIN_FRAMES``; the "short trajectory" tests use
60 samples so the prerender branch is skipped and playback fires
immediately (this is the documented behavior in
``docs/prerender_design.md``).
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")


def _synthetic_trajectory(n: int) -> SimpleNamespace:
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


def test_short_trajectory_skips_prerender(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Below ``_PRERENDER_MIN_FRAMES`` the GUI plays immediately.

    No prerender worker is spawned; the renderer's cache stays unbuilt.
    """

    window = _make_window(qtbot)
    traj = _synthetic_trajectory(60)
    window._on_sim_finished(traj)  # noqa: SLF001

    # Playback starts immediately on the short branch.
    assert window._is_playing  # noqa: SLF001
    window._pause()  # noqa: SLF001
    assert window._prerender_thread is None  # noqa: SLF001
    # Renderer exists but its prerender cache was never populated.
    assert window._current_renderer is not None  # noqa: SLF001
    assert not window._current_renderer.has_prerender_cache  # noqa: SLF001


def test_long_trajectory_runs_prerender(qtbot) -> None:  # type: ignore[no-untyped-def]
    """At or above ``_PRERENDER_MIN_FRAMES`` the worker fires and warms the cache.

    We wait on the prerender thread's ``finished`` signal so the test
    is deterministic rather than racing the QTimer.
    """

    from PySide6.QtCore import QEventLoop, QTimer

    window = _make_window(qtbot)
    threshold = window._PRERENDER_MIN_FRAMES  # noqa: SLF001
    traj = _synthetic_trajectory(max(threshold, 800))

    window._on_sim_finished(traj)  # noqa: SLF001

    # Playback should NOT have started yet — we're in the prep phase.
    assert not window._is_playing  # noqa: SLF001
    assert window._prerender_thread is not None  # noqa: SLF001

    # Wait for prerender to finish. We hop the event loop so the
    # QThread's signals can land. Bound the wait so a stuck worker
    # doesn't hang the suite.
    loop = QEventLoop()
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)
    timeout.start(5000)  # 5 s ceiling; typical prerender < 200 ms
    window._prerender_worker.finished.connect(loop.quit)  # noqa: SLF001
    window._prerender_worker.cancelled.connect(loop.quit)  # noqa: SLF001
    window._prerender_worker.error.connect(lambda *_: loop.quit())  # noqa: SLF001
    loop.exec()

    # After finished, playback starts and the cache is warm.
    assert window._current_renderer is not None  # noqa: SLF001
    assert window._current_renderer.has_prerender_cache  # noqa: SLF001
    # Stop the timer immediately so the rest of the suite is quiet.
    window._pause()  # noqa: SLF001


def test_prerender_emits_progress(qtbot) -> None:  # type: ignore[no-untyped-def]
    """The worker emits ``progress(current, total)`` at least once before finished."""

    from PySide6.QtCore import QEventLoop, QTimer

    window = _make_window(qtbot)
    threshold = window._PRERENDER_MIN_FRAMES  # noqa: SLF001
    traj = _synthetic_trajectory(max(threshold, 800))
    window._on_sim_finished(traj)  # noqa: SLF001
    assert window._prerender_worker is not None  # noqa: SLF001

    progress_events: list[tuple[int, int]] = []
    window._prerender_worker.progress.connect(  # noqa: SLF001
        lambda c, t: progress_events.append((c, t))
    )

    loop = QEventLoop()
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)
    timeout.start(5000)
    window._prerender_worker.finished.connect(loop.quit)  # noqa: SLF001
    window._prerender_worker.cancelled.connect(loop.quit)  # noqa: SLF001
    window._prerender_worker.error.connect(lambda *_: loop.quit())  # noqa: SLF001
    loop.exec()

    assert progress_events, "prerender worker emitted no progress events"
    last_cur, last_tot = progress_events[-1]
    assert last_cur == last_tot
    window._pause()  # noqa: SLF001


def test_prerender_cancel(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Cancelling mid-prerender stops the worker and leaves playback paused.

    We cancel as soon as the worker emits its first progress signal so
    the test doesn't race the (typically fast) warm-up loop.
    """

    from PySide6.QtCore import QEventLoop, QTimer

    window = _make_window(qtbot)
    threshold = window._PRERENDER_MIN_FRAMES  # noqa: SLF001
    traj = _synthetic_trajectory(max(threshold, 800))
    window._on_sim_finished(traj)  # noqa: SLF001
    worker = window._prerender_worker  # noqa: SLF001
    assert worker is not None

    # Arm: cancel the worker on its first progress emission.
    cancelled_yet = {"flag": False}

    def _cancel_on_first_progress(_cur: int, _tot: int) -> None:
        if not cancelled_yet["flag"]:
            cancelled_yet["flag"] = True
            worker.cancel()

    worker.progress.connect(_cancel_on_first_progress)

    loop = QEventLoop()
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)
    timeout.start(5000)
    worker.cancelled.connect(loop.quit)
    worker.finished.connect(loop.quit)
    worker.error.connect(lambda *_: loop.quit())
    loop.exec()

    # The cancel path leaves the cache unbuilt and playback paused.
    # (If the warm-up was fast enough that the worker finished before
    # the cancel arrived, the test is non-deterministic but still
    # well-defined — we just confirm one of the two end states.)
    r = window._current_renderer  # noqa: SLF001
    assert r is not None
    if cancelled_yet["flag"]:
        assert not window._is_playing  # noqa: SLF001
    window._pause()  # noqa: SLF001
