# State schema — draft-proposal

## Path layout

```
.claude/notes/draft-proposals/<ID>/
├── state.json                    ← the canonical state (atomically written)
├── source-brief.md               ← Phase 1 output (main session)
└── artifacts/
    ├── draft.md                  ← Phase 2 drafter output
    ├── sequencing.md             ← Phase 2 sequencer output
    └── critique.md               ← Phase 3 critic output

docs/proposals/<slug>-<DATE>.md   ← Phase 4 refiner output (NOT under .claude/notes)
```

`<ID>` is `<slug>-<YYYY-MM-DD>`. The whole `.claude/notes/draft-proposals/<ID>/`
tree is gitignored — pipeline artifacts are run-local. The final
proposal under `docs/proposals/` is the only artifact that ships to
the repository (and even then, only when the user reviews it and
runs `/milestone-pipeline`, which commits it alongside the first
implemented item).

## state.json schema

```json
{
  "id": "next-diagnostics-2026-05-19",
  "kind": "draft-proposal",
  "slug": "next-diagnostics",
  "date": "2026-05-19",
  "created_at": "2026-05-19T18:00:00Z",
  "updated_at": "2026-05-19T18:42:00Z",
  "phase": "critique-complete",
  "phase_history": [
    {"phase": "init",                "at": "2026-05-19T18:00:00Z"},
    {"phase": "resolve-running",     "at": "2026-05-19T18:01:00Z"},
    {"phase": "resolve-complete",    "at": "2026-05-19T18:05:00Z"},
    {"phase": "draft-running",       "at": "2026-05-19T18:06:00Z"},
    {"phase": "draft-complete",      "at": "2026-05-19T18:25:00Z"},
    {"phase": "critique-running",    "at": "2026-05-19T18:30:00Z"},
    {"phase": "critique-complete",   "at": "2026-05-19T18:42:00Z"}
  ],

  "source_kind": "csc-items",
  "csc_items": ["CSC-011", "CSC-012", "CSC-013"],
  "draft_brief": "",

  "source_brief_path": ".claude/notes/draft-proposals/next-diagnostics-2026-05-19/source-brief.md",
  "resolved_csc_items": [
    "CSC-2026-q2-broadening-011",
    "CSC-2026-q2-broadening-012",
    "CSC-2026-q2-broadening-013"
  ],

  "agents_dispatched": ["drafter", "sequencer"],
  "agents_returned":   ["drafter", "sequencer"],
  "draft_path": ".claude/notes/draft-proposals/next-diagnostics-2026-05-19/artifacts/draft.md",
  "sequencing_path": ".claude/notes/draft-proposals/next-diagnostics-2026-05-19/artifacts/sequencing.md",
  "item_count": 3,

  "critique_path": ".claude/notes/draft-proposals/next-diagnostics-2026-05-19/artifacts/critique.md",
  "critique_finding_counts": {"blocker": 1, "major": 5, "minor": 8, "none": 16},

  "final_proposal_path": null,
  "final_item_count": 0,
  "dropped_at_refinement": []
}
```

## Field reference

| Field | Type | Mutator | Notes |
|---|---|---|---|
| `id` | str | init | Immutable. `<slug>-<DATE>`. |
| `kind` | str | init | Always `"draft-proposal"`. Disambiguates from other pipelines sharing `.claude/notes/`. |
| `slug` | str | init | The kebab-case noun phrase. |
| `date` | str | init | `YYYY-MM-DD` — the date the proposal will use in filename + H1. |
| `phase` | str | `checkpoint.py <ID> <new-phase>` | Forward-only. |
| `phase_history` | list[{phase, at}] | every advance | Append-only timeline. |
| `source_kind` | str | init | `"csc-items"` / `"single-csc"` / `"freeform-brief"`. |
| `csc_items` | list[str] | init | Raw tokens passed via `--from`. Phase 1 resolves them. |
| `draft_brief` | str | init | Verbatim freeform brief (empty for csc-driven runs). |
| `source_brief_path` | str \| null | main session `--set` (Phase 1) | Path to the assembled source brief. |
| `resolved_csc_items` | list[str] | main session `--set` (Phase 1) | Fully-qualified CSC IDs after synthesis lookup. |
| `agents_dispatched` | list[str] | main session `--append` | Phase 2 agents fired in the dispatch turn. |
| `agents_returned` | list[str] | main session `--append` | Subset of dispatched that have produced an artifact. |
| `draft_path` | str \| null | main session `--set` (Phase 2) | Path to `artifacts/draft.md`. |
| `sequencing_path` | str \| null | main session `--set` (Phase 2) | Path to `artifacts/sequencing.md`. |
| `item_count` | int | main session `--set` (Phase 2) | Number of items in the draft. |
| `critique_path` | str \| null | main session `--set` (Phase 3) | Path to `artifacts/critique.md`. |
| `critique_finding_counts` | dict | main session `--set` (Phase 3) | `{blocker, major, minor, none}` counts from the critic. |
| `final_proposal_path` | str \| null | main session `--set` (Phase 4) | Path to `docs/proposals/<slug>-<DATE>.md`. |
| `final_item_count` | int | main session `--set` (Phase 4) | Number of items in the final proposal (after DROPs). |
| `dropped_at_refinement` | list[dict] | main session `--set` (Phase 4) | Each entry: `{id, title, blocker_axis}`. |

## Phase transitions (forward-only, single-step)

```
init
  → resolve-running       (Phase 1 — main session resolves source into source-brief.md)
  → resolve-complete      (source brief written)
  → draft-running         (Phase 2 — dispatch drafter + sequencer in ONE turn)
  → draft-complete        (both artifacts returned)
  → critique-running      (Phase 3 — dispatch critic)
  → critique-complete     (critique.md written)
  → refine-running        (Phase 4 — dispatch refiner)
  → refine-complete       (final proposal written to docs/proposals/)
  → complete              (Phase 5 — main session prints handoff offer)
```

`checkpoint.py` refuses any transition that's backward or skips a
phase. This is the resume-safety guarantee — if compaction strikes
mid-run, the next session can `checkpoint.py status <ID>` and pick up exactly
where it left off.
