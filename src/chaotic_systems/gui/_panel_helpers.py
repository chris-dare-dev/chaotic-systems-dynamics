"""Shared helpers for analysis-panel modules (FU-022).

Pre-FU-022 each of the five analysis-panel modules (``phase_panel``,
``basin_panel``, ``bifurcation_panel``, ``recurrence_panel``,
``poincare_panel``) carried verbatim copies of three patterns that
the current-state-critic enumerated in HR-01 through HR-04:

- An 8-line ``_swap_canvas(self, fig)`` that builds a new
  ``FigureCanvasQTAgg``, calls ``layout().replaceWidget(old, new)``,
  reparents + ``deleteLater``s the old canvas, and rebinds
  ``self.canvas``. Five copies. AP-02: none guarded against
  ``replaceWidget`` failing when ``old`` wasn't actually in the
  layout.
- A ``QDockWidget`` scaffolding block in every ``build_*_dialog``
  factory: ``setObjectName`` / ``setWindowTitle`` /
  ``WA_DeleteOnClose`` / four ``setAllowedAreas`` / three
  ``DockWidgetFeature`` flags / ``setWidget`` / ``resize``. Five
  copies, near-identical post-FU-018.
- The literals ``8`` (panel content-margin) and ``6`` (panel
  spacing) used unnamed across the five panel ``__init__``
  bodies.

Post-FU-022 the three duplications collapse into:

- :data:`PANEL_MARGIN` (``8``) and :data:`PANEL_SPACING` (``6``)
  constants — applied via :func:`apply_panel_margins`.
- :func:`swap_mpl_canvas` — the canvas-swap pattern with the AP-02
  ``old in layout`` guard baked in.
- :func:`make_panel_dialog` — the FU-018 ``QDockWidget``
  scaffolding pattern as a single call.

QThread plumbing extraction (the synthesis's
``run_in_qthread`` helper) is deferred for now: the three panels
that run workers (``basin_panel``, ``bifurcation_panel``,
``poincare_panel``) have heterogeneous signal wiring (progress
vs no-progress, cancel vs no-cancel, custom cleanup chains) and
unifying them would either lose flexibility or grow the helper's
signature past the value of the abstraction. The other three
helpers carry the bulk of HR-01 through HR-04's value.

References
----------
- ``current-state-critic-brief.md §4`` HR-01 / HR-02 / HR-03 / HR-04.
- ``current-state-critic-brief.md §6`` AP-02 (replaceWidget guard).
- ``synthesis.md §FU-022``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import only for type hints
    from PySide6.QtWidgets import (
        QBoxLayout,
        QDockWidget,
        QWidget,
    )

__all__ = [
    "PANEL_MARGIN",
    "PANEL_SPACING",
    "apply_panel_margins",
    "make_panel_dialog",
    "swap_mpl_canvas",
]


#: Standard outer ``setContentsMargins`` value for an analysis
#: panel's top-level ``QVBoxLayout``. ``8`` px gives the panel
#: visible breathing room from its parent (typically a
#: :class:`QDockWidget` post-FU-018) without crowding the
#: matplotlib canvas. Pre-FU-022 each of the five panels
#: hard-coded ``8`` four times.
PANEL_MARGIN: int = 8

#: Standard inter-widget spacing for an analysis panel's outer
#: ``QVBoxLayout``. ``6`` px reads as "grouped" (tighter than the
#: card-rail's ``16``) without merging the controls into a single
#: vertical run. Pre-FU-022 each of the five panels hard-coded
#: ``6`` once.
PANEL_SPACING: int = 6


def apply_panel_margins(
    layout: QBoxLayout,
    *,
    margin: int = PANEL_MARGIN,
    spacing: int = PANEL_SPACING,
) -> None:
    """Apply the canonical panel margin + spacing to ``layout``.

    Replaces five verbatim copies of::

        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

    The helper is a thin pass-through but documents the
    *intent* — "this is an analysis panel's outer layout" —
    rather than the magic numbers. Callers that need a
    different spacing (e.g. ``bifurcation_panel``'s inner
    panel-host uses ``0`` because it's nested inside an outer
    panel) pass ``margin``/``spacing`` overrides explicitly.

    Parameters
    ----------
    layout
        The layout whose margins + spacing should be set.
    margin
        Override for :data:`PANEL_MARGIN`. Default keeps the
        canonical 8 px.
    spacing
        Override for :data:`PANEL_SPACING`. Default keeps the
        canonical 6 px.
    """

    layout.setContentsMargins(margin, margin, margin, margin)
    layout.setSpacing(spacing)


def swap_mpl_canvas(
    layout: QBoxLayout,
    old_canvas: QWidget,
    new_canvas: QWidget,
) -> bool:
    """Replace ``old_canvas`` with ``new_canvas`` in ``layout``.

    The canonical canvas-swap pattern, with the
    ``current-state-critic §6 AP-02`` guard baked in: if
    ``old_canvas`` is not actually a child of ``layout``
    (e.g. it was already replaced by a concurrent code path),
    the function returns ``False`` without raising or
    leaving ``new_canvas`` orphaned. The caller can then
    decide to add the new canvas via ``addWidget`` instead,
    or simply skip the swap.

    Pre-FU-022 each panel module implemented this inline::

        old = self.canvas
        new = FigureCanvasQTAgg(fig)
        new.setObjectName("..._canvas")
        self.layout().replaceWidget(old, new)
        old.setParent(None)
        old.deleteLater()
        self.canvas = new

    Five copies, none guarded against ``replaceWidget``
    failing when ``old`` wasn't in the layout (AP-02).

    Parameters
    ----------
    layout
        The layout that contains ``old_canvas``. Typically a
        ``QVBoxLayout`` returned by ``self.layout()``.
    old_canvas
        The widget to remove. Will be ``setParent(None)``-ed
        and ``deleteLater()``-ed on success.
    new_canvas
        The widget to install in its place.

    Returns
    -------
    bool
        ``True`` if the swap succeeded, ``False`` if
        ``old_canvas`` was not in ``layout`` (AP-02 guard
        triggered).
    """

    if layout.indexOf(old_canvas) < 0:
        # AP-02 guard — ``old_canvas`` is not in this layout.
        # The caller can recover by adding ``new_canvas`` via
        # ``addWidget`` on a fresh layout / dropping the new
        # canvas entirely / surfacing a status message.
        return False
    layout.replaceWidget(old_canvas, new_canvas)
    old_canvas.setParent(None)
    old_canvas.deleteLater()
    return True


def make_panel_dialog(
    *,
    object_name: str,
    title: str,
    panel: QWidget,
    size: tuple[int, int] = (780, 820),
    parent: QWidget | None = None,
    panel_attr: str | None = None,
) -> QDockWidget:
    """Build a ``QDockWidget`` wrapping an analysis ``panel`` (FU-018 scaffolding).

    The 9-step pattern that every ``build_*_dialog`` factory
    repeats post-FU-018:

    1. ``QDockWidget(parent)``.
    2. ``setObjectName(object_name)``.
    3. ``setWindowTitle(title)``.
    4. ``setAttribute(WA_DeleteOnClose, True)`` so closing the
       dock tears down the C++ object via Qt's lifecycle.
    5. ``setAllowedAreas(<all four areas>)``.
    6. ``setFeatures(Movable | Floatable | Closable)``.
    7. ``setWidget(panel)``.
    8. ``resize(*size)``.
    9. (Optional) Expose the panel as a named attribute on the
       dock — pre-FU-022 every factory wrote
       ``dock.<name>_panel = panel`` so tests + scripted
       callers could reach the inner panel without an extra
       ``findChild`` call.

    Parameters
    ----------
    object_name
        The dock's ``objectName``. Used by the FU-014 command
        palette and ``docs/ui_design.md`` layout-spec
        assertions. Stable across FU-018 (pre-FU-018 these
        were ``QMainWindow`` ``objectName``s).
    title
        The user-facing window title.
    panel
        The widget that becomes the dock's ``setWidget``
        payload. Reparented under the dock.
    size
        The initial size in logical pixels. The synthesis-era
        default of ``(780, 820)`` matches pre-FU-022 panel
        sizes; callers pass overrides for the bifurcation
        dialog (``(900, 700)`` because the map picker takes
        more horizontal room).
    parent
        Parent widget; the dock is reparented to the main
        window via ``_open_as_floating_dock`` later.
    panel_attr
        If non-``None``, the helper sets
        ``setattr(dock, panel_attr, panel)`` so existing
        attribute-access paths (``dock.phase_panel``,
        ``dock.basin_panel``, etc.) keep working post-FU-022.

    Returns
    -------
    QDockWidget
        Configured dock ready to be shown via
        ``_open_as_floating_dock`` on the main window, or
        ``show()``-n directly as a standalone window.
    """

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDockWidget

    dock = QDockWidget(parent)
    dock.setObjectName(object_name)
    dock.setWindowTitle(title)
    dock.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dock.setAllowedAreas(
        Qt.DockWidgetArea.LeftDockWidgetArea
        | Qt.DockWidgetArea.RightDockWidgetArea
        | Qt.DockWidgetArea.BottomDockWidgetArea
        | Qt.DockWidgetArea.TopDockWidgetArea
    )
    dock.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetMovable
        | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        | QDockWidget.DockWidgetFeature.DockWidgetClosable
    )
    dock.setWidget(panel)
    width, height = size
    dock.resize(int(width), int(height))
    if panel_attr is not None:
        # Dynamic attribute is intentional, mirroring the
        # pre-FU-022 pattern (``dock.phase_panel = panel`` etc.).
        setattr(dock, panel_attr, panel)
    return dock
