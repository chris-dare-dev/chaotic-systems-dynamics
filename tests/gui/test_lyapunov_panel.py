"""Tests for the Lyapunov-spectrum Diagnostics card.

The full Lyapunov spectrum has been computable since the initial
implementation in ``core/lyapunov.py``, but wasn't surfaced in the
GUI until this card landed (see docs/proposals/capability-roadmap-
2026-05-17.md, proposal D1). These tests pin:

- The card's widgets exist.
- ``_format_lyapunov_spectrum`` classifies regular / chaotic /
  hyperchaotic correctly and pulls out the leading exponent.
- The worker's ``finished`` signal flows into the result label and
  the status-bar chip.
- Changing systems resets the card to its prompt copy.

The actual ``lyapunov_spectrum`` compute is the
``tests/core/test_lyapunov.py`` suite's concern — these tests stub
the worker so they stay fast.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")

from chaotic_systems.gui.main_window import _format_lyapunov_spectrum


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


def test_format_classifies_hyperchaotic_4d() -> None:
    # 4D hyperchaos: two positive exponents.
    text, leading = _format_lyapunov_spectrum(np.array([0.16, 0.03, 0.0, -25.0]))
    assert "Hyperchaotic" in text
    assert "2 positive" in text
    assert leading == pytest.approx(0.16)


def test_format_sorts_unordered_input() -> None:
    text, leading = _format_lyapunov_spectrum(np.array([-14.57, 0.91, 0.0]))
    assert "λ1 = +0.9100" in text
    assert leading == pytest.approx(0.91)


def test_format_handles_empty_spectrum() -> None:
    text, leading = _format_lyapunov_spectrum(np.array([]))
    assert "empty" in text.lower()
    assert leading == 0.0


# ---------------------------------------------------------------------------
# GUI wiring tests.
# ---------------------------------------------------------------------------


def test_card_widgets_exist(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Compute button + result label are wired into the left panel."""

    window = _make_window(qtbot)
    assert window.lyapunov_button is not None
    assert window.lyapunov_button.objectName() == "button_lyapunov"
    assert window.lyapunov_result_label is not None
    # Initial copy invites the user to compute.
    assert "compute" in window.lyapunov_result_label.text().lower()


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
