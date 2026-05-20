"""Persistent settings + Preferences dialog (FU-013).

Closes the longest-standing item on ``CONTEXT.md`` "What's next" #1 —
"Persistent settings. Remember the last-used system, parameters, and
integrator across launches (``QSettings``)."

This module ships two halves:

1. **Persistence backend** — :class:`PersistedSettings` (a dataclass
   snapshot of every persisted preference), :func:`load_settings`,
   :func:`save_settings`. Reads / writes via a ``QSettings``
   instance configured in :class:`QSettings.Format.IniFormat` and
   :class:`QSettings.Scope.UserScope` so the file location is
   per-platform sane and *not* the Windows registry (avoids
   confusing users who want to inspect / delete their settings).

2. **Preferences dialog** — :class:`PreferencesDialog`, a
   ``QDialog`` opened from the Settings menu and Ctrl+, with
   three sections (Appearance, Defaults, Restore-on-launch).
   Emits :attr:`PreferencesDialog.applied` with the new
   :class:`PersistedSettings` on OK; the host (main window)
   persists the snapshot and re-applies what's changed live.

Schema versioning
-----------------
Every settings file carries a ``settings/version`` integer key.
Bumping :data:`SETTINGS_VERSION` invalidates all previous keys —
the loader returns the default :class:`PersistedSettings` rather
than reading values written under a stale schema. Add an explicit
migration step here if a key needs to survive a schema bump.

Architecture
------------
The synthesis lists this as **foundational** because FU-018
(undockable diagnostic panels) depends on ``QSettings.setValue`` /
:meth:`QMainWindow.saveState` / :meth:`QMainWindow.restoreState`
landing first. ``window_geometry`` and ``window_state`` are
already persisted here so the dock-widget work in FU-018 only
adds *what* to remember, not *how*.

References
----------
- napari, *Preferences guide*, https://napari.org/dev/guides/preferences.html
  (2024) — the canonical Python implementation; the
  ``save_window_geometry`` / ``save_window_state`` separation
  this module mirrors comes from there.
- napari PR #5483 — command palette + preferences-dialog interplay,
  https://github.com/napari/napari/pull/5483.
- ParaView, Blender — both ship a Preferences dialog with at
  minimum theme / defaults / restore-on-launch sections; cited in
  the frontend-uplift inspiration brief (C1 convergent pattern).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import only for type hints
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QWidget


#: Bump when the serialised schema changes in a non-backwards-compatible
#: way. A mismatched ``settings/version`` triggers a reset to defaults
#: rather than silently mis-applying stale values.
SETTINGS_VERSION: int = 1

#: Organisation + application identifiers Qt uses to derive the
#: settings-file location. Kept stable across versions so a user's
#: file persists across releases.
SETTINGS_ORG: str = "chaotic-systems-dynamics"
SETTINGS_APP: str = "MainWindow"


@dataclass
class PersistedSettings:
    """Snapshot of every user preference persisted across launches.

    The defaults match the pre-FU-013 launch experience so an empty
    or missing settings file yields the same first-launch behavior
    as before (theme=dark, no preselected system, RK45, t_end=40,
    dt=0.01).
    """

    # --- Appearance ------------------------------------------------
    theme: str = "dark"
    bg_color: str | None = None

    # --- Defaults --------------------------------------------------
    last_system: str | None = None
    last_integrator: str | None = None
    last_t_end: float | None = None
    last_dt: float | None = None

    # --- Restore-on-launch toggles ---------------------------------
    remember_last_used: bool = True
    save_window_layout: bool = True

    # --- Window geometry + dock state (consumed by FU-018) ---------
    # Stored as bytes (``QMainWindow.saveGeometry`` / ``saveState``
    # return ``QByteArray``; we serialise the raw bytes).
    window_geometry: bytes | None = None
    window_state: bytes | None = None

    # --- Per-system parameter dicts --------------------------------
    # Layout: ``{system_name: {param_name: value}}``. Only populated
    # when :attr:`remember_last_used` is True. Stale keys (system or
    # param removed from the registry) are tolerated on load.
    system_parameters: dict[str, dict[str, float]] = field(default_factory=dict)


# --------------------------------------------------------------------------
# QSettings I/O
# --------------------------------------------------------------------------


def _new_qsettings() -> QSettings:
    """Build a ``QSettings`` with the canonical Ini layout.

    Forced to :class:`QSettings.Format.IniFormat` for cross-platform
    portability — without it Qt would write to the Windows registry,
    which is opaque to users wanting to delete or inspect their
    config.
    """
    from PySide6.QtCore import QSettings

    return QSettings(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        SETTINGS_ORG,
        SETTINGS_APP,
    )


def _as_bool(value: Any, default: bool) -> bool:
    """Coerce a ``QSettings`` value to ``bool``.

    Qt's INI backend stores booleans as the strings ``"true"`` /
    ``"false"`` rather than Python bools. The platform-native backend
    sometimes round-trips real bools. Be defensive.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes", "on"):
            return True
        if lowered in ("false", "0", "no", "off"):
            return False
    return default


