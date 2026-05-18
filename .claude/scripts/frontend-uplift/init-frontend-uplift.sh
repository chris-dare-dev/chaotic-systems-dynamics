#!/usr/bin/env bash
# Initialize frontend-uplift state directory and state.json.
#
# Usage: init-frontend-uplift.sh <ID> [--brief "..."] [--lean | --deep]
#
# Idempotent: if state.json exists, prints current phase and exits 0.

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: init-frontend-uplift.sh <ID> [--brief \"...\"] [--lean | --deep]" >&2
  exit 2
fi

ID="$1"
shift

BRIEF=""
DISCOVER_MODE="standard"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --brief)
      BRIEF="${2:-}"
      shift 2
      ;;
    --lean)
      DISCOVER_MODE="lean"
      shift
      ;;
    --deep)
      DISCOVER_MODE="deep"
      shift
      ;;
    *)
      echo "unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
DIR="$REPO_ROOT/.claude/notes/frontend-uplifts/$ID"
STATE="$DIR/state.json"

if [[ -f "$STATE" ]]; then
  PHASE=$(python3 -c "import json; print(json.load(open('$STATE'))['phase'])")
  echo "state already exists at $STATE (phase=$PHASE) — resuming"
  exit 0
fi

mkdir -p "$DIR/discover-briefs" "$DIR/screenshots" "$DIR/artifacts"

# Per-agent project memory dirs — accumulate across runs (do not clear).
mkdir -p \
  "$REPO_ROOT/.claude/agent-memory/frontend-uplift-visual" \
  "$REPO_ROOT/.claude/agent-memory/frontend-uplift-library" \
  "$REPO_ROOT/.claude/agent-memory/frontend-uplift-inspiration" \
  "$REPO_ROOT/.claude/agent-memory/frontend-uplift-current-state-critic" \
  "$REPO_ROOT/.claude/agent-memory/frontend-uplift-challenger"

NOW=$(python3 -c "from datetime import datetime, timezone; print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))")

python3 - "$STATE" "$ID" "$NOW" "$BRIEF" "$DISCOVER_MODE" <<'PY'
import json, os, sys
state_path, sid, now, brief, mode = sys.argv[1:6]
state = {
    "id": sid,
    "kind": "frontend-uplift",            # immutable
    "created_at": now,
    "updated_at": now,
    "phase": "init",
    "phase_history": [{"phase": "init", "at": now}],
    "frontend_uplift_brief": brief,
    "discover_mode": mode,                # "standard" | "lean" | "deep"
    "agents_dispatched": [],
    "agents_returned": [],
    "discover_briefs": [],
    "screenshots_dir": ".claude/notes/frontend-uplifts/" + sid + "/screenshots",
    "screenshot_count": 0,
    "synthesis_path": None,
    "candidate_count": 0,
    "challenge_path": None,
    "challenge_finding_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0},
    "final_report_path": None,
    "ranked_candidates": [],
}
tmp = state_path + ".tmp"
with open(tmp, "w") as f:
    json.dump(state, f, indent=2)
os.replace(tmp, state_path)
PY

echo "initialized $STATE"
echo "  brief: $(if [[ -n "$BRIEF" ]]; then echo "set"; else echo "(empty — pass --brief to populate)"; fi)"
echo "  mode:  $DISCOVER_MODE"
echo "  phase: init"
