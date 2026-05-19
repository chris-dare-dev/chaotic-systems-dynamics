"""Tests for the Poincaré-section GUI panel (CSC-029 / W1).

GUI tests inherit the ``CHAOTIC_GUI_TESTS_USE_DISPLAY`` gate from
``tests/gui/conftest.py``.

The pure compute side ``poincare_section`` was tested since day one in
``tests/systems/test_henon_heiles.py``; these tests pin the GUI
*wire-up*: that the panel constructs against a system, has the
expected controls with stable object names, dispatches the worker
correctly, and updates the canvas / status when a result lands.

Numerical observable
--------------------
``test_henon_heiles_section_observable`` reproduces the panel's
default-UX numerical claim directly: with Hénon-Heiles registered,
the section through ``x = 0`` with upward crossings (direction = +1)
at the panel's default ``t_end = 200`` and ``t_transient = 10`` on
the system's default IC yields >= 20 crossings, all on the
hyperplane to numerical precision, and all with
``|p_y| < 1`` (the Hénon-Heiles 1964 mixed-phase-space scale at
E ≈ 0.125). Measurement: the canonical default IC
``[0, 0.1, 0.45, 0]`` produces ~31 crossings in t=200 with this
event-detection setup (the synthesis brief's optimistic estimate of
>= 50 only holds at t_end >= 500 with the same IC; we test the
panel default behaviour rather than the longer-window claim). This
calls the panel's worker directly (not via QThread) so the test
stays inside the non-GUI test budget while still exercising the
panel's wiring contract.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")

from chaotic_systems.systems.henon_heiles import HenonHeiles


def _make_panel(qtbot, system=None):  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.poincare_panel import PoincarePanel

    if system is None:
        system = HenonHeiles()
    panel = PoincarePanel(system, axes_labels=("x", "y", "p_x", "p_y"))
    qtbot.addWidget(panel)
    return panel


# ---------------------------------------------------------------------------
# Construction + widget existence.
# ---------------------------------------------------------------------------


def test_panel_controls_exist(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    assert panel.section_axis_box.objectName() == "poincare_section_axis"
    assert panel.offset_spin.objectName() == "poincare_offset"
    assert panel.direction_box.objectName() == "poincare_direction"
    assert panel.t_end_spin.objectName() == "poincare_t_end"
    assert panel.t_transient_spin.objectName() == "poincare_t_transient"
    assert panel.display_x_box.objectName() == "poincare_display_x"
    assert panel.display_y_box.objectName() == "poincare_display_y"
    assert panel.equal_aspect_box.objectName() == "poincare_equal_aspect"
    assert panel.compute_button.objectName() == "poincare_compute"
    assert panel.cancel_button.objectName() == "poincare_cancel"
    assert panel.status_label.objectName() == "poincare_status"
    assert panel.canvas.objectName() == "poincare_canvas"
    # Cancel starts disabled; Compute starts enabled.
    assert panel.cancel_button.isEnabled() is False
    assert panel.compute_button.isEnabled() is True


def test_panel_section_axis_combo_has_one_entry_per_state_component(
    qtbot,  # type: ignore[no-untyped-def]
) -> None:
    panel = _make_panel(qtbot)  # HenonHeiles -> state_dim = 4
    assert panel.section_axis_box.count() == 4
    # Default section axis is component 0 (x).
    assert int(panel.section_axis_box.currentData()) == 0
    # Display defaults exclude the section axis: (1, 3) for HenonHeiles
    # -> (y, p_y), the canonical Hénon-Heiles 1964 Fig. 4 projection.
    assert int(panel.display_x_box.currentData()) == 1
    assert int(panel.display_y_box.currentData()) == 3


def test_panel_direction_combo_has_three_entries(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    assert panel.direction_box.count() == 3
    directions = {
        int(panel.direction_box.itemData(i))
        for i in range(panel.direction_box.count())
    }
    assert directions == {-1, 0, 1}


def test_panel_defaults_match_canonical_henon_heiles_section(
    qtbot,  # type: ignore[no-untyped-def]
) -> None:
    panel = _make_panel(qtbot)
    assert panel.offset_spin.value() == pytest.approx(0.0)
    assert panel.t_end_spin.value() == pytest.approx(200.0)
    assert panel.t_transient_spin.value() == pytest.approx(10.0)


def test_panel_last_crossings_starts_none(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    assert panel.last_crossings() is None


def test_panel_rejects_state_dim_less_than_two(qtbot) -> None:  # type: ignore[no-untyped-def]
    """A 1D system has no meaningful 2D projection — reject explicitly."""
    from chaotic_systems.gui.poincare_panel import PoincarePanel

    class _Toy1D:
        name = "Toy1D"
        state_dim = 1

    with pytest.raises(ValueError, match="state_dim >= 2"):
        PoincarePanel(_Toy1D())


def test_section_axis_change_repositions_display_defaults(
    qtbot,  # type: ignore[no-untyped-def]
) -> None:
    """Selecting section axis = y swaps the display defaults accordingly."""
    panel = _make_panel(qtbot)
    # Switch to section axis = component 1 (y).
    idx_for_y = 1
    panel.section_axis_box.setCurrentIndex(idx_for_y)
    # New display defaults exclude axis 1; picks first and last of others.
    # _default_display_axes(4, 1) -> (0, 3) = (x, p_y).
    assert int(panel.display_x_box.currentData()) == 0
    assert int(panel.display_y_box.currentData()) == 3


# ---------------------------------------------------------------------------
# Worker compute path — runs the same numerical observable the existing
# tests/systems/test_henon_heiles.py pins, but via the panel's worker
# infrastructure so the wire-up itself is verified.
# ---------------------------------------------------------------------------


def test_henon_heiles_section_observable(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Direct worker call: HenonHeiles default IC, x=0, dir +1, t_end=200.

    Reproduces the panel's default-UX numerical observable: with the
    canonical default IC ``[0, 0.1, 0.45, 0]`` (E ≈ 0.125), the
    section through ``x = 0`` with upward crossings collects >= 20
    points in t=200 (measured: ~31), all on the hyperplane and all
    with ``|p_y| < 1``. Calls the worker class synchronously
    (no QThread) so the test runs in the non-GUI budget.
    """
    from chaotic_systems.gui.poincare_panel import _build_worker_class

    worker_cls = _build_worker_class()
    system = HenonHeiles()
    normal = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
    worker = worker_cls(
        system=system,
        normal=normal,
        offset=0.0,
        direction=+1,
        t_end=200.0,
        t_transient=10.0,
        max_step=0.5,
    )

    results: list[object] = []
    worker.finished.connect(lambda traj: results.append(traj))
    errors: list[tuple[str, str]] = []
    worker.error.connect(lambda kind, msg: errors.append((kind, msg)))

    worker.run()

    assert not errors, f"unexpected error: {errors!r}"
    assert len(results) == 1
    crossings = results[0]
    assert crossings is not None
    n_crossings = int(crossings.y.shape[0])
    # The panel-default numerical observable: >= 20 crossings in 200 t.u.
    # (measured value on default IC is ~31; the longer-window >=50 claim
    # in the synthesis only holds at t_end >= 500).
    assert n_crossings >= 20, (
        f"expected >= 20 section crossings on canonical HenonHeiles IC, "
        f"got {n_crossings}"
    )
    # All crossings must lie on x = 0 to numerical precision.
    np.testing.assert_allclose(crossings.y[:, 0], 0.0, atol=1e-8)
    # p_y values bounded by the Hénon-Heiles 1964 mixed-phase-space scale.
    assert float(np.max(np.abs(crossings.y[:, 3]))) < 1.0


