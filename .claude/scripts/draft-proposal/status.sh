#!/usr/bin/env bash
# Print current draft-proposal state in a human-readable form.
# Usage: status.sh <ID>

set -euo pipefail

# Portable Python interpreter probe (native Windows has no `python3`).
PY="$(command -v python3 || command -v python || true)"
if [[ -z "$PY" ]]; then
  echo "error: no python3/python interpreter found on PATH" >&2
  exit 1
fi

if [[ $# -lt 1 ]]; then
  echo "usage: status.sh <ID>" >&2
  exit 2
fi

ID="$1"
REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
STATE="$REPO_ROOT/.claude/notes/draft-proposals/$ID/state.json"

if [[ ! -f "$STATE" ]]; then
  echo "no state for $ID — run init-draft-proposal.sh first" >&2
  exit 1
fi

"$PY" - "$STATE" <<'PY'
import json, sys
from datetime import datetime, timezone

# Windows defaults stdout to cp1252, which cannot encode the U+2192 arrows
# printed below; force UTF-8 so output matches Linux/macOS.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

state_path = sys.argv[1]
state = json.load(open(state_path, encoding="utf-8"))


def parse(ts):
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


now = datetime.now(timezone.utc)
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
last_ts = parse(hist[-1]["at"])
mins_in_phase = int((now - last_ts).total_seconds() // 60)
print(f"Phase:          {cur_phase} (since {hist[-1]['at']}, {mins_in_phase} min ago)")

print("History:")
for i, entry in enumerate(hist):
    ts = parse(entry["at"])
    if i + 1 < len(hist):
        nxt = parse(hist[i + 1]["at"])
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
    print(f"                returned={','.join(returned) if returned else '(none yet)'}")
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

NEXT = {
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
print(f"Next:           {NEXT.get(cur_phase, '(unknown)')}")
PY
