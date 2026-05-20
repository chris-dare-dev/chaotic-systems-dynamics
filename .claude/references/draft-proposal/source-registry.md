# Source registry — draft-proposal

Curated list of sources each Phase 2 / Phase 3 agent reaches for
first, indexed by source kind. **Loaded by sub-agents at phase
start, NOT by the main session at slash-command load.**

The drafter, sequencer, critic, and refiner all read different
subsets. This file is the index.

---

## §1 — Drafter lens (for `draft-proposal-drafter`)

The drafter's source set depends on `{SOURCE_KIND}`.

### `csc-items` / `single-csc` (bundle from synthesis)

| Source | Why |
|---|---|
| `{SOURCE_BRIEF_PATH}` | The Phase 1 main-session resolution. Contains the full verbatim CSC sections. The drafter's primary input. |
| The newest `.claude/notes/capability-scouts/*/artifacts/synthesis.md` | Cross-reference if the source brief truncated anything. Use the same synthesis the source-brief cited. |
| `docs/proposals/capability-roadmap-2026-05-17.md` | The canonical proposal format. Per-item W/W/S/E/R shape, sequencing table layout, "Rejected" footer. |
| `docs/proposals/README.md` | Naming convention: `<slug>-<YYYY-MM-DD>.md`. |
| `CLAUDE.md` "The frontend is native — do not change that" + "Mathematical correctness" | The architectural locks the drafter must respect at drafting time. Web framework / Julia-Rust-C++ deps get dropped pre-critique. |
| `CONTEXT.md` "Recently shipped" (every section) | Path-conflict pre-check. If a CSC item targets a file already shipped, the drafter should propose a wire-up not a duplicate. |

### `freeform-brief`

The drafter has no CSC to copy from — it must elicit per-item
structure from the brief.

| Source | Why |
|---|---|
| `{SOURCE_BRIEF_PATH}` | The verbatim user brief + the auto-generated "Context for drafting" section the Phase-1 main session added. |
| `CONTEXT.md` "Current state" | Knowing what's already shipped is non-negotiable for freeform drafts. |
| `CONTEXT.md` "Recently shipped" | Avoid re-proposing shipped work. |
| The most recent `.claude/notes/capability-scouts/*/survey-briefs/internal-adversary-brief.md` (if present) | Useful for freeform drafters who suspect their brief implies a wire-up of existing-but-un-surfaced code (D1-class). |
| `docs/proposals/capability-roadmap-2026-05-17.md` | Format reference. |
| `docs/proposals/README.md` | Naming convention. |
| `CLAUDE.md` | Hard locks. |
| `docs/systems.md`, `docs/numerics.md`, `docs/visualization.md` | If the brief touches a specific subsystem, the relevant `docs/*.md` is the architectural reference. |

---

## §2 — Sequencer lens (for `draft-proposal-sequencer`)

The sequencer does NOT read the drafter's output. It reads only:

| Source | Why |
|---|---|
| `{SOURCE_BRIEF_PATH}` | The same Phase 1 resolution the drafter sees. CSC items' "Depends on" lines are the primary dependency signal. |
| `CONTEXT.md` "Recently shipped" | Which dependencies are already met. If item B "depends on" something that shipped two weeks ago, B has no un-met dep and can ship first. |
| `docs/proposals/capability-roadmap-2026-05-17.md` § Sequencing | The exact table format. Single-row-per-item, four columns, "Why first / why not" in single-clause phrases. |
| `CLAUDE.md` | Locks that affect sequencing — e.g. you cannot sequence an item before its un-met diffrax-backend dependency. |

The sequencer does NOT consult arXiv, GitHub, or any external
web source. Its job is structural, not novelty-discovery.

---

## §3 — Critic lens (for `draft-proposal-critic`)

The critic reads the most:

| Source | Why |
|---|---|
| `{DRAFT_PATH}` | The artifact under critique. End-to-end read. |
| `{SEQUENCING_PATH}` | Cycle detection, foundational-violation detection, effort-stacking detection. |
| `{SOURCE_BRIEF_PATH}` | Source traceability check (axis 1). |
| `CONTEXT.md` "Recently shipped" (every section) | Path-conflict check (axis 2). The critic's highest-yield axis. |
| `git log --oneline -50` | Cross-reference against CONTEXT.md — sometimes a commit landed after the last "Recently shipped" rollout. |
| `CLAUDE.md` | Native + foreign-compile check (axis 6), additive vs invasive (axis 7). |
| `.claude/references/draft-proposal/phase-3-critique.md` | The 10-axis checklist + rubric. |

The critic does NOT consult external web sources — its job is
checking proposal hygiene against the project's own rules.

---

## §4 — Refiner lens (for `draft-proposal-refiner`)

The integration phase:

| Source | Why |
|---|---|
| `{DRAFT_PATH}` | The W/W/S/E/R content to copy verbatim (or REDESIGN). |
| `{SEQUENCING_PATH}` | The table to paste, after DROP-aware renumbering. |
| `{CRITIQUE_PATH}` | The dispositions to apply. |
| `{SOURCE_BRIEF_PATH}` | For REDESIGN cases, the original evidence the refiner is re-anchoring against. |
| `.claude/references/draft-proposal/proposal-template.md` | The canonical skeleton. |
| `CLAUDE.md` | Final correctness gate. |
| `docs/proposals/capability-roadmap-2026-05-17.md` | Format consistency. |
| `docs/proposals/README.md` | Filename convention. |

The refiner does NOT add new W/W/S/E/R content beyond what's in the
draft or what a REDESIGN strictly requires. It also does NOT consult
external web sources.

---

## Updating this file

When a new source proves load-bearing in a real run (e.g. a freeform
brief that needed `docs/prerender_design.md` to draft correctly),
add it here. This file IS the institutional memory of "where do we
look for X when drafting a proposal".
