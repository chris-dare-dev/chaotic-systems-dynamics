"""Drag-to-scrub :class:`QDoubleSpinBox` subclass (FU-015).

A :class:`_ScrubSpinBox` behaves identically to a stock
:class:`QDoubleSpinBox` except that a horizontal drag inside the
edit field adjusts the value continuously — no click-then-step
needed.

Modifier-key conventions follow the Blender 5.1 manual and the
Houdini convention (both surfaced as inspiration P03 / C2 in
``inspiration-brief.md §2``):

==================  ============================================
Modifier            Effect
==================  ============================================
*(none)*            1 ``singleStep`` per logical pixel of drag
Shift               0.1 ``singleStep`` per pixel (10× fine)
Ctrl                Snap to the nearest ``singleStep`` multiple
==================  ============================================

Keyboard navigation is preserved: arrow keys still call
:meth:`QAbstractSpinBox.stepBy` via the unchanged parent
implementation, so a non-pointer user keeps the existing
up / down stepping path (challenger §FU-015 §10 — the MAJOR
keyboard-equivalence concern). The drag handler never touches
``keyPressEvent``.

The class explicitly:

1. Calls :meth:`setFocus` on ``mousePressEvent`` so the FU-016
   focus ring follows the drag (challenger §CC-04 mitigation).
2. Calls :meth:`releaseMouse` unconditionally in
   ``mouseReleaseEvent`` so a focus-grab cannot persist past
   the gesture (challenger §FU-015 mitigation #1).
3. Treats a sub-threshold press-release as a *click* (no value
   change) and delegates to the parent so the spinbox's
   text-field selection / context menu still work.

References
----------
- Blender 5.1 manual — Interface > Numeric Fields > Dragging.
- Houdini help — "Slider fields support drag-to-scrub".
- Inspiration brief §2 P03 / §4 C2.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QDoubleSpinBox, QWidget

__all__ = ["_ScrubSpinBox"]


class _ScrubSpinBox(QDoubleSpinBox):
    """A QDoubleSpinBox that supports horizontal drag-to-scrub.

    Drop-in replacement: every public API
    (:meth:`value`, :meth:`setValue`, :meth:`setRange`,
    :meth:`setDecimals`, :meth:`setSingleStep`,
    :attr:`valueChanged` signal, :meth:`stepBy`, etc.) is the
    plain-class behaviour, only ``mousePressEvent`` /
    ``mouseMoveEvent`` / ``mouseReleaseEvent`` are augmented.
    """

    #: Pixel distance the cursor must travel before the press
    #: is interpreted as a drag rather than a click. Smaller
    #: values feel "twitchy"; larger values delay the scrub
    #: feedback. 2 px matches Blender's default drag threshold.
    DRAG_THRESHOLD_PX: int = 2

    #: ``Shift``-held drag multiplies the per-pixel step by
    #: this fraction for fine adjustment. 0.1 matches the
    #: Blender / Houdini convention.
    SCALE_FINE: float = 0.1

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # State carried across the three mouse events. ``None``
        # signals "no drag in progress" — the events fall through
        # to the parent implementation.
        self._drag_anchor_x: float | None = None
        self._drag_start_value: float = 0.0
        self._drag_active: bool = False
        # Hint the affordance with the horizontal-resize cursor.
        # Same cursor Blender uses on numeric drag-fields; signals
        # "I take horizontal drags" without a visual icon.
        self.setCursor(Qt.CursorShape.SizeHorCursor)

    # ------------------------------------------------------------------
    # Mouse event overrides
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self._drag_anchor_x = float(event.position().x())
            self._drag_start_value = float(self.value())
            self._drag_active = False
            # CC-04 mitigation — without this the FU-016 focus
            # ring stays on the previously-focused widget while
            # the user drags the spinbox. setFocus before the
            # drag classification is intentional: any press
            # gesture, drag or click, should move focus.
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            # Accept the press but do NOT super-dispatch yet —
            # the parent class would start a text-field selection
            # that would fight the scrub. The release handler
            # re-dispatches if no drag occurred (click semantics).
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if self._drag_anchor_x is None:
            super().mouseMoveEvent(event)
            return
        # ``event.position()`` reports in logical pixels (Qt
        # auto-divides physical-pixel coordinates by the device
        # pixel ratio on Hi-DPI surfaces). A logical-pixel delta
        # gives consistent perceived sensitivity across DPRs:
        # a 1-cm physical drag on a 96-dpi display and on a
        # 192-dpi display both produce the same logical-pixel
        # delta (per Qt docs). The challenger's §FU-015 §5 note
        # about DPR scaling is satisfied by Qt's automatic
        # logical-coordinate normalisation; no manual
        # ``devicePixelRatioF()`` division is needed.
        dx = float(event.position().x()) - self._drag_anchor_x
        if not self._drag_active:
            if abs(dx) < self.DRAG_THRESHOLD_PX:
                return
            self._drag_active = True

        mods = event.modifiers()
        per_pixel_step = float(self.singleStep())
        if mods & Qt.KeyboardModifier.ShiftModifier:
            per_pixel_step *= self.SCALE_FINE

        new_value = self._drag_start_value + dx * per_pixel_step

        if mods & Qt.KeyboardModifier.ControlModifier:
            base = float(self.singleStep())
            if base > 0.0:
                new_value = round(new_value / base) * base

        # Clamp to the spinbox's declared range — the underlying
        # ``setValue`` would clamp anyway, but doing it here keeps
        # the value the scrub computes truthful for future deltas
        # (e.g. dragging far past max then back).
        lo = float(self.minimum())
        hi = float(self.maximum())
        new_value = max(lo, min(hi, new_value))
        self.setValue(new_value)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        was_dragging = self._drag_active
        anchor = self._drag_anchor_x
        # Reset state BEFORE any super-dispatch so a re-entrant
        # event sees a clean slate.
        self._drag_anchor_x = None
        self._drag_active = False
        # Mitigation #1 — unconditional release. If the spinbox
        # had grabbed the mouse during the drag, leaving it grabbed
        # past the gesture causes every subsequent click on any
        # widget to also land here. ``releaseMouse`` is a no-op
        # when no grab is held, so unconditional calling is safe.
        self.releaseMouse()
        if anchor is None or not was_dragging:
            # Sub-threshold press-release = click semantics. Let
            # the parent class handle it (text-field selection,
            # context menu request, etc.).
            super().mouseReleaseEvent(event)
            return
        event.accept()
