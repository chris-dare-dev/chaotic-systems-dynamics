#!/usr/bin/env python3
"""Advance draft-proposal state to the next phase, or read/write a field.

Usage:
  checkpoint.py init <slug> [--from CSC-A,...] [--brief "..."]  # create state.json
  checkpoint.py status <ID>                   # print human-readable state
  checkpoint.py <ID> <new-phase>             # advance state
  checkpoint.py <ID> --get <field>           # read a top-level field
  checkpoint.py <ID> --set <field>=<json>    # set a top-level field
  checkpoint.py <ID> --append <field>=<json> # append json to a list field

Refuses backward and skipped transitions.  Writes atomically.

The ``init`` subcommand (PT1a,
docs/proposals/python-only-pipeline-tooling-2026-05-31.md) is the pure-Python
replacement for the former ``init-draft-proposal.sh``; ``python`` + ``git``
are the only runtime requirements on any OS.
"""

from __future__ import annotations

import json
import os
import re
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

    UTC = timezone.utc  # noqa: UP017 - fallback for Python <3.11

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
    "resolve-running",
    "resolve-complete",
    "draft-running",
    "draft-complete",
    "critique-running",
    "critique-complete",
    "refine-running",
    "refine-complete",
    "recritique-running",
    "recritique-complete",
    "complete",
]

# Allowed loop-back transitions for the re-critique cycle (A4 in the
# 2026-05-19 adversary review). The loop bound is enforced by reading
# `critique_cycle` from state.json — see `advance` below.
LOOP_BACK_TRANSITIONS = {
    ("recritique-running", "refine-running"),
}
MAX_CRITIQUE_CYCLES = 3


def _state_path(uid: str) -> Path:
    # Path: .claude/scripts/draft-proposal/checkpoint.py
    #       parents[3] = repo root
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / ".claude" / "notes" / "draft-proposals" / uid / "state.json"


