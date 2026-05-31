#!/usr/bin/env bash
# Verify the chaotic-systems-dynamics GUI is bootable before dispatching
# Phase 1 of /frontend-uplift. Exits 0 on green, 1 on red — the slash
# command invokes this BEFORE the parallel dispatch.
#
# Specifically: confirms that (a) the venv exists, (b) PySide6 +
# PyVista + pyvistaqt + chaotic_systems all import, and (c) the
# build_application factory can construct a window and immediately
# quit without raising.

set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
VENV="$REPO_ROOT/.venv"

if [[ ! -d "$VENV" ]]; then
  cat <<EOF >&2
[fail] .venv not present at $VENV

Before /frontend-uplift can run Phase 1, the project's virtual
environment must be set up. Recovery:

    cd $REPO_ROOT
    python3.12 -m venv .venv
    source .venv/bin/activate
    pip install -e ".[dev]"

Then re-invoke /frontend-uplift.
EOF
  exit 1
fi

# Source the venv and check the actual import + factory path. Use a
# short Python snippet rather than re-implementing the bootability
# check in shell.
# shellcheck disable=SC1091
source "$VENV/bin/activate"

OUTPUT=$("$PY" <<'PY' 2>&1
import sys

try:
    from PySide6.QtCore import QTimer  # noqa: F401
    from PySide6.QtWidgets import QApplication  # noqa: F401
except Exception as exc:
    print(f"PYSIDE6_FAIL: {type(exc).__name__}: {exc}")
    sys.exit(2)

try:
    import pyvista  # noqa: F401
    import pyvistaqt  # noqa: F401
except Exception as exc:
    print(f"PYVISTA_FAIL: {type(exc).__name__}: {exc}")
    sys.exit(3)

try:
    from chaotic_systems.gui.main_window import build_application
except Exception as exc:
    print(f"IMPORT_FAIL: {type(exc).__name__}: {exc}")
    sys.exit(4)

try:
    # Build but immediately quit — confirms the window is constructible.
    app, window = build_application([])
    QTimer = __import__("PySide6.QtCore", fromlist=["QTimer"]).QTimer
    QTimer.singleShot(0, app.quit)
    rc = app.exec()
    if rc != 0:
        print(f"EXEC_NONZERO: rc={rc}")
        sys.exit(5)
except Exception as exc:
    print(f"BOOT_FAIL: {type(exc).__name__}: {exc}")
    sys.exit(6)

print("OK: GUI is bootable")
PY
)

RC=$?

if [[ $RC -eq 0 ]]; then
  echo "[ok] $OUTPUT"
  exit 0
fi

cat <<EOF >&2
[fail] GUI is not bootable.

Detail: $OUTPUT

Before /frontend-uplift can run Phase 1, the GUI must boot cleanly.
Recovery depends on the failure mode:

  PYSIDE6_FAIL    → pip install -e ".[dev]"
  PYVISTA_FAIL    → pip install pyvista pyvistaqt
  IMPORT_FAIL     → pip install -e ".[dev]"  (project itself)
  BOOT_FAIL       → likely a code-level regression; investigate the
                    traceback above. /frontend-uplift cannot run a
                    visual-evidence pipeline against a broken GUI.

Then re-invoke /frontend-uplift. This preflight runs ONLY before
Phase 1; once discover-running advances, you may stop or modify the
GUI.
EOF
exit 1
