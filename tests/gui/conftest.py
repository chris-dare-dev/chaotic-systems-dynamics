"""GUI test fixtures.

We use ``pytest-qt`` for the ``qtbot`` fixture.

Headless caveat
---------------
The 3D viewport is a ``pyvistaqt.QtInteractor``, which wraps VTK and needs a
real OpenGL context. Under the Qt ``offscreen`` platform plugin (CI default)
VTK still tries to create that context and segfaults on some macOS / VTK
combinations. Rather than ship a flaky test, we honor an opt-in:

- Set ``CHAOTIC_GUI_TESTS_USE_DISPLAY=1`` to run the GUI tests against a real
  display. Required on macOS.
- Otherwise the GUI tests are skipped (the rest of the suite still runs).

This keeps the visualization tests as the load-bearing smoke check for the
PyVista renderer; the GUI tests cover widget-wiring on top of that.

Scoping
-------
The ``pytest_collection_modifyitems`` hook below filters strictly to items
*under* ``tests/gui/``. Earlier versions iterated over every collected
item, which silently skipped the entire 38 + 13 = 51 backend test suite
when running ``pytest`` from the repo root.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_THIS_DIR = Path(__file__).resolve().parent


def _can_run_gui_tests() -> bool:
    return os.environ.get("CHAOTIC_GUI_TESTS_USE_DISPLAY") == "1"


def _item_is_under_gui(item: pytest.Item) -> bool:
    """True iff ``item`` lives under this directory (tests/gui/)."""

    item_path = getattr(item, "path", None)
    if item_path is not None:
        try:
            Path(item_path).resolve().relative_to(_THIS_DIR)
            return True
        except ValueError:
            return False
    # Fallback for pytest < 7 — item.fspath.
    fspath = getattr(item, "fspath", None)
    if fspath is None:
        return False
    return str(_THIS_DIR) in str(fspath)


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if _can_run_gui_tests():
        return
    skip_marker = pytest.mark.skip(
        reason=(
            "GUI tests need a real display; set "
            "CHAOTIC_GUI_TESTS_USE_DISPLAY=1 to enable."
        )
    )
    for item in items:
        if _item_is_under_gui(item):
            item.add_marker(skip_marker)


@pytest.fixture(scope="session")
def qapp_args() -> list[str]:  # pragma: no cover - trivial fixture
    """Args passed to the QApplication built by ``pytest-qt``."""

    return ["chaotic-systems-tests"]


@pytest.fixture(scope="session", autouse=True)
def _isolate_qsettings_path(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Point ``QSettings`` at a tmp directory for the test session.

    FU-013 introduces a ``QSettings``-backed persistent-settings layer
    (theme, last system, last integrator, per-system parameter values,
    window geometry) that the main window loads at startup. Without
    isolation, the test session would read / mutate the developer's
    real settings file under ``~/.config/`` (Linux) / ``%APPDATA%``
    (Windows) — flaky in CI and corrupting on a dev machine.

    We redirect via :meth:`QSettings.setPath` for both ``IniFormat`` /
    ``UserScope`` and ``IniFormat`` / ``SystemScope`` so every code
    path that constructs a default ``QSettings`` lands in the tmp dir.
    Session-scoped so the redirect is set once before any GUI test
    imports ``preferences_dialog``; the per-test clear below resets
    the contents between tests.
    """

    if not _can_run_gui_tests():
        return
    try:
        from PySide6.QtCore import QSettings
    except ImportError:  # pragma: no cover - PySide6 missing
        return

    tmp_dir = tmp_path_factory.mktemp("qsettings_isolation")
    QSettings.setPath(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        str(tmp_dir),
    )
    QSettings.setPath(
        QSettings.Format.IniFormat,
        QSettings.Scope.SystemScope,
        str(tmp_dir),
    )


@pytest.fixture(autouse=True)
def _clear_qsettings_between_tests() -> None:
    """Wipe the redirected ``QSettings`` file before each GUI test.

    ``MainWindow.closeEvent`` persists the live snapshot via
    :func:`save_settings`, so any earlier test that closes a window
    leaves state behind — without this clear, ``last_system`` from
    test A leaks into the startup-load path of test B and changes
    the picker silently. Function-scoped + autouse so every GUI test
    starts from an empty settings file.
    """

    if not _can_run_gui_tests():
        return
    try:
        from chaotic_systems.gui.preferences_dialog import _new_qsettings
    except ImportError:  # pragma: no cover - PySide6 missing
        return

    qs = _new_qsettings()
    qs.clear()
    qs.sync()
