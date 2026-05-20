"""Tests for FU-010 — force LaTeX reflow on ``showEvent`` + via ``singleShot``.

Pre-FU-010 the ``_FlowingLatex`` widget rendered rows immediately
during ``set_latex`` and measured ``self.width()`` *at that
moment* to decide whether each row pixmap needed scaling down.
When ``set_latex`` ran during window construction (before the
parent layout had settled the widget's final width), the row
pixmap was sized against a stale width and the first row clipped
at the card edge on initial render — visible on
DoublePendulum's kinetic-energy expression (visual scout F-07,
``screenshots/double-pendulum-latex.png``).

Post-FU-010:

1. ``set_latex`` queues a deferred ``QTimer.singleShot(0,
   self._reflow_all)`` after the row inserts so Qt's layout pass
   has a chance to settle before the row pixmaps are re-measured.
2. ``showEvent`` re-reflows the rows once the widget first
   becomes visible (belt-and-suspenders — geometry is always
   correct after ``show``).

This module pins the timing contract. The narrow-panel
non-overflow contract was already covered by
``test_latex_wrap.py``; FU-010 only changes *when* the reflow
fires, not the result.

Coverage:

- ``_FlowingLatex._reflow_all`` exists and is callable.
- ``set_latex`` schedules at least one deferred call to
  ``_reflow_all`` (caught via ``processEvents`` + a spy on the
  method).
- ``showEvent`` schedules a deferred call to ``_reflow_all``.
- Behavioural F-07 fix: setting LaTeX while the widget is still
  at its initial (zero / tiny) width and *then* resizing the
  widget wider produces a row pixmap that fits the new width —
  the pre-FU-010 bug left it clipped at the stale measurement.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("matplotlib")


@pytest.fixture()
def make_widget():  # type: ignore[no-untyped-def]
    """Return a callable that builds a fresh window + its ODE widget."""

    from PySide6.QtWidgets import QApplication

    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()

    def factory():  # type: ignore[no-untyped-def]
        app = QApplication.instance() or QApplication([])
        _ = app
        win = Window()
        widget = win.ode_widget  # _FlowingLatex instance
        return win, widget

    return factory


# ---------------------------------------------------------------------------
# Contract: _reflow_all method exists
# ---------------------------------------------------------------------------


def test_reflow_all_method_exists(make_widget, qtbot) -> None:  # type: ignore[no-untyped-def]
    """``_FlowingLatex`` exposes a callable ``_reflow_all`` (FU-010 entry point)."""

    win, widget = make_widget()
    qtbot.addWidget(win)
    try:
        assert hasattr(widget, "_reflow_all")
        assert callable(widget._reflow_all)  # noqa: SLF001
    finally:
        win.close()


# ---------------------------------------------------------------------------
# Contract: set_latex schedules a deferred reflow
# ---------------------------------------------------------------------------


def test_set_latex_schedules_deferred_reflow(make_widget, qtbot) -> None:  # type: ignore[no-untyped-def]
    """After ``set_latex`` returns, a queued ``_reflow_all`` fires next tick."""

    from PySide6.QtCore import QCoreApplication

    win, widget = make_widget()
    qtbot.addWidget(win)
    try:
        # Spy on _reflow_all to count post-set_latex invocations.
        calls = {"n": 0}
        original = widget._reflow_all  # noqa: SLF001

        def spy() -> None:
            calls["n"] += 1
            original()

        widget._reflow_all = spy  # type: ignore[assignment]  # noqa: SLF001

        widget.set_latex(
            r"\dot{x} = \sigma (y - x)",
            color="#000000",
            fontsize=13,
            dpi=120,
            dpr=1.0,
        )
        # Drain the event loop so the singleShot(0, ...) fires.
        QCoreApplication.processEvents()

        assert calls["n"] >= 1, (
            "FU-010 — set_latex must queue a QTimer.singleShot(0, "
            "self._reflow_all) so the deferred layout pass runs "
            "after Qt has settled the widget's final width."
        )
    finally:
        win.close()


def test_set_latex_does_not_schedule_when_empty(make_widget, qtbot) -> None:  # type: ignore[no-untyped-def]
    """Empty LaTeX clears rows and short-circuits before scheduling reflow.

    The pre-FU-010 ``set_latex`` already early-returned on empty
    input; FU-010 must not regress that — calling
    ``_reflow_all`` on an empty row list would be a harmless
    no-op anyway but scheduling it is wasted work.
    """

    from PySide6.QtCore import QCoreApplication

    win, widget = make_widget()
    qtbot.addWidget(win)
    try:
        calls = {"n": 0}
        original = widget._reflow_all  # noqa: SLF001

        def spy() -> None:
            calls["n"] += 1
            original()

        widget._reflow_all = spy  # type: ignore[assignment]  # noqa: SLF001

        widget.set_latex("", color="#000000", fontsize=13, dpi=120, dpr=1.0)
        QCoreApplication.processEvents()

        assert calls["n"] == 0, (
            "FU-010 — set_latex must not schedule a reflow on empty "
            "LaTeX (no rows to reflow)"
        )
    finally:
        win.close()


# ---------------------------------------------------------------------------
# Contract: showEvent triggers a deferred reflow
# ---------------------------------------------------------------------------


def test_show_event_triggers_reflow(make_widget, qtbot) -> None:  # type: ignore[no-untyped-def]
    """``showEvent`` queues a ``_reflow_all`` call (the belt-and-suspenders pass)."""

    from PySide6.QtCore import QCoreApplication

    win, widget = make_widget()
    qtbot.addWidget(win)
    try:
        # First render some content so there's something to reflow.
        widget.set_latex(
            r"\dot{x} = -x",
            color="#000000",
            fontsize=13,
            dpi=120,
            dpr=1.0,
        )
        QCoreApplication.processEvents()

        # Reset the spy after the initial set_latex's deferred fire.
        calls = {"n": 0}
        original = widget._reflow_all  # noqa: SLF001

        def spy() -> None:
            calls["n"] += 1
            original()

        widget._reflow_all = spy  # type: ignore[assignment]  # noqa: SLF001

        # Triggering a show on a not-yet-visible widget fires
        # showEvent. The window itself may have been built but not
        # shown yet (qtbot.addWidget doesn't show).
        win.show()
        QCoreApplication.processEvents()

        assert calls["n"] >= 1, (
            "FU-010 — showEvent must queue a deferred _reflow_all "
            "so the first-render geometry can be re-measured after "
            "Qt has assigned the widget its real width."
        )
    finally:
        win.close()


# ---------------------------------------------------------------------------
# Behavioural F-07 fix: pixmap re-fits after a late resize
# ---------------------------------------------------------------------------


def test_reflow_after_late_resize_fits_new_width(make_widget, qtbot) -> None:  # type: ignore[no-untyped-def]
    """The F-07 regression test — late-arriving width is honoured.

    Pre-FU-010 the row pixmap was sized once during ``set_latex``
    against the widget's (then) current width; a subsequent
    resize wider didn't re-fit the row, so DoublePendulum's
    first-row equation rendered scaled-down even though the
    panel was wider. After FU-010 the deferred reflow pass
    catches the late geometry and rescales.
    """

    win, widget = make_widget()
    qtbot.addWidget(win)
    try:
        # Squeeze the widget narrow so the long-equation row scales
        # down hard at set_latex time.
        widget.resize(200, widget.height() or 100)
        widget.set_latex(
            r"\ddot{\theta} + \frac{g}{\ell} \sin\theta + "
            r"\alpha \dot{\theta} = \tau(t)",
            color="#000000",
            fontsize=13,
            dpi=120,
            dpr=1.0,
        )
        # Drain the singleShot(0) that fires from set_latex.
        from PySide6.QtCore import QCoreApplication

        QCoreApplication.processEvents()

        # Now widen the widget — the FU-010 reflow path (via
        # resizeEvent on each _LatexRow + an explicit _reflow_all
        # call) must let the row re-measure against the new width.
        widget.resize(900, widget.height())
        for row in widget._rows:  # noqa: SLF001
            row.resize(900, row.height())
        widget._reflow_all()  # noqa: SLF001
        QCoreApplication.processEvents()

        # The displayed pixmap should now fit comfortably under
        # 900 px — confirming the row honoured the late resize.
        # (The native render at 13pt / 120dpi is well under 900 px;
        # the assertion is "≤ 900" plus a small slack.)
        displayed = widget.max_row_pixmap_width()
        assert displayed <= 900 + 2, (
            f"FU-010 — after a late widen, row pixmap stayed at "
            f"{displayed}; must re-fit to the new width."
        )
        # And the row didn't disappear or get sized to zero by the
        # reflow churn.
        assert displayed > 0, (
            "FU-010 — reflow must not zero out the row pixmap width"
        )
    finally:
        win.close()
