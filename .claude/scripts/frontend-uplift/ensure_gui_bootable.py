"""Verify the chaotic-systems-dynamics GUI is bootable (cross-platform).

PT2 — docs/proposals/python-only-pipeline-tooling-2026-05-31.md. Pure-Python,
stdlib-only replacement for ``ensure-gui-bootable.sh`` so that ``python`` +
``git`` are the only runtime requirements on any OS — including a native
Windows box with no Git Bash / WSL. Preflight for Phase 1 of /frontend-uplift.

Confirms that (a) the project ``.venv`` exists, (b) PySide6 + PyVista +
pyvistaqt + chaotic_systems all import inside that venv, and (c) the GUI can be
constructed headless (offscreen) and immediately quit without raising. Exits 0
on green, non-zero on red.

SOTA / authority references (verbatim per CLAUDE.md "cite the source"):
  - PEP 405 "Python Virtual Environments" (python.org/dev/peps/pep-0405/):
    a venv is usable by invoking its interpreter binary directly; the
    ``activate`` script is a convenience, never a requirement. The bash
    version's ``source .venv/bin/activate`` was POSIX-only and the direct
    cause of the Windows breakage — this port calls the venv interpreter
    binary instead, avoiding activation entirely.
  - venv layout (docs.python.org/3.12/library/venv.html §"How venvs work"):
    the interpreter lives at ``.venv/Scripts/python.exe`` on Windows and
    ``.venv/bin/python`` on POSIX. We probe the filesystem for whichever is
    present rather than branching on ``os.name`` (a cross-compiled or unusual
    layout could otherwise lie).
  - ``subprocess.run`` (docs.python.org/3.12/library/subprocess.html) spawns
    the probe in a clean interpreter context with ``QT_QPA_PLATFORM=offscreen``
    so the GUI construction works on a headless host.

Why a rewrite rather than a tweak (verified against the bash on 2026-05-31):
the legacy ``ensure-gui-bootable.sh`` is non-functional as written --
  1. line 37 ``source "$VENV/bin/activate"`` is POSIX-only (the documented
     Windows breakage; there is no ``.venv/Scripts/activate`` branch), and
  2. line 39 invokes ``"$PY"`` but the script never defines ``PY`` (unlike the
     sibling ``status.sh`` / ``init-*.sh``, which carry a ``command -v``
     probe), so under its own ``set -u`` it aborts with an unbound-variable
     error even on POSIX.
This port keeps what the bash got right -- it constructs the real
``build_application()`` entry (returns the ``(app, window)`` pair, the same one
``tests/`` and ``python -m chaotic_systems.gui`` use) and returns 0 on green /
non-zero on red -- and just makes it run everywhere.

Stdlib only -- no third-party dependencies (os / subprocess / sys / pathlib).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Import the shared cross-platform helpers from the .claude/scripts tree.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _pipeline_common as common  # noqa: E402

common.configure_utf8_streams()

# The bootability probe, run inside the venv interpreter via ``-c``. Staged
# exit codes (3/4/5/6) give the caller a diagnostic on which layer failed.
# QT_QPA_PLATFORM=offscreen + pyvista.OFF_SCREEN render the 3D viewport to an
# offscreen framebuffer so the GUI builds on a display-less host; a host with
# no usable GL context at all still cannot initialise VTK -- that surfaces as
# BOOT_FAIL and is the caller's signal to run this on a GL-capable host.
_PROBE_SRC = r"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QTimer  # noqa: F401
    from PySide6.QtWidgets import QApplication  # noqa: F401
except Exception as exc:
    print(f"PYSIDE6_FAIL: {exc}")
    sys.exit(3)

try:
    import pyvista
    import pyvistaqt  # noqa: F401
    pyvista.OFF_SCREEN = True
except Exception as exc:
    print(f"PYVISTA_FAIL: {exc}")
    sys.exit(4)

try:
    import chaotic_systems  # noqa: F401
    from chaotic_systems.gui.main_window import build_application
except Exception as exc:
    print(f"IMPORT_FAIL: {exc}")
    sys.exit(5)

try:
    from PySide6.QtCore import QTimer
    # build_application() is the project's own construct-without-exec entry
    # point (it returns the (app, window) pair); the same one the legacy
    # ensure-gui-bootable.sh probe used and that tests/ use to build-and-quit.
    app, _window = build_application([])
    QTimer.singleShot(0, app.quit)
    app.exec()
    print("BOOT_OK")
except Exception as exc:
    print(f"BOOT_FAIL: {exc}")
    sys.exit(6)
"""


def find_venv_python(repo_root: Path) -> Path | None:
    """Locate the project venv's interpreter, cross-platform.

    Returns the path to ``.venv/Scripts/python.exe`` (Windows) or
    ``.venv/bin/python`` (POSIX) -- whichever actually exists on disk -- or
    ``None`` if neither is present. Probing the filesystem (rather than
    branching on ``os.name``) means an unusual or cross-built layout cannot
    mislead us.
    """
    candidates = (
        repo_root / ".venv" / "Scripts" / "python.exe",  # Windows
        repo_root / ".venv" / "bin" / "python",  # POSIX
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def recovery_message(repo_root: Path) -> str:
    """Human-facing setup instructions printed when ``.venv`` is missing.

    Cross-platform: shows both the POSIX and Windows activation forms (the
    legacy bash script showed only ``source .venv/bin/activate``).
    """
    return (
        f"[fail] .venv not present at {repo_root / '.venv'}\n"
        "\n"
        "Before /frontend-uplift can run Phase 1, the project's virtual\n"
        "environment must be set up. Recovery:\n"
        "\n"
        f"    cd {repo_root}\n"
        "    python -m venv .venv\n"
        "    # POSIX:    source .venv/bin/activate\n"
        "    # Windows:  .venv\\Scripts\\activate\n"
        '    pip install -e ".[dev]"\n'
        "\n"
        "Then re-invoke /frontend-uplift."
    )


def main(argv: list[str] | None = None) -> int:
    """Run the bootability preflight. Returns 0 on green, non-zero on red."""
    print("ensure-gui-bootable: probing GUI import + headless construction")

    root = common.repo_root()
    venv_python = find_venv_python(root)
    if venv_python is None:
        print(recovery_message(root), file=sys.stderr)
        return 1

    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    result = subprocess.run(
        [str(venv_python), "-c", _PROBE_SRC],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    output = (result.stdout + result.stderr).strip()
    if output:
        print(output)

    if result.returncode != 0:
        print(
            f"[fail] GUI bootability probe failed (rc={result.returncode})",
            file=sys.stderr,
        )
        return result.returncode

    print("[ok] GUI is bootable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
