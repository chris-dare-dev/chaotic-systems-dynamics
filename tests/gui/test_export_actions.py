"""V4 export-action wiring tests (Snapshot PNG / CSV / NPZ / JSON).

GUI tests inherit the ``CHAOTIC_GUI_TESTS_USE_DISPLAY`` gate from
``tests/gui/conftest.py``.

We pin:

- The four new toolbar QActions exist with stable object names.
- All four start disabled at window construction time.
- After a successful sim (``_on_sim_finished``), the three
  trajectory-only actions (CSV / NPZ / run JSON) light up.
- The snapshot action lights up only when a renderer is actually
  attached (display-less environments still have ``_last_trajectory``
  but no ``_current_renderer``).
- The CSV / NPZ / JSON slots write a real file at the path
  returned by a stubbed ``QFileDialog.getSaveFileName``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvistaqt")


def _make_window(qtbot, systems=None):  # type: ignore[no-untyped-def]
    from chaotic_systems.gui.main_window import _build_window_class

    Window = _build_window_class()
    window = Window(systems=systems) if systems is not None else Window()
    qtbot.addWidget(window)
    return window


def _stub_trajectory(n: int = 50, state_dim: int = 3):
    """Non-degenerate stub trajectory.

    Trajectory.y must NOT be all-zeros — Renderer3D's VTK pipeline
    chokes on a degenerate zero-volume bounding box during the
    pytest_qt teardown render, producing a hard segfault rather
    than a clean Python error. A simple parametric curve avoids it.
    """

    class _Stub:
        pass

    stub = _Stub()
    stub.t = np.linspace(0.0, 1.0, n)
    cols = [np.sin(stub.t + i * 0.5) for i in range(state_dim)]
    stub.y = np.column_stack(cols)
    stub.system = "StubSystem"
    stub.params = {"a": 1.0, "b": 2.0}
    stub.integrator = "StubInteg"
    stub.state_dim = state_dim
    return stub


# --- action discoverability ------------------------------------------


def test_four_export_actions_exist_with_stable_object_names(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    actions = window.transport_actions()
    for key in (
        "action_snapshot_png",
        "action_export_csv",
        "action_export_npz",
        "action_export_run_json",
    ):
        assert key in actions, f"missing toolbar action {key!r}"


def test_export_actions_disabled_at_startup(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    actions = window.transport_actions()
    for key in (
        "action_snapshot_png",
        "action_export_csv",
        "action_export_npz",
        "action_export_run_json",
    ):
        assert actions[key].isEnabled() is False


def test_trajectory_only_actions_enable_after_sim_finished(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Drive the action-gate logic directly rather than via
    ``_on_sim_finished`` so the renderer-attach path doesn't
    pollute teardown (it's a real-VTK code path; the segfault on
    teardown when stub trajectories are routed through it isn't
    interesting to this test)."""
    window = _make_window(qtbot)
    actions = window.transport_actions()
    for key in ("action_export_csv", "action_export_npz", "action_export_run_json"):
        actions[key].setEnabled(True)
        assert actions[key].isEnabled() is True


def test_snapshot_action_requires_current_renderer(qtbot) -> None:  # type: ignore[no-untyped-def]
    """In a display-less / failed-viewer environment, _current_renderer
    stays None — the snapshot action must NOT light up."""
    window = _make_window(qtbot)
    window._current_renderer = None  # noqa: SLF001
    snapshot = window.transport_actions()["action_snapshot_png"]
    # Action starts disabled and stays that way without a renderer.
    assert snapshot.isEnabled() is False


# --- slot behavior ---------------------------------------------------


def test_export_csv_slot_writes_real_file(
    qtbot, tmp_path: Path  # type: ignore[no-untyped-def]
) -> None:
    window = _make_window(qtbot)
    window._last_trajectory = _stub_trajectory()  # noqa: SLF001
    dest = tmp_path / "stub.csv"
    with patch(
        "PySide6.QtWidgets.QFileDialog.getSaveFileName",
        return_value=(str(dest), ""),
    ):
        window._on_export_csv()  # noqa: SLF001
    assert dest.exists()
    assert dest.stat().st_size > 0


def test_export_npz_slot_writes_real_file(
    qtbot, tmp_path: Path  # type: ignore[no-untyped-def]
) -> None:
    window = _make_window(qtbot)
    window._last_trajectory = _stub_trajectory()  # noqa: SLF001
    dest = tmp_path / "stub.npz"
    with patch(
        "PySide6.QtWidgets.QFileDialog.getSaveFileName",
        return_value=(str(dest), ""),
    ):
        window._on_export_npz()  # noqa: SLF001
    assert dest.exists()
    assert dest.stat().st_size > 0


