"""Tests for the per-system observables Diagnostics-card wiring (CSC-033 / T3).

Pins the GUI side of the PostSimDiagnosticProvider hook:

- The Diagnostics card has a ``system_observables_label`` QLabel
  with stable ``objectName`` ``system_observables_label``.
- The label starts hidden (no Run yet → nothing to show).
- After ``_on_sim_finished(traj)`` with a Kuramoto trajectory, the
  label is visible and contains ``|r|`` and ``ψ`` lines.
- After ``_on_sim_finished(traj)`` with a Lorenz trajectory (a
  non-provider), the label stays hidden.
- Switching system via ``system_box`` resets the label to hidden
  even if a previous Run had populated it.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")

from chaotic_systems.core.base import Trajectory


def _make_window(qtbot):  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)
    return window


def _select_system_by_name(window, target: str) -> bool:  # type: ignore[no-untyped-def]
    """Switch ``window.system_box`` to the entry matching ``target``.

    Returns ``True`` on success; ``False`` if the target isn't registered
    (test callers should skip in that case).
    """
    for i in range(window.system_box.count()):
        if str(window.system_box.itemText(i)) == target:
            window.system_box.setCurrentIndex(i)
            return True
    return False


def test_diagnostics_card_has_system_observables_label(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    assert hasattr(window, "system_observables_label")
    assert (
        window.system_observables_label.objectName()
        == "system_observables_label"
    )


def test_system_observables_label_starts_hidden(qtbot) -> None:  # type: ignore[no-untyped-def]
    """No Run yet — label is hidden until a provider returns observables."""
    window = _make_window(qtbot)
    # ``isHidden`` mirrors the explicit setVisible flag regardless of
    # whether the parent window is shown; we use it to read the
    # programmatic intent rather than physical screen visibility.
    assert window.system_observables_label.isHidden()


def test_kuramoto_run_populates_observables_label(qtbot) -> None:  # type: ignore[no-untyped-def]
    """After _on_sim_finished on a Kuramoto trajectory, |r| and ψ appear."""
    window = _make_window(qtbot)
    if not _select_system_by_name(window, "Kuramoto"):
        pytest.skip("Kuramoto not in this registry")

    # Build a hand-crafted trajectory whose final frame has all phases
    # aligned -> |r| = 1, psi = 0. Avoids running the actual simulation
    # in the GUI smoke test.
    n = window.current_system.state_dim
    y = np.zeros((4, n), dtype=np.float64)
    traj = Trajectory(
        t=np.linspace(0.0, 1.0, 4),
        y=y,
        system="Kuramoto",
        params={"K": 1.5},
        integrator="test",
    )
    window._on_sim_finished(traj)  # noqa: SLF001

    label = window.system_observables_label
    assert not label.isHidden()
    text = label.text()
    assert "|r|" in text
    assert "ψ" in text
    assert "1.0000" in text  # |r| = 1 for fully aligned phases


def test_lorenz_run_keeps_observables_label_hidden(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Lorenz is not a PostSimDiagnosticProvider — label must stay hidden."""
    window = _make_window(qtbot)
    if not _select_system_by_name(window, "Lorenz"):
        pytest.skip("Lorenz not in this registry")

    traj = Trajectory(
        t=np.array([0.0, 0.01]),
        y=np.array([[1.0, 1.0, 1.0], [1.01, 1.0, 1.0]]),
        system="Lorenz",
        params={"sigma": 10.0, "rho": 28.0, "beta": 8.0 / 3.0},
        integrator="test",
    )
    window._on_sim_finished(traj)  # noqa: SLF001

    assert window.system_observables_label.isHidden()


def test_system_switch_resets_observables_label(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Switching from a provider to a non-provider hides the label."""
    window = _make_window(qtbot)
    if not _select_system_by_name(window, "Kuramoto"):
        pytest.skip("Kuramoto not in this registry")

    # Populate the label first.
    n = window.current_system.state_dim
    y = np.zeros((3, n), dtype=np.float64)
    window._on_sim_finished(  # noqa: SLF001
        Trajectory(
            t=np.linspace(0.0, 1.0, 3),
            y=y,
            system="Kuramoto",
            params={"K": 1.5},
            integrator="test",
        )
    )
    assert not window.system_observables_label.isHidden()

    # Switch to Lorenz — the system-change handler must clear the label.
    if not _select_system_by_name(window, "Lorenz"):
        pytest.skip("Lorenz not in this registry")
    assert window.system_observables_label.isHidden()
    assert window.system_observables_label.text() == ""


def test_henon_heiles_run_populates_energy_and_drift(qtbot) -> None:  # type: ignore[no-untyped-def]
    """HenonHeiles provider surfaces E + |ΔE/E₀| chips."""
    window = _make_window(qtbot)
    if not _select_system_by_name(window, "HenonHeiles"):
        pytest.skip("HenonHeiles not in this registry")

    state = np.array([0.0, 0.1, 0.45, 0.0])
    y = np.tile(state, (4, 1))  # stationary trajectory -> drift = 0
    traj = Trajectory(
        t=np.linspace(0.0, 1.0, 4),
        y=y,
        system="HenonHeiles",
        params={},
        integrator="test",
    )
    window._on_sim_finished(traj)  # noqa: SLF001

    label = window.system_observables_label
    assert not label.isHidden()
    text = label.text()
    assert "E" in text
    # The drift label uses the Delta symbol; substring-check is enough.
    assert "ΔE/E₀" in text
    # Stationary trajectory -> drift parses to exactly 0.
    drift_line = [line for line in text.splitlines() if "ΔE/E₀" in line][0]
    drift_val = float(drift_line.split("=")[-1].strip())
    assert drift_val == 0.0
