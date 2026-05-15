"""Tests for the flowing LaTeX widget.

These verify that ``_FlowingLatex`` never produces a rendered pixmap whose
*logical* width exceeds the panel's available width — i.e. the widget
scales equations down rather than overflowing horizontally.

The widget itself is defined inside ``_build_window_class`` so the tests
fetch it through the same lazy loader the main window uses. Like the
other GUI tests it requires a real display
(``CHAOTIC_GUI_TESTS_USE_DISPLAY=1``).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("matplotlib")


@pytest.fixture()
def FlowingLatex():  # type: ignore[no-untyped-def]
    """Return the ``_FlowingLatex`` class from the cached window builder."""

    from chaotic_systems.gui.main_window import _build_window_class

    # Build the class so its closure is captured. We then reach into the
    # closure (Qt closures are real Python closures) to grab the inner
    # class. There isn't a public accessor — but exposing one would only
    # be useful to this test, so we live with the SLF001 access.
    _build_window_class()
    # The inner class isn't bound to the module namespace, so we ship a
    # tiny test-only window and read off the widget instance to fetch the
    # class.
    from chaotic_systems.gui.main_window import _build_window_class as builder

    Window = builder()
    return Window, _make_widget_class_extractor(Window)


def _make_widget_class_extractor(Window):  # type: ignore[no-untyped-def]
    """Return a callable that builds a fresh ``_FlowingLatex`` instance."""

    from PySide6.QtWidgets import QApplication

    def make(parent=None):  # type: ignore[no-untyped-def]
        # Ensure a QApplication is up so widgets can be instantiated.
        app = QApplication.instance() or QApplication([])
        _ = app
        win = Window()
        # The window's `.ode_widget` is a `_FlowingLatex` instance — we use
        # it as a representative and reset its state for each test.
        widget = win.ode_widget
        return win, widget

    return make


def test_widget_renders_single_equation(FlowingLatex, qtbot) -> None:  # type: ignore[no-untyped-def]
    """A simple inline equation renders one row with a non-null pixmap."""

    _Window, make = FlowingLatex
    win, widget = make()
    qtbot.addWidget(win)
    win.resize(800, 600)

    widget.set_latex(
        r"\dot{x} = \sigma (y - x)", color="#000000", fontsize=13, dpi=120, dpr=1.0
    )
    assert widget.has_pixmap_rows()


def test_widget_unrolls_aligned_environment(FlowingLatex, qtbot) -> None:  # type: ignore[no-untyped-def]
    """``\\begin{aligned}`` blocks produce one row per equation."""

    _Window, make = FlowingLatex
    win, widget = make()
    qtbot.addWidget(win)
    win.resize(800, 600)

    widget.set_latex(
        r"\begin{aligned}"
        r"\dot{x} &= \sigma (y - x) \\"
        r"\dot{y} &= x (\rho - z) - y \\"
        r"\dot{z} &= x y - \beta z"
        r"\end{aligned}",
        color="#000000",
        fontsize=13,
        dpi=120,
        dpr=1.0,
    )
    # Three rows for the three equations.
    assert len(widget._rows) == 3  # noqa: SLF001


def test_widget_never_overflows_narrow_panel(FlowingLatex, qtbot) -> None:  # type: ignore[no-untyped-def]
    """At narrow widths the displayed pixmap fits the available panel width."""

    _Window, make = FlowingLatex
    win, widget = make()
    qtbot.addWidget(win)
    win.show()
    # Render a long single-row equation that would naturally exceed 200 px.
    widget.set_latex(
        r"\dot{q}_1 = \frac{p_1 - p_2 \cos(\theta_1 - \theta_2)}"
        r"{m_1 \ell_1^2 + m_2 \ell_1^2 \sin^2(\theta_1 - \theta_2)}",
        color="#000000",
        fontsize=13,
        dpi=120,
        dpr=1.0,
    )

    # Force the row into a *narrow* panel and let the resize event fire.
    target_w = 240
    widget.resize(target_w, widget.height())
    for row in widget._rows:  # noqa: SLF001
        row.resize(target_w, row.height())
        row._reflow()  # noqa: SLF001 — force a synchronous reflow
    # The largest displayed pixmap (in logical pixels) must fit inside the
    # widget's current width.
    displayed = widget.max_row_pixmap_width()
    assert displayed <= target_w + 2, (
        f"row pixmap width {displayed} exceeds available {target_w}"
    )


def test_widget_clears_on_empty_latex(FlowingLatex, qtbot) -> None:  # type: ignore[no-untyped-def]
    _Window, make = FlowingLatex
    win, widget = make()
    qtbot.addWidget(win)

    widget.set_latex(r"\dot x = -x", color="#000000", fontsize=13, dpi=120, dpr=1.0)
    assert widget.has_pixmap_rows()
    widget.set_latex("", color="#000000", fontsize=13, dpi=120, dpr=1.0)
    assert not widget.has_pixmap_rows()
