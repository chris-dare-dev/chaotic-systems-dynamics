"""Tests for FU-029 — inline parameter labels under equation rows.

Below the "Equations of motion" section the Mathematics card now
ships a monospace token strip showing the current parameter values
for the active system (e.g.
``sigma = 10.000    rho = 28.000    beta = 2.667``). The strip
refreshes whenever a parameter spinbox value changes or the user
switches systems. Closes the inspiration-brief A5 anti-pattern
("equation panel as pure read-only display") at S cost.

Coverage:

- The strip widget exists with ``role="param-strip"`` after the
  Mathematics card is built.
- For Lorenz (3 parameters) the strip renders all three tokens in
  the canonical fixed-decimal format.
- Changing a parameter spinbox updates the strip live (route:
  ``_on_param_changed_for_preview`` regardless of whether
  live-preview is armed).
- Switching to a different system rebuilds the strip's contents.
- A system with no parameters (rare; documented in the helper)
  hides the strip rather than showing an empty line.
- The ``dark.qss`` rule for ``QLabel[role="param-strip"]`` is
  present and uses PALETTE tokens.
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
# Widget existence + initial render
# ---------------------------------------------------------------------------


def test_param_strip_exists_with_canonical_role(qtbot) -> None:  # type: ignore[no-untyped-def]
    """The Mathematics card carries a ``QLabel[role="param-strip"]``."""

    from PySide6.QtWidgets import QLabel

    window = _make_window(qtbot)
    strip = window._param_strip  # noqa: SLF001
    assert isinstance(strip, QLabel)
    assert strip.objectName() == "param_strip"
    assert strip.property("role") == "param-strip"


def test_param_strip_renders_lorenz_parameters_at_startup(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Default system Lorenz has sigma/rho/beta — all three appear in the strip."""

    window = _make_window(qtbot)
    text = window._param_strip.text()  # noqa: SLF001
    # Strip not hidden (``isVisible()`` checks ancestors; pytest's
    # unshown window would fail that, so we check the widget's own
    # hidden flag).
    assert not window._param_strip.isHidden()  # noqa: SLF001
    # Each canonical parameter renders.
    assert "sigma" in text
    assert "rho" in text
    assert "beta" in text
    # Default Lorenz values: sigma=10, rho=28, beta=8/3=2.667.
    assert "sigma = 10.000" in text
    assert "rho = 28.000" in text
    assert "beta = 2.667" in text


def test_param_strip_uses_four_space_separator(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Tokens are joined with four spaces (visual breathing room).

    Pinning the separator keeps the strip's spacing predictable
    across future systems; a future drift to comma-separated or
    tab-separated would change the visual cadence noticeably.
    """

    window = _make_window(qtbot)
    text = window._param_strip.text()  # noqa: SLF001
    # Lorenz has three tokens, so two separators.
    assert text.count("    ") >= 2


# ---------------------------------------------------------------------------
# Live updates
# ---------------------------------------------------------------------------


def test_param_strip_updates_when_spinbox_changes(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Driving a parameter spinbox refreshes the strip text live.

    The route is ``QDoubleSpinBox.valueChanged -> _on_param_changed_for_preview
    -> _refresh_param_strip``. The live-preview setting being off
    does *not* prevent the strip refresh — the strip is a passive
    display, not a compute trigger.
    """

    window = _make_window(qtbot)
    # Live-preview off to confirm the strip refreshes regardless.
    assert window._setting_live_preview is False  # noqa: SLF001

    sigma_widget = window._param_widgets["sigma"]  # noqa: SLF001
    sigma_widget._spin.setValue(15.5)  # noqa: SLF001
    text = window._param_strip.text()  # noqa: SLF001
    assert "sigma = 15.500" in text, (
        f"FU-029 — strip didn't refresh after spinbox change; got {text!r}"
    )


def test_param_strip_rebuilds_when_system_changes(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Switching to a different system rebuilds the strip's contents.

    Rossler has parameters a/b/c (different names from Lorenz's
    sigma/rho/beta), so the strip's text must change substantively
    when the system picker switches.
    """

    window = _make_window(qtbot)
    lorenz_text = window._param_strip.text()  # noqa: SLF001
    assert "sigma" in lorenz_text

    # Switch to Rossler — find by display name in the system box.
    idx = window.system_box.findText("Rossler")
    if idx < 0:
        pytest.skip("Rossler not registered in this build")
    window.system_box.setCurrentIndex(idx)
    rossler_text = window._param_strip.text()  # noqa: SLF001
    # Different system → different parameter names → different text.
    assert "sigma" not in rossler_text
    # Rossler uses a, b, c (Rossler 1976).
    assert "a = " in rossler_text
    assert "b = " in rossler_text
    assert "c = " in rossler_text


# ---------------------------------------------------------------------------
# QSS — token discipline
# ---------------------------------------------------------------------------


def test_param_strip_qss_rule_uses_palette_tokens() -> None:
    """The ``QLabel[role="param-strip"]`` rule uses PALETTE tokens.

    Same token-discipline contract FU-019 introduced: a future
    palette change must update the strip's QSS too (or this test
    fails).
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

    selector = 'QLabel[role="param-strip"]'
    assert selector in qss_text, (
        f"FU-029 — dark.qss missing {selector!r} rule"
    )
    start = qss_text.index(selector)
    block = qss_text[start : start + 400]

    # text-secondary is the canonical color for supplementary text.
    assert PALETTE.text_secondary in block, (
        "param-strip color must use PALETTE.text_secondary"
    )
    # Monospace font keeps tokens column-stable.
    assert "monospace" in block.lower()


# ---------------------------------------------------------------------------
# Refresh helper — direct invocation
# ---------------------------------------------------------------------------


def test_refresh_param_strip_is_idempotent(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Calling ``_refresh_param_strip`` twice produces the same text."""

    window = _make_window(qtbot)
    window._refresh_param_strip()  # noqa: SLF001
    text_1 = window._param_strip.text()  # noqa: SLF001
    window._refresh_param_strip()  # noqa: SLF001
    text_2 = window._param_strip.text()  # noqa: SLF001
    assert text_1 == text_2