def test_henon_heiles_section_long_window_matches_synthesis_50_count(
    qtbot,  # type: ignore[no-untyped-def]
) -> None:
    """The synthesis's >= 50 claim holds at t_end=500 on the default IC.

    Slower than the default-UX test (~3-5 s on scipy), but worth
    pinning so the synthesis acceptance criterion isn't lost.
    """
    from chaotic_systems.gui.poincare_panel import _build_worker_class

    worker_cls = _build_worker_class()
    system = HenonHeiles()
    normal = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
    worker = worker_cls(
        system=system,
        normal=normal,
        offset=0.0,
        direction=+1,
        t_end=500.0,
        t_transient=10.0,
        max_step=0.5,
    )
    results: list[object] = []
    worker.finished.connect(lambda traj: results.append(traj))
    worker.run()
    assert len(results) == 1
    crossings = results[0]
    assert crossings is not None
    n_crossings = int(crossings.y.shape[0])
    assert n_crossings >= 50, (
        f"synthesis acceptance criterion at t_end=500: expected >= 50, "
        f"got {n_crossings}"
    )
    assert float(np.max(np.abs(crossings.y[:, 3]))) < 1.0


def test_worker_emits_error_on_bad_normal_shape(qtbot) -> None:  # type: ignore[no-untyped-def]
    """A normal vector of the wrong shape surfaces as ValueError via the signal."""
    from chaotic_systems.gui.poincare_panel import _build_worker_class

    worker_cls = _build_worker_class()
    system = HenonHeiles()
    # state_dim=4 but normal has length 3 -> ValueError from core/poincare.
    bad_normal = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    worker = worker_cls(
        system=system,
        normal=bad_normal,
        offset=0.0,
        direction=+1,
        t_end=10.0,
        t_transient=0.0,
        max_step=0.5,
    )

    errors: list[tuple[str, str]] = []
    worker.error.connect(lambda kind, msg: errors.append((kind, msg)))
    worker.run()

    assert len(errors) == 1
    kind, message = errors[0]
    assert kind == "ValueError"
    assert "shape" in message or "expected" in message


