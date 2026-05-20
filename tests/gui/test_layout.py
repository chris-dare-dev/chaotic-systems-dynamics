"""Layout-contract tests (FU-007).

The main window's central widget is a horizontal ``QSplitter``
hosting three columns: left parameter cards, center 3D viewport,
right Mathematics panel. FU-007 (frontend-uplift 2026-05-19-initial)
changes the left column's stretch factor from ``0`` to ``1`` so the
panel grows proportionally with the window instead of starving at
wide widths — the regression visible in
``.claude/notes/frontend-uplifts/2026-05-19-initial/screenshots/wide.png``.

These tests pin the layout contract so a future change that
restores the zero-stretch behaviour (or accidentally swaps the
ratio) fails immediately.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")


def _find_central_splitter(window):
    """Locate the horizontal three-way splitter at the window's centre."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QSplitter

    central = window.centralWidget()
    assert isinstance(central, QSplitter), (
        f"expected central widget to be QSplitter, got {type(central).__name__}"
    )
    assert central.orientation() == Qt.Orientation.Horizontal
    assert central.count() == 3, (
        f"expected 3-column splitter, got {central.count()} columns"
    )
    return central


def test_splitter_stretch_ratio_is_left_one_viewport_three_right_one() -> None:
    """FU-007 — left panel has stretch=1 (was 0), viewport=3, right=1.

    The ratio ``1 : 3 : 1`` means extra width at wide windows
    distributes 20% / 60% / 20% across the three columns rather
    than the pre-FU-007 0% / 75% / 25% — keeping all three columns
    readable as the window grows.

    ``QSplitter`` doesn't expose a public getter for the per-index
    stretch factor (only ``setStretchFactor``), so we pin the
    contract by parsing the relevant block out of
    ``main_window.py`` directly. Any future swap that re-zeroes
    the left column fails this test immediately.
    """
    import re
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "chaotic_systems"
        / "gui"
        / "main_window.py"
    ).read_text(encoding="utf-8")
    # Locate the splitter-construction block (kept narrow so we
    # don't accidentally match unrelated stretch-factor calls
    # elsewhere in the file).
    block_match = re.search(
        r"splitter\.addWidget\(left\).*?self\.setCentralWidget\(splitter\)",
        source,
        re.DOTALL,
    )
    assert block_match is not None, (
        "could not locate the central-splitter construction block"
    )
    block = block_match.group(0)
    # FU-007 — left column stretch must be 1 (was 0 pre-FU-007).
    assert "splitter.setStretchFactor(0, 1)" in block, (
        "FU-007 — central splitter must call "
        "setStretchFactor(0, 1) (was 0 pre-FU-007; visual-scout F-06)"
    )
    # Viewport stays at stretch=3 (the bulk of the extra width).
    assert "splitter.setStretchFactor(1, 3)" in block, (
        "viewport must keep stretch=3"
    )
    # Right Mathematics panel stays at stretch=1.
    assert "splitter.setStretchFactor(2, 1)" in block, (
        "right Mathematics panel keeps stretch=1"
    )


def test_left_panel_keeps_minimum_width_when_window_shrinks() -> None:
    """At narrow widths the left panel respects its ``setMinimumWidth(300)``.

    The minimum-width contract is separate from the stretch
    contract — even with stretch=1, Qt should refuse to shrink
    the left column below 300 px (the documented minimum that
    keeps the parameter spinboxes operable).
    """
    from chaotic_systems.gui.main_window import build_application

    app, window = build_application([])
    try:
        splitter = _find_central_splitter(window)
        # ``setChildrenCollapsible(False)`` is the line above the
        # stretch-factor calls in main_window.py; verify it's still
        # in effect (FU-007 did not touch it).
        assert not splitter.childrenCollapsible(), (
            "splitter must keep childrenCollapsible(False) so the "
            "left panel can't be dragged to zero width"
        )
        # The left widget's minimum width is documented as 300 px.
        left_widget = splitter.widget(0)
        assert left_widget.minimumWidth() >= 300, (
            f"left panel minimum width regressed: got "
            f"{left_widget.minimumWidth()}, expected >= 300"
        )
    finally:
        window.close()
        assert app is not None
