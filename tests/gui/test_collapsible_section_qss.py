"""Tests for FU-004 — ``_CollapsibleSection`` ``variant="section-toggle"`` QSS rule.

Pre-FU-004 ``_CollapsibleSection.__init__`` carried an inline
``setStyleSheet`` call with a hardcoded ``color: #c0caf5`` literal
and a ``font-size: 12pt`` value that didn't match any token in
``docs/ui_design.md``:

.. code-block:: python

    self._toggle.setStyleSheet(
        "QPushButton[variant=\"section-toggle\"] {"
        " text-align: left; padding: 4px 6px;"
        " font-weight: 600; border: none; background: transparent;"
        " color: #c0caf5; font-size: 12pt; }"
    )

Post-FU-004 the rule lives in ``assets/dark.qss`` so a future
light-theme stylesheet can override it without touching Python,
and the font size is pinned at the canonical ``font-ctrl=13pt``
(``docs/ui_design.md §typography``). The visual semantics
(transparent background, no border, text-align left, padding,
weight) are preserved verbatim.

Coverage:

- ``_CollapsibleSection``'s toggle button no longer carries an
  inline stylesheet (the QSS rule lives in ``dark.qss``).
- The ``variant`` property remains set to ``"section-toggle"`` so
  the QSS selector still matches.
- ``dark.qss`` carries the ``QPushButton[variant="section-toggle"]``
  rule with token-grounded colour (``PALETTE.text_primary``) and
  ``font-size: 13pt`` (``font-ctrl``).
- The legacy ``font-size: 12pt`` literal is gone from the rule
  body.
- A ``:hover`` / ``:pressed`` override block exists so the
  borderless affordance doesn't pick up the default
  ``QPushButton:hover`` pill (visual scout F-04).
- The widget still expands / collapses end-to-end (no regression
  on the only behavioural contract the section exposes).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_window(qtbot):  # type: ignore[no-untyped-def]
    """Build a main window and register it with qtbot for cleanup."""

    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    win = Window()
    qtbot.addWidget(win)
    return win


def _first_section(window):  # type: ignore[no-untyped-def]
    """Return the first ``_CollapsibleSection`` instance attached to ``window``.

    ``_CollapsibleSection`` is a closure-local class inside
    ``_build_window_class``; the window creates several of them
    (``_ode_section``, ``_lagr_section``, ``_notes_section``) and
    we just need one to exercise the toggle.
    """

    # Mathematics panel always builds an ODE section.
    section = getattr(window, "_ode_section", None)
    assert section is not None, (
        "FU-004 test setup — main window must expose ``_ode_section``"
    )
    return section


# ---------------------------------------------------------------------------
# Inline stylesheet removed
# ---------------------------------------------------------------------------


def test_section_toggle_has_no_inline_stylesheet(qtbot) -> None:  # type: ignore[no-untyped-def]
    """The toggle button no longer carries an inline ``setStyleSheet``.

    Pre-FU-004 the inline style was the source of two problems:
    a literal ``#c0caf5`` bypassing PALETTE, and ``font-size: 12pt``
    contradicting the spec's ``font-ctrl=13pt`` for buttons.
    """

    window = _make_window(qtbot)
    try:
        section = _first_section(window)
        toggle = section._toggle  # noqa: SLF001
        ss = toggle.styleSheet()
        # The inline style is empty after FU-004.
        assert ss == "", (
            f"FU-004 — _CollapsibleSection toggle inline stylesheet "
            f"must be empty (the rule moved to dark.qss); got {ss!r}"
        )
        # And the two literals that motivated FU-004 must be gone.
        assert "#c0caf5" not in ss, "FU-004 — #c0caf5 literal must move to QSS"
        assert "12pt" not in ss, (
            "FU-004 — undocumented font-size: 12pt must be gone; "
            "the QSS rule pins 13pt (font-ctrl) per docs/ui_design.md"
        )
    finally:
        window.close()


def test_section_toggle_variant_property_preserved(qtbot) -> None:  # type: ignore[no-untyped-def]
    """The ``variant="section-toggle"`` property survives so the QSS rule matches."""

    window = _make_window(qtbot)
    try:
        section = _first_section(window)
        toggle = section._toggle  # noqa: SLF001
        assert toggle.property("variant") == "section-toggle", (
            "FU-004 — the variant property must remain set so the "
            "QPushButton[variant=\"section-toggle\"] QSS selector "
            "still matches; without it the inline-rule removal would "
            "leave the toggle un-styled."
        )
    finally:
        window.close()


# ---------------------------------------------------------------------------
# dark.qss carries the rule with token-grounded values
# ---------------------------------------------------------------------------


def _read_dark_qss() -> str:
    from pathlib import Path

    return (
        Path(__file__).resolve().parents[2]
        / "src"
        / "chaotic_systems"
        / "gui"
        / "assets"
        / "dark.qss"
    ).read_text(encoding="utf-8")


def test_dark_qss_carries_section_toggle_rule() -> None:
    """``dark.qss`` defines ``QPushButton[variant="section-toggle"]``."""

    qss = _read_dark_qss()
    assert 'QPushButton[variant="section-toggle"] {' in qss, (
        "FU-004 — dark.qss must declare the section-toggle rule"
    )


def test_section_toggle_rule_uses_palette_text_primary() -> None:
    """The rule's colour matches ``PALETTE.text_primary`` (token discipline)."""

    from chaotic_systems.gui.theme import PALETTE

    qss = _read_dark_qss()
    start = qss.index('QPushButton[variant="section-toggle"] {')
    # Read just the body of this rule (and its companion :hover block).
    block = qss[start : start + 1200]
    assert PALETTE.text_primary in block, (
        f"FU-004 — section-toggle rule must use PALETTE.text_primary "
        f"({PALETTE.text_primary!r}); without this the rule re-introduces "
        f"the token leak FU-004 was supposed to close."
    )