def _load(state_path: Path) -> dict:
    if not state_path.exists():
        sys.exit(
            f"state.json not found at {state_path} — run "
            "'checkpoint.py init <slug>' first"
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
        sys.exit(
            f"unknown phase: {new_phase}. Valid: {', '.join(PHASE_ORDER)}"
        )
    sp = _state_path(uid)
    state = _load(sp)
    cur = state["phase"]
    # Allowed loop-back for re-critique (CSC adversary review A4).
    if (cur, new_phase) in LOOP_BACK_TRANSITIONS:
        cycle = int(state.get("critique_cycle", 1))
        if cycle >= MAX_CRITIQUE_CYCLES:
            sys.exit(
                f"refusing re-critique loop: critique_cycle = "
                f"{cycle} >= MAX_CRITIQUE_CYCLES = {MAX_CRITIQUE_CYCLES}. "
                "Escalate the BLOCKERs to the user for manual review."
            )
        state["critique_cycle"] = cycle + 1
        now = _now()
        state["phase"] = new_phase
        state["updated_at"] = now
        state["phase_history"].append(
            {"phase": new_phase, "at": now, "loop_cycle": cycle + 1}
        )
        _save_atomic(sp, state)
        print(
            f"{uid}: {cur} -> {new_phase} (loop cycle {cycle + 1}/"
            f"{MAX_CRITIQUE_CYCLES}) @ {now}"
        )
        return
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
    # Use ASCII arrow for portability across cp1252 / utf-8 consoles.
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
        sys.exit(f"unknown field: {field}. Add it to the schema first.")
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
        sys.exit(
            f"field {field!r} is not a list ({type(state[field]).__name__})"
        )
    state[field].append(val)
    state["updated_at"] = _now()
    _save_atomic(sp, state)
    print(f"{uid}: appended to {field} (new length {len(state[field])})")


_DATE_SUFFIX_RE = re.compile(r"-(\d{4}-\d{2}-\d{2})$")


def init(argv: list[str]) -> None:
    """Create the draft-proposal state directory + state.json.

    Pure-Python replacement for ``init-draft-proposal.sh``. Accepts a bare
    ``<slug>`` (the ID becomes ``<slug>-<UTC-date>``) or a fully-qualified
    ``<slug>-<YYYY-MM-DD>`` ID (idempotent resume). Optional ``--from
    CSC-A,...`` or ``--brief "..."`` (mutually exclusive). Captures
    ``init_head_sha`` for the phase-5 rogue-commit guard.
    """
    if not argv:
        sys.exit(
            'usage: checkpoint.py init <slug> [--from CSC-A[,CSC-B,...]] '
            '[--brief "..."]'
        )
    raw_id = argv[0]
    csc_list = ""
    brief = ""
    rest = argv[1:]
    i = 0
    while i < len(rest):
        arg = rest[i]
        if arg == "--from":
            csc_list = rest[i + 1] if i + 1 < len(rest) else ""
            i += 2
        elif arg == "--brief":
            brief = rest[i + 1] if i + 1 < len(rest) else ""
            i += 2
        elif arg == "--resume":
            # No-op: idempotent resume is the default when state.json exists.
            i += 1
        else:
            sys.exit(f"unknown arg: {arg}")
    if csc_list and brief:
        sys.exit("refusing to accept both --from and --brief -- pick one source kind")

    # Compute <ID> = <slug>-<UTC-date>, preserving an already-stamped raw id.
    match = _DATE_SUFFIX_RE.search(raw_id)
    if match:
        sid = raw_id
        slug = raw_id[: match.start()]
        date_stamp = match.group(1)
    else:
        slug = raw_id
        date_stamp = common.utc_date()
        sid = f"{slug}-{date_stamp}"

    root = common.repo_root()
    state_dir = root / ".claude" / "notes" / "draft-proposals" / sid
    state_path = state_dir / "state.json"
    if common.resume_if_exists(state_path):
        return

    # Derive source_kind from the flags (matches the bash precedence).
    if csc_list:
        source_kind = "csc-items" if "," in csc_list else "single-csc"
    elif brief:
        source_kind = "freeform-brief"
    else:
        source_kind = "freeform-brief"
    csc_items = [tok.strip() for tok in csc_list.split(",") if tok.strip()]

    common.ensure_dirs(state_dir / "artifacts")
    mem = root / ".claude" / "agent-memory"
    common.ensure_dirs(
        mem / "draft-proposal-drafter",
        mem / "draft-proposal-sequencer",
        mem / "draft-proposal-critic",
        mem / "draft-proposal-refiner",
    )
    now = _now()
    state = {
        "id": sid,
        "kind": "draft-proposal",
        "slug": slug,
        "date": date_stamp,
        "date_stamp": date_stamp,  # alias kept for verify.py
        "created_at": now,
        "updated_at": now,
        "init_head_sha": common.git_head_sha(root),  # phase-5 rogue-commit guard
        "phase": "init",
        "phase_history": [{"phase": "init", "at": now}],
        # Phase 1 inputs
        "source_kind": source_kind,
        "csc_items": csc_items,
        "draft_brief": brief,
        # Phase 1 outputs
        "source_brief_path": None,
        "resolved_csc_items": [],
        # Phase 2
        "agents_dispatched": [],
        "agents_returned": [],
        "draft_path": None,
        "sequencing_path": None,
        "item_count": 0,
        # Phase 3
        "critique_path": None,
        "critique_finding_counts": {"blocker": 0, "major": 0, "minor": 0, "none": 0},
        "critique_cycle": 1,
        # Phase 4
        "final_proposal_path": None,
        "final_item_count": 0,
        "dropped_at_refinement": [],
    }
    common.write_state_atomic(state_path, state)
    print(f"initialized {state_path}")
    print(f"  slug:        {slug}")
    print(f"  date:        {date_stamp}")
    print(f"  source kind: {source_kind}")
    if csc_list:
        print(f"  csc items:   {csc_list}")
    if brief:
        print("  brief:       (set)")
    print("  phase:       init")


def _parse_ts(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def status(argv: list[str]) -> None:
    """Print the draft-proposal state in a human-readable form.

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

    print(f"Draft-proposal: {state['id']}")
    print(f"Slug:           {state.get('slug', '(unknown)')}")
    print(f"Date:           {state.get('date', '(unknown)')}")
    print(f"Source kind:    {state.get('source_kind', '(unknown)')}")
    csc = state.get("csc_items") or []
    if csc:
        print(f"CSC items:      {','.join(csc)}")
    brief = state.get("draft_brief") or ""
    if brief:
        print(f"Brief:          (set, {len(brief)} chars)")

    cur_phase = state["phase"]
    last_ts = _parse_ts(hist[-1]["at"])
    mins_in_phase = int((now - last_ts).total_seconds() // 60)
    print(
        f"Phase:          {cur_phase} (since {hist[-1]['at']}, "
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

    if state.get("source_brief_path"):
        resolved = state.get("resolved_csc_items") or []
        extra = f" ({len(resolved)} CSC items resolved)" if resolved else ""
        print(f"Source brief:   {state['source_brief_path']}{extra}")

    dispatched = state.get("agents_dispatched") or []
    returned = state.get("agents_returned") or []
    if dispatched:
        pending = sorted(set(dispatched) - set(returned))
        print(f"Agents:         dispatched={','.join(dispatched)}")
        print(
            f"                returned="
            f"{','.join(returned) if returned else '(none yet)'}"
        )
        if pending:
            print(f"                pending={','.join(pending)}")

    if state.get("draft_path"):
        print(
            f"Draft:          {state['draft_path']} "
            f"({state.get('item_count', 0)} items)"
        )

    if state.get("sequencing_path"):
        print(f"Sequencing:     {state['sequencing_path']}")

    if state.get("critique_path"):
        counts = state.get(
            "critique_finding_counts",
            {"blocker": 0, "major": 0, "minor": 0, "none": 0},
        )
        print(
            f"Critique:       {state['critique_path']} "
            f"(blocker={counts.get('blocker', 0)}, major={counts.get('major', 0)}, "
            f"minor={counts.get('minor', 0)}, none={counts.get('none', 0)})"
        )

    if state.get("final_proposal_path"):
        dropped = state.get("dropped_at_refinement") or []
        extra = f"; {len(dropped)} dropped at refinement" if dropped else ""
        print(
            f"Final proposal: {state['final_proposal_path']} "
            f"({state.get('final_item_count', 0)} items{extra})"
        )

    next_hint = {
        "init": "resolve-running (Phase 1 — main session resolves source into source-brief.md)",
        "resolve-running": "resolve-complete (source brief written)",
        "resolve-complete": "draft-running (Phase 2 — dispatch drafter + sequencer in ONE turn)",
        "draft-running": "draft-complete (drafter + sequencer in flight)",
        "draft-complete": "critique-running (Phase 3 — dispatch critic)",
        "critique-running": "critique-complete (critic in flight)",
        "critique-complete": "refine-running (Phase 4 — dispatch refiner)",
        "refine-running": "refine-complete (refiner writes docs/proposals/<slug>-<DATE>.md)",
        "refine-complete": "complete (Phase 5 — main session prints handoff offer)",
        "complete": "(terminal — pipeline done; offer /milestone-pipeline handoff)",
    }
    print(f"Next:           {next_hint.get(cur_phase, '(unknown)')}")


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
