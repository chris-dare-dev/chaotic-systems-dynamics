"""Tests for FU-024 — dialog window-reference cleanup on close.

All five analysis dialogs (Bifurcation / Recurrence / Basin /
Poincaré / Phase) are constructed with ``Qt.WA_DeleteOnClose``,
which means closing the dialog frees the underlying C++ object.
Pre-FU-024 the main window kept the Python attribute (e.g.
``self._poincare_window``) pointing at the now-deleted shiboken
wrapper — any access between close and reopen raised
``RuntimeError: wrapped C++ object has been deleted``. FU-024
wires ``dialog.destroyed`` to reset the attribute to ``None`` at
the right moment.

Coverage:

- All five ``_*_window`` attributes default to ``None`` at
  construction (introspection before the first open is safe).
- ``_wire_window_cleanup`` is a real method that connects the
  ``destroyed`` signal.
- Simulating ``destroyed`` resets the named attribute back to
  ``None`` (covers all five names without paying for the cost of
  actually opening a real ``QMainWindow`` sub-dialog).
- The closure captures ``attr_name`` as a default argument so
  two wires in the same scope target different attributes.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")


def _make_window(qtbot):  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)
    return window


# ---------------------------------------------------------------------------
# Default-None initialisation
# ---------------------------------------------------------------------------


def test_all_five_dialog_window_attrs_default_to_none(qtbot) -> None:  # type: ignore[no-untyped-def]
    """FU-024 — every analysis dialog's window attribute starts as None.

    Pre-FU-024 these attributes only materialised on first open, so
    code that introspected them before any dialog had been shown
    hit ``AttributeError``. The init block in ``_MainWindow.__init__``
    pre-creates all five with ``None``.
    """

    window = _make_window(qtbot)
    for attr in (
        "_bifurcation_window",
        "_recurrence_window",
        "_basin_window",
        "_poincare_window",
        "_phase_window",
    ):
        assert hasattr(window, attr), (
            f"FU-024 — missing pre-init attribute {attr!r}"
        )
        assert getattr(window, attr) is None, (
            f"FU-024 — {attr!r} should default to None; got "
            f"{getattr(window, attr)!r}"
        )


# ---------------------------------------------------------------------------
# _wire_window_cleanup — destroyed → None
# ---------------------------------------------------------------------------


def test_wire_window_cleanup_resets_attr_on_destroyed(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Emitting ``destroyed`` on a wired dialog nulls the named attribute.

    We use a real ``QObject`` (no need to spin up a full panel
    dialog) and verify the destroyed-signal path. The lambda
    captures ``attr_name`` by default-argument so the cleanup
    targets the right attribute even when multiple wires share a
    scope.
    """

    from PySide6.QtCore import QObject

    window = _make_window(qtbot)
    fake_dialog = QObject()
    # Pretend the dialog was opened.
    window._poincare_window = fake_dialog  # noqa: SLF001
    window._wire_window_cleanup(fake_dialog, "_poincare_window")  # noqa: SLF001
    # Emit the signal (rather than calling deleteLater + waiting).
    fake_dialog.destroyed.emit()
    assert window._poincare_window is None, (  # noqa: SLF001
        "FU-024 — _poincare_window must reset to None on destroyed"
    )


def test_wire_window_cleanup_handles_multiple_dialogs_independently(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Two simultaneous wires must not collide on the late-binding closure.

    A naive ``lambda: setattr(self, attr_name, None)`` capture would
    bind ``attr_name`` by reference, so the last wired name would
    overwrite every prior one. The default-argument trick
    (``lambda name=attr_name: ...``) avoids this — we verify it
    explicitly by wiring two fake dialogs and ensuring each
    destroyed signal resets only its own attribute.
    """

    from PySide6.QtCore import QObject

    window = _make_window(qtbot)
    dialog_a = QObject()
    dialog_b = QObject()
    window._poincare_window = dialog_a  # noqa: SLF001
    window._phase_window = dialog_b  # noqa: SLF001
    window._wire_window_cleanup(dialog_a, "_poincare_window")  # noqa: SLF001
    window._wire_window_cleanup(dialog_b, "_phase_window")  # noqa: SLF001

    # Destroy A only — B must remain untouched.
    dialog_a.destroyed.emit()
    assert window._poincare_window is None  # noqa: SLF001
    assert window._phase_window is dialog_b  # noqa: SLF001

    # Now destroy B — A stays None, B resets.
    dialog_b.destroyed.emit()
    assert window._poincare_window is None  # noqa: SLF001
    assert window._phase_window is None  # noqa: SLF001


# ---------------------------------------------------------------------------
# Helper exists + accepts every documented attr name
# ---------------------------------------------------------------------------


def test_wire_window_cleanup_method_exists(qtbot) -> None:  # type: ignore[no-untyped-def]
    """The FU-024 helper method is defined on _MainWindow."""

    window = _make_window(qtbot)
    assert hasattr(window, "_wire_window_cleanup")
    assert callable(window._wire_window_cleanup)  # noqa: SLF001


def test_wire_window_cleanup_accepts_every_documented_attr(qtbot) -> None:  # type: ignore[no-untyped-def]
    """All five canonical attribute names work without raising.

    A defensive test against future renames: if someone refactors
    ``_basin_window`` -> ``_basins_window`` (or similar) but
    forgets to update the slot's ``_wire_window_cleanup`` call,
    no early-warning fires from this test. But the existence-of-
    attribute check above catches it. This test belt-and-suspenders
    the path: every documented attribute name is wirable.
    """

    from PySide6.QtCore import QObject

    window = _make_window(qtbot)
    for attr in (
        "_bifurcation_window",
        "_recurrence_window",
        "_basin_window",
        "_poincare_window",
        "_phase_window",
    ):
        fake = QObject()
        setattr(window, attr, fake)
        window._wire_window_cleanup(fake, attr)  # noqa: SLF001
        fake.destroyed.emit()
        assert getattr(window, attr) is None, (
            f"FU-024 — {attr!r} did not reset to None"
        )
