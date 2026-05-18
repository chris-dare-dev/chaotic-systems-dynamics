# Project-local Claude Code agents

Reusable agent definitions for `chaotic-systems-dynamics`. These let any
Claude Code session invoke a long, repo-aware brief by short name
instead of re-typing a 600-line prompt every time.

## Inventory

### Standalone read-only scouts (proposal-only)

The standalone `ui-upgrade-scout` has been superseded by the
`/frontend-uplift` pipeline below — but the single-agent file is kept
for users who want a fast, single-context UI evaluation without
running a full 4-phase pipeline.

| Agent | Purpose | Output |
|---|---|---|
| `ui-upgrade-scout` | Single-agent UI evaluation (deprecated — prefer `/frontend-uplift`). | `docs/proposals/ui-upgrade-<date>.md` |

### Multi-agent pipeline workers

Two slash commands orchestrate 4-phase parallel-agent pipelines (see
`.claude/commands/`). These agents are not invoked individually in
normal use — the slash commands dispatch them.

**`/capability-scout`** — what capability should we build next?

| Agent | Phase | Role |
|---|---|---|
| `capability-scout-competitive` | 1 (parallel) | Surveys tools occupying the same niche (dysts, DynamicalSystems.jl, pynamicalsys, etc.). |
| `capability-scout-academic` | 1 (parallel) | Surveys 2023-2026 arXiv / journal literature on chaotic dynamics + numerics. |
| `capability-scout-oss` | 1 (parallel) | Surveys active Python OSS with strict last-release-date discipline. |
| `capability-scout-internal-adversary` | 1 (parallel) | Reads the codebase to find "already built but un-exposed" capabilities (D1-class wins). |
| `capability-scout-challenger` | 3 (sequential) | Argues against every candidate in the synthesis using a 10-axis checklist. |

**`/frontend-uplift`** — where can the frontend become more modern?

| Agent | Phase | Role |
|---|---|---|
| `frontend-uplift-visual` | 1 (parallel) | Boots the GUI, screenshots multiple states, identifies visual defects. |
| `frontend-uplift-library` | 1 (parallel) | Surveys active PySide6/PyVista/theme libraries (qtawesome, qfluentwidgets, superqt, etc.). |
| `frontend-uplift-inspiration` | 1 (parallel) | Studies napari / ParaView / Houdini / Logic Pro patterns to borrow. |
| `frontend-uplift-current-state-critic` | 1 (parallel) | Reads GUI code + screenshots; surfaces token leaks, spec-vs-impl drift, dead code, reject list. |
| `frontend-uplift-challenger` | 3 (sequential) | Argues against every candidate using a 10-axis checklist (native-only, worker-thread, token discipline, renderer pacing, hi-DPI, a11y, etc.). |

The Phase 2 (synthesize) and Phase 4 (prioritize) phases run in the
**main session**, not as sub-agents, because synthesis requires all
4 briefs in working memory and prioritization is the user-review
surface.

## How to invoke

**Standalone scouts** (e.g. `ui-upgrade-scout`): in a fresh Claude
Code session, dispatch via the `Agent` tool with `subagent_type` set
to the agent name and a brief task description.

**Pipeline agents** (`capability-scout-*`): do NOT invoke individually.
Run `/capability-scout <ID>` instead; the slash command body
orchestrates Phase 1 dispatch + Phase 3 challenge.

**Mid-session limitation.** If you add or modify an agent definition
during a running session, the harness's `Agent` tool will NOT see the
new definition — the agent list is locked at session start. Workaround:
dispatch via `subagent_type: "general-purpose"` and put `"You are
acting as the <name> agent defined at .claude/agents/<name>.md — read
that file first and follow it exactly"` at the top of the prompt.
Restart the session to get the auto-discovered path back.

## Why this pattern

Every prior round of evaluation / research in this repo was a
one-shot inline prompt that died with the agent. By persisting the
agent definitions here:

- Future sessions reuse the same vocabulary and evaluation axes.
- The "what does this project look like to an outside expert" lens is
  one slash command away rather than a fresh hour of prompt-writing.
- Per-agent project memory accumulates under
  `.claude/agent-memory/<agent-name>/lessons.md`.

## Agent memory

All scouts have `memory: project` and accumulate lessons across runs
under `.claude/agent-memory/<agent-name>/lessons.md`. Do NOT clear or
overwrite these files; agents read them at the start of every run.

## When to add a new agent

Add a new agent here when you find yourself writing the same long
brief twice. Single-shot work stays inline. The bar for adding a
persistent agent is "I expect to invoke this 3+ times over the
project's life".

If a use case spans multiple lenses + a synthesizer + a challenger,
don't add five separate agents — build a slash command in
`.claude/commands/` that orchestrates them. See `capability-scout` as
the reference implementation.
