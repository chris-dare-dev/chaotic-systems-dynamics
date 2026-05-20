"""Icon mapping helper — qtawesome MDI6 glyphs (FU-005).

Replaces the eleven hand-rolled SVGs under ``assets/icons/`` and
the URL-rewriting hack in ``theme.py`` with a centralised
stem-to-glyph table backed by ``qtawesome`` (Material Design Icons
6 + FontAwesome 6 + Codicons, bundled as a single MIT-licensed
font pack).

Why qtawesome?
--------------
The visual scout's brief flagged five toolbar actions
(``bifurcation`` / ``phase-portrait`` / ``recurrence`` / ``basins``
/ ``poincare``) that silently degraded to text-only because their
SVG files were never authored — Qt's ``if icon_path.exists():``
guard ate the failure (current-state-critic anti-pattern AP-04).
The library scout's brief recommended ``qtawesome`` as a one-line
fix: every glyph the project needs already exists in MDI6;
``qta.icon(...)`` returns a theme-colored :class:`QIcon` directly;
the URL-rewriting block in ``theme.py`` is no longer needed.

The synthesis lists this as **FU-005** (RICE 1.80, MAJOR severity
mitigated by FU-002 landing first so the icon color routes
through ``PALETTE.text_primary``).

API
---
:func:`icon_for_stem` maps every legacy icon-stem name (``"run"``,
``"pause"``, ..., ``"basins"``, ``"poincare"``) to a
qtawesome-backed :class:`QIcon` coloured from the current palette.
:data:`STEM_TO_GLYPH` is the underlying table — exported so tests
and the Preferences dialog can introspect it.

References
----------
- qtawesome 1.4.2 — Spyder IDE,
  https://github.com/spyder-ide/qtawesome (MIT, Apr 2026).
- Material Design Icons 6 — https://pictogrammers.com/library/mdi/
  (Apache 2.0). Glyph IDs in :data:`STEM_TO_GLYPH` resolve directly
  to MDI6 names.
- Frontend-uplift 2026-05-19-initial — library-brief.md §2.5,
  current-state-critic-brief.md §6 AP-04 ("missing SVGs silently
  degrade"), final-report.md FU-005.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import only for type hints
    from PySide6.QtGui import QIcon


#: Stable mapping from the project's legacy icon-stem vocabulary
#: (used by ``_toolbar_action_specs`` for years before FU-005) to
#: MDI6 glyph names. Every stem the codebase ever referenced is
#: covered here, including the five orphan stems that previously
#: had no SVG file — so the toolbar now ships with icons for all
#: 12 actions instead of degrading 5 of them to text-only.
STEM_TO_GLYPH: dict[str, str] = {
    # Transport bar — media-player vocabulary.
    "run": "mdi6.play",
    "pause": "mdi6.pause",
    "stop": "mdi6.stop",
    "jump-end": "mdi6.skip-next",
    # Export + view.
    "export": "mdi6.file-export-outline",
    "reset-view": "mdi6.crop-rotate",
    # Theme + settings.
    "theme": "mdi6.theme-light-dark",
    "gear": "mdi6.cog",
    # FU-005 backfills — the five analytics actions that previously
    # had no SVG file. Glyph choices follow the visual scout's
    # suggestions in visual-brief.md F-02 and the library scout's
    # MDI6 mapping in library-brief.md §2.5.
    "bifurcation": "mdi6.chart-bell-curve-cumulative",
    "phase-portrait": "mdi6.chart-scatter-plot",
    "recurrence": "mdi6.dots-grid",
    "basins": "mdi6.map-marker-radius",
    "poincare": "mdi6.crosshairs",
}


def icon_for_stem(stem: str, color: str | None = None) -> QIcon:
    """Return a qtawesome-backed :class:`QIcon` for ``stem``.

    Parameters
    ----------
    stem
        One of the keys in :data:`STEM_TO_GLYPH` (e.g. ``"run"``,
        ``"pause"``, ``"phase-portrait"``).
    color
        Optional hex string. ``None`` resolves to
        ``PALETTE.text_primary`` at call time, so a future palette
        / theme switch can re-tint the icon by calling this factory
        again. Hard-coding a literal here would defeat the purpose
        of the FU-002 token discipline.

    Returns
    -------
    QIcon
        A live qtawesome :class:`QIcon`. Rasterised on demand at
        the requested size by Qt's icon machinery; no precomputed
        pixmap is cached at the call site (qtawesome handles its
        own LRU internally).

    Raises
    ------
    KeyError
        If ``stem`` is not in :data:`STEM_TO_GLYPH`. Add the mapping
        here before adding a new icon stem to
        ``_toolbar_action_specs``.
    """
    from qtawesome import icon as qta_icon

    if color is None:
        from chaotic_systems.gui.theme import PALETTE

        color = PALETTE.text_primary

    glyph = STEM_TO_GLYPH[stem]
    return qta_icon(glyph, color=color)


__all__ = ["STEM_TO_GLYPH", "icon_for_stem"]
