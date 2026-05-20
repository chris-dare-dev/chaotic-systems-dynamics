"""Tests for FU-020 — scrubber timestamp tooltip while dragging.

The transport bar's scrubber is now a ``_ScrubSlider`` subclass of
``QSlider`` that surfaces a floating ``QToolTip`` at the cursor on
``mousePressEvent`` and ``mouseMoveEvent`` while the slider is being
driven. The status bar still shows the same readout; the tooltip
keeps it close to the interaction point. Borrowed from Ableton 12
and ParaView animation timelines (inspiration brief P12).

Coverage:

- ``_ScrubSlider`` is a ``QSlider`` subclass with a
  ``set_format_fn`` injection point.
- A pre-Run window's scrubber tooltip text is empty (suppresses
  the tooltip when no trajectory exists).
- ``_scrubber_tooltip_text`` formats the canonical
  ``"t = X.XXX / X.XXX s    frame I / N"`` string for an
  arbitrary frame index.
- The main window's ``frame_scrubber`` is an instance of
  ``_ScrubSlider`` (not a plain ``QSlider``) — pins the migration
  contract.
- The slider doesn't crash on mouse events when no format fn is
  set (defensive — the slot may be cleared during tear-down).
- All imports stay at module level (AP-03 — current-state-critic
  warned against ``from PySide6...`` inside event handlers).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")


def _make_window(qtbot):  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)
    return window


# ---------------------------------------------------------------------------
# Class shape + main-window wiring
# ---------------------------------------------------------------------------


def test_scrubslider_is_a_qslider_subclass(qtbot) -> None:  # type: ignore[no-untyped-def]
    """The side-attached ``_ScrubSlider`` IS-A ``QSlider``."""

    from PySide6.QtWidgets import QSlider

    from chaotic_systems.gui.main_window import _build_window_class

    cls = _build_window_class()
    scrub_cls = cls._ScrubSlider  # noqa: SLF001
    assert issubclass(scrub_cls, QSlider), (
        f"FU-020 — _ScrubSlider must subclass QSlider; "
        f"MRO is {[c.__name__ for c in scrub_cls.__mro__]}"
    )


def test_frame_scrubber_uses_scrubslider_subclass(qtbot) -> None:  # type: ignore[no-untyped-def]
    """The main window's ``frame_scrubber`` is now a ``_ScrubSlider``.

    Pre-FU-020 it was a plain ``QSlider``. The migration pins
    that the transport panel actually uses the subclass.
    """

    from chaotic_systems.gui.main_window import _build_window_class

    cls = _build_window_class()
    window = cls()
    qtbot.addWidget(window)
    try:
        scrub_cls = cls._ScrubSlider  # noqa: SLF001
        assert isinstance(window.frame_scrubber, scrub_cls), (
            f"FU-020 — frame_scrubber should be _ScrubSlider; "
            f"got {type(window.frame_scrubber).__name__}"
        )
    finally:
        window.close()


def test_scrubslider_format_fn_default_is_none(qtbot) -> None:  # type: ignore[no-untyped-def]
    """A freshly-constructed ``_ScrubSlider`` has no format fn.

    The host must inject the formatter explicitly (the widget
    stays decoupled from any specific data model).
    """

    from PySide6.QtCore import Qt

    from chaotic_systems.gui.main_window import _build_window_class

    cls = _build_window_class()
    scrub_cls = cls._ScrubSlider  # noqa: SLF001
    s = scrub_cls(Qt.Orientation.Horizontal)
    try:
        assert s._format_fn is None  # noqa: SLF001
    finally:
        s.deleteLater()


def test_scrubslider_accepts_format_fn_injection(qtbot) -> None:  # type: ignore[no-untyped-def]
    """``set_format_fn`` stores the callback for the tooltip path."""

    from PySide6.QtCore import Qt

    from chaotic_systems.gui.main_window import _build_window_class

    cls = _build_window_class()
    s = cls._ScrubSlider(Qt.Orientation.Horizontal)  # noqa: SLF001
    try:

        def fmt(value: int) -> str:
            return f"frame {value}"

        s.set_format_fn(fmt)
        assert s._format_fn is fmt  # noqa: SLF001
    finally:
        s.deleteLater()


# ---------------------------------------------------------------------------
# _scrubber_tooltip_text — host-side formatter
# ---------------------------------------------------------------------------


def test_scrubber_tooltip_text_is_empty_before_first_run(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Pre-Run the formatter returns ``""`` so the tooltip is suppressed.

    Showing ``"t = 0.000 / 0.000 s    frame 0 / 0"`` over an empty
    viewport would be visually noisy and misleading. Empty string is
    the contract that tells ``_ScrubSlider._show_tooltip`` to skip.
    """

    window = _make_window(qtbot)
    # No simulation has run; ``_last_trajectory`` is None.
    assert window._last_trajectory is None  # noqa: SLF001
    text = window._scrubber_tooltip_text(0)  # noqa: SLF001
    assert text == "", (
        f"FU-020 — pre-Run tooltip should be empty; got {text!r}"
    )


