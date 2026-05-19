"""Tests for the Lyapunov-spectrum Diagnostics card.

The full Lyapunov spectrum has been computable since the initial
implementation in ``core/lyapunov.py``, but wasn't surfaced in the
GUI until this card landed (see docs/proposals/capability-roadmap-
2026-05-17.md, proposal D1). These tests pin:

- The card's widgets exist (including the CSC-032 quick-mode toggle).
- ``_format_lyapunov_spectrum`` classifies regular / chaotic /
  hyperchaotic correctly and pulls out the leading exponent.
- ``_format_quick_lyapunov`` formats a single-exponent quick result
  with no D_KY line (CSC-032 / T1).
- The worker's ``finished`` signal flows into the result label and
  the status-bar chip; the ``quick_finished`` signal renders the
  one-line quick-mode output.
- Changing systems resets the card to its prompt copy.

The actual ``lyapunov_spectrum`` / ``largest_lyapunov_two_trajectory``
computes are the ``tests/core/`` and ``tests/systems/`` suites'
concern — these tests stub the worker so they stay fast.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")

from chaotic_systems.gui.main_window import (
    _format_lyapunov_spectrum,
    _format_quick_lyapunov,
)


def _make_window(qtbot):  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)
    return window


# ---------------------------------------------------------------------------
# Pure-function tests for the formatter.
# ---------------------------------------------------------------------------


def test_format_classifies_regular() -> None:
    text, leading = _format_lyapunov_spectrum(np.array([0.0, -0.5, -1.2]))
    assert "Regular" in text
    assert leading == pytest.approx(0.0)


def test_format_classifies_chaotic_lorenz_like() -> None:
    # Lorenz-like spectrum: one positive, one near-zero, one strongly negative.
    text, leading = _format_lyapunov_spectrum(np.array([0.91, 0.0, -14.57]))
    assert "Chaotic" in text
    assert "1 positive" in text
    assert leading == pytest.approx(0.91)
    # Sorted descending for display.
    assert "λ1 = +0.9100" in text
    assert "λ3 = -14.5700" in text
    # Kaplan-Yorke dimension is rendered as the last line; Sprott
    # Table 5.1 quotes ~2.062 for Lorenz canonical.
    assert "D_KY = 2.062" in text


def test_format_classifies_hyperchaotic_4d() -> None:
    # 4D hyperchaos: two positive exponents.
    text, leading = _format_lyapunov_spectrum(np.array([0.16, 0.03, 0.0, -25.0]))
    assert "Hyperchaotic" in text
    assert "2 positive" in text
    assert leading == pytest.approx(0.16)
    # 4D hyperchaos: D_KY > 3 with two positive exponents.
    # Cumulative sums: (0.16, 0.19, 0.19, -24.81) -> k=3, D_KY = 3 + 0.19/25.
    assert "D_KY = 3.008" in text


def test_format_sorts_unordered_input() -> None:
    text, leading = _format_lyapunov_spectrum(np.array([-14.57, 0.91, 0.0]))
    assert "λ1 = +0.9100" in text
    assert leading == pytest.approx(0.91)


def test_format_handles_empty_spectrum() -> None:
    text, leading = _format_lyapunov_spectrum(np.array([]))
    assert "empty" in text.lower()
    assert leading == 0.0


# ---------------------------------------------------------------------------
# CSC-032 / T1 — quick-mode formatter.
# ---------------------------------------------------------------------------


def test_quick_format_chaotic_classification() -> None:
    """λ₁ > 0 (above zero tol) → Chaotic + (quick estimate) suffix."""
    text, leading = _format_quick_lyapunov(0.9072)
    assert "Chaotic" in text
    assert "quick estimate" in text
    assert "λ1 = +0.9072" in text
    # No D_KY line: Kaplan-Yorke needs the whole spectrum.
    assert "D_KY" not in text
    assert leading == pytest.approx(0.9072)


def test_quick_format_regular_classification() -> None:
    text, _ = _format_quick_lyapunov(-0.5)
    assert "Regular" in text
    assert "λ1 = -0.5000" in text


def test_quick_format_marginal_near_zero() -> None:
    text, _ = _format_quick_lyapunov(0.0)
    assert "Marginal" in text
    assert "λ1 = +0.0000" in text


def test_quick_format_non_finite_input() -> None:
    text, leading = _format_quick_lyapunov(float("nan"))
    assert "non-finite" in text.lower()
    assert leading == 0.0


# ---------------------------------------------------------------------------
# GUI wiring tests.
# ---------------------------------------------------------------------------


def test_card_widgets_exist(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Compute button + result label + quick-mode toggle are wired in."""

    window = _make_window(qtbot)
    assert window.lyapunov_button is not None
    assert window.lyapunov_button.objectName() == "button_lyapunov"
    assert window.lyapunov_result_label is not None
    # Initial copy invites the user to compute.
    assert "compute" in window.lyapunov_result_label.text().lower()
    # CSC-032 — the quick-mode toggle exists, has the expected
    # objectName, and defaults to unchecked so the full spectrum
    # remains the default path.
    assert hasattr(window, "quick_lyapunov_checkbox")
    assert window.quick_lyapunov_checkbox.objectName() == "checkbox_quick_lyapunov"
    assert window.quick_lyapunov_checkbox.isChecked() is False


