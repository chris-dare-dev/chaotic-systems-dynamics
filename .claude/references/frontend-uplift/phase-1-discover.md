# Phase 1 — Discover

## Purpose

Fan out N specialized sub-agents in parallel to surface visual /
interaction defects + opportunities from independent lenses. The
visual-scout boots the GUI and produces PNG evidence under
`screenshots/`; the other scouts read briefs + the codebase + the web.

## Inputs

- `state.json` field `frontend_uplift_brief` — user-supplied scope.
- `state.json` field `discover_mode` — `standard` (4 agents) /
  `lean` (3, drops inspiration) / `deep` (4, opus-bumped critic).
- Curated sources at
  `.claude/references/frontend-uplift/source-registry.md`.
- Canonical prompts at
  `.claude/references/frontend-uplift/agent-prompts.md`.

## Preflight (REQUIRED before dispatch)

```bash
.claude/scripts/frontend-uplift/ensure-gui-bootable.sh
```

Exits non-zero with a copy-paste recovery hint if the GUI can't boot
cleanly. Halt the pipeline if it fails — Phase 1 cannot run a
visual-evidence pipeline against a broken GUI.

## Output

- One brief per agent under
  `.claude/notes/frontend-uplifts/<ID>/discover-briefs/<agent>-brief.md`.
- N screenshots under
  `.claude/notes/frontend-uplifts/<ID>/screenshots/<state>.png` (from
  visual-scout).

## Dispatch matrix

| Mode | Agents dispatched | Notes |
|---|---|---|
| `standard` | visual + library + inspiration + current-state-critic | Default. 4 agents, sonnet, worktree-isolated. |
| `lean` | visual + library + current-state-critic | Drop inspiration for fast scans. |
| `deep` | visual + library + inspiration + current-state-critic (opus) | Same 4; opus-bump the critic when scope is wide. |

## Dispatch protocol — ONE assistant turn

ONE turn containing N parallel `Agent` tool blocks. Each uses
`subagent_type: general-purpose`, `model: sonnet` (or opus for the
deep critic), `isolation: worktree`.

Prompts come verbatim from `agent-prompts.md` §1-§4. Substitute
`{ID}`, `{BRIEF}`, `{BRIEF_PATH}`, `{SCREENSHOTS_DIR}`.

After dispatching, append each agent name to `agents_dispatched` and
advance to `discover-running`.

## As briefs return

For each agent:
1. Verify the brief file exists.
2. For visual: verify ≥ 5 PNGs under `screenshots/`.
3. `checkpoint.py <ID> --append agents_returned='"<agent>"'`
4. `checkpoint.py <ID> --append discover_briefs='"<path>"'`

When all returned, `checkpoint.py <ID> --set screenshot_count=<N>`
(count PNGs) and advance to `discover-complete`.

## Hard rules

- Preflight passes before dispatch. No exceptions.
- One assistant turn for all N agents.
- Each agent's prompt is the canonical version. Substitute
  placeholders only.
- Visual-scout MUST produce screenshots. If it returns without PNGs,
  re-dispatch.
- No code. Each agent writes a brief.

## Failure modes

| Failure | Recovery |
|---|---|
| Preflight fails | Surface the recovery hint to the user. Halt. |
| Visual-scout returns without screenshots | Re-dispatch; verify the driver script ran. |
| Brief proposes web/Electron | Surface in synthesis under "rejected by Phase 1 hard rule". |
| Compaction mid-Phase-1 | `status.sh <ID>` shows pending agents; resume by checking each worktree for an emitted brief and re-dispatching if missing. |

## Anti-patterns

- Synthesizing before all 4 briefs are in.
- Skipping the visual-scout because "the GUI hasn't changed much".
  The screenshots are the evidence base for the synthesizer.
- Skipping the current-state-critic. The critic is the analog of
  capability-scout's internal-adversary: surfaces "already shipped,
  don't propose this" + token leaks the other scouts can't catch.