def test_scrubber_tooltip_text_renders_after_trajectory_lands(qtbot) -> None:  # type: ignore[no-untyped-def]
    """With a trajectory in place, the formatter renders the canonical string.

    Format pinned: ``"t = <t_now> / <t_end> s    frame <i+1> / <n>"``.
    Slot saturates frame index to ``[0, n - 1]`` so out-of-range
    drag positions don't crash.
    """

    import types

    import numpy as np

    window = _make_window(qtbot)
    # Forge a minimal trajectory: t = [0, 1, 2, 3, 4], n_frames = 5.
    fake_traj = types.SimpleNamespace(
        t=np.linspace(0.0, 4.0, 5),
        y=np.zeros((5, 3)),
    )
    window._last_trajectory = fake_traj  # noqa: SLF001
    # _renderer_total_frames reads from the renderer; stub via a
    # MagicMock-style assignment is overkill — patch the method.
    window._renderer_total_frames = lambda: 5  # type: ignore[method-assign]  # noqa: SLF001

    text = window._scrubber_tooltip_text(2)  # noqa: SLF001
    # Format: t = 2.000 / 4.000 s    frame 3 / 5
    assert "t = 2.000" in text
    assert "/ 4.000 s" in text
    assert "frame 3 / 5" in text


def test_scrubber_tooltip_text_saturates_out_of_range_index(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Index past the last frame clamps to the final time value."""

    import types

    import numpy as np

    window = _make_window(qtbot)
    fake_traj = types.SimpleNamespace(
        t=np.linspace(0.0, 10.0, 11),
        y=np.zeros((11, 3)),
    )
    window._last_trajectory = fake_traj  # noqa: SLF001
    window._renderer_total_frames = lambda: 11  # type: ignore[method-assign]  # noqa: SLF001

    # Past-end value should clamp to t = 10.0, frame 11.
    text = window._scrubber_tooltip_text(999)  # noqa: SLF001
    assert "t = 10.000" in text
    assert "frame 11 / 11" in text


# ---------------------------------------------------------------------------
# Defensive behaviour
# ---------------------------------------------------------------------------


def test_scrubslider_show_tooltip_no_op_without_format_fn(qtbot) -> None:  # type: ignore[no-untyped-def]
    """``_show_tooltip`` is a safe no-op when the format fn is ``None``.

    During window tear-down or before the host has wired the
    formatter, the slider must not raise. The implementation
    guards on both ``_format_fn is None`` and ``not isSliderDown()``;
    we verify the early-return path here.
    """

    from PySide6.QtCore import QPoint, Qt

    from chaotic_systems.gui.main_window import _build_window_class

    cls = _build_window_class()
    s = cls._ScrubSlider(Qt.Orientation.Horizontal)  # noqa: SLF001
    try:
        # No exception even with no format fn set.
        s._show_tooltip(QPoint(0, 0))  # noqa: SLF001
    finally:
        s.deleteLater()


# ---------------------------------------------------------------------------
# AP-03 token-discipline — no PySide imports inside event handlers
# ---------------------------------------------------------------------------


def test_scrubslider_event_handlers_have_no_inline_imports() -> None:
    """``_ScrubSlider`` keeps PySide6 imports at module level.

    The critic's AP-03 anti-pattern warned against importing PySide6
    symbols inside ``paintEvent`` or other event handlers — module
    caching makes it harmless at runtime but the pattern is fragile.
    Parses the class source to assert no ``from PySide6`` lines
    appear inside the ``mousePressEvent`` / ``mouseMoveEvent`` /
    ``_show_tooltip`` method bodies.
    """

    import inspect

    from chaotic_systems.gui.main_window import _build_window_class

    cls = _build_window_class()
    scrub_cls = cls._ScrubSlider  # noqa: SLF001
    for method_name in ("mousePressEvent", "mouseMoveEvent", "_show_tooltip"):
        method = getattr(scrub_cls, method_name)
        try:
            source = inspect.getsource(method)
        except (TypeError, OSError):  # pragma: no cover
            continue
        assert "from PySide6" not in source, (
            f"FU-020 / AP-03 — {method_name} contains a PySide6 import; "
            "all imports must be at module level"
        )
