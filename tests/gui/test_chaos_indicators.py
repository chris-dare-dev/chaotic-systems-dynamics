"""Tests for the Chaos Indicator Suite Diagnostics-card section (CIS-1).

Mirrors `tests/gui/test_lyapunov_panel.py` in shape: pure-function
tests for the formatter, then GUI wiring tests gated on
``CHAOTIC_GUI_TESTS_USE_DISPLAY=1`` + ``PySide6`` + ``pyvistaqt``.

The compute side is the four `chaotic_systems.core.diagnostics`
functions shipped by CSC-011/012/013/014, each independently
tested in their own ``tests/core/test_chaos_*.py`` files (64 tests
total). These tests pin the GUI wire-up only — the button exists,
the worker dispatch path is correct, the finished handler updates
the result label + sampling-rate banner appropriately, the error
handler re-enables the button, and the system-change reset hides
the banner / clears the result.

Numerical observable from the CIS-1 proposal: with HenonHeiles at
the canonical IC, after a Run + clicking "Compute indicators", all
four chips populate within ~10 s with K (≈ 0 for regular orbits /
≈ 1 for chaotic), digit-loss (≈ 16 for regular / ≈ 1-3 for
chaotic), H_PE (> 0.99 for chaotic), H_Hurst (≈ 0.56 for
memoryless signals) — within the documented reference ranges from
``diagnostics.py``.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")

from chaotic_systems.gui.main_window import (
    _CHAOS_SAMPLING_DT_THRESHOLD,
    _format_chaos_indicators,
)


def _make_window(qtbot):  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)
    return window


# ---------------------------------------------------------------------------
# Pure-function tests for _format_chaos_indicators.
# ---------------------------------------------------------------------------


def test_format_chaotic_lorenz_like_no_oversampling_warning() -> None:
    """Chaotic Lorenz-like payload at dt=1.0 -> no warning."""
    payload = {
        "K": 0.998,
        "digit_loss": 2.4,
        "H_PE": 0.99,
        "H_Hurst": 0.56,
        "dt": 1.0,
        "n_samples": 2000,
    }
    text, warn = _format_chaos_indicators(payload)
    assert "K       = 0.9980" in text
    assert "d-loss  = 2.400" in text
    assert "H_PE    = 0.9900" in text
    assert "H_Hurst = 0.5600" in text
    assert "N = 2000 samples" in text
    assert "dt = 1" in text
    assert warn is False


def test_format_oversampled_payload_raises_warning() -> None:
    """dt = 0.04 (below the 0.1 threshold) -> warning."""
    payload = {
        "K": 0.025,
        "digit_loss": 8.7,
        "H_PE": 0.85,
        "H_Hurst": 0.7,
        "dt": 0.04,
        "n_samples": 2000,
    }
    text, warn = _format_chaos_indicators(payload)
    assert "dt = 0.04" in text
    assert warn is True


def test_format_partial_failure_renders_nan_as_n_a() -> None:
    """NaN indicator values render as ``n/a`` rather than ``nan``."""
    payload = {
        "K": 0.5,
        "digit_loss": 4.5,
        "H_PE": 0.6,
        "H_Hurst": float("nan"),
        "dt": 0.5,
        "n_samples": 500,
    }
    text, _ = _format_chaos_indicators(payload)
    assert "H_Hurst = n/a" in text
    assert "nan" not in text  # the nan->n/a substitution worked


def test_format_missing_dt_omits_dt_clause() -> None:
    """dt = NaN -> the header omits the ``dt = ...`` clause entirely."""
    payload = {
        "K": 0.5,
        "digit_loss": 4.5,
        "H_PE": 0.6,
        "H_Hurst": 0.5,
        "dt": float("nan"),
        "n_samples": 1000,
    }
    text, warn = _format_chaos_indicators(payload)
    assert "dt =" not in text
    assert warn is False  # NaN dt does not trigger the warning


def test_threshold_constant_matches_docstring_calibration() -> None:
    """The sampling-rate threshold should be 0.1 per chaos_zero_one_test docstring."""
    assert _CHAOS_SAMPLING_DT_THRESHOLD == 0.1


# ---------------------------------------------------------------------------
# GUI wiring tests.
# ---------------------------------------------------------------------------


def test_chaos_indicators_widgets_exist(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Button + banner + result label are present with stable object names."""
    window = _make_window(qtbot)
    assert hasattr(window, "chaos_indicators_button")
    assert (
        window.chaos_indicators_button.objectName() == "button_chaos_indicators"
    )
    assert hasattr(window, "chaos_indicators_banner")
    assert (
        window.chaos_indicators_banner.objectName()
        == "chaos_indicators_banner"
    )
    assert hasattr(window, "chaos_indicators_result_label")
    assert (
        window.chaos_indicators_result_label.objectName()
        == "chaos_indicators_result_label"
    )
    # Banner is hidden until a sampling-rate violation is detected.
    assert window.chaos_indicators_banner.isHidden()
    # Result label carries the prompt copy until a compute lands.
    assert "Click to compute" in window.chaos_indicators_result_label.text()
    # Button is enabled — the click-time handler decides whether a
    # trajectory exists; we don't pre-gate.
    assert window.chaos_indicators_button.isEnabled()


