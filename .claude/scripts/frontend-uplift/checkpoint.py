#!/usr/bin/env python3
"""Advance frontend-uplift state to the next phase, or read/write a field.

Usage:
  checkpoint.py init <ID> [--brief "..."] [--lean | --deep]  # create state.json
  checkpoint.py status <ID>                   # print human-readable state
  checkpoint.py <ID> <new-phase>             # advance state
  checkpoint.py <ID> --get <field>           # read a top-level field
  checkpoint.py <ID> --set <field>=<json>    # set a top-level field
  checkpoint.py <ID> --append <field>=<json> # append json to a list field

Refuses backward and skipped transitions.  Writes atomically.

The ``init`` subcommand (PT1a,
docs/proposals/python-only-pipeline-tooling-2026-05-31.md) is the pure-Python
replacement for the former ``init-frontend-uplift.sh``; ``python`` + ``git``
are the only runtime requirements on any OS.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Import the shared cross-platform helpers from the sibling ``.claude/scripts``
# directory. The scripts tree is not an installed package, so prepend its path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _pipeline_common as common  # noqa: E402

try:
    from datetime import UTC, datetime
except ImportError:  # pragma: no cover - Python <3.11 fallback
    from datetime import datetime, timezone

    UTC = timezone.utc

# Windows consoles default to a legacy code page (cp1252) whose codec cannot
# encode the arrows / em-dashes used in the messages below; that raised
# UnicodeEncodeError mid-pipeline. Force UTF-8 on the std streams so output is
# identical on Linux and Windows regardless of the active code page.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):  # pragma: no cover - non-TextIO stream
        pass

PHASE_ORDER = [
    "init",
    "discover-running",
    "discover-complete",
    "synthesize-running",
    "synthesize-complete",
    "challenge-running",
    "challenge-complete",
    "prioritize-running",
    "complete",
]


def _state_path(uid: str) -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / ".claude" / "notes" / "frontend-uplifts" / uid / "state.json"


def _load(state_path: Path) -> dict:
    if not state_path.exists():
        sys.exit(
            f"state.json not found at {state_path} — run "
            "init-frontend-uplift.sh first"
        )
    return json.loads(state_path.read_text(encoding="utf-8"))


def _save_atomic(state_path: Path, state: dict) -> None:
    tmp = state_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, state_path)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def advance(uid: str, new_phase: str) -> None:
    if new_phase not in PHASE_ORDER:
        sys.exit(f"unknown phase: {new_phase}. Valid: {', '.join(PHASE_ORDER)}")
    sp = _state_path(uid)
    state = _load(sp)
    cur = state["phase"]
    cur_idx = PHASE_ORDER.index(cur)
    new_idx = PHASE_ORDER.index(new_phase)
    if new_idx == cur_idx:
        # Idempotent no-op: re-advancing to the current phase is safe and
        # must NOT error, so a call whose write landed but whose response was
        # lost (cancelled parallel-tool batch / flaky transport) can be
        # re-run cleanly. No history entry is appended.
        print(f"{uid}: already at {new_phase} (no-op)")
        return
    if new_idx < cur_idx:
        sys.exit(f"refusing backward transition: {cur} -> {new_phase}")
    if new_idx - cur_idx > 1:
        sys.exit(f"refusing skipped transition: {cur} -> {new_phase}")
    now = _now()
    state["phase"] = new_phase
    state["updated_at"] = now
    state["phase_history"].append({"phase": new_phase, "at": now})
    _save_atomic(sp, state)
    # ASCII arrow: robust even if stdout reconfigure() above failed.
    print(f"{uid}: {cur} -> {new_phase} @ {now}")


def get_field(uid: str, field: str) -> None:
    state = _load(_state_path(uid))
    if field not in state:
        sys.exit(f"unknown field: {field}. Valid: {', '.join(state.keys())}")
    val = state[field]
    if isinstance(val, (dict, list)):
        print(json.dumps(val, indent=2))
    elif val is None:
        print("")
    else:
        print(val)


def set_field(uid: str, expr: str) -> None:
    if "=" not in expr:
        sys.exit("--set value must be field=<json>")
    field, raw = expr.split("=", 1)
    field = field.strip()
    try:
        val = json.loads(raw)
    except json.JSONDecodeError:
        val = raw
    sp = _state_path(uid)
    state = _load(sp)
    if field not in state:
        sys.exit(f"unknown field: {field}.")
    state[field] = val
    state["updated_at"] = _now()
    _save_atomic(sp, state)
    print(f"{uid}: set {field} = {json.dumps(val)[:80]}")


def append_field(uid: str, expr: str) -> None:
    if "=" not in expr:
        sys.exit("--append value must be field=<json>")
    field, raw = expr.split("=", 1)
    field = field.strip()
    try:
        val = json.loads(raw)
    except json.JSONDecodeError:
        val = raw
    sp = _state_path(uid)
    state = _load(sp)
    if field not in state:
        sys.exit(f"unknown field: {field}.")
    if not isinstance(state[field], list):
        sys.exit(f"field {field!r} is not a list ({type(state[field]).__name__})")
    state[field].append(val)
    state["updated_at"] = _now()
    _save_atomic(sp, state)
    print(f"{uid}: appended to {field} (new length {len(state[field])})")


def init(argv: list[str]) -> None:
    """Create the frontend-uplift state directory + state.json.

    Pure-Python replacement for ``init-frontend-uplift.sh``. Free-form ``ID``;
    optional ``--brief``, ``--lean`` / ``--deep`` mode flags. Idempotent: if
    state.json already exists, prints the resume line and returns (exit 0).
    """
    if not argv:
        sys.exit('usage: checkpoint.py init <ID> [--brief "..."] [--lean | --deep]')
    uid = argv[0]
    brief = ""
    discover_mode = "standard"
    rest = argv[1:]
    i = 0
    while i < len(rest):
        arg = rest[i]
        if arg == "--brief":
            brief = rest[i + 1] if i + 1 < len(rest) else ""
            i += 2
        elif arg == "--lean":
            discover_mode = "lean"
            i += 1
        elif arg == "--deep":
            discover_mode = "deep"
            i += 1
        else:
            sys.exit(f"unknown arg: {arg}")
    root = common.repo_root()
    state_dir = root / ".claude" / "notes" / "frontend-uplifts" / uid
    state_path = state_dir / "state.json"
    if common.resume_if_exists(state_path):
        return
    common.ensure_dirs(
        state_dir / "discover-briefs",
        state_dir / "screenshots",
        state_dir / "artifacts",
    )
    mem = root / ".claude" / "agent-memory"
    common.ensure_dirs(
        mem / "frontend-uplift-visual",
        mem / "frontend-uplift-library",
        mem / "frontend-uplift-inspiration",
        mem / "frontend-uplift-current-state-critic",
        mem / "frontend-uplift-challenger",
    )
    now = _now()
    state = {
        "id": uid,
        "kind": "frontend-uplift",
        "created_at": now,
        "updated_at": now,
        "phase": "init",
        "phase_history": [{"phase": "init", "at": now}],
        "frontend_uplift_brief": brief,
        "discover_mode": discover_mode,
        "agents_dispatched": [],
        "agents_returned": [],
        "discover_briefs": [],
        "screenshots_dir": ".claude/notes/frontend-uplifts/" + uid + "/screenshots",
        "screenshot_count": 0,
        "synthesis_path": None,
        "candidate_count": 0,
        "challenge_path": None,
        "challenge_finding_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0},
        "final_report_path": None,
        "ranked_candidates": [],
    }
    common.write_state_atomic(state_path, state)
    print(f"initialized {state_path}")
    print(f"  brief: {'set' if brief else '(empty -- pass --brief to populate)'}")
    print(f"  mode:  {discover_mode}")
    print("  phase: init")


def _parse_ts(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def status(argv: list[str]) -> None:
    """Print the frontend-uplift state in a human-readable form.

    Pure-Python replacement for ``status.sh``. Output is byte-identical to the
    former bash heredoc (same labels, column widths, phase-history elapsed
    deltas, and ``Next:`` hint).
    """
    if not argv:
        sys.exit("usage: checkpoint.py status <ID>")
    uid = argv[0]
    state_path = _state_path(uid)
    if not state_path.exists():
        sys.exit(
            f"no state for {uid} -- run 'checkpoint.py init {uid}' first"
        )
    state = json.loads(state_path.read_text(encoding="utf-8"))

    now = datetime.now(UTC)
    hist = state["phase_history"]

    print(f"Frontend-uplift: {state['id']}")
    print(f"Mode:            {state.get('discover_mode', 'standard')}")
    cur_phase = state["phase"]
    last_ts = _parse_ts(hist[-1]["at"])
    mins_in_phase = int((now - last_ts).total_seconds() // 60)
    print(
        f"Phase:           {cur_phase} (since {hist[-1]['at']}, "
        f"{mins_in_phase} min ago)"
    )

    print("History:")
    for i, entry in enumerate(hist):
        ts = _parse_ts(entry["at"])
        if i + 1 < len(hist):
            nxt = _parse_ts(hist[i + 1]["at"])
            delta = nxt - ts
            mins = int(delta.total_seconds() // 60)
            secs = int(delta.total_seconds() % 60)
            elapsed = (
                f"+{mins:>2}m → {hist[i + 1]['phase']}"
                if mins > 0
                else f"+{secs:>2}s → {hist[i + 1]['phase']}"
            )
        else:
            elapsed = "(now)"
        print(f"  {entry['phase']:<22} {entry['at']} {elapsed}")

    dispatched = state.get("agents_dispatched") or []
    returned = state.get("agents_returned") or []
    if dispatched:
        pending = sorted(set(dispatched) - set(returned))
        print(f"Agents:          dispatched={','.join(dispatched)}")
        print(
            f"                 returned="
            f"{','.join(returned) if returned else '(none yet)'}"
        )
        if pending:
            print(f"                 pending={','.join(pending)}")

    # Screenshot count — visual-scout dumps PNGs into screenshots/. Mirror the
    # legacy status.sh exactly: scan the on-disk dir (under repo root) rather
    # than trusting a state field, list up to 5 names, then a "+N more" tail.
    ss_dir = common.repo_root() / state.get("screenshots_dir", "")
    if ss_dir.is_dir():
        pngs = sorted(p.name for p in ss_dir.iterdir() if p.suffix == ".png")
        print(
            f"Screenshots:     {len(pngs)} in {state.get('screenshots_dir', '')}"
        )
        for p in pngs[:5]:
            print(f"                 - {p}")
        if len(pngs) > 5:
            print(f"                 ... +{len(pngs) - 5} more")

    if state.get("synthesis_path"):
        print(
            f"Synthesis:       {state['synthesis_path']} "
            f"({state.get('candidate_count', 0)} candidates)"
        )

    if state.get("challenge_path"):
        counts = state.get(
            "challenge_finding_counts",
            {"critical": 0, "high": 0, "medium": 0, "low": 0},
        )
        print(
            f"Challenge:       {state['challenge_path']} "
            f"(critical={counts.get('critical', 0)}, high={counts.get('high', 0)}, "
            f"medium={counts.get('medium', 0)}, low={counts.get('low', 0)})"
        )

    if state.get("final_report_path"):
        print(f"Final report:    {state['final_report_path']}")

    next_hint = {
        "init": "discover-running (preflight ensure-gui-bootable.sh, then dispatch 4 agents)",
        "discover-running": "discover-complete (agents in flight; await briefs + screenshots)",
        "discover-complete": "synthesize-running (run Phase 2 — main session merges)",
        "synthesize-running": "synthesize-complete (synthesis.md written)",
        "synthesize-complete": "challenge-running (run Phase 3 — dispatch challenger)",
        "challenge-running": "challenge-complete (challenger in flight)",
        "challenge-complete": "prioritize-running (run Phase 4 — main session ranks)",
        "prioritize-running": "complete (final-report.md written)",
        "complete": "(terminal — pipeline done; offer /milestone-pipeline handoff)",
    }
    print(f"Next:            {next_hint.get(cur_phase, '(unknown)')}")


def main(argv: list[str]) -> None:
    if len(argv) >= 2 and argv[1] == "init":
        init(argv[2:])
        return
    if len(argv) >= 2 and argv[1] == "status":
        status(argv[2:])
        return
    if len(argv) < 3:
        sys.exit(__doc__)
    uid, second = argv[1], argv[2]
    if second == "--get":
        get_field(uid, argv[3])
    elif second == "--set":
        set_field(uid, argv[3])
    elif second == "--append":
        append_field(uid, argv[3])
    else:
        advance(uid, second)


if __name__ == "__main__":
    main(sys.argv)
