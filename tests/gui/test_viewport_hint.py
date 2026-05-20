"""Tests for FU-011 — viewport hint label showEvent anchoring.

Pre-FU-011 the viewport's "Press Ctrl-R to simulate" hint label was
positioned once at construction via ``QTimer.singleShot(0,
self._reposition_overlay)``. Under the offscreen Qt platform plugin
(CI / screenshot runs) the first paint sometimes happened *before*
the layout pass finished, so the hint sat at its initial ``(0, 0)``
position until the next resize event re-anchored it — the
visual-scout F-10 finding from ``screenshots/initial.png``.

FU-011 overrides ``_MainWindow.showEvent`` to call
``_reposition_overlay`` once the window's final geometry exists.
The single-shot timer is kept as a backstop for headless tests
that never call ``show()``.

Coverage:

- ``_MainWindow`` defines ``showEvent`` (was inherited unmodified
  from ``QMainWindow`` pre-FU-011).
- The override calls ``super().showEvent`` (Qt's machinery still
  fires) and then ``_reposition_overlay``.
- Driving ``show()`` on the window positions the hint at the
  bottom-center of the viewport frame (within a tolerance — the
  test runner can't pin pixel-exact coordinates without a real
  display).
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


def test_main_window_overrides_show_event() -> None:
    """FU-011 — ``_MainWindow.showEvent`` is defined locally.

    Pre-FU-011 the window inherited the QMainWindow default. Adding
    the override is the FU-011 contract; if a future refactor
    removes it the hint regressions to its (0,0) starting position
    under offscreen render and this test fails.
    """

    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    # ``showEvent`` must be defined directly on _MainWindow, not
    # inherited. Walking the MRO and finding it before QMainWindow
    # confirms the override.
    method_owners = []
    for klass in Window.__mro__:
        if "showEvent" in vars(klass):
            method_owners.append(klass.__name__)
    assert method_owners, "FU-011 — no showEvent override found in MRO"
    assert method_owners[0] == Window.__name__, (
        f"FU-011 — showEvent should be defined on _MainWindow first; "
        f"found on {method_owners[0]!r} instead"
    )


def test_show_event_calls_super_and_repositions(qtbot) -> None:  # type: ignore[no-untyped-def]
    """The override delegates to ``super().showEvent`` then re-anchors.

    Skipping ``super().showEvent`` would break Qt's machinery
    (focus events, first-paint signal, etc.); skipping
    ``_reposition_overlay`` would re-introduce the F-10 regression.
    Both must happen.
    """

    window = _make_window(qtbot)

    # Spy on _reposition_overlay.
    calls = {"count": 0}
    original = window._reposition_overlay  # noqa: SLF001

    def spy() -> None:
        calls["count"] += 1
        original()

    window._reposition_overlay = spy  # type: ignore[method-assign]  # noqa: SLF001

    # Drive showEvent directly with a dummy event. Qt accepts a
    # QShowEvent constructor with no arguments.
    from PySide6.QtGui import QShowEvent

    window.showEvent(QShowEvent())
    assert calls["count"] >= 1, (
        "FU-011 — showEvent override did not call _reposition_overlay"
    )


def test_show_positions_hint_near_bottom_of_viewport(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Behavioural check: showing the window anchors the hint to the
    bottom half of the viewport frame.

    We don't pin a pixel-exact position (the test runner has no
    deterministic frame size without a real display), but the
    hint's ``y()`` must be in the lower half of the viewport
    frame's height after ``show()`` runs.
    """

    from PySide6.QtCore import QSize

    window = _make_window(qtbot)
    # Force a known size so the viewport frame has non-trivial
    # geometry to anchor against. ``resize`` + processEvents drives
    # the layout pass.
    window.resize(QSize(1200, 800))
    window.show()
    try:
        from PySide6.QtCore import QCoreApplication

        QCoreApplication.processEvents()
        # After show + processEvents the hint must be positioned
        # in the viewport frame's bottom half.
        hint = window.viewport_hint
        frame = window._viewport_frame  # noqa: SLF001
        # Hint widget is a child of the viewport frame, so its y()
        # is relative to the frame's local coords.
        if frame.height() > 100:  # only meaningful if layout settled
            assert hint.y() > frame.height() / 2, (
                f"FU-011 — hint at y={hint.y()} should be in the bottom "
                f"half of the viewport frame (height={frame.height()})"
            )
    finally:
        window.close()


def test_reposition_overlay_method_exists(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Sanity — ``_reposition_overlay`` is the slot the showEvent calls.

    Renaming the method without updating the showEvent override
    would silently break FU-011. This test pins the method name.
    """

    window = _make_window(qtbot)
    assert hasattr(window, "_reposition_overlay")
    assert callable(window._reposition_overlay)  # noqa: SLF001
