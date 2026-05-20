"""Tests for FU-015 — drag-to-scrub parameter spinboxes.

Pre-FU-015 every parameter adjustment required either typing or
multiple click-on-arrow steps. ``_ScrubSpinBox`` adds Blender-style
drag-to-scrub: hover, press, drag horizontally — the value
changes continuously in step-per-pixel increments. Shift = 0.1×
(fine), Ctrl = snap to nearest ``singleStep``.

The class is a strict :class:`QDoubleSpinBox` subclass so
existing callers (``_param_widgets[name].value()``, keyboard
arrow stepping, the FU-019 readout chip wired to
``valueChanged``, the E2 live-preview pipeline) keep working
unchanged.

Coverage:

- :class:`_ScrubSpinBox` inherits :class:`QDoubleSpinBox` (no
  API surface regression).
- A horizontal drag of ``N`` pixels changes the value by
  ``N × singleStep`` (the canonical Blender convention).
- A Shift-drag uses 0.1× sensitivity (fine scrub).
- A Ctrl-drag snaps the value to the nearest ``singleStep``
  multiple.
- A press-release with no movement does *not* change the value
  (click semantics preserved).
- After a drag gesture, ``stepBy(±1)`` still works — i.e. the
  keyboard up/down arrow path is intact (challenger §10 MAJOR
  mitigation).
- ``releaseMouse`` is called unconditionally on release
  (mitigation #1: no persistent mouse-grab).
- ``mousePressEvent`` moves focus to the spinbox so the FU-016
  focus ring tracks the drag (CC-04 mitigation).
- Values clamp to ``[minimum(), maximum()]`` during a drag past
  the range.
- The ``_ParamWidget`` in the main window uses
  ``_ScrubSpinBox`` as its underlying ``_spin`` (the substitution
  the synthesis prescribes).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")


# ---------------------------------------------------------------------------
# Helpers — synthetic mouse events
# ---------------------------------------------------------------------------


def _make_mouse_event(widget, kind, x, *, modifiers=None):  # type: ignore[no-untyped-def]
    """Build a synthetic ``QMouseEvent`` at ``(x, 10)`` of ``widget``."""

    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    pos = QPointF(float(x), 10.0)
    global_pos = QPointF(
        widget.mapToGlobal(pos.toPoint()).x(),
        widget.mapToGlobal(pos.toPoint()).y(),
    )
    button = Qt.MouseButton.LeftButton
    buttons = button if kind != QEvent.Type.MouseButtonRelease else Qt.MouseButton.NoButton
    return QMouseEvent(
        kind,
        pos,
        global_pos,
        button,
        buttons,
        modifiers or Qt.KeyboardModifier.NoModifier,
    )


def _drag(spinbox, dx_px, *, modifiers=None):  # type: ignore[no-untyped-def]
    """Synthesise a press → move(dx) → release gesture on ``spinbox``."""

    from PySide6.QtCore import QEvent

    start_x = 20.0
    end_x = start_x + float(dx_px)
    spinbox.mousePressEvent(
        _make_mouse_event(spinbox, QEvent.Type.MouseButtonPress, start_x)
    )
    spinbox.mouseMoveEvent(
        _make_mouse_event(
            spinbox, QEvent.Type.MouseMove, end_x, modifiers=modifiers
        )
    )
    spinbox.mouseReleaseEvent(
        _make_mouse_event(spinbox, QEvent.Type.MouseButtonRelease, end_x)
    )


# ---------------------------------------------------------------------------
# Type contract
# ---------------------------------------------------------------------------


def test_scrub_spinbox_inherits_qdoublespinbox(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Drop-in contract: every QDoubleSpinBox API surface keeps working."""

    from PySide6.QtWidgets import QDoubleSpinBox

    from chaotic_systems.gui._scrub_spinbox import _ScrubSpinBox

    spin = _ScrubSpinBox()
    qtbot.addWidget(spin)
    try:
        assert isinstance(spin, QDoubleSpinBox)
    finally:
        spin.deleteLater()


# ---------------------------------------------------------------------------
# Plain drag — 1 step per pixel
# ---------------------------------------------------------------------------


