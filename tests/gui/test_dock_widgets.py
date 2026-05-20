"""Tests for FU-018 — promote 5 dialog panels to ``QDockWidget``.

Pre-FU-018 the analysis dialogs (Phase / Basin / Bifurcation /
Recurrence / Poincaré) shipped as standalone ``QMainWindow``s
that floated independently. Post-FU-018 each ``build_*_dialog``
returns a ``QDockWidget`` so the user can dock the panel beside
the 3D viewport. The default UX still opens them as separate
floating windows (``setFloating(True)`` after attach); the user
drags them back into the main window to dock. napari's
``add_dock_widget`` pattern (PR #5483).

Coverage:

- Each of the 5 ``build_*_dialog`` factories returns a
  ``QDockWidget`` (was ``QMainWindow``).
- The canonical objectName (``"phase_dialog"`` etc.) and panel
  attribute (``.phase_panel``) survive the migration — existing
  tests + scripted callers keep working.
- The dock is movable / floatable / closable (the three feature
  flags the synthesis prescribed).
- All four dock areas are allowed.
- ``QDockWidget`` QSS rules exist in ``dark.qss`` (CC-1
  mitigation — without them the title bar renders system-native).
- ``_open_as_floating_dock`` is the helper that attaches +
  floats + shows; it exists and is callable.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")


# ---------------------------------------------------------------------------
# Factory return type
# ---------------------------------------------------------------------------


def _phase_dialog():
    """Build a phase dialog with a minimal synthetic trajectory."""
    import types

    import numpy as np

    from chaotic_systems.gui.phase_panel import build_phase_dialog

    traj = types.SimpleNamespace(t=np.linspace(0, 1, 10), y=np.zeros((10, 3)))
    return build_phase_dialog(traj, axes_labels=("x", "y", "z"))


def _basin_dialog():
    from chaotic_systems.gui.basin_panel import build_basin_dialog

    return build_basin_dialog()


def _bifurcation_dialog():
    from chaotic_systems.gui.bifurcation_panel import build_bifurcation_dialog

    return build_bifurcation_dialog()


def _recurrence_dialog():
    import types

    import numpy as np

    from chaotic_systems.gui.recurrence_panel import build_recurrence_dialog

    traj = types.SimpleNamespace(t=np.linspace(0, 1, 50), y=np.zeros((50, 3)))
    return build_recurrence_dialog(traj)


def _poincare_dialog():
    from chaotic_systems.gui.poincare_panel import build_poincare_dialog
    from chaotic_systems.systems.registry import get_system

    sys_obj = get_system("HenonHeiles")
    return build_poincare_dialog(sys_obj, axes_labels=("x", "y", "p_x"))


@pytest.mark.parametrize(
    "factory,attr_name",
    [
        (_phase_dialog, "phase_panel"),
        (_basin_dialog, "basin_panel"),
        (_recurrence_dialog, "recurrence_panel"),
        (_poincare_dialog, "poincare_panel"),
    ],
)
def test_dialog_factories_return_qdockwidget(qtbot, factory, attr_name) -> None:  # type: ignore[no-untyped-def]
    """FU-018 — every ``build_*_dialog`` factory returns a ``QDockWidget``.

    The migration's headline contract. The bifurcation dialog is
    tested separately because its factory has a different
    signature (no trajectory) but the same dock-widget shape.
    """

    from PySide6.QtWidgets import QDockWidget

    dock = factory()
    qtbot.addWidget(dock)
    try:
        assert isinstance(dock, QDockWidget), (
            f"FU-018 — {factory.__name__} should return a QDockWidget; "
            f"got {type(dock).__name__}"
        )
        # The panel attribute survives the migration so existing
        # scripted callers + tests keep working.
        panel = getattr(dock, attr_name, None)
        assert panel is not None, (
            f"FU-018 — {factory.__name__} dock missing the {attr_name!r} "
            "attribute; pre-FU-018 ``QMainWindow``-based callers relied on it"
        )
    finally:
        dock.close()


def test_bifurcation_dialog_returns_qdockwidget(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Bifurcation dialog tested separately (different factory signature)."""

    from PySide6.QtWidgets import QDockWidget

    dock = _bifurcation_dialog()
    qtbot.addWidget(dock)
    try:
        assert isinstance(dock, QDockWidget)
        # Bifurcation exposes ``.map_picker``, not a single ``.panel``,
        # because the dialog hosts a map-picker combo + swappable
        # BifurcationPanel internally.
        assert dock.map_picker is not None
    finally:
        dock.close()


# ---------------------------------------------------------------------------
# Object names + canonical attributes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "factory,expected_name",
    [
        (_phase_dialog, "phase_dialog"),
        (_basin_dialog, "basin_dialog"),
        (_bifurcation_dialog, "bifurcation_dialog"),
        (_recurrence_dialog, "recurrence_dialog"),
        (_poincare_dialog, "poincare_dialog"),
    ],
)
def test_dialog_object_names_survive_migration(qtbot, factory, expected_name) -> None:  # type: ignore[no-untyped-def]
    """The canonical objectName is preserved across the QDockWidget swap.

    External agents (the FU-014 command palette, layout-spec
    assertions, tests) look up the dialogs by objectName; the
    migration must preserve them.
    """

    dock = factory()
    qtbot.addWidget(dock)
    try:
        assert dock.objectName() == expected_name
    finally:
        dock.close()


