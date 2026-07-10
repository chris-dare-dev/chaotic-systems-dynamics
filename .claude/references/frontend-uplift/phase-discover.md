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
python .claude/scripts/frontend-uplift/ensure_gui_bootable.py
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

## Surface + dispatch matrix

**Surface class — this repo is S-2 (native Qt tool); default `--surface tool`.** The
`art-direction-scout` fires in EVERY mode: it authors the run's design frame (visual thesis + 3
divergent directions + active BAN-1..15 list + surface map) from
`.claude/references/frontend-design-language.md` + the house overlay
`.claude/references/frontend-uplift/design-system.md`. Dropping it re-creates the undirected
default look this pipeline exists to prevent. The `experiential-scout` is **INERT here and is NOT
dispatched** — reverse-engineering award-winning WEBSITES has near-zero transfer to a native Qt
desktop app (no DOM, no scroll surface, no WebGL hero); experiential motion is BLOCKED on S-2
(design-language §3 / motion-vocabulary §0). Say that plainly rather than silently dropping it.

| Mode | Agents dispatched | Notes |
|---|---|---|
| `standard` | art-direction + visual + library + inspiration + current-state-critic | Default. 5 agents, sonnet, worktree-isolated. |
| `lean` | art-direction + visual + library + current-state-critic | Drop inspiration for fast scans — never art-direction. |
| `deep` | art-direction + visual + library + inspiration + current-state-critic (opus) | Same 5; opus-bump the critic when scope is wide. |
| `experiential` | art-direction + visual + library + current-state-critic | Offered for parity; the experiential lens is INERT on S-2 Qt — the report says so rather than dispatching a near-useless web-teardown scout. |

## Dispatch protocol — ONE assistant turn

ONE turn containing N parallel `Agent` tool blocks. Each uses
`subagent_type: general-purpose`, `model: sonnet` (or opus for the
deep critic), `isolation: worktree`.

Prompts for visual / library / inspiration / current-state-critic come verbatim from
`agent-prompts.md` §1-§4 (substitute `{ID}`, `{BRIEF}`, `{BRIEF_PATH}`, `{SCREENSHOTS_DIR}`).
The `art-direction-scout` reads the flat canon (`frontend-design-language.md`) + the house
overlay (`design-system.md`) directly — it has no `agent-prompts.md §` entry.

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
| Compaction mid-Phase-1 | `checkpoint.py status <ID>` shows pending agents; resume by checking each worktree for an emitted brief and re-dispatching if missing. |

## Anti-patterns

- Synthesizing before all 4 briefs are in.
- Skipping the visual-scout because "the GUI hasn't changed much".
  The screenshots are the evidence base for the synthesizer.
- Skipping the current-state-critic. The critic is the analog of
  capability-scout's internal-adversary: surfaces "already shipped,
  don't propose this" + token leaks the other scouts can't catch.
