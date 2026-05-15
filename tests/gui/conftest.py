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
"""

from __future__ import annotations

import os

import pytest


def _can_run_gui_tests() -> bool:
    return os.environ.get("CHAOTIC_GUI_TESTS_USE_DISPLAY") == "1"


def pytest_collection_modifyitems(config, items):  # type: ignore[no-untyped-def]
    if _can_run_gui_tests():
        return
    skip_marker = pytest.mark.skip(
        reason=(
            "GUI tests need a real display; set "
            "CHAOTIC_GUI_TESTS_USE_DISPLAY=1 to enable."
        )
    )
    for item in items:
        item.add_marker(skip_marker)


@pytest.fixture(scope="session")
def qapp_args() -> list[str]:  # pragma: no cover - trivial fixture
    """Args passed to the QApplication built by ``pytest-qt``."""

    return ["chaotic-systems-tests"]
