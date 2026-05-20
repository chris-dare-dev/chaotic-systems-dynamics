"""Tests for FU-022 — ``_panel_helpers.py`` shared utilities.

Pre-FU-022 the five analysis-panel modules carried verbatim
copies of three patterns (HR-01 through HR-04 in the
current-state-critic brief):

- An 8-line ``_swap_canvas`` (five copies, none guarded against
  AP-02 — ``replaceWidget`` failing on a missing ``old``).
- A ``QDockWidget`` scaffolding block in every
  ``build_*_dialog`` factory (five copies).
- ``setContentsMargins(8, 8, 8, 8)`` + ``setSpacing(6)``
  magic numbers (five panel ``__init__`` bodies).

Post-FU-022 the three duplications collapse into helpers in
``src/chaotic_systems/gui/_panel_helpers.py``:

- :data:`PANEL_MARGIN` (``8``) + :data:`PANEL_SPACING` (``6``)
  constants + :func:`apply_panel_margins` helper.
- :func:`swap_mpl_canvas` with the AP-02 ``old in layout``
  guard.
- :func:`make_panel_dialog` for the FU-018 ``QDockWidget``
  scaffolding.

QThread plumbing extraction (``run_in_qthread``) is
deferred — the three panels that run workers have
heterogeneous signal wiring (progress vs no-progress,
cancel vs no-cancel, custom cleanup chains).

Coverage:

- ``PANEL_MARGIN`` and ``PANEL_SPACING`` are the synthesis-
  prescribed values (8 / 6).
- ``apply_panel_margins`` writes the canonical margin +
  spacing to a layout; overrides honoured.
- ``swap_mpl_canvas`` swaps successfully when ``old`` is in
  the layout (returns ``True``).
- ``swap_mpl_canvas`` returns ``False`` and leaves the
  layout untouched when ``old`` is NOT in the layout
  (AP-02 guard).
- ``make_panel_dialog`` builds a ``QDockWidget`` with all
  FU-018 contract bits: objectName, title, ``WA_DeleteOnClose``,
  all four allowed areas, three feature flags, panel set as
  widget, ``resize`` applied, optional panel_attr exposed.
- The 5 panel modules use the helpers (no verbatim copies
  remain).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_panel_margin_is_eight() -> None:
    """``PANEL_MARGIN`` matches the synthesis-prescribed 8 px."""

    from chaotic_systems.gui._panel_helpers import PANEL_MARGIN

    assert PANEL_MARGIN == 8


def test_panel_spacing_is_six() -> None:
    """``PANEL_SPACING`` matches the synthesis-prescribed 6 px."""

    from chaotic_systems.gui._panel_helpers import PANEL_SPACING

    assert PANEL_SPACING == 6


# ---------------------------------------------------------------------------
# apply_panel_margins
# ---------------------------------------------------------------------------


def test_apply_panel_margins_uses_defaults(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Default invocation writes 8 / 6 to the layout."""

    from PySide6.QtWidgets import QVBoxLayout, QWidget

    from chaotic_systems.gui._panel_helpers import apply_panel_margins

    host = QWidget()
    qtbot.addWidget(host)
    try:
        layout = QVBoxLayout(host)
        apply_panel_margins(layout)
        m = layout.contentsMargins()
        assert (m.left(), m.top(), m.right(), m.bottom()) == (8, 8, 8, 8)
        assert layout.spacing() == 6
    finally:
        host.close()


