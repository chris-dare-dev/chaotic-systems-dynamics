#!/usr/bin/env bash
# Initialize draft-proposal state directory and state.json.
#
# Usage:
#   init-draft-proposal.sh <slug> [--from CSC-A[,CSC-B,...]] [--brief "..."]
#
# Idempotent: if state.json exists for the computed <ID> (<slug>-<DATE>),
# prints the current phase and exits 0. The slash command body
# substitutes the date stamp into <ID>; here we accept either a bare
# slug (date stamp computed from today's UTC date) or a fully-qualified
# <slug>-<YYYY-MM-DD> ID.
#
# The state.json schema is documented in
# .claude/references/draft-proposal/state-schema.md.

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
  echo "usage: init-draft-proposal.sh <slug> [--from CSC-A[,CSC-B,...]] [--brief \"...\"]" >&2
  exit 2
fi

RAW_ID="$1"
shift

CSC_LIST=""
BRIEF=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --from)
      CSC_LIST="${2:-}"
      shift 2
      ;;
    --brief)
      BRIEF="${2:-}"
      shift 2
      ;;
    --resume)
      # No-op: idempotent resume is the default when state.json
      # exists for the computed <ID>. The flag is accepted for
      # documentation parity with the slash command's usage block
      # (G3 in the 2026-05-19 adversary review).
      shift
      ;;
    *)
      echo "unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -n "$CSC_LIST" && -n "$BRIEF" ]]; then
  echo "refusing to accept both --from and --brief — pick one source kind" >&2
  exit 2
fi

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"

# Compute <ID> = <slug>-<YYYY-MM-DD>. If the raw ID already ends with
# a date stamp, keep it as-is (idempotent resume).
DATE_STAMP="$("$PY" -c "from datetime import datetime, timezone; print(datetime.now(timezone.utc).strftime('%Y-%m-%d'))")"
if [[ "$RAW_ID" =~ -[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  ID="$RAW_ID"
  # Extract slug and date deterministically via sed; the earlier
  # parameter-expansion attempts (G2 in the 2026-05-19 adversary
  # review) didn't work portably across bash versions, so the sed
  # version is the only path now.
  SLUG="$(printf '%s' "$RAW_ID" | sed -E 's/(.*)-[0-9]{4}-[0-9]{2}-[0-9]{2}$/\1/')"
  DATE_STAMP="$(printf '%s' "$RAW_ID" | sed -E 's/.*-([0-9]{4}-[0-9]{2}-[0-9]{2})$/\1/')"
else
  SLUG="$RAW_ID"
  ID="${SLUG}-${DATE_STAMP}"
fi

DIR="$REPO_ROOT/.claude/notes/draft-proposals/$ID"
STATE="$DIR/state.json"

if [[ -f "$STATE" ]]; then
  PHASE=$("$PY" -c "import json; print(json.load(open('$STATE', encoding='utf-8'))['phase'])")
  echo "state already exists at $STATE (phase=$PHASE) — resuming"
  exit 0
fi

# Determine source_kind from arguments.
if [[ -n "$CSC_LIST" ]]; then
  # csc-items if comma-separated, single-csc if a single ID.
  if [[ "$CSC_LIST" == *,* ]]; then
    SOURCE_KIND="csc-items"
  else
    SOURCE_KIND="single-csc"
  fi
elif [[ -n "$BRIEF" ]]; then
  SOURCE_KIND="freeform-brief"
else
  # Neither --from nor --brief — the slash command should have caught
  # this and asked the user; but if it slips through, default to
  # freeform with an empty brief and let Phase 1 fail loudly.
  SOURCE_KIND="freeform-brief"
fi

# Convert comma-separated CSC list to a JSON array of tokens. We pass
# the raw input via stdin to avoid leaning on /tmp/ (G1 in the
# 2026-05-19 adversary review: cross-platform shell discipline) and
# capture the JSON output into a shell variable directly.
CSC_ITEMS_JSON="$("$PY" - "$CSC_LIST" <<'PY'
import json, sys
raw = sys.argv[1]
items = []
if raw:
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        # Accept either "CSC-NNN" or "CSC-<run>-NNN" — normalize to the
        # raw token (Phase 1 does the actual resolution against the
        # newest synthesis).
        items.append(token)
print(json.dumps(items))
PY
)"

mkdir -p "$DIR/artifacts"

# Per-agent project memory dirs — accumulate across runs (do not clear).
mkdir -p \
  "$REPO_ROOT/.claude/agent-memory/draft-proposal-drafter" \
  "$REPO_ROOT/.claude/agent-memory/draft-proposal-sequencer" \
  "$REPO_ROOT/.claude/agent-memory/draft-proposal-critic" \
  "$REPO_ROOT/.claude/agent-memory/draft-proposal-refiner"

NOW=$("$PY" -c "from datetime import datetime, timezone; print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))")
# Record the current git HEAD so verify.py phase-5 can detect any
# rogue agent commits during the pipeline run (G4 in the 2026-05-19
# adversary review — the "general-purpose-via-prompt" dispatch can
# subvert the tool-allowlist and let an agent `git commit`).
INIT_HEAD_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo '')"

"$PY" - "$STATE" "$ID" "$SLUG" "$DATE_STAMP" "$NOW" "$SOURCE_KIND" "$CSC_ITEMS_JSON" "$BRIEF" "$INIT_HEAD_SHA" <<'PY'
import json, os, sys
state_path, sid, slug, date_stamp, now, source_kind, csc_items_raw, brief, init_head_sha = sys.argv[1:10]
csc_items = json.loads(csc_items_raw)
state = {
    "id": sid,
    "kind": "draft-proposal",                # immutable; disambiguates state files
    "slug": slug,
    "date": date_stamp,
    "date_stamp": date_stamp,                # alias kept for verify.py
    "created_at": now,
    "updated_at": now,
    "init_head_sha": init_head_sha,          # phase-5 rogue-commit guard
    "phase": "init",
    "phase_history": [{"phase": "init", "at": now}],
    # Phase 1 inputs
    "source_kind": source_kind,              # "csc-items" | "single-csc" | "freeform-brief"
    "csc_items": csc_items,                  # raw tokens — Phase 1 resolves them
    "draft_brief": brief,                    # verbatim freeform brief (empty for csc-driven runs)
    # Phase 1 outputs
    "source_brief_path": None,
    "resolved_csc_items": [],                # fully-qualified IDs after Phase 1 resolution
    # Phase 2
    "agents_dispatched": [],
    "agents_returned": [],
    "draft_path": None,
    "sequencing_path": None,
    "item_count": 0,
    # Phase 3
    "critique_path": None,
    "critique_finding_counts": {"blocker": 0, "major": 0, "minor": 0, "none": 0},
    "critique_cycle": 1,                     # incremented by recritique loop (max 3)
    # Phase 4
    "final_proposal_path": None,
    "final_item_count": 0,
    "dropped_at_refinement": [],
}
tmp = state_path + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(state, f, indent=2)
os.replace(tmp, state_path)
PY

echo "initialized $STATE"
echo "  slug:        $SLUG"
echo "  date:        $DATE_STAMP"
echo "  source kind: $SOURCE_KIND"
if [[ -n "$CSC_LIST" ]]; then
  echo "  csc items:   $CSC_LIST"
fi
if [[ -n "$BRIEF" ]]; then
  echo "  brief:       (set)"
fi
echo "  phase:       init"
