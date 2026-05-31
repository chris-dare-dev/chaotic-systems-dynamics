#!/usr/bin/env bash
# Print current capability-scout state in a human-readable form.
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
STATE="$REPO_ROOT/.claude/notes/capability-scouts/$ID/state.json"

if [[ ! -f "$STATE" ]]; then
  echo "no state for $ID — run init-capability-scout.sh first" >&2
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

print(f"Capability-scout: {state['id']}")
print(f"Mode:             {state.get('survey_mode', 'standard')}")
cur_phase = state["phase"]
last_ts = parse(hist[-1]["at"])
mins_in_phase = int((now - last_ts).total_seconds() // 60)
print(f"Phase:            {cur_phase} (since {hist[-1]['at']}, {mins_in_phase} min ago)")

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

dispatched = state.get("agents_dispatched") or []
returned = state.get("agents_returned") or []
if dispatched:
    pending = sorted(set(dispatched) - set(returned))
    print(f"Agents:           dispatched={','.join(dispatched)}")
    print(f"                  returned={','.join(returned) if returned else '(none yet)'}")
    if pending:
        print(f"                  pending={','.join(pending)}")

if state.get("synthesis_path"):
    print(
        f"Synthesis:        {state['synthesis_path']} "
        f"({state.get('candidate_count', 0)} candidates)"
    )

if state.get("challenge_path"):
    counts = state.get(
        "challenge_finding_counts", {"critical": 0, "high": 0, "medium": 0, "low": 0}
    )
    print(
        f"Challenge:        {state['challenge_path']} "
        f"(critical={counts.get('critical', 0)}, high={counts.get('high', 0)}, "
        f"medium={counts.get('medium', 0)}, low={counts.get('low', 0)})"
    )

if state.get("final_report_path"):
    print(f"Final report:     {state['final_report_path']}")

NEXT = {
    "init": "survey-running (run Phase 1 — dispatch 4 agents in ONE turn)",
    "survey-running": "survey-complete (agents in flight; await briefs)",
    "survey-complete": "synthesize-running (run Phase 2 — main session merges)",
    "synthesize-running": "synthesize-complete (synthesis.md written)",
    "synthesize-complete": "challenge-running (run Phase 3 — dispatch challenger)",
    "challenge-running": "challenge-complete (challenger in flight)",
    "challenge-complete": "prioritize-running (run Phase 4 — main session ranks)",
    "prioritize-running": "complete (final-report.md written)",
    "complete": "(terminal — pipeline done; offer /milestone-pipeline handoff)",
}
print(f"Next:             {NEXT.get(cur_phase, '(unknown)')}")
PY
