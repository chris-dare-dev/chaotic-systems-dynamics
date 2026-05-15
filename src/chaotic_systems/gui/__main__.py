"""Entry point: ``python -m chaotic_systems.gui`` launches the desktop app."""

from __future__ import annotations

import sys

from .main_window import run


def main() -> int:
    """Run the GUI event loop. Returns the Qt exit code."""

    return run(sys.argv)


if __name__ == "__main__":  # pragma: no cover - entry-point shim
    sys.exit(main())