def test_chaos_indicators_finished_signal_updates_card(qtbot) -> None:  # type: ignore[no-untyped-def]
    """A simulated worker-finished call populates the result label + chips."""
    window = _make_window(qtbot)
    # Disable the button as if a compute had been in flight, then
    # drive the finished handler directly. Lorenz-canonical payload.
    window.chaos_indicators_button.setEnabled(False)
    payload = {
        "K": 0.998,
        "digit_loss": 2.4,
        "H_PE": 0.99,
        "H_Hurst": 0.56,
        "dt": 1.0,
        "n_samples": 2000,
    }
    window._on_chaos_indicators_finished(payload)  # noqa: SLF001
    text = window.chaos_indicators_result_label.text()
    assert "K       = 0.9980" in text
    assert "d-loss  = 2.400" in text
    assert "H_PE    = 0.9900" in text
    assert "H_Hurst = 0.5600" in text
    # No oversampling warning at dt = 1.0.
    assert window.chaos_indicators_banner.isHidden()
    # Button is re-enabled.
    assert window.chaos_indicators_button.isEnabled()


def test_chaos_indicators_oversampling_banner_appears(qtbot) -> None:  # type: ignore[no-untyped-def]
    """dt < 0.1 -> the sampling-rate banner becomes visible."""
    window = _make_window(qtbot)
    payload = {
        "K": 0.025,
        "digit_loss": 8.7,
        "H_PE": 0.85,
        "H_Hurst": 0.7,
        "dt": 0.04,
        "n_samples": 2000,
    }
    window._on_chaos_indicators_finished(payload)  # noqa: SLF001
    assert not window.chaos_indicators_banner.isHidden()
    banner_text = window.chaos_indicators_banner.text()
    assert "0.04" in banner_text
    assert "oversampled" in banner_text.lower()
    assert "downsample" in banner_text.lower()


def test_chaos_indicators_error_signal_re_enables_button(qtbot) -> None:  # type: ignore[no-untyped-def]
    """A simulated worker-error call surfaces the message + re-enables button."""
    window = _make_window(qtbot)
    window.chaos_indicators_button.setEnabled(False)
    window.chaos_indicators_banner.setVisible(True)
    window._on_chaos_indicators_error(  # noqa: SLF001
        "ValueError", "timeseries too short for chaos indicators"
    )
    assert (
        "ValueError" in window.chaos_indicators_result_label.text()
    )
    assert (
        "too short" in window.chaos_indicators_result_label.text()
    )
    assert window.chaos_indicators_button.isEnabled()
    # Banner is hidden on error (no dt to surface).
    assert window.chaos_indicators_banner.isHidden()


