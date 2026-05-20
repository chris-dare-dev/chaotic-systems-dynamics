"""Tests for FU-013 — QSettings persistence + Preferences dialog.

Two halves mirror the implementation:

1. **Persistence backend** — :class:`PersistedSettings` round-trips
   through a tmp-path-backed :class:`QSettings` instance, the
   schema-version key triggers a reset on mismatch, and per-system
   parameter dicts survive intact.

2. **Dialog** — :class:`PreferencesDialog` constructs without
   raising, populates its three sections from the supplied
   snapshot, and emits :attr:`applied` carrying the updated
   snapshot on OK.

3. **Main window wiring** — ``Ctrl+,`` opens the dialog;
   ``closeEvent`` persists settings after the existing worker
   cancellation; loading at startup restores the system / integrator
   picker.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")


# ---------------------------------------------------------------------------
# Persistence backend
# ---------------------------------------------------------------------------


def _make_settings(tmp_path: Path):
    """Return a tmp-path-backed ``QSettings`` for hermetic tests."""
    from PySide6.QtCore import QSettings

    return QSettings(str(tmp_path / "prefs.ini"), QSettings.Format.IniFormat)


def test_default_persisted_settings_match_pre_FU013_launch_state() -> None:
    """A fresh ``PersistedSettings`` matches the pre-FU-013 launch experience.

    A new install with no settings file must behave exactly like the
    project did before FU-013 — theme=dark, no preselected system,
    remember-last-used + save-window-layout opt-in by default.
    """

    from chaotic_systems.gui.preferences_dialog import PersistedSettings

    snapshot = PersistedSettings()
    assert snapshot.theme == "dark"
    assert snapshot.last_system is None
    assert snapshot.last_integrator is None
    assert snapshot.last_t_end is None
    assert snapshot.last_dt is None
    assert snapshot.remember_last_used is True
    assert snapshot.save_window_layout is True
    assert snapshot.window_geometry is None
    assert snapshot.window_state is None
    assert snapshot.system_parameters == {}


def test_save_then_load_roundtrips_every_field(tmp_path: Path) -> None:
    """The full snapshot survives a save -> load cycle.

    Includes the per-system parameter dict and the optional bytes
    fields (``window_geometry`` / ``window_state``).
    """

    from chaotic_systems.gui.preferences_dialog import (
        PersistedSettings,
        load_settings,
        save_settings,
    )

    snapshot = PersistedSettings(
        theme="light",
        bg_color="#1a1b26",
        last_system="Lorenz",
        last_integrator="DOP853",
        last_t_end=80.0,
        last_dt=0.005,
        remember_last_used=True,
        save_window_layout=False,
        window_geometry=b"\x01\x02\x03",
        window_state=b"\x04\x05\x06",
        system_parameters={
            "Lorenz": {"sigma": 10.5, "rho": 28.5, "beta": 2.7},
            "Rossler": {"a": 0.1, "b": 0.1, "c": 14.0},
        },
    )
    qs = _make_settings(tmp_path)
    save_settings(snapshot, qs)

    qs2 = _make_settings(tmp_path)
    out = load_settings(qs2)

    assert out.theme == "light"
    assert out.bg_color == "#1a1b26"
    assert out.last_system == "Lorenz"
    assert out.last_integrator == "DOP853"
    assert out.last_t_end == pytest.approx(80.0)
    assert out.last_dt == pytest.approx(0.005)
    assert out.remember_last_used is True
    assert out.save_window_layout is False
    assert out.window_geometry == b"\x01\x02\x03"
    assert out.window_state == b"\x04\x05\x06"
    assert out.system_parameters["Lorenz"]["sigma"] == pytest.approx(10.5)
    assert out.system_parameters["Lorenz"]["rho"] == pytest.approx(28.5)
    assert out.system_parameters["Rossler"]["c"] == pytest.approx(14.0)


def test_schema_version_mismatch_resets_to_defaults(tmp_path: Path) -> None:
    """A wrong ``settings/version`` triggers a clean reset.

    Bumping :data:`SETTINGS_VERSION` is the canonical way to
    invalidate a settings file when a key's meaning changes — the
    loader must ignore stale values rather than mis-applying them.
    """

    from chaotic_systems.gui.preferences_dialog import (
        SETTINGS_VERSION,
        load_settings,
    )

    qs = _make_settings(tmp_path)
    qs.setValue("settings/version", SETTINGS_VERSION + 99)
    qs.setValue("appearance/theme", "light")
    qs.setValue("defaults/last_system", "Lorenz")
    qs.sync()

    out = load_settings(qs)
    # Defaults — none of the stale values bled through.
    assert out.theme == "dark"
    assert out.last_system is None


def test_missing_settings_file_returns_defaults(tmp_path: Path) -> None:
    """An empty / never-written file is indistinguishable from defaults."""

    from chaotic_systems.gui.preferences_dialog import (
        PersistedSettings,
        load_settings,
    )

    qs = _make_settings(tmp_path)
    out = load_settings(qs)
    assert out == PersistedSettings()


def test_save_then_load_clears_removed_system_parameters(tmp_path: Path) -> None:
    """Saving a snapshot with fewer systems removes the stale keys.

    If the user removes a system from the registry, the next save
    must drop its persisted parameters — leaving stale keys would
    cause the loader to materialise a parameter dict for a system
    that no longer exists.
    """

    from chaotic_systems.gui.preferences_dialog import (
        PersistedSettings,
        load_settings,
        save_settings,
    )

    qs = _make_settings(tmp_path)
    first = PersistedSettings(
        last_system="Lorenz",
        system_parameters={
            "Lorenz": {"sigma": 10.0},
            "OldSystem": {"k": 1.0},
        },
    )
    save_settings(first, qs)

    second = PersistedSettings(
        last_system="Lorenz",
        system_parameters={"Lorenz": {"sigma": 11.0}},
    )
    save_settings(second, qs)

    qs2 = _make_settings(tmp_path)
    out = load_settings(qs2)
    assert "OldSystem" not in out.system_parameters
    assert out.system_parameters["Lorenz"]["sigma"] == pytest.approx(11.0)


def test_save_settings_writes_canonical_version(tmp_path: Path) -> None:
    """The version key is always written, even on a default snapshot."""

    from chaotic_systems.gui.preferences_dialog import (
        SETTINGS_VERSION,
        PersistedSettings,
        save_settings,
    )

    qs = _make_settings(tmp_path)
    save_settings(PersistedSettings(), qs)

    qs2 = _make_settings(tmp_path)
    assert int(qs2.value("settings/version")) == SETTINGS_VERSION


# ---------------------------------------------------------------------------
# Preferences dialog
# ---------------------------------------------------------------------------


def test_preferences_dialog_constructs_with_current_snapshot(qapp) -> None:  # type: ignore[no-untyped-def]
    """Dialog instantiates without raising and shows three sections."""

    from chaotic_systems.gui.preferences_dialog import (
        PersistedSettings,
        build_preferences_dialog,
    )

    current = PersistedSettings(
        theme="dark",
        last_system="Lorenz",
        last_integrator="RK45",
        remember_last_used=True,
        save_window_layout=False,
    )
    dialog = build_preferences_dialog(
        parent=None,
        current=current,
        systems=["Lorenz", "Rossler", "DoublePendulum"],
        integrators=["RK45", "DOP853", "LSODA"],
    )
    try:
        # Three section group boxes by objectName.
        assert (
            dialog.findChild(object, "preferences_appearance") is not None
        )
        assert (
            dialog.findChild(object, "preferences_defaults") is not None
        )
        assert (
            dialog.findChild(object, "preferences_restore") is not None
        )

        # Selected values match the snapshot.
        assert dialog.theme_box.currentText() == "dark"
        assert dialog.system_box.currentData() == "Lorenz"
        assert dialog.integrator_box.currentData() == "RK45"
        assert dialog.remember_last_used_box.isChecked() is True
        assert dialog.save_window_layout_box.isChecked() is False
    finally:
        dialog.deleteLater()


def test_preferences_dialog_emits_applied_with_updated_snapshot(qapp) -> None:  # type: ignore[no-untyped-def]
    """OK button emits ``applied`` carrying the user's edits."""

    from chaotic_systems.gui.preferences_dialog import (
        PersistedSettings,
        build_preferences_dialog,
    )

    current = PersistedSettings(theme="dark", last_system="Lorenz")
    dialog = build_preferences_dialog(
        parent=None,
        current=current,
        systems=["Lorenz", "Rossler"],
        integrators=["RK45", "DOP853"],
    )
    try:
        captured: list = []
        dialog.applied.connect(lambda s: captured.append(s))

        # Simulate the user changing the integrator + theme.
        dialog.theme_box.setCurrentText("light")
        idx = dialog.integrator_box.findData("DOP853")
        dialog.integrator_box.setCurrentIndex(idx)
        dialog.remember_last_used_box.setChecked(False)
        dialog._on_ok()  # noqa: SLF001 — testing the OK handler

        assert len(captured) == 1
        out = captured[0]
        assert out.theme == "light"
        assert out.last_integrator == "DOP853"
        assert out.remember_last_used is False
        # Unchanged fields preserve the prior values.
        assert out.last_system == "Lorenz"
    finally:
        dialog.deleteLater()


