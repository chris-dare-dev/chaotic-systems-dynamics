"""Native desktop GUI for the simulator.

This is a native desktop application — NOT a web frontend. See ``CLAUDE.md``
at the repository root for the rationale and constraints.

Public surface
--------------
- :func:`run` — build the app and enter the Qt event loop.
- :func:`build_application` — same, but return ``(app, window)`` without
  starting the event loop (useful for tests).
- :class:`MainWindow` — the top-level window (lazy attribute; resolves on
  attribute access so importing :mod:`chaotic_systems.gui` does not force
  PySide6 to load).
"""

from __future__ import annotations

from typing import Any

from .main_window import build_application, run

__all__ = ["MainWindow", "build_application", "run"]


def __getattr__(name: str) -> Any:  # pragma: no cover - trivial
    if name == "MainWindow":
        from .main_window import _build_window_class  # type: ignore[attr-defined]

        return _build_window_class()
    raise AttributeError(name)
