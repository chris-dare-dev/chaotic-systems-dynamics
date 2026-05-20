"""Tests for FU-019 — inline parameter value readout chip.

Each ``_ParamWidget`` row now ends with a monospace readout
``QLabel`` showing the current parameter value, formatted to three
decimals normally and to scientific notation when the magnitude
crosses three orders (|v| ≥ 1000 or 0 < |v| < 0.001). The
``role="readout-chip"`` selector hooks the chip into the project's
dark-theme QSS vocabulary.

Coverage:

- ``_format_param_readout`` returns the right text for every band:
  zero, normal range, large (sci), small (sci), negative variants.
- A built ``_ParamWidget`` exposes a ``_readout`` ``QLabel`` with
  ``role="readout-chip"`` and the initial value rendered.
- Changing the spinbox value updates the readout text via the
  ``valueChanged`` signal connection.
- The ``dark.qss`` rule for ``QLabel[role="readout-chip"]`` is
  present and uses the canonical PALETTE tokens (token-discipline
  check — the synthesis flagged this as the MINOR risk).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")


# ---------------------------------------------------------------------------
# _format_param_readout — formatter contract
# ---------------------------------------------------------------------------


def _get_formatter():
    """Return the side-attached ``_format_param_readout`` staticmethod."""
    from chaotic_systems.gui.main_window import _build_window_class

    cls = _build_window_class()
    return cls._format_param_readout  # noqa: SLF001


def test_format_param_readout_uses_three_decimals_in_normal_band(qapp) -> None:  # type: ignore[no-untyped-def]
    """Values in [0.001, 1000) render as ``name = X.XXX``."""

    fmt = _get_formatter()
    assert fmt("sigma", 10.0) == "sigma = 10.000"
    assert fmt("rho", 28.0) == "rho = 28.000"
    assert fmt("beta", 8.0 / 3.0) == "beta = 2.667"
    assert fmt("K", 1.5) == "K = 1.500"
    assert fmt("delta", 0.2) == "delta = 0.200"


def test_format_param_readout_switches_to_scientific_for_large(qapp) -> None:  # type: ignore[no-untyped-def]
    """Magnitudes >= 1000 render in scientific notation.

    The synthesis ties the switch to "three orders of magnitude" — 1000
    is the exclusive upper edge of the fixed-decimal band.
    """

    fmt = _get_formatter()
    out = fmt("c", 1234.5)
    assert "e+" in out.lower()
    assert out.startswith("c = ")
    # Round-trip check: parse the value back, should be close.
    value_text = out.split(" = ", 1)[1]
    assert float(value_text) == pytest.approx(1234.5, rel=1e-3)


def test_format_param_readout_switches_to_scientific_for_small(qapp) -> None:  # type: ignore[no-untyped-def]
    """Magnitudes in (0, 0.001) render in scientific notation."""

    fmt = _get_formatter()
    out = fmt("epsilon", 1e-6)
    assert "e-" in out.lower()
    assert out.startswith("epsilon = ")
    value_text = out.split(" = ", 1)[1]
    assert float(value_text) == pytest.approx(1e-6, rel=1e-3)


def test_format_param_readout_renders_zero_as_fixed(qapp) -> None:  # type: ignore[no-untyped-def]
    """Zero is fixed (``0.000``), not scientific (``0.000e+00``).

    Edge case: the magnitude check ``av >= 1000 or av < 0.001`` would
    naively trigger scientific for ``av == 0``; the formatter guards
    against this so zero renders cleanly.
    """

    fmt = _get_formatter()
    assert fmt("z", 0.0) == "z = 0.000"


def test_format_param_readout_handles_negative(qapp) -> None:  # type: ignore[no-untyped-def]
    """Negative values format identically modulo the leading minus."""

    fmt = _get_formatter()
    assert fmt("alpha", -1.5) == "alpha = -1.500"
    out_big = fmt("alpha", -1e5)
    assert "-" in out_big and "e+" in out_big.lower()


# ---------------------------------------------------------------------------
# _ParamWidget integration
# ---------------------------------------------------------------------------


def _make_param_widget(qapp, *, default: float = 10.0):  # type: ignore[no-untyped-def]
    """Build a fresh ``_ParamWidget`` for ``sigma``-like defaults."""
    from chaotic_systems.core.base import Parameter
    from chaotic_systems.gui.main_window import _build_window_class

    cls = _build_window_class()
    p = Parameter("sigma", default, 0.1, 50.0, "Prandtl number", "")
    return cls._ParamWidget(p)  # noqa: SLF001


def test_param_widget_carries_a_readout_chip_label(qapp) -> None:  # type: ignore[no-untyped-def]
    """``_ParamWidget`` exposes ``_readout`` with ``role="readout-chip"``."""

    from PySide6.QtWidgets import QLabel

    widget = _make_param_widget(qapp)
    try:
        readout = widget._readout  # noqa: SLF001
        assert isinstance(readout, QLabel)
        assert readout.property("role") == "readout-chip"
        # The initial text reflects the default value.
        assert readout.text() == "sigma = 10.000"
    finally:
        widget.deleteLater()


def test_param_widget_readout_updates_when_spinbox_changes(qapp) -> None:  # type: ignore[no-untyped-def]
    """Driving the spinbox programmatically updates the readout text live."""

    widget = _make_param_widget(qapp, default=10.0)
    try:
        # Use the public spin setter — this fires valueChanged, which
        # is connected to the readout-update slot.
        widget._spin.setValue(25.5)  # noqa: SLF001
        assert widget._readout.text() == "sigma = 25.500"  # noqa: SLF001

        widget._spin.setValue(48.0)  # noqa: SLF001 — within range
        assert widget._readout.text() == "sigma = 48.000"  # noqa: SLF001
    finally:
        widget.deleteLater()


def test_param_widget_readout_scientific_path_on_wide_range_parameter(qapp) -> None:  # type: ignore[no-untyped-def]
    """A parameter with a wide range that includes small values renders scientific.

    The previous test pins the fixed-decimal path; this one exercises
    the scientific branch end-to-end. Uses a synthetic Parameter
    whose range admits values below 0.001 (the formatter's
    fixed-to-scientific threshold).
    """

    from chaotic_systems.core.base import Parameter
    from chaotic_systems.gui.main_window import _build_window_class

    cls = _build_window_class()
    # Eps-style parameter whose *default* is small — this drives the
    # _ParamWidget decimals heuristic to give the spinbox enough
    # precision (step ≈ 1% of default = 1e-8, so decimals = 10) that
    # a setValue(1e-6) call survives spinbox rounding intact.
    p = Parameter("eps", 1e-6, 1e-9, 1.0, "tolerance", "")
    widget = cls._ParamWidget(p)  # noqa: SLF001
    try:
        # The default itself is already small enough; just verify the
        # initial readout rendered scientific.
        text = widget._readout.text()  # noqa: SLF001
        assert text.startswith("eps = ")
        assert "e-" in text.lower(), (
            f"FU-019 — small value should render scientific; got {text!r}"
        )
    finally:
        widget.deleteLater()


def test_param_widget_readout_appears_after_slider_in_layout(qapp) -> None:  # type: ignore[no-untyped-def]
    """The readout sits at the right edge of the row (after the slider).

    The synthesis positions the chip "to the right of the spinbox";
    practically the row is ``[spin][slider][readout]`` so the chip
    lands at the right edge where it doesn't fight the slider for
    horizontal space.
    """

    widget = _make_param_widget(qapp)
    try:
        layout = widget.layout()
        assert layout.count() == 3, (
            f"FU-019 — _ParamWidget row should have 3 widgets "
            f"(spin, slider, readout); got {layout.count()}"
        )
        last_item = layout.itemAt(layout.count() - 1).widget()
        assert last_item is widget._readout, (  # noqa: SLF001
            "readout chip must be the right-most widget in the row"
        )
    finally:
        widget.deleteLater()


# ---------------------------------------------------------------------------
# QSS — token discipline
# ---------------------------------------------------------------------------


def test_readout_chip_qss_rule_uses_palette_tokens() -> None:
    """The ``QLabel[role="readout-chip"]`` rule uses canonical PALETTE tokens.

    Synthesis flagged this as the FU-019 MINOR risk: "If the
    implementation picks an arbitrary background or monospace font
    size, it's a token leak." This test parses the rule out of
    ``dark.qss`` and asserts it references the right tokens.
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

    # Find the readout-chip block.
    selector = 'QLabel[role="readout-chip"]'
    assert selector in qss_text, (
        f"FU-019 — dark.qss missing {selector!r} rule"
    )
    start = qss_text.index(selector)
    block = qss_text[start : start + 600]

    # PALETTE tokens that must appear in the rule.
    assert PALETTE.text_primary in block, (
        "readout-chip color must use PALETTE.text_primary"
    )
    assert PALETTE.bg_elevated in block, (
        "readout-chip background must use PALETTE.bg_elevated"
    )
    assert PALETTE.border in block, (
        "readout-chip border must use PALETTE.border"
    )
    # Monospace font is the chip's defining characteristic.
    assert "monospace" in block.lower()