def test_apply_panel_margins_honours_overrides(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Caller-supplied ``margin`` and ``spacing`` override the defaults."""

    from PySide6.QtWidgets import QVBoxLayout, QWidget

    from chaotic_systems.gui._panel_helpers import apply_panel_margins

    host = QWidget()
    qtbot.addWidget(host)
    try:
        layout = QVBoxLayout(host)
        apply_panel_margins(layout, margin=0, spacing=0)
        m = layout.contentsMargins()
        assert (m.left(), m.top(), m.right(), m.bottom()) == (0, 0, 0, 0)
        assert layout.spacing() == 0
    finally:
        host.close()


# ---------------------------------------------------------------------------
# swap_mpl_canvas — AP-02 guard
# ---------------------------------------------------------------------------


def test_swap_mpl_canvas_succeeds_for_present_old(qtbot) -> None:  # type: ignore[no-untyped-def]
    """The happy path: ``old`` is in the layout, swap returns ``True``."""

    from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

    from chaotic_systems.gui._panel_helpers import swap_mpl_canvas

    host = QWidget()
    qtbot.addWidget(host)
    try:
        layout = QVBoxLayout(host)
        old = QLabel("old", host)
        new = QLabel("new", host)
        layout.addWidget(old)

        result = swap_mpl_canvas(layout, old, new)
        assert result is True
        # The new widget is in the layout; the old one is not.
        assert layout.indexOf(new) >= 0
        assert layout.indexOf(old) < 0
    finally:
        host.close()


def test_swap_mpl_canvas_returns_false_when_old_missing(qtbot) -> None:  # type: ignore[no-untyped-def]
    """AP-02 guard: if ``old`` is not in ``layout``, return ``False`` without raising."""

    from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

    from chaotic_systems.gui._panel_helpers import swap_mpl_canvas

    host = QWidget()
    qtbot.addWidget(host)
    try:
        layout = QVBoxLayout(host)
        stray = QLabel("stray", host)  # never added to the layout
        new = QLabel("new", host)

        result = swap_mpl_canvas(layout, stray, new)
        assert result is False, (
            "FU-022 AP-02 guard — when ``old`` is not in the "
            "layout, the helper must return False without raising "
            "and without installing ``new`` (orphan-prevention)"
        )
        assert layout.indexOf(new) < 0
    finally:
        host.close()


# ---------------------------------------------------------------------------
# make_panel_dialog — FU-018 scaffolding contract
# ---------------------------------------------------------------------------


def _make_dialog(qtbot, **overrides):  # type: ignore[no-untyped-def]
    """Build a panel dialog with a trivial payload widget."""

    from PySide6.QtWidgets import QLabel

    from chaotic_systems.gui._panel_helpers import make_panel_dialog

    panel = QLabel("test panel")
    defaults = {
        "object_name": "test_dialog",
        "title": "Test panel",
        "panel": panel,
    }
    defaults.update(overrides)
    dock = make_panel_dialog(**defaults)
    qtbot.addWidget(dock)
    return dock, panel


def test_make_panel_dialog_returns_qdockwidget(qtbot) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtWidgets import QDockWidget

    dock, _ = _make_dialog(qtbot)
    try:
        assert isinstance(dock, QDockWidget)
    finally:
        dock.close()


def test_make_panel_dialog_sets_object_name_and_title(qtbot) -> None:  # type: ignore[no-untyped-def]
    dock, _ = _make_dialog(qtbot, object_name="custom_obj", title="Custom title")
    try:
        assert dock.objectName() == "custom_obj"
        assert dock.windowTitle() == "Custom title"
    finally:
        dock.close()


def test_make_panel_dialog_carries_delete_on_close(qtbot) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtCore import Qt

    dock, _ = _make_dialog(qtbot)
    try:
        assert dock.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    finally:
        dock.close()


def test_make_panel_dialog_allows_all_four_areas(qtbot) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtCore import Qt

    dock, _ = _make_dialog(qtbot)
    try:
        allowed = dock.allowedAreas()
        for area in (
            Qt.DockWidgetArea.LeftDockWidgetArea,
            Qt.DockWidgetArea.RightDockWidgetArea,
            Qt.DockWidgetArea.BottomDockWidgetArea,
            Qt.DockWidgetArea.TopDockWidgetArea,
        ):
            assert allowed & area
    finally:
        dock.close()


def test_make_panel_dialog_sets_movable_floatable_closable(qtbot) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtWidgets import QDockWidget

    dock, _ = _make_dialog(qtbot)
    try:
        features = dock.features()
        assert features & QDockWidget.DockWidgetFeature.DockWidgetMovable
        assert features & QDockWidget.DockWidgetFeature.DockWidgetFloatable
        assert features & QDockWidget.DockWidgetFeature.DockWidgetClosable
    finally:
        dock.close()


def test_make_panel_dialog_installs_panel_as_widget(qtbot) -> None:  # type: ignore[no-untyped-def]
    dock, panel = _make_dialog(qtbot)
    try:
        assert dock.widget() is panel
    finally:
        dock.close()


def test_make_panel_dialog_applies_size(qtbot) -> None:  # type: ignore[no-untyped-def]
    dock, _ = _make_dialog(qtbot, size=(640, 480))
    try:
        assert dock.size().width() == 640
        assert dock.size().height() == 480
    finally:
        dock.close()


def test_make_panel_dialog_exposes_panel_attr(qtbot) -> None:  # type: ignore[no-untyped-def]
    """``panel_attr="foo"`` → ``dock.foo == panel`` (back-compat for tests)."""

    dock, panel = _make_dialog(qtbot, panel_attr="example_panel")
    try:
        assert dock.example_panel is panel  # type: ignore[attr-defined]
    finally:
        dock.close()


def test_make_panel_dialog_omits_panel_attr_when_none(qtbot) -> None:  # type: ignore[no-untyped-def]
    """When ``panel_attr=None`` the dock has no dynamic attribute attached."""

    dock, panel = _make_dialog(qtbot, panel_attr=None)
    try:
        # No surprise attribute is set; this is the bifurcation
        # dialog's pattern (it sets ``.map_picker`` separately).
        for forbidden in ("phase_panel", "basin_panel", "recurrence_panel"):
            assert not hasattr(dock, forbidden), (
                f"FU-022 — make_panel_dialog must not set "
                f"a panel_attr when caller passed None; "
                f"unexpected attribute: {forbidden}"
            )
    finally:
        dock.close()


# ---------------------------------------------------------------------------
# Adoption — the 5 panel modules import the helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "module_name",
    [
        "chaotic_systems.gui.phase_panel",
        "chaotic_systems.gui.basin_panel",
        "chaotic_systems.gui.bifurcation_panel",
        "chaotic_systems.gui.recurrence_panel",
        "chaotic_systems.gui.poincare_panel",
    ],
)
def test_panel_module_source_references_panel_helpers(module_name) -> None:  # type: ignore[no-untyped-def]
    """Every panel module imports from ``_panel_helpers``."""

    from importlib import util

    spec = util.find_spec(module_name)
    assert spec is not None and spec.origin is not None
    source = open(spec.origin, encoding="utf-8").read()
    assert "from chaotic_systems.gui._panel_helpers import" in source, (
        f"FU-022 — {module_name} should import from _panel_helpers; "
        f"the verbatim copies the synthesis enumerated must be replaced "
        f"by helper calls."
    )


@pytest.mark.parametrize(
    "module_name",
    [
        "chaotic_systems.gui.phase_panel",
        "chaotic_systems.gui.basin_panel",
        "chaotic_systems.gui.bifurcation_panel",
        "chaotic_systems.gui.recurrence_panel",
        "chaotic_systems.gui.poincare_panel",
    ],
)
def test_panel_module_no_verbatim_8_8_8_8_margin(module_name) -> None:  # type: ignore[no-untyped-def]
    """The verbatim ``setContentsMargins(8, 8, 8, 8)`` literal is gone.

    Pre-FU-022 each panel module wrote this literal once. Post-
    FU-022 ``apply_panel_margins`` carries the same effect via
    the ``PANEL_MARGIN`` constant.
    """

    from importlib import util

    spec = util.find_spec(module_name)
    assert spec is not None and spec.origin is not None
    source = open(spec.origin, encoding="utf-8").read()
    assert "setContentsMargins(8, 8, 8, 8)" not in source, (
        f"FU-022 — {module_name} still contains the verbatim "
        f"setContentsMargins(8, 8, 8, 8) literal; use "
        f"apply_panel_margins(outer) instead."
    )