def test_section_toggle_rule_uses_font_ctrl_13pt() -> None:
    """The rule pins ``font-size: 13pt`` per ``docs/ui_design.md §typography``.

    Section headers are buttons (not card titles or H1s), so
    ``font-ctrl`` is the correct token. Synthesis §FU-004 makes
    this call explicitly.
    """

    qss = _read_dark_qss()
    start = qss.index('QPushButton[variant="section-toggle"] {')
    block = qss[start : start + 600]
    assert "font-size: 13pt" in block, (
        "FU-004 — section-toggle rule must use font-size: 13pt "
        "(font-ctrl token); the pre-FU-004 inline 12pt was a third "
        "undocumented type size."
    )
    assert "12pt" not in block, (
        "FU-004 — the legacy 12pt literal must be gone from the rule"
    )


def test_section_toggle_rule_has_hover_pressed_override() -> None:
    """A borderless / transparent override exists for ``:hover`` / ``:pressed``.

    Without it the default ``QPushButton:hover`` paints a
    ``#343a55`` pill behind the chevron, which visually reads as a
    button and breaks the row's clean affordance (visual-brief
    F-04).
    """

    qss = _read_dark_qss()
    assert 'QPushButton[variant="section-toggle"]:hover' in qss, (
        "FU-004 — section-toggle must override :hover or it inherits "
        "the default QPushButton hover pill"
    )
    assert 'QPushButton[variant="section-toggle"]:pressed' in qss, (
        "FU-004 — section-toggle must override :pressed for the same reason"
    )


# ---------------------------------------------------------------------------
# Behavioural regression check — collapse still works
# ---------------------------------------------------------------------------


def test_section_still_expands_and_collapses(qtbot) -> None:  # type: ignore[no-untyped-def]
    """The collapse / expand contract survives the QSS refactor.

    The only behaviour ``_CollapsibleSection`` exposes is the
    toggle's effect on the body's visibility + the chevron glyph.
    Both must still work after the inline-style removal.
    """

    window = _make_window(qtbot)
    try:
        section = _first_section(window)
        toggle = section._toggle  # noqa: SLF001
        body = section._body  # noqa: SLF001

        # The section may start in either state depending on which
        # one ``_ode_section`` defaults to — exercise both
        # transitions explicitly.
        toggle.setChecked(False)
        assert not toggle.isChecked()
        assert "▸" in toggle.text(), (
            "FU-004 — collapsed chevron glyph must still render"
        )
        toggle.setChecked(True)
        assert toggle.isChecked()
        assert "▾" in toggle.text(), (
            "FU-004 — expanded chevron glyph must still render"
        )
        # The body's visibility tracks the toggle state.
        assert body.isVisibleTo(section)
    finally:
        window.close()