def test_plain_drag_changes_value_by_pixels_times_step(qtbot) -> None:  # type: ignore[no-untyped-def]
    """A horizontal drag of ``N`` px shifts value by ``N × singleStep``."""

    from chaotic_systems.gui._scrub_spinbox import _ScrubSpinBox

    spin = _ScrubSpinBox()
    qtbot.addWidget(spin)
    try:
        spin.setRange(-100.0, 100.0)
        spin.setDecimals(3)
        spin.setSingleStep(0.5)
        spin.setValue(10.0)

        _drag(spin, dx_px=20)

        # 20 px × 0.5 step = +10.0 → final value 20.0.
        assert spin.value() == pytest.approx(20.0, rel=1e-6), (
            f"FU-015 — plain drag of 20 px @ step=0.5 should land at "
            f"20.0; got {spin.value()}"
        )
    finally:
        spin.deleteLater()


def test_negative_drag_decreases_value(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Dragging left subtracts."""

    from chaotic_systems.gui._scrub_spinbox import _ScrubSpinBox

    spin = _ScrubSpinBox()
    qtbot.addWidget(spin)
    try:
        spin.setRange(-100.0, 100.0)
        spin.setSingleStep(1.0)
        spin.setValue(50.0)
        _drag(spin, dx_px=-15)
        assert spin.value() == pytest.approx(35.0, rel=1e-6)
    finally:
        spin.deleteLater()


# ---------------------------------------------------------------------------
# Modifier keys
# ---------------------------------------------------------------------------


def test_shift_drag_uses_fine_scale(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Shift-drag multiplies the per-pixel step by ``SCALE_FINE`` (0.1×)."""

    from PySide6.QtCore import Qt

    from chaotic_systems.gui._scrub_spinbox import _ScrubSpinBox

    spin = _ScrubSpinBox()
    qtbot.addWidget(spin)
    try:
        spin.setRange(0.0, 100.0)
        spin.setSingleStep(1.0)
        spin.setValue(10.0)
        _drag(spin, dx_px=20, modifiers=Qt.KeyboardModifier.ShiftModifier)
        # 20 px × 1.0 × 0.1 (fine) = +2.0 → 12.0.
        assert spin.value() == pytest.approx(12.0, rel=1e-6), (
            f"FU-015 — Shift-drag must use 0.1× sensitivity; got {spin.value()}"
        )
    finally:
        spin.deleteLater()


def test_ctrl_drag_snaps_to_single_step(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Ctrl-drag snaps the result to the nearest ``singleStep`` multiple."""

    from PySide6.QtCore import Qt

    from chaotic_systems.gui._scrub_spinbox import _ScrubSpinBox

    spin = _ScrubSpinBox()
    qtbot.addWidget(spin)
    try:
        spin.setRange(0.0, 100.0)
        spin.setSingleStep(1.0)
        spin.setDecimals(3)
        spin.setValue(10.0)
        # Drag 7.3 px (in a fractional sense via non-integer step) →
        # use step=0.3 so dx=7 yields +2.1 → snap to 2.0 → final 12.0.
        spin.setSingleStep(0.3)
        spin.setValue(10.0)
        _drag(spin, dx_px=7, modifiers=Qt.KeyboardModifier.ControlModifier)
        # 7 × 0.3 = 2.1 → start 10.0 → 12.1 → snap to 0.3-multiple
        # → round(12.1 / 0.3) * 0.3 = 40 * 0.3 = 12.0.
        assert spin.value() == pytest.approx(12.0, rel=1e-3), (
            f"FU-015 — Ctrl-drag must snap to singleStep; got {spin.value()}"
        )
    finally:
        spin.deleteLater()


# ---------------------------------------------------------------------------
# Click semantics — no drag, no value change
# ---------------------------------------------------------------------------


def test_press_release_without_movement_does_not_change_value(qtbot) -> None:  # type: ignore[no-untyped-def]
    """A click (press → release with no movement) leaves the value untouched."""

    from PySide6.QtCore import QEvent

    from chaotic_systems.gui._scrub_spinbox import _ScrubSpinBox

    spin = _ScrubSpinBox()
    qtbot.addWidget(spin)
    try:
        spin.setRange(0.0, 100.0)
        spin.setSingleStep(1.0)
        spin.setValue(42.0)

        x = 20.0
        spin.mousePressEvent(
            _make_mouse_event(spin, QEvent.Type.MouseButtonPress, x)
        )
        spin.mouseReleaseEvent(
            _make_mouse_event(spin, QEvent.Type.MouseButtonRelease, x)
        )
        assert spin.value() == pytest.approx(42.0), (
            "FU-015 — a click without horizontal movement must not "
            "change the value (click semantics preserved)"
        )
    finally:
        spin.deleteLater()


def test_sub_threshold_drag_does_not_change_value(qtbot) -> None:  # type: ignore[no-untyped-def]
    """A 1-pixel jitter under ``DRAG_THRESHOLD_PX`` is not a drag."""

    from chaotic_systems.gui._scrub_spinbox import _ScrubSpinBox

    spin = _ScrubSpinBox()
    qtbot.addWidget(spin)
    try:
        spin.setRange(0.0, 100.0)
        spin.setSingleStep(1.0)
        spin.setValue(50.0)
        _drag(spin, dx_px=1)  # under the 2 px threshold
        assert spin.value() == pytest.approx(50.0), (
            "FU-015 — sub-threshold movement must not engage the scrub"
        )
    finally:
        spin.deleteLater()


# ---------------------------------------------------------------------------
# Keyboard equivalence — challenger §10 MAJOR mitigation
# ---------------------------------------------------------------------------


def test_keyboard_step_still_works_after_drag(qtbot) -> None:  # type: ignore[no-untyped-def]
    """``stepBy(±1)`` (the arrow-key path) is intact after a drag gesture."""

    from chaotic_systems.gui._scrub_spinbox import _ScrubSpinBox

    spin = _ScrubSpinBox()
    qtbot.addWidget(spin)
    try:
        spin.setRange(0.0, 100.0)
        spin.setSingleStep(1.0)
        spin.setValue(10.0)
        _drag(spin, dx_px=5)  # value now 15.0
        # The arrow-key path runs stepBy(+1) / stepBy(-1).
        spin.stepBy(1)
        assert spin.value() == pytest.approx(16.0), (
            "FU-015 — after a drag, stepBy(+1) must still step by "
            "singleStep; the drag handler must not break the keyboard "
            "navigation path (challenger §10 MAJOR)."
        )
        spin.stepBy(-1)
        assert spin.value() == pytest.approx(15.0)
    finally:
        spin.deleteLater()


# ---------------------------------------------------------------------------
# Mouse-grab + focus contracts
# ---------------------------------------------------------------------------


def test_release_event_unconditionally_releases_mouse(qtbot) -> None:  # type: ignore[no-untyped-def]
    """``mouseReleaseEvent`` calls ``releaseMouse`` even on a click.

    The challenger's mitigation #1: a persistent mouse grab past
    the gesture causes every subsequent click anywhere in the
    window to land back on this spinbox. ``releaseMouse`` is a
    no-op when no grab is held, so unconditional calling is safe
    and the contract is "after release, no grab is held by this
    widget".
    """

    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    from chaotic_systems.gui._scrub_spinbox import _ScrubSpinBox

    spin = _ScrubSpinBox()
    qtbot.addWidget(spin)
    try:
        spin.setRange(0.0, 100.0)
        spin.setValue(0.0)
        spin.grabMouse()
        x = 20.0
        spin.mouseReleaseEvent(
            _make_mouse_event(spin, QEvent.Type.MouseButtonRelease, x)
        )
        # After release the application-wide mouse grabber should
        # not be this spinbox.
        assert QApplication.mouseButtons() is not None  # sanity
        # ``mouseGrabber()`` returns the widget currently grabbing
        # the mouse, or None.
        from PySide6.QtWidgets import QWidget

        grabber = QWidget.mouseGrabber()
        assert grabber is not spin, (
            "FU-015 — after mouseReleaseEvent, the spinbox must not "
            "be the active mouse grabber (mitigation #1)"
        )
    finally:
        spin.deleteLater()


def test_mouse_press_calls_set_focus(qtbot) -> None:  # type: ignore[no-untyped-def]
    """``mousePressEvent`` calls ``setFocus`` so the focus ring tracks the drag.

    CC-04 mitigation. We can't reliably assert ``hasFocus()`` is
    True afterward because focus can be denied if the spinbox's
    top-level window isn't active (which happens when this test
    runs alongside other GUI tests that hold their own windows).
    Instead we spy on the ``setFocus`` call directly — if the
    handler invokes it, the contract is satisfied; whether the
    OS grants focus is a separate concern outside our control.
    """

    from PySide6.QtCore import QEvent

    from chaotic_systems.gui._scrub_spinbox import _ScrubSpinBox

    spin = _ScrubSpinBox()
    qtbot.addWidget(spin)
    try:
        spin.setRange(0.0, 100.0)
        spin.setValue(0.0)

        calls: list[object] = []
        original_set_focus = spin.setFocus

        def spy(*args, **kwargs):  # type: ignore[no-untyped-def]
            calls.append((args, kwargs))
            return original_set_focus(*args, **kwargs)

        spin.setFocus = spy  # type: ignore[assignment]

        x = 20.0
        spin.mousePressEvent(
            _make_mouse_event(spin, QEvent.Type.MouseButtonPress, x)
        )
        assert len(calls) >= 1, (
            "FU-015 — mousePressEvent must call setFocus on the "
            "spinbox so the FU-016 focus ring follows the drag "
            "(CC-04 mitigation)"
        )
    finally:
        spin.deleteLater()


# ---------------------------------------------------------------------------
# Range clamping
# ---------------------------------------------------------------------------


def test_drag_clamps_to_maximum(qtbot) -> None:  # type: ignore[no-untyped-def]
    """A drag past ``maximum()`` clamps at the upper bound."""

    from chaotic_systems.gui._scrub_spinbox import _ScrubSpinBox

    spin = _ScrubSpinBox()
    qtbot.addWidget(spin)
    try:
        spin.setRange(0.0, 10.0)
        spin.setSingleStep(1.0)
        spin.setValue(8.0)
        _drag(spin, dx_px=50)  # 50 × 1.0 = +50, but max is 10.0.
        assert spin.value() == pytest.approx(10.0), (
            "FU-015 — drag past maximum must clamp"
        )
    finally:
        spin.deleteLater()


def test_drag_clamps_to_minimum(qtbot) -> None:  # type: ignore[no-untyped-def]
    """A drag past ``minimum()`` clamps at the lower bound."""

    from chaotic_systems.gui._scrub_spinbox import _ScrubSpinBox

    spin = _ScrubSpinBox()
    qtbot.addWidget(spin)
    try:
        spin.setRange(0.0, 10.0)
        spin.setSingleStep(1.0)
        spin.setValue(2.0)
        _drag(spin, dx_px=-50)
        assert spin.value() == pytest.approx(0.0)
    finally:
        spin.deleteLater()


# ---------------------------------------------------------------------------
# _ParamWidget substitution (the synthesis-prescribed wire-up)
# ---------------------------------------------------------------------------


def test_param_widget_spin_is_scrub_spinbox(qtbot) -> None:  # type: ignore[no-untyped-def]
    """``_ParamWidget._spin`` is a ``_ScrubSpinBox`` instance post-FU-015."""

    from chaotic_systems.gui._scrub_spinbox import _ScrubSpinBox
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    win = Window()
    qtbot.addWidget(win)
    try:
        # Pick any registered parameter widget. The Lorenz default
        # sigma / rho / beta are always present after init.
        param_widgets = win._param_widgets  # noqa: SLF001
        assert len(param_widgets) > 0, (
            "FU-015 test setup — main window has no param widgets"
        )
        for name, widget in param_widgets.items():
            assert isinstance(widget._spin, _ScrubSpinBox), (  # noqa: SLF001
                f"FU-015 — _ParamWidget[{name!r}]._spin must be a "
                f"_ScrubSpinBox; got {type(widget._spin).__name__}"  # noqa: SLF001
            )
            # And value()/setValue() still work via the inherited API.
            current = widget.value()
            assert isinstance(current, float)
    finally:
        win.close()
