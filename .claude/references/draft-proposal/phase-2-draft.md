# Phase 2 — Draft (parallel: drafter + sequencer)

## Purpose

Two sub-agents run in parallel in ONE assistant turn:

1. **`draft-proposal-drafter`** — produces the per-item
   What/Where/SOTA/Effort/Rationale sections in
   `.claude/notes/draft-proposals/<ID>/artifacts/draft.md`.
2. **`draft-proposal-sequencer`** — independently produces the
   dependency DAG + top-of-file sequencing table in
   `.claude/notes/draft-proposals/<ID>/artifacts/sequencing.md`.

The sequencer runs in parallel — and explicitly does NOT read the
drafter's output — to avoid anchoring the dependency analysis on
whatever order the drafter happened to author the items in. This
mirrors `/capability-scout`'s synthesizer-vs-challenger separation:
distinct roles, fresh contexts.

## Inputs

- Source brief: `.claude/notes/draft-proposals/<ID>/source-brief.md`
  (from Phase 1).
- `state.json` field `slug`, `source_kind`, `resolved_csc_items`.
- Canonical prompts at
  `.claude/references/draft-proposal/agent-prompts.md` §§1-2.
- Template skeleton at
  `.claude/references/draft-proposal/proposal-template.md`.

## Output

- `.claude/notes/draft-proposals/<ID>/artifacts/draft.md`
- `.claude/notes/draft-proposals/<ID>/artifacts/sequencing.md`

## Dispatch protocol — ONE assistant turn

**Critical**: both agents are dispatched in a SINGLE assistant turn
containing two parallel `Agent` tool blocks. Sequential dispatch
doubles wall-clock and breaks the anti-anchoring design.

Each `Agent` call uses:
- `subagent_type: general-purpose` (the harness's agent list locks at
  session start; project-local `draft-proposal-*` agents may not be
  visible mid-session — the workaround is to dispatch via
  general-purpose and embed the brief via "act as the
  draft-proposal-<role> agent defined at
  .claude/agents/draft-proposal-<role>.md — read that file first").
- `model: sonnet` (drafter and sequencer don't need opus).
- `isolation: worktree`.
- Prompt verbatim from
  `.claude/references/draft-proposal/agent-prompts.md` §1 (drafter)
  or §2 (sequencer) with placeholders substituted.

After dispatching:

```bash
for agent in drafter sequencer; do
  .claude/scripts/draft-proposal/checkpoint.py <ID> --append agents_dispatched="\"$agent\""
done
```

## As briefs return

For each agent that returns:
1. Read the agent's reply (it should include the artifact path + a
   3-line summary).
2. Verify the artifact file exists at the expected path.
3. `checkpoint.py <ID> --append agents_returned='"<agent-name>"'`

When both returned, advance:

```bash
.claude/scripts/draft-proposal/checkpoint.py <ID> --set draft_path='".claude/notes/draft-proposals/<ID>/artifacts/draft.md"'
.claude/scripts/draft-proposal/checkpoint.py <ID> --set sequencing_path='".claude/notes/draft-proposals/<ID>/artifacts/sequencing.md"'
.claude/scripts/draft-proposal/checkpoint.py <ID> draft-complete
```

## Hard rules

- **One assistant turn for the dispatch.** Sequential = anchoring
  bias re-introduced.
- **Sequencer does NOT read the drafter's output.** It reads ONLY
  the source brief. The agent prompt encodes this rule; do not
  loosen it.
- **Drafter outputs no sequencing table.** It leaves a
  `<!-- SEQUENCING_TABLE_GOES_HERE -->` marker. The refiner pastes
  the sequencer's table into that marker in Phase 4.
- **No code from either agent.** Both produce markdown artifacts.

## Failure modes

| Failure | Recovery |
|---|---|
| Drafter returns without a draft file | Re-dispatch drafter alone. |
| Sequencer returns with an empty / cyclic DAG | Sequencer must surface the cycle in "Detected cycles". If the cycle is real, the critic will flag it as BLOCKER in Phase 3 and the refiner will redesign or drop in Phase 4. |
| Drafter proposes a path that collides with shipped code | This is a critic-axis-2 finding (path conflict), not a Phase 2 failure. Let it pass and catch it in Phase 3. |
| Drafter writes "(populated after critique)" everywhere | Correct — that placeholder is the contract for the Risks / open questions subsection. The refiner populates it. |

## Anti-patterns

- **Drafter writes the sequencing table.** Forbidden. Two roles by
  design.
- **Sequencer reads the draft.** Forbidden. Order is derived from
  the source brief alone.
- **Bundling heterogeneous categories without a sequencer cluster.**
  The drafter should write category-grouped items (systems →
  integrators → diagnostics → ...) so the sequencer can cluster
  them, even though the sequencer reorders by dependency. Category
  order is the tie-break, not the primary sort.
