"""Launch the desktop GUI pre-loaded with the Lorenz attractor.

Usage::

    python examples/lorenz_gui.py

If the registry exposes a system named ``"Lorenz"``, the GUI selects it
automatically; otherwise it falls back to the in-GUI Lorenz placeholder
so this example always launches.

Note: this script does NOT auto-trigger a simulation on launch — the
``Run`` button runs the simulation on a worker thread (see
``main_window.py``). Press ``Run`` (or ``Ctrl-R``) to integrate.
"""

from __future__ import annotations

import sys

from chaotic_systems.gui.main_window import build_application
from chaotic_systems.visualization.contract import list_systems_safe


def main() -> int:
    app, window = build_application(sys.argv)
    candidates = [getattr(s, "name", "") for s in list_systems_safe()]
    for needle in ("Lorenz", "lorenz", "Lorenz attractor"):
        if needle in candidates:
            idx = window.system_box.findText(needle)
            if idx >= 0:
                window.system_box.setCurrentIndex(idx)
                break
    window.show()
    return int(app.exec())


if __name__ == "__main__":
    raise SystemExit(main())
