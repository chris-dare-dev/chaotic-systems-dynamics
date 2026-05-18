# State schema — frontend-uplift

## Path layout

```
.claude/notes/frontend-uplifts/<ID>/
├── state.json                    ← canonical state (atomically written)
├── discover-briefs/              ← Phase 1 output
│   ├── visual-brief.md
│   ├── library-brief.md
│   ├── inspiration-brief.md
│   └── current-state-critic-brief.md
├── screenshots/                  ← visual-scout's PNGs
│   ├── initial.png
│   ├── lorenz-running.png
│   ├── settings-open.png
│   └── ...
└── artifacts/
    ├── synthesis.md              ← Phase 2 output
    ├── challenge.md              ← Phase 3 output
    └── final-report.md           ← Phase 4 output
```

The whole tree is gitignored — pipeline artifacts are run-local.

## state.json schema

```json
{
  "id": "2026-05-18-toolbar",
  "kind": "frontend-uplift",
  "created_at": "...",
  "updated_at": "...",
  "phase": "discover-running",
  "phase_history": [...],
  "frontend_uplift_brief": "focus on toolbar density and Diagnostics card hierarchy",
  "discover_mode": "standard",
  "agents_dispatched": ["visual", "library", "inspiration", "current-state-critic"],
  "agents_returned": [],
  "discover_briefs": [],
  "screenshots_dir": ".claude/notes/frontend-uplifts/2026-05-18-toolbar/screenshots",
  "screenshot_count": 0,
  "synthesis_path": null,
  "candidate_count": 0,
  "challenge_path": null,
  "challenge_finding_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0},
  "final_report_path": null,
  "ranked_candidates": []
}
```

## Field reference

| Field | Type | Mutator | Notes |
|---|---|---|---|
| `id` | str | init | Immutable. |
| `kind` | str | init | Always `"frontend-uplift"`. |
| `phase` | str | `checkpoint.py <ID> <new-phase>` | Forward-only. |
| `discover_mode` | str | init `--lean/--deep` | `"standard"` (4) / `"lean"` (3, drops inspiration) / `"deep"` (4, opus-bumped critic). |
| `agents_dispatched` | list[str] | main session `--append` | Subset of `{visual, library, inspiration, current-state-critic}`. |
| `agents_returned` | list[str] | main session `--append` | Subset of dispatched. |
| `discover_briefs` | list[str] | main session `--append` | Paths to written briefs. |
| `screenshots_dir` | str | init | Relative path; visual-scout writes PNGs here. |
| `screenshot_count` | int | main session `--set` | Number of PNGs after Phase 1 (sanity check). |
| Other fields | | | Mirror capability-scout's. |

## Phase transitions (forward-only, single-step)

```
init
  → discover-running    (preflight + Phase 1 dispatch — 4 agents in ONE turn)
  → discover-complete   (all briefs + screenshots returned)
  → synthesize-running
  → synthesize-complete
  → challenge-running
  → challenge-complete
  → prioritize-running
  → complete            (final-report.md; offer /milestone-pipeline)
```

`checkpoint.py` refuses backward and skipped transitions.
