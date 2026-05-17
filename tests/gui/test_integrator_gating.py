"""Tests for per-system integrator gating in the picker.

Symplectic integrators (leapfrog / velocity_verlet / yoshida4) only
apply to separable Hamiltonian systems. The GUI must disable them in
the integrator combobox when the current system isn't Hamiltonian, so
the user can't accidentally trigger the cryptic
``grad_t_fn / grad_v_fn missing`` error mid-Run. If the user had a
symplectic integrator selected and the system changes to a
non-Hamiltonian one, the picker auto-falls-back to RK45.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")

from chaotic_systems.integrators import SYMPLECTIC_INTEGRATORS


def _make_window(qtbot):  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)
    return window


def _symplectic_enabled_states(window) -> dict[str, bool]:  # type: ignore[no-untyped-def]
    from PySide6.QtCore import Qt

    model = window.integrator_box.model()
    states: dict[str, bool] = {}
    for row in range(window.integrator_box.count()):
        name = window.integrator_box.itemText(row)
        if name not in SYMPLECTIC_INTEGRATORS:
            continue
        item = model.item(row)
        states[name] = bool(item.flags() & Qt.ItemFlag.ItemIsEnabled)
    return states


def _select_system(window, predicate) -> str:  # type: ignore[no-untyped-def]
    """Move the system picker to the first system matching ``predicate``.

    Returns the selected system name. Raises ``RuntimeError`` if no
    matching system is registered.
    """

    for i in range(window.system_box.count()):
        window.system_box.setCurrentIndex(i)
        if predicate(window.current_system):
            return window.system_box.itemText(i)
    raise RuntimeError("no system matched the predicate")


def test_symplectic_disabled_for_lorenz(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Lorenz is dissipative — symplectic items must be disabled."""

    window = _make_window(qtbot)
    _select_system(window, lambda s: s.name == "Lorenz")
    states = _symplectic_enabled_states(window)
    assert states, "expected symplectic items to be registered in the picker"
    assert not any(states.values()), (
        f"symplectic integrators should be disabled on Lorenz, got {states}"
    )


def test_symplectic_enabled_for_hamiltonian_system(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Henon-Heiles is a separable Hamiltonian — symplectic items enabled."""

    window = _make_window(qtbot)
    _select_system(
        window,
        lambda s: getattr(s, "hamiltonian", None) is not None
        and bool(getattr(s.hamiltonian, "separable", False)),
    )
    states = _symplectic_enabled_states(window)
    assert states, "expected symplectic items to be registered in the picker"
    assert all(states.values()), (
        f"symplectic integrators should be enabled on a Hamiltonian system, "
        f"got {states}"
    )


def test_switching_off_hamiltonian_falls_back_to_rk45(qtbot) -> None:  # type: ignore[no-untyped-def]
    """If a symplectic integrator is selected and the system flips to
    a non-Hamiltonian one, the picker must rebind to RK45."""

    window = _make_window(qtbot)
    # Pick a Hamiltonian system and select leapfrog.
    _select_system(
        window,
        lambda s: getattr(s, "hamiltonian", None) is not None
        and bool(getattr(s.hamiltonian, "separable", False)),
    )
    leapfrog_idx = window.integrator_box.findText("leapfrog")
    assert leapfrog_idx >= 0
    window.integrator_box.setCurrentIndex(leapfrog_idx)
    assert window.integrator_box.currentText() == "leapfrog"

    # Switch to Lorenz; the picker must auto-fall-back to RK45.
    _select_system(window, lambda s: s.name == "Lorenz")
    assert window.integrator_box.currentText() == "RK45"