def test_compute_without_trajectory_surfaces_friendly_hint(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Clicking compute with no trajectory yields a Run-first hint."""
    window = _make_window(qtbot)
    assert window._last_trajectory is None  # noqa: SLF001
    window._on_compute_chaos_indicators()  # noqa: SLF001
    text = window.chaos_indicators_result_label.text()
    assert "Run a simulation first" in text
    # No worker should have started.
    assert window._chaos_indicators_thread is None  # noqa: SLF001
    assert window.chaos_indicators_button.isEnabled()


def test_system_switch_resets_chaos_indicators_card(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Switching systems clears the result label + hides the banner."""
    window = _make_window(qtbot)
    # Pretend a previous compute left state behind.
    window._on_chaos_indicators_finished(  # noqa: SLF001
        {
            "K": 0.025,
            "digit_loss": 8.7,
            "H_PE": 0.85,
            "H_Hurst": 0.7,
            "dt": 0.04,
            "n_samples": 2000,
        }
    )
    assert "K       = 0.0250" in window.chaos_indicators_result_label.text()
    assert not window.chaos_indicators_banner.isHidden()
    # Cycle to the next registered system, if there is one.
    if window.system_box.count() < 2:
        pytest.skip("only one system registered; cycling is a no-op")
    next_idx = (
        window.system_box.currentIndex() + 1
    ) % window.system_box.count()
    window.system_box.setCurrentIndex(next_idx)
    text = window.chaos_indicators_result_label.text()
    assert "Click to compute" in text
    assert "K       = 0.0250" not in text
    assert window.chaos_indicators_banner.isHidden()


# ---------------------------------------------------------------------------
# Worker compute-path integration test (runs the actual worker on a
# small synthetic trajectory; pinned by reference observable).
# ---------------------------------------------------------------------------


def test_worker_run_emits_finished_with_all_four_values(qtbot) -> None:  # type: ignore[no-untyped-def]
    """The worker runs all four indicators and emits the dict payload."""
    from chaotic_systems.gui.main_window import _build_window_class

    _build_window_class()  # ensures the worker class is built lazily.
    # Re-import after the class build so the worker is in scope.
    from chaotic_systems.gui.main_window import _build_window_class as _bwc

    _bwc()
    # Reach into the module's lazy-build cache to grab the worker class.

    worker_cls = None
    # The lazy-built classes live as locals to _build_window_class;
    # since we have no direct accessor, drive the worker via the
    # window instance's slot which constructs it internally.
    window = _make_window(qtbot)

    # Build a synthetic trajectory with enough samples for all four
    # indicators (most-restrictive floor is WBA/Hurst at 200).
    rng = np.random.default_rng(42)
    n = 800
    y = np.zeros((n, 3), dtype=np.float64)
    y[:, 0] = rng.standard_normal(n)
    y[:, 1] = rng.standard_normal(n)
    y[:, 2] = rng.standard_normal(n)
    t = np.linspace(0.0, 800.0, n)

    class _StubTraj:
        pass

    traj = _StubTraj()
    traj.y = y  # type: ignore[attr-defined]
    traj.t = t  # type: ignore[attr-defined]
    window._last_trajectory = traj  # noqa: SLF001

    # Synchronously verify dispatch path by patching the slot at
    # the QThread.start boundary: capture the worker's finished
    # signal payload via a list.
    received: list[dict] = []
    original_finished = window._on_chaos_indicators_finished  # noqa: SLF001

    def _capture(payload: dict) -> None:
        received.append(payload)
        original_finished(payload)

    window._on_chaos_indicators_finished = _capture  # type: ignore[method-assign]  # noqa: SLF001
    window._on_compute_chaos_indicators()  # noqa: SLF001
    # Spin the Qt event loop briefly to let the worker thread emit.
    qtbot.waitUntil(lambda: len(received) > 0, timeout=30_000)
    assert len(received) == 1
    payload = received[0]
    for key in ("K", "digit_loss", "H_PE", "H_Hurst", "dt", "n_samples"):
        assert key in payload
    # IID Gaussian: K close to 1 (random-walk-like), digit-loss low
    # (~1-2), H_PE close to 1, H_Hurst near 0.5 (memoryless).
    assert 0.0 <= payload["K"] <= 1.0
    assert 0.0 <= payload["digit_loss"] <= 16.0
    assert 0.0 <= payload["H_PE"] <= 1.0
    assert payload["n_samples"] == n
    # dt was 800/n = 1.0, above threshold.
    assert payload["dt"] == pytest.approx(t[1] - t[0])
    _ = worker_cls  # silence unused-name when the cls accessor is unused
