"""Shared cross-platform helpers for the agentic-pipeline tooling entrypoints.

PT1a — docs/proposals/python-only-pipeline-tooling-2026-05-31.md.

This module replaces the POSIX-only primitives that the ``init-*.sh`` bash
wrappers relied on (``command -v`` interpreter probe, ``git rev-parse``,
``mkdir -p``, ``date``) with Python-stdlib equivalents so that ``python`` +
``git`` are the only runtime requirements on any OS — including a native
Windows box with no Git Bash / WSL.

SOTA / authority references (verbatim per CLAUDE.md "cite the source"):
  - ``sys.executable`` (docs.python.org/3.12/library/sys.html#sys.executable)
    is the cross-platform self-reference that replaces the bash
    ``command -v python3 || command -v python`` probe — a Python process
    already knows its own interpreter path.
  - ``pathlib.Path.mkdir(parents=True, exist_ok=True)``
    (docs.python.org/3.12/library/pathlib.html) replaces ``mkdir -p``.
  - ``subprocess.run(["git", "rev-parse", ...])``
    (docs.python.org/3.12/library/subprocess.html) replaces the shelled-out
    ``git -C ... rev-parse``.
  - ``datetime.now(timezone.utc)`` replaces the bash UTC ``date`` call.
  - .claude/scripts/PORTABILITY.md §"The remaining cross-platform ceiling"
    (2026-05-31) recommends this exact port.

Stdlib only — no third-party dependencies (json / os / subprocess / sys /
pathlib / datetime).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

try:
    from datetime import UTC, datetime
except ImportError:  # pragma: no cover - Python <3.11 fallback
    from datetime import datetime, timezone

    UTC = timezone.utc  # noqa: UP017 - fallback for Python <3.11

# UTC timestamp formats shared with the historical ``.sh`` heredocs so the
# produced ``state.json`` is byte-identical regardless of entrypoint.
_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_DATE_FORMAT = "%Y-%m-%d"


def configure_utf8_streams() -> None:
    """Force UTF-8 on stdout/stderr (Windows consoles default to cp1252).

    Idempotent and safe to call at import time of every entrypoint; mirrors
    the block already present in the ``checkpoint.py`` files so the ``->``
    transition glyphs and any non-ASCII state content print identically on
    Linux, macOS, and Windows.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):  # pragma: no cover - non-TextIO
            pass


def repo_root() -> Path:
    """Absolute repository root.

    This module lives at ``.claude/scripts/_pipeline_common.py`` so
    ``parents[2]`` is the repo root. Computed from the file location (not the
    cwd) so the entrypoints work from any working directory — the same
    invariant the ``checkpoint.py`` files already rely on.
    """
    return Path(__file__).resolve().parents[2]


def utc_now_iso() -> str:
    """Current UTC instant as ``YYYY-MM-DDTHH:MM:SSZ`` (matches the old bash)."""
    return datetime.now(UTC).strftime(_TS_FORMAT)


def utc_date() -> str:
    """Current UTC date as ``YYYY-MM-DD`` (matches the old bash date stamp)."""
    return datetime.now(UTC).strftime(_DATE_FORMAT)


def git_head_sha(root: Path | None = None) -> str:
    """Current ``git HEAD`` short-circuiting to ``""`` on any failure.

    Replaces ``git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo ''``.
    The draft-proposal pipeline records this as ``init_head_sha`` for its
    phase-5 rogue-commit guard; an empty string is an acceptable sentinel
    (the guard treats a missing baseline as "cannot verify", same as bash).
    """
    root = root or repo_root()
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, ValueError):  # pragma: no cover - git absent
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def ensure_dirs(*dirs: Path) -> None:
    """``mkdir -p`` for each path; parents created, existing dirs left alone."""
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def read_state(state_path: Path) -> dict:
    """Load a ``state.json`` as UTF-8 JSON."""
    return json.loads(state_path.read_text(encoding="utf-8"))


def write_state_atomic(state_path: Path, state: dict) -> None:
    """Write ``state.json`` atomically (tmp + ``os.replace``), UTF-8, indent 2.

    Matches the ``.sh`` heredocs' ``tmp = state_path + ".tmp"`` /
    ``os.replace`` pattern exactly so concurrent readers never see a partial
    file.
    """
    tmp = state_path.with_suffix(state_path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, state_path)


def resume_if_exists(state_path: Path) -> bool:
    """If ``state_path`` exists, print the idempotent-resume line and return True.

    Reproduces the bash guard::

        if [[ -f "$STATE" ]]; then
          PHASE=$(... ['phase'])
          echo "state already exists at $STATE (phase=$PHASE) — resuming"
          exit 0
        fi

    The caller exits 0 on a True return.
    """
    if not state_path.exists():
        return False
    phase = read_state(state_path)["phase"]
    print(f"state already exists at {state_path} (phase={phase}) -- resuming")
    return True