def test_preferences_dialog_no_preselection_serialises_as_none(qapp) -> None:  # type: ignore[no-untyped-def]
    """The ``(no preselection)`` entry resolves to ``None``."""

    from chaotic_systems.gui.preferences_dialog import (
        PersistedSettings,
        build_preferences_dialog,
    )

    current = PersistedSettings()
    dialog = build_preferences_dialog(
        parent=None,
        current=current,
        systems=["Lorenz"],
        integrators=["RK45"],
    )
    try:
        # The default selection is the "(no preselection)" entry whose
        # userData is None.
        assert dialog.system_box.currentData() is None
        assert dialog.integrator_box.currentData() is None
        # Snapshot gathered from the unmodified dialog matches the
        # default (no preselection).
        snap = dialog._gather()  # noqa: SLF001
        assert snap.last_system is None
        assert snap.last_integrator is None
    finally:
        dialog.deleteLater()


# ---------------------------------------------------------------------------
# Main-window wiring
# ---------------------------------------------------------------------------


def test_main_window_registers_preferences_action() -> None:
    """The Settings menu carries an ``action_preferences`` entry."""

    from chaotic_systems.gui.main_window import build_application

    app, window = build_application([])
    try:
        action = window.action_preferences
        assert action is not None
        assert action.objectName() == "action_preferences"
        # Ctrl+, shortcut is wired (Qt formats the binding as "Ctrl+,").
        assert "Ctrl+," in action.shortcut().toString()
    finally:
        window.close()
        assert app is not None  # keep reference alive


def test_main_window_persisted_snapshot_reflects_live_state() -> None:
    """``_persisted_settings_snapshot`` reads the live picker values."""

    from chaotic_systems.gui.main_window import build_application

    app, window = build_application([])
    try:
        snap = window._persisted_settings_snapshot()  # noqa: SLF001
        # The current system + integrator are non-empty (the window
        # picks defaults for each at construction).
        assert snap.last_system is not None
        assert snap.last_integrator is not None
        assert snap.last_t_end is not None
        assert snap.last_dt is not None
        # If the live system has any parameter widgets, they must
        # appear under ``system_parameters[last_system]``. Systems
        # with no parameters (HenonHeiles, for example, exposes only
        # initial conditions) don't get a dict entry — that's by
        # design so we don't persist empty dicts.
        live_param_count = len(window._param_widgets)  # noqa: SLF001
        if live_param_count > 0:
            assert snap.last_system in snap.system_parameters
            assert (
                len(snap.system_parameters[snap.last_system])
                == live_param_count
            )
    finally:
        window.close()
        assert app is not None