# ---------------------------------------------------------------------------
# Dock feature flags
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "factory",
    [_phase_dialog, _basin_dialog, _bifurcation_dialog, _recurrence_dialog, _poincare_dialog],
)
def test_dock_widget_features(qtbot, factory) -> None:  # type: ignore[no-untyped-def]
    """The synthesis-prescribed feature flags are set.

    Movable / floatable / closable — these are the three flags that
    let the user drag the dock around, undock it to a floating
    window, and close it via the title bar. The default
    ``QDockWidget`` ships all three, but pinning them explicitly
    documents the contract.
    """

    from PySide6.QtWidgets import QDockWidget

    dock = factory()
    qtbot.addWidget(dock)
    try:
        features = dock.features()
        assert features & QDockWidget.DockWidgetFeature.DockWidgetMovable
        assert features & QDockWidget.DockWidgetFeature.DockWidgetFloatable
        assert features & QDockWidget.DockWidgetFeature.DockWidgetClosable
    finally:
        dock.close()


@pytest.mark.parametrize(
    "factory",
    [_phase_dialog, _basin_dialog, _bifurcation_dialog, _recurrence_dialog, _poincare_dialog],
)
def test_dock_widget_allows_all_four_areas(qtbot, factory) -> None:  # type: ignore[no-untyped-def]
    """All four dock areas (Left / Right / Top / Bottom) are allowed."""

    from PySide6.QtCore import Qt

    dock = factory()
    qtbot.addWidget(dock)
    try:
        allowed = dock.allowedAreas()
        for area in (
            Qt.DockWidgetArea.LeftDockWidgetArea,
            Qt.DockWidgetArea.RightDockWidgetArea,
            Qt.DockWidgetArea.BottomDockWidgetArea,
            Qt.DockWidgetArea.TopDockWidgetArea,
        ):
            assert allowed & area, (
                f"FU-018 — {factory.__name__} should allow {area!r}"
            )
    finally:
        dock.close()


# ---------------------------------------------------------------------------
# Theme — QSS rules for QDockWidget exist
# ---------------------------------------------------------------------------


def test_dark_qss_styles_qdockwidget() -> None:
    """CC-1 mitigation: ``dark.qss`` carries explicit ``QDockWidget`` rules.

    Without these the dock title bar renders with the system-native
    palette on Windows — same regression FU-001 caught for QMenu.
    The synthesis explicitly flagged this as the FU-018 MAJOR risk.
    """

    from pathlib import Path

    from chaotic_systems.gui.theme import PALETTE

    qss_text = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "chaotic_systems"
        / "gui"
        / "assets"
        / "dark.qss"
    ).read_text(encoding="utf-8")

    # The dock selector + the title pseudo-element both need rules.
    assert "QDockWidget {" in qss_text, "FU-018 — missing QDockWidget rule"
    assert "QDockWidget::title" in qss_text, (
        "FU-018 — missing QDockWidget::title rule"
    )
    # Token discipline: the dock background uses ``bg-panel`` and
    # the title bar uses ``bg-window``.
    start = qss_text.index("QDockWidget {")
    block = qss_text[start : start + 2000]
    assert PALETTE.bg_panel in block, (
        "QDockWidget rule must use PALETTE.bg_panel"
    )
    assert PALETTE.bg_window in block, (
        "QDockWidget::title rule must use PALETTE.bg_window"
    )
    assert PALETTE.text_primary in block, (
        "QDockWidget rule must use PALETTE.text_primary"
    )


# ---------------------------------------------------------------------------
# Main-window helper
# ---------------------------------------------------------------------------


def test_open_as_floating_dock_method_exists(qtbot) -> None:  # type: ignore[no-untyped-def]
    """The FU-018 ``_open_as_floating_dock`` helper is on ``_MainWindow``."""

    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)
    try:
        assert hasattr(window, "_open_as_floating_dock")
        assert callable(window._open_as_floating_dock)  # noqa: SLF001
    finally:
        window.close()


def test_open_as_floating_dock_attaches_and_floats(qtbot) -> None:  # type: ignore[no-untyped-def]
    """``_open_as_floating_dock`` adds the dock to the window and floats it."""

    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)
    try:
        dock = _phase_dialog()
        window._open_as_floating_dock(dock)  # noqa: SLF001
        # The dock is now a child of the main window.
        assert dock.parent() is window
        # And it's floating (the synthesis-prescribed default UX).
        assert dock.isFloating(), (
            "FU-018 — _open_as_floating_dock should setFloating(True)"
        )
    finally:
        window.close()