def test_quick_lyapunov_finished_signal_updates_card(qtbot) -> None:  # type: ignore[no-untyped-def]
    """The CSC-032 quick-mode signal renders λ₁ with no D_KY line."""

    window = _make_window(qtbot)
    window._on_quick_lyapunov_finished(0.9072)  # noqa: SLF001
    text = window.lyapunov_result_label.text()
    assert "Chaotic" in text
    assert "quick estimate" in text
    assert "0.9072" in text
    # No spectrum or D_KY in quick-mode output.
    assert "D_KY" not in text
    assert "λ2" not in text
    assert "λ3" not in text
    # Status-bar chip still mirrors the leading exponent.
    if hasattr(window, "lyapunov_chip"):
        assert "0.9072" in window.lyapunov_chip.text()
        assert not window.lyapunov_chip.isHidden()
    # Compute button re-enables for the next click.
    assert window.lyapunov_button.isEnabled()


def test_quick_toggle_survives_system_change(qtbot) -> None:  # type: ignore[no-untyped-def]
    """The quick-mode preference is sticky across system switches."""

    window = _make_window(qtbot)
    window.quick_lyapunov_checkbox.setChecked(True)
    if window.system_box.count() < 2:
        pytest.skip("only one system registered; cycling is a no-op")
    next_idx = (window.system_box.currentIndex() + 1) % window.system_box.count()
    window.system_box.setCurrentIndex(next_idx)
    # User preference persists; the result label resets but the
    # toggle does not.
    assert window.quick_lyapunov_checkbox.isChecked() is True


def test_lyapunov_finished_signal_updates_card(qtbot) -> None:  # type: ignore[no-untyped-def]
    """A simulated worker-finished call updates the label + status chip."""

    window = _make_window(qtbot)
    # Lorenz-canonical spectrum.
    spectrum = np.array([0.9072, 0.0, -14.572])
    window._on_lyapunov_finished(spectrum)  # noqa: SLF001
    assert "Chaotic" in window.lyapunov_result_label.text()
    assert "0.9072" in window.lyapunov_result_label.text()
    # Status-bar chip mirrors the leading exponent. ``isVisible``
    # depends on parent show-state (the test never shows the window),
    # so check ``not isHidden`` which tracks the explicit setVisible
    # flag instead.
    if hasattr(window, "lyapunov_chip"):
        assert "0.9072" in window.lyapunov_chip.text()
        assert not window.lyapunov_chip.isHidden()
    # Button re-enables.
    assert window.lyapunov_button.isEnabled()


def test_lyapunov_error_signal_re_enables_button(qtbot) -> None:  # type: ignore[no-untyped-def]
    """A simulated worker-error call surfaces the message + re-enables."""

    window = _make_window(qtbot)
    window.lyapunov_button.setEnabled(False)
    window._on_lyapunov_error("RuntimeError", "diverged")  # noqa: SLF001
    assert "diverged" in window.lyapunov_result_label.text()
    assert "RuntimeError" in window.lyapunov_result_label.text()
    assert window.lyapunov_button.isEnabled()


def test_card_resets_on_system_change(qtbot) -> None:  # type: ignore[no-untyped-def]
    """After a result lands, switching systems clears the card to prompt copy."""

    window = _make_window(qtbot)
    # Pretend a previous compute left a result behind.
    window._on_lyapunov_finished(np.array([0.91, 0.0, -14.57]))  # noqa: SLF001
    assert "Chaotic" in window.lyapunov_result_label.text()
    # Cycle to the next registered system (if there is one).
    if window.system_box.count() < 2:
        pytest.skip("only one system registered; cycling is a no-op")
    next_idx = (window.system_box.currentIndex() + 1) % window.system_box.count()
    window.system_box.setCurrentIndex(next_idx)
    text = window.lyapunov_result_label.text().lower()
    assert "compute" in text
    assert "chaotic" not in text
