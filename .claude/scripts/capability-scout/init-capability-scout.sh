#!/usr/bin/env bash
# Initialize capability-scout state directory and state.json.
#
# Usage: init-capability-scout.sh <ID> [--brief "verbatim user brief"]
#
# Idempotent: if state.json exists, prints current phase and exits 0.
# <ID> is a free-form slug. Typical convention: date-tagged scope
# (e.g. 2026-05-18-diagnostics, 2026-q2-perf, etc.).

set -euo pipefail

# Resolve a Python interpreter portably: native Windows ships `python`
# (or the `py` launcher), not `python3`. Probe so this script runs the
# same under Linux/macOS and Windows Git Bash/WSL.
PY="$(command -v python3 || command -v python || true)"
if [[ -z "$PY" ]]; then
  echo "error: no python3/python interpreter found on PATH" >&2
  exit 1
fi

if [[ $# -lt 1 ]]; then
  echo "usage: init-capability-scout.sh <ID> [--brief \"...\"]" >&2
  exit 2
fi

ID="$1"
shift

BRIEF=""
SURVEY_MODE="standard"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --brief)
      BRIEF="${2:-}"
      shift 2
      ;;
    --lean)
      SURVEY_MODE="lean"
      shift
      ;;
    --deep)
      SURVEY_MODE="deep"
      shift
      ;;
    *)
      echo "unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
DIR="$REPO_ROOT/.claude/notes/capability-scouts/$ID"
STATE="$DIR/state.json"

if [[ -f "$STATE" ]]; then
  PHASE=$("$PY" -c "import json; print(json.load(open('$STATE', encoding='utf-8'))['phase'])")
  echo "state already exists at $STATE (phase=$PHASE) — resuming"
  exit 0
fi

# Phase 1 brief drop + artifacts + per-agent memory dirs.
mkdir -p "$DIR/survey-briefs" "$DIR/artifacts"

# Per-agent project memory directories — created once, accumulate across
# runs (do not clear).
mkdir -p \
  "$REPO_ROOT/.claude/agent-memory/capability-scout-competitive" \
  "$REPO_ROOT/.claude/agent-memory/capability-scout-academic" \
  "$REPO_ROOT/.claude/agent-memory/capability-scout-oss" \
  "$REPO_ROOT/.claude/agent-memory/capability-scout-internal-adversary" \
  "$REPO_ROOT/.claude/agent-memory/capability-scout-challenger"

NOW=$("$PY" -c "from datetime import datetime, timezone; print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))")

"$PY" - "$STATE" "$ID" "$NOW" "$BRIEF" "$SURVEY_MODE" <<'PY'
import json, os, sys
state_path, sid, now, brief, mode = sys.argv[1:6]
state = {
    "id": sid,
    "kind": "capability-scout",            # immutable; disambiguates state files
    "created_at": now,
    "updated_at": now,
    "phase": "init",
    "phase_history": [{"phase": "init", "at": now}],
    "capability_scout_brief": brief,       # free-form user scope, read by Phase 1
    # Phase 1
    "survey_mode": mode,                   # "standard" | "lean" | "deep"
    "agents_dispatched": [],
    "agents_returned": [],
    "survey_briefs": [],                   # paths to written briefs
    # Phase 2
    "synthesis_path": None,
    "candidate_count": 0,
    # Phase 3
    "challenge_path": None,
    "challenge_finding_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0},
    # Phase 4
    "final_report_path": None,
    "ranked_candidates": [],
}
tmp = state_path + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(state, f, indent=2)
os.replace(tmp, state_path)
PY

echo "initialized $STATE"
echo "  brief: $(if [[ -n "$BRIEF" ]]; then echo "set"; else echo "(empty — pass --brief to populate)"; fi)"
echo "  mode:  $SURVEY_MODE"
echo "  phase: init"
