"""Tests for FU-005 — qtawesome icon migration.

Covers:

- ``STEM_TO_GLYPH`` covers every icon stem the toolbar specs reference;
  no stem can silently degrade to text-only (the AP-04 anti-pattern
  the critic flagged for the pre-FU-005 SVG path).
- ``icon_for_stem`` returns a non-null :class:`QIcon` with a
  rasterisable pixmap at toolbar size.
- The hand-rolled SVG directory is gone (asset cleanup landed).
- After ``_on_toggle_theme()`` fires, toolbar action icons still
  have non-null pixmaps (the challenger's CC-mitigation smoke
  test — catches qtawesome cache-invalidation regressions).
- ``theme.apply_theme`` no longer touches the ``assets/icons/``
  directory (the URL-rewriting hack is gone).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("qtawesome")


# ---------------------------------------------------------------------------
# Mapping table
# ---------------------------------------------------------------------------


def test_stem_to_glyph_covers_every_toolbar_action_spec() -> None:
    """Every icon stem ``_toolbar_action_specs`` declares is in the map.

    The pre-FU-005 path had a silent ``if icon_path.exists():`` guard
    that ate missing SVG files. FU-005's contract is the opposite:
    a missing mapping raises ``KeyError`` at construction time.
    This test pins the contract so a future toolbar addition is
    forced to add its glyph mapping.
    """

    from chaotic_systems.gui.icons import STEM_TO_GLYPH
    from chaotic_systems.gui.main_window import build_application

    app, window = build_application([])
    try:
        for spec in window._toolbar_action_specs():  # noqa: SLF001
            _obj, _label, stem, *_ = spec
            assert stem in STEM_TO_GLYPH, (
                f"icon stem {stem!r} from _toolbar_action_specs missing "
                f"from STEM_TO_GLYPH — FU-005 contract violation"
            )
        # And the gear stem (Settings button) is in the map too.
        assert "gear" in STEM_TO_GLYPH
    finally:
        window.close()
        assert app is not None


def test_stem_to_glyph_values_are_mdi6_glyph_ids() -> None:
    """Every mapping value is an ``mdi6.*`` glyph id.

    qtawesome supports multiple icon-font namespaces (``fa.``,
    ``mdi.``, ``mdi6.``, ``ph.``, ``msc.``). The project standardised
    on MDI6 because every glyph the project needs already exists
    there and the dependency stays single-font-pack.
    """

    from chaotic_systems.gui.icons import STEM_TO_GLYPH

    for stem, glyph in STEM_TO_GLYPH.items():
        assert glyph.startswith("mdi6."), (
            f"{stem!r} maps to {glyph!r}; expected mdi6.* prefix"
        )


# ---------------------------------------------------------------------------
# icon_for_stem — runtime behaviour
# ---------------------------------------------------------------------------


def test_icon_for_stem_returns_qicon_with_rasterisable_pixmap(qapp) -> None:  # type: ignore[no-untyped-def]
    """``icon_for_stem`` returns a real :class:`QIcon` with usable pixmap."""

    from PySide6.QtCore import QSize
    from PySide6.QtGui import QIcon

    from chaotic_systems.gui.icons import icon_for_stem
    from chaotic_systems.gui.theme import apply_theme

    apply_theme(qapp, "dark")
    icon = icon_for_stem("run")
    assert isinstance(icon, QIcon)
    assert not icon.isNull()

    # qtawesome rasterises on demand. A 16x16 pixmap (toolbar size)
    # must be non-null and the expected size.
    pix = icon.pixmap(QSize(16, 16))
    assert not pix.isNull()
    assert pix.width() == 16
    assert pix.height() == 16


def test_icon_for_stem_rejects_unknown_stem(qapp) -> None:  # type: ignore[no-untyped-def]
    """Unknown stems raise ``KeyError`` — no silent degradation."""

    from chaotic_systems.gui.icons import icon_for_stem

    with pytest.raises(KeyError):
        icon_for_stem("not-a-real-stem")


# ---------------------------------------------------------------------------
# Toolbar wiring — every action has a non-null icon
# ---------------------------------------------------------------------------


def test_every_toolbar_action_has_a_non_null_icon() -> None:
    """Pre-FU-005 the five analytics actions degraded to text-only.

    This is the headline behavioural fix — visual-scout F-02:
    "Five analysis toolbar actions have no SVG icons." After
    FU-005 every action's ``QAction.icon()`` is non-null and
    renders a 16x16 pixmap.
    """

    from PySide6.QtCore import QSize

    from chaotic_systems.gui.main_window import build_application

    app, window = build_application([])
    try:
        actions = window.transport_actions()
        missing: list[str] = []
        for name, action in actions.items():
            icon = action.icon()
            if icon.isNull() or icon.pixmap(QSize(16, 16)).isNull():
                missing.append(name)
        assert not missing, (
            f"FU-005 — toolbar actions still missing icons: {missing}"
        )
    finally:
        window.close()
        assert app is not None


def test_theme_toggle_keeps_icons_rasterisable() -> None:
    """Challenger CC-2 mitigation: after ``_on_toggle_theme()`` fires,
    toolbar icons must still have non-null pixmaps.

    qtawesome caches glyph pixmaps; a buggy cache-invalidation step
    on theme change could leave icons null or stuck at the prior
    theme's color. We don't pixel-compare (the test runner has no
    DPR contract); we verify the icon machinery still produces a
    pixmap at the new theme.
    """

    from PySide6.QtCore import QSize

    from chaotic_systems.gui.main_window import build_application

    app, window = build_application([])
    try:
        # Fire the theme-toggle slot directly (mirrors the toolbar
        # button press).
        window._on_toggle_theme()  # noqa: SLF001
        for name, action in window.transport_actions().items():
            pix = action.icon().pixmap(QSize(16, 16))
            assert not pix.isNull(), (
                f"FU-005 — {name!r} icon went null after theme toggle"
            )
    finally:
        window.close()
        assert app is not None


# ---------------------------------------------------------------------------
# Asset / theme cleanup
# ---------------------------------------------------------------------------


def test_assets_icons_directory_has_no_svgs() -> None:
    """The eleven hand-rolled SVG files are gone.

    FU-005 deletes the entire pre-qtawesome icon set. A future
    contributor adding a new SVG would re-introduce the
    silent-degradation surface, so this test pins emptiness.
    """

    from pathlib import Path

    icons_dir = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "chaotic_systems"
        / "gui"
        / "assets"
        / "icons"
    )
    # Directory itself may not exist after the cleanup (or may exist
    # as an empty dir). Either way, no .svg should be inside.
    if icons_dir.exists():
        svgs = list(icons_dir.glob("*.svg"))
        assert svgs == [], (
            f"FU-005 — stale SVG icons under {icons_dir}: {svgs}"
        )


def test_apply_theme_does_not_rewrite_icon_urls() -> None:
    """The pre-FU-005 URL-rewriting block in ``theme.apply_theme`` is gone.

    Setting up a QSS with the old ``url(assets/icons/foo.svg)``
    syntax would previously be rewritten in place. After FU-005 no
    such rewrite happens — the QSS is installed verbatim.
    """

    import inspect

    from chaotic_systems.gui import theme

    source = inspect.getsource(theme.apply_theme)
    # The literal substring search is robust: if a future change
    # restores the URL-rewriting hack, the test fails immediately.
    assert "url(assets/icons/" not in source, (
        "FU-005 — theme.apply_theme still contains a URL-rewriting "
        "block; the qtawesome migration should have removed it"
    )
