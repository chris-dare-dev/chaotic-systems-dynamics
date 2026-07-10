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

### Registry-synced pipeline workers (`/milestone-pipeline` + `/roadmap`)

The `/milestone-pipeline` and `/roadmap` slash commands, their base
agents, references (`.claude/references/{milestone-pipeline,roadmap}-*`),
and scripts (`.claude/scripts/{milestone-pipeline,roadmap}-*`) are
**copy-synced from the claude-registry repo** — hashes recorded in
`.claude/.registry-manifest.json`. Never edit the synced copies in-repo;
edit the registry and re-sync.

| Agent | Pipeline | Role |
|---|---|---|
| `milestone-researcher` | `/milestone-pipeline` Phase 1 | Research fan-out for the milestone brief. |
| `milestone-implementer` | `/milestone-pipeline` Phase 2 | Delegated implementation in `isolation: worktree`. |
| `milestone-adversary-critic` | `/milestone-pipeline` Phase 3 | Adversarial critique — always fires. |
| `milestone-oss-scout` | `/milestone-pipeline` Phase 3 | Optional OSS-survey critic (`--oss-scout` flag). |
| `roadmap-refiner` | `/roadmap` Phase 1 | HMW restatement, assumption ledger, outcome shaping. |
| `roadmap-decomposer` | `/roadmap` Phase 2 | Epic/milestone decomposition (roadmap/1 items). |
| `roadmap-sequencer` | `/roadmap` Phase 3 | MoSCoW cut + RICE rank via the synced scoring scripts. |
| `roadmap-materializer` | `/roadmap` Phase 4 | Validation + gated external-write hand-off. |

`/roadmap` writes `plans/<slug>/roadmap.yaml` (roadmap/1 format);
`/milestone-pipeline` resolves briefs via
`.claude/scripts/milestone-pipeline-resolve-brief.py` — canonical source
`plans/*/roadmap.yaml`, with a legacy prose fallback over `plans/*.md`
(`### <ID> — ` headings). NOTE: `docs/proposals/*.md` produced by
`/draft-proposal` are NOT searched — promote a proposal's milestones
into a `plans/` roadmap before invoking `/milestone-pipeline`.
Repo-local Phase 3 overlay critics can be added as
`.claude/agents/milestone-*-critic.md` files (NOT in the manifest) —
the synced orchestrator discovers them by filename glob; none exist in
this repo yet.

### Multi-agent pipeline workers (repo-local)

Three further slash commands orchestrate 4-phase parallel-agent pipelines (see
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
| `frontend-uplift-art-direction-scout` | 1 (every mode) | Authors the run's design frame — visual thesis + 3 divergent directions + BAN-1..15 list + surface map — from `frontend-design-language.md` + the house overlay `frontend-uplift/design-system.md`. |
| `frontend-uplift-visual-scout` | 1 (parallel) | Boots the GUI, screenshots multiple states, identifies visual defects. |
| `frontend-uplift-library-scout` | 1 (parallel) | Surveys active PySide6/PyVista/theme libraries (qtawesome, qfluentwidgets, superqt, etc.). |
| `frontend-uplift-inspiration-scout` | 1 (parallel) | Studies napari / ParaView / Houdini / Logic Pro patterns to borrow. |
| `frontend-uplift-current-state-critic` | 1 (parallel) | Reads GUI code + screenshots; surfaces token leaks, spec-vs-impl drift, dead code, reject list. |
| `frontend-uplift-challenger` | 3 (sequential) | Argues against every candidate using the 11-axis checklist (native-only, worker-thread, token discipline, renderer pacing, hi-DPI, a11y, keyboard-equivalent, + axis 11 distinctiveness/anti-template vs BAN-1..15). |
| `frontend-uplift-experiential-scout` | — (INERT) | Synced canon agent; NOT dispatched on this S-2 native surface — award-website motion has near-zero transfer to Qt. |

The Phase 2 (synthesize) and Phase 4 (prioritize) phases run in the
**main session**, not as sub-agents, because synthesis requires all
briefs in working memory and prioritization is the user-review surface.
The synthesis OPENS with the art-direction frame; Phase 4 ranks in
portfolio lanes (a11y-safety-debt mandatory, listed first).

**`/draft-proposal`** — promote CSC items (or a freeform brief) into
a clean `docs/proposals/*.md` ready for `/milestone-pipeline`.

| Agent | Phase | Role |
|---|---|---|
| `draft-proposal-drafter` | 2 (parallel) | Produces per-item What/Where/SOTA/Effort/Rationale sections from the source brief, matching the `capability-roadmap-2026-05-17.md` shape. |
| `draft-proposal-sequencer` | 2 (parallel) | Independently produces the top-of-file dependency table — explicitly does NOT read the drafter's output (anti-anchoring). |
| `draft-proposal-critic` | 3 (sequential) | Walks a 10-axis proposal-hygiene checklist (source traceability, path conflict, citation quality, observable presence, effort calibration, native locks, additivity, bundle coherence, dependency declarations, risks discipline). Same severity calibration as `/capability-scout`'s challenger. |
| `draft-proposal-refiner` | 4 (sequential) | Applies DROP / REDESIGN / MITIGATE / PROCEED dispositions; renumbers the sequencing table; writes the final `docs/proposals/<slug>-<DATE>.md`. The only agent in the pipeline that writes to `docs/`. |

Phase 1 (resolve) and Phase 5 (handoff) run in the **main session**:
resolve needs CLAUDE.md/CONTEXT.md/synthesis-file context already in
working memory; handoff is the user-review surface that OFFERS the
`/milestone-pipeline` invocation (never auto-invokes).

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