def _as_float_or_none(value: Any) -> float | None:
    """Coerce to float; ``None`` if missing / unparseable."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_str_or_none(value: Any) -> str | None:
    """Coerce to str; ``None`` if missing / empty."""
    if value is None:
        return None
    text = str(value)
    return text if text else None


def load_settings(qs: QSettings | None = None) -> PersistedSettings:
    """Read persisted settings, returning defaults on schema mismatch.

    Parameters
    ----------
    qs
        Optional ``QSettings`` to read from. ``None`` (default) uses
        the canonical platform-scoped Ini file via
        :func:`_new_qsettings`. Tests pass a custom instance backed
        by a tmp-path ``QSettings(filename, IniFormat)``.

    Returns
    -------
    PersistedSettings
        The loaded snapshot. If the ``settings/version`` key is
        missing or mismatched, a default-valued snapshot is
        returned (no migration is attempted — bumping the version
        is a clean reset).
    """
    if qs is None:
        qs = _new_qsettings()

    try:
        stored_version = int(qs.value("settings/version", 0))
    except (TypeError, ValueError):
        stored_version = 0
    if stored_version != SETTINGS_VERSION:
        return PersistedSettings()

    out = PersistedSettings()
    out.theme = _as_str_or_none(qs.value("appearance/theme")) or out.theme
    out.bg_color = _as_str_or_none(qs.value("appearance/bg_color"))
    out.last_system = _as_str_or_none(qs.value("defaults/last_system"))
    out.last_integrator = _as_str_or_none(qs.value("defaults/last_integrator"))
    out.last_t_end = _as_float_or_none(qs.value("defaults/last_t_end"))
    out.last_dt = _as_float_or_none(qs.value("defaults/last_dt"))
    out.remember_last_used = _as_bool(
        qs.value("restore/remember_last_used"), out.remember_last_used
    )
    out.save_window_layout = _as_bool(
        qs.value("restore/save_window_layout"), out.save_window_layout
    )

    # Window geometry / state — bytes round-trip cleanly through Ini.
    geom = qs.value("window/geometry")
    if isinstance(geom, (bytes, bytearray)):
        out.window_geometry = bytes(geom)
    elif geom is not None:
        # QByteArray on platforms where Qt wraps it; convert.
        try:
            out.window_geometry = bytes(geom)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            out.window_geometry = None

    state = qs.value("window/state")
    if isinstance(state, (bytes, bytearray)):
        out.window_state = bytes(state)
    elif state is not None:
        try:
            out.window_state = bytes(state)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            out.window_state = None

    # Per-system parameters live under a ``parameters/<system>/`` group.
    qs.beginGroup("parameters")
    for system_name in qs.childGroups():
        qs.beginGroup(system_name)
        params: dict[str, float] = {}
        for param_name in qs.childKeys():
            val = _as_float_or_none(qs.value(param_name))
            if val is not None:
                params[param_name] = val
        qs.endGroup()
        if params:
            out.system_parameters[system_name] = params
    qs.endGroup()

    return out


def save_settings(snapshot: PersistedSettings, qs: QSettings | None = None) -> None:
    """Write ``snapshot`` to the persistent settings file.

    Idempotent: a follow-up :func:`load_settings` returns an equal
    snapshot (modulo ``None`` vs default-coerced values for missing
    optional fields).
    """
    if qs is None:
        qs = _new_qsettings()

    qs.setValue("settings/version", SETTINGS_VERSION)
    qs.setValue("appearance/theme", snapshot.theme)
    if snapshot.bg_color is not None:
        qs.setValue("appearance/bg_color", snapshot.bg_color)
    else:
        qs.remove("appearance/bg_color")

    for key, value in (
        ("defaults/last_system", snapshot.last_system),
        ("defaults/last_integrator", snapshot.last_integrator),
        ("defaults/last_t_end", snapshot.last_t_end),
        ("defaults/last_dt", snapshot.last_dt),
    ):
        if value is None:
            qs.remove(key)
        else:
            qs.setValue(key, value)

    qs.setValue("restore/remember_last_used", snapshot.remember_last_used)
    qs.setValue("restore/save_window_layout", snapshot.save_window_layout)

    if snapshot.window_geometry is not None:
        qs.setValue("window/geometry", snapshot.window_geometry)
    else:
        qs.remove("window/geometry")
    if snapshot.window_state is not None:
        qs.setValue("window/state", snapshot.window_state)
    else:
        qs.remove("window/state")

    # Per-system parameter persistence. Clear the group first so a
    # system removal (or rename) doesn't leave stale entries.
    qs.remove("parameters")
    for system_name, params in snapshot.system_parameters.items():
        qs.beginGroup(f"parameters/{system_name}")
        for param_name, value in params.items():
            qs.setValue(param_name, float(value))
        qs.endGroup()

    qs.sync()


# --------------------------------------------------------------------------
# Preferences dialog
# --------------------------------------------------------------------------


def build_preferences_dialog(
    parent: QWidget,
    current: PersistedSettings,
    systems: list[str],
    integrators: list[str],
) -> PreferencesDialog:
    """Factory that wraps :class:`PreferencesDialog` instantiation.

    Provided for symmetry with the existing ``build_*_dialog``
    pattern in the GUI (``build_phase_dialog`` etc.). The dialog is
    not auto-shown — callers invoke :meth:`PreferencesDialog.exec`
    (modal) or :meth:`show` (non-modal).
    """
    return PreferencesDialog(
        parent=parent, current=current, systems=systems, integrators=integrators
    )


# Imports for the dialog class live at module scope so a future
# AP-03 challenger (no PySide6 imports inside paint events) is
# automatically satisfied.
from PySide6.QtCore import Qt, Signal  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QVBoxLayout,
)


class PreferencesDialog(QDialog):
    """Three-section Preferences dialog.

    Sections:

    - **Appearance** — theme picker (dark / light) + background-color
      readout. The dark-mode-only path is the canonical Tokyo-Night
      experience; light is a stub today (see ``apply_theme`` falling
      back to ``dark.qss`` when ``light.qss`` is absent).
    - **Defaults** — default system, default integrator. Pre-selects
      the values stored in the supplied :class:`PersistedSettings`.
    - **Restore-on-launch** — two toggles: remember last-used
      parameters (drives the per-system parameter persistence) and
      save window layout (drives ``QMainWindow.saveGeometry`` /
      ``saveState``).

    Emits :attr:`applied` carrying the new :class:`PersistedSettings`
    when the user clicks OK; emits no signal on Cancel. Callers
    typically connect :attr:`applied` to a slot that calls
    :func:`save_settings` and re-applies any changed knobs.
    """

    #: Emitted with the new :class:`PersistedSettings` when the user
    #: clicks OK. ``QDialog.accepted`` is also emitted (Qt-native);
    #: this signal carries the new snapshot.
    applied = Signal(object)

    def __init__(
        self,
        *,
        parent: QWidget | None = None,
        current: PersistedSettings,
        systems: list[str],
        integrators: list[str],
    ) -> None:
        super().__init__(parent)
        self.setObjectName("preferences_dialog")
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(380)
        self._current = current

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        outer.addWidget(self._build_appearance_group())
        outer.addWidget(self._build_defaults_group(systems, integrators))
        outer.addWidget(self._build_restore_group())
        outer.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            Qt.Orientation.Horizontal,
            self,
        )
        buttons.setObjectName("preferences_buttons")
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    # --- section builders ---------------------------------------------

    def _build_appearance_group(self) -> QGroupBox:
        group = QGroupBox("Appearance", self)
        group.setObjectName("preferences_appearance")
        form = QFormLayout(group)
        form.setContentsMargins(12, 8, 12, 12)
        form.setHorizontalSpacing(12)

        self.theme_box = QComboBox(group)
        self.theme_box.setObjectName("preferences_theme")
        self.theme_box.addItems(["dark", "light"])
        idx = self.theme_box.findText(self._current.theme)
        if idx >= 0:
            self.theme_box.setCurrentIndex(idx)
        form.addRow(QLabel("Theme", group), self.theme_box)

        bg_label_text = self._current.bg_color or "(default)"
        self.bg_readout = QLabel(bg_label_text, group)
        self.bg_readout.setObjectName("preferences_bg_color_readout")
        self.bg_readout.setProperty("role", "caption")
        form.addRow(QLabel("Background color", group), self.bg_readout)

        return group

    def _build_defaults_group(
        self, systems: list[str], integrators: list[str]
    ) -> QGroupBox:
        group = QGroupBox("Defaults", self)
        group.setObjectName("preferences_defaults")
        form = QFormLayout(group)
        form.setContentsMargins(12, 8, 12, 12)
        form.setHorizontalSpacing(12)

        self.system_box = QComboBox(group)
        self.system_box.setObjectName("preferences_default_system")
        self.system_box.addItem("(no preselection)", userData=None)
        for name in systems:
            self.system_box.addItem(name, userData=name)
        if self._current.last_system is not None:
            idx = self.system_box.findData(self._current.last_system)
            if idx >= 0:
                self.system_box.setCurrentIndex(idx)
        form.addRow(QLabel("System on launch", group), self.system_box)

        self.integrator_box = QComboBox(group)
        self.integrator_box.setObjectName("preferences_default_integrator")
        self.integrator_box.addItem("(no preselection)", userData=None)
        for name in integrators:
            self.integrator_box.addItem(name, userData=name)
        if self._current.last_integrator is not None:
            idx = self.integrator_box.findData(self._current.last_integrator)
            if idx >= 0:
                self.integrator_box.setCurrentIndex(idx)
        form.addRow(QLabel("Integrator on launch", group), self.integrator_box)

        return group

    def _build_restore_group(self) -> QGroupBox:
        group = QGroupBox("Restore on launch", self)
        group.setObjectName("preferences_restore")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(6)

        self.remember_last_used_box = QCheckBox(
            "Remember last-used parameters across sessions", group
        )
        self.remember_last_used_box.setObjectName(
            "preferences_remember_last_used"
        )
        self.remember_last_used_box.setChecked(self._current.remember_last_used)
        layout.addWidget(self.remember_last_used_box)

        self.save_window_layout_box = QCheckBox(
            "Save window layout on close", group
        )
        self.save_window_layout_box.setObjectName(
            "preferences_save_window_layout"
        )
        self.save_window_layout_box.setChecked(self._current.save_window_layout)
        layout.addWidget(self.save_window_layout_box)

        return group

    # --- accept handler -----------------------------------------------

    def _gather(self) -> PersistedSettings:
        """Read the current widget values back into a :class:`PersistedSettings`.

        Preserves fields the dialog doesn't expose (``window_geometry``,
        ``window_state``, ``system_parameters``, ``bg_color``) from the
        current snapshot — the dialog isn't authoritative for them.
        """
        return PersistedSettings(
            theme=self.theme_box.currentText(),
            bg_color=self._current.bg_color,
            last_system=self.system_box.currentData(),
            last_integrator=self.integrator_box.currentData(),
            last_t_end=self._current.last_t_end,
            last_dt=self._current.last_dt,
            remember_last_used=self.remember_last_used_box.isChecked(),
            save_window_layout=self.save_window_layout_box.isChecked(),
            window_geometry=self._current.window_geometry,
            window_state=self._current.window_state,
            system_parameters=dict(self._current.system_parameters),
        )

    def _on_ok(self) -> None:
        snapshot = self._gather()
        self.applied.emit(snapshot)
        self.accept()


__all__ = [
    "PersistedSettings",
    "PreferencesDialog",
    "SETTINGS_APP",
    "SETTINGS_ORG",
    "SETTINGS_VERSION",
    "build_preferences_dialog",
    "load_settings",
    "save_settings",
]
