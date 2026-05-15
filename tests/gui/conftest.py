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
