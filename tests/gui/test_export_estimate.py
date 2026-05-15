"""Tests for the pre-export size estimate math + chip wiring.

The size estimate is a tiny pure-math helper plus a chip / tooltip
surface. The math is unit-tested directly; the chip wiring is exercised
behind ``CHAOTIC_GUI_TESTS_USE_DISPLAY=1`` via a synthetic trajectory.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")


def _synthetic_trajectory(n: int) -> SimpleNamespace:
    t = np.linspace(0.0, n / 30.0, n)
    y = np.column_stack([np.cos(t), np.sin(t), 0.1 * t])
    return SimpleNamespace(t=t, y=y, state_dim=3)


def _make_window(qtbot):  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)
    return window


def test_format_export_estimate_zero_frames(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    text = window._format_export_estimate(  # noqa: SLF001
        n_frames=0, fps=30, mb_per_sec=2.1
    )
    assert text == "—"


def test_format_export_estimate_ten_seconds(qtbot) -> None:  # type: ignore[no-untyped-def]
    """4000 frames @ 30 fps caps at the worker's 10 s clip (≈ 21 MB)."""

    window = _make_window(qtbot)
    text = window._format_export_estimate(  # noqa: SLF001
        n_frames=4000, fps=30, mb_per_sec=2.1
    )
    # The worker hard-codes 10 s and the empirical bytes/sec is 2.1 MB.
    assert "21.0 MB" in text
    assert "4000 frames" in text
    assert "10.0 s" in text
    assert "@ 30 fps" in text


def test_format_export_estimate_short_trajectory(qtbot) -> None:  # type: ignore[no-untyped-def]
    """A 60-frame trajectory at 30 fps gives a 2-second clip ~4 MB."""

    window = _make_window(qtbot)
    text = window._format_export_estimate(  # noqa: SLF001
        n_frames=60, fps=30, mb_per_sec=2.1
    )
    assert "60 frames" in text
    assert "2.0 s" in text


def test_estimate_chip_hidden_initially(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    # ``isHidden`` is the right property here — ``isVisible`` is False
    # whenever the parent window itself isn't shown.
    assert window.export_estimate_chip.isHidden()
    tip = window._transport_actions["action_export"].toolTip()
    assert "Run a simulation first" in tip


def test_estimate_chip_after_sim(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    traj = _synthetic_trajectory(200)
    window._on_sim_finished(traj)  # noqa: SLF001
    window._pause()  # noqa: SLF001

    assert not window.export_estimate_chip.isHidden()
    txt = window.export_estimate_chip.text()
    assert "MB" in txt
    assert "200 frames" in txt
    # Tooltip on the export action carries the estimate too.
    tip = window._transport_actions["action_export"].toolTip()
    assert "Estimated:" in tip