# ---------------------------------------------------------------------------
# Finished-handler updates the panel state without a thread roundtrip.
# ---------------------------------------------------------------------------


def test_finished_handler_stores_crossings_and_updates_status(
    qtbot,  # type: ignore[no-untyped-def]
) -> None:
    from chaotic_systems.core.base import Trajectory

    panel = _make_panel(qtbot)
    panel.compute_button.setEnabled(False)
    panel.cancel_button.setEnabled(True)

    # Stub a 7-point section result on HenonHeiles state shape.
    y = np.zeros((7, 4), dtype=np.float64)
    y[:, 1] = np.linspace(-0.3, 0.3, 7)  # spread the y component
    fake = Trajectory(
        t=np.arange(7, dtype=np.float64),
        y=y,
        system="HenonHeiles",
        params={},
        integrator="poincare",
    )
    panel._on_finished(fake)  # noqa: SLF001

    assert panel.last_crossings() is fake
    assert "7 section crossings" in panel.status_label.text()
    assert panel.compute_button.isEnabled()
    assert panel.cancel_button.isEnabled() is False


def test_cancelled_finished_handler_surfaces_message(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    panel.compute_button.setEnabled(False)
    panel.cancel_button.setEnabled(True)
    panel._on_finished(None)  # noqa: SLF001
    assert "Cancelled" in panel.status_label.text()
    assert panel.compute_button.isEnabled()
    assert panel.cancel_button.isEnabled() is False
    assert panel.last_crossings() is None


def test_error_handler_re_enables_compute(qtbot) -> None:  # type: ignore[no-untyped-def]
    panel = _make_panel(qtbot)
    panel.compute_button.setEnabled(False)
    panel.cancel_button.setEnabled(True)
    panel._on_error("ValueError", "bad normal shape")  # noqa: SLF001
    assert "ValueError" in panel.status_label.text()
    assert "bad normal" in panel.status_label.text()
    assert panel.compute_button.isEnabled()
    assert panel.cancel_button.isEnabled() is False


def test_t_transient_must_be_less_than_t_end(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Setting t_transient >= t_end triggers a guard, not a worker dispatch."""
    panel = _make_panel(qtbot)
    panel.t_end_spin.setValue(50.0)
    panel.t_transient_spin.setValue(80.0)
    panel._on_compute()  # noqa: SLF001
    assert "t_transient" in panel.status_label.text()
    # Compute button remains enabled because no worker started.
    assert panel.compute_button.isEnabled()


# ---------------------------------------------------------------------------
# Toolbar action wiring on the main window.
# ---------------------------------------------------------------------------


def test_main_window_exposes_action_poincare(qtbot) -> None:  # type: ignore[no-untyped-def]
    """The main toolbar lists `action_poincare` enabled by default."""
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window()
    qtbot.addWidget(window)

    actions = window.transport_actions()
    assert "action_poincare" in actions
    poincare_action = actions["action_poincare"]
    # Like Basins (D4), the action does not require a prior Run — the
    # panel runs its own compute against the current system.
    assert poincare_action.isEnabled() is True
    assert "Poincaré" in poincare_action.text()