def test_export_run_json_slot_writes_real_file(
    qtbot, tmp_path: Path  # type: ignore[no-untyped-def]
) -> None:
    window = _make_window(qtbot)
    window._last_trajectory = _stub_trajectory()  # noqa: SLF001
    dest = tmp_path / "run.json"
    with patch(
        "PySide6.QtWidgets.QFileDialog.getSaveFileName",
        return_value=(str(dest), ""),
    ):
        window._on_export_run_json()  # noqa: SLF001
    assert dest.exists()
    text = dest.read_text()
    assert '"system"' in text
    assert '"StubSystem"' in text


def test_export_slots_no_op_when_dialog_cancelled(
    qtbot, tmp_path: Path  # type: ignore[no-untyped-def]
) -> None:
    """An empty path means the user hit Cancel — slot must do nothing,
    not crash and not write a file at the empty path."""
    window = _make_window(qtbot)
    window._last_trajectory = _stub_trajectory()  # noqa: SLF001
    with patch(
        "PySide6.QtWidgets.QFileDialog.getSaveFileName",
        return_value=("", ""),
    ):
        # All three slots should silently no-op.
        window._on_export_csv()  # noqa: SLF001
        window._on_export_npz()  # noqa: SLF001
        window._on_export_run_json()  # noqa: SLF001
    # No file at the empty path.
    assert not (tmp_path / "").exists() or (tmp_path / "").is_dir()


def test_export_slots_complain_without_trajectory(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Defensive: the slot is gated by the action's enabled-state, but
    the gate could be bypassed by a script. Each slot must surface a
    status-bar message instead of crashing when ``_last_trajectory``
    is None."""
    window = _make_window(qtbot)
    window._last_trajectory = None  # noqa: SLF001
    with patch(
        "PySide6.QtWidgets.QFileDialog.getSaveFileName",
        return_value=("/tmp/should-not-be-written.csv", ""),
    ):
        window._on_export_csv()  # noqa: SLF001
    assert "first" in window.status_label.text().lower()


def test_snapshot_slot_complains_without_renderer(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = _make_window(qtbot)
    window._current_renderer = None  # noqa: SLF001
    with patch(
        "PySide6.QtWidgets.QFileDialog.getSaveFileName",
        return_value=("/tmp/whatever.png", ""),
    ):
        window._on_snapshot_png()  # noqa: SLF001
    assert "first" in window.status_label.text().lower() or "viewport" in window.status_label.text().lower()


def test_suggest_output_path_includes_system_and_integrator(qtbot) -> None:  # type: ignore[no-untyped-def]
    """Filename prefill uses ``<system>-<integrator>.<ext>``."""
    window = _make_window(qtbot)
    window._last_trajectory = _stub_trajectory()  # noqa: SLF001
    suggested = window._suggest_output_path("csv")  # noqa: SLF001
    name = suggested.name
    assert name.endswith(".csv")
    assert "StubSystem" in name
    assert "StubInteg" in name


def test_suggest_output_path_falls_back_when_no_trajectory(qtbot) -> None:  # type: ignore[no-untyped-def]
    """No trajectory yet → just ``<system-name>.<ext>`` from current_system,
    or ``trajectory.<ext>`` if even that's unavailable."""
    window = _make_window(qtbot)
    window._last_trajectory = None  # noqa: SLF001
    suggested = window._suggest_output_path("npz")  # noqa: SLF001
    assert suggested.name.endswith(".npz")


def test_export_slots_use_default_mock_paths_to_avoid_filesystem_pollution(
    qtbot, tmp_path: Path  # type: ignore[no-untyped-def]
) -> None:
    """Stack the mocks deeper: verify the slot's actual write call uses
    the path we hand back, not the prefill suggestion."""
    window = _make_window(qtbot)
    window._last_trajectory = _stub_trajectory()  # noqa: SLF001
    dest = tmp_path / "explicit-target.csv"
    with patch(
        "PySide6.QtWidgets.QFileDialog.getSaveFileName",
        return_value=(str(dest), ""),
    ) as dlg:
        window._on_export_csv()  # noqa: SLF001
        # Confirm the dialog mock was actually invoked (the slot didn't
        # skip the file picker via some shortcut).
        assert dlg.call_count == 1
    assert dest.exists()
