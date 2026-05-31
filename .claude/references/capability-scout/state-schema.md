# State schema — capability-scout

## Path layout

```
.claude/notes/capability-scouts/<ID>/
├── state.json                    ← the canonical state (atomically written)
├── survey-briefs/                ← Phase 1 output
│   ├── competitive-brief.md
│   ├── academic-brief.md
│   ├── oss-brief.md
│   └── internal-adversary-brief.md
└── artifacts/
    ├── synthesis.md              ← Phase 2 output
    ├── challenge.md              ← Phase 3 output
    └── final-report.md           ← Phase 4 output
```

`<ID>` is a free-form slug — typical convention `YYYY-MM-DD-<scope>` (e.g.
`2026-05-18-diagnostics`, `2026-q2-perf`).

The whole tree is gitignored — pipeline artifacts are run-local. The
`.claude/notes/` directory pattern is established by `checkpoint.py init`.

## state.json schema

```json
{
  "id": "2026-05-18-diagnostics",
  "kind": "capability-scout",
  "created_at": "2026-05-18T18:00:00Z",
  "updated_at": "2026-05-18T18:42:00Z",
  "phase": "synthesize-complete",
  "phase_history": [
    {"phase": "init",                "at": "2026-05-18T18:00:00Z"},
    {"phase": "survey-running",      "at": "2026-05-18T18:01:00Z"},
    {"phase": "survey-complete",     "at": "2026-05-18T18:25:00Z"},
    {"phase": "synthesize-running",  "at": "2026-05-18T18:30:00Z"},
    {"phase": "synthesize-complete", "at": "2026-05-18T18:42:00Z"}
  ],
  "capability_scout_brief": "focus on diagnostics and Hamiltonian flow analyzers",
  "survey_mode": "standard",
  "agents_dispatched": ["competitive", "academic", "oss", "internal-adversary"],
  "agents_returned":   ["competitive", "academic", "oss", "internal-adversary"],
  "survey_briefs": [
    ".claude/notes/capability-scouts/2026-05-18-diagnostics/survey-briefs/competitive-brief.md",
    ".claude/notes/capability-scouts/2026-05-18-diagnostics/survey-briefs/academic-brief.md",
    ".claude/notes/capability-scouts/2026-05-18-diagnostics/survey-briefs/oss-brief.md",
    ".claude/notes/capability-scouts/2026-05-18-diagnostics/survey-briefs/internal-adversary-brief.md"
  ],
  "synthesis_path": ".claude/notes/capability-scouts/2026-05-18-diagnostics/artifacts/synthesis.md",
  "candidate_count": 14,
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
| `kind` | str | init | Always `"capability-scout"`. Disambiguates from other pipelines sharing `.claude/notes/`. |
| `phase` | str | `checkpoint.py <ID> <new-phase>` | Forward-only. |
| `phase_history` | list[{phase, at}] | every advance | Append-only timeline. |
| `capability_scout_brief` | str | init `--brief` | Free-form user scope; read by every Phase 1 agent. |
| `survey_mode` | str | init `--lean/--deep` | `"standard"` (4 agents) / `"lean"` (3 agents) / `"deep"` (4 agents, opus-bumped adversary). |
| `agents_dispatched` | list[str] | main session `--append` | Phase 1 agents fired in the dispatch turn. |
| `agents_returned` | list[str] | main session `--append` | Subset of dispatched that have produced a brief. |
| `survey_briefs` | list[str] | main session `--append` | Paths to written briefs. |
| `synthesis_path` | str \| null | main session `--set` | Path to `artifacts/synthesis.md`. |
| `candidate_count` | int | main session `--set` | Number of unique candidates surfaced by synthesis. |
| `challenge_path` | str \| null | main session `--set` | Path to `artifacts/challenge.md`. |
| `challenge_finding_counts` | dict | main session `--set` | `{critical, high, medium, low}` counts from the challenger. |
| `final_report_path` | str \| null | main session `--set` | Path to `artifacts/final-report.md`. |
| `ranked_candidates` | list[dict] | main session `--set` | Ordered RICE-ranked list. Each entry: `{id, title, rice_score, severity_after_challenge}`. |

## Phase transitions (forward-only, single-step)

```
init
  → survey-running       (Phase 1 dispatch — 4 agents in ONE turn)
  → survey-complete      (all briefs returned)
  → synthesize-running   (main session reads briefs)
  → synthesize-complete  (synthesis.md written)
  → challenge-running    (challenger dispatched)
  → challenge-complete   (challenge.md written)
  → prioritize-running   (main session ranks)
  → complete             (final-report.md written; offer /milestone-pipeline)
```

`checkpoint.py` refuses any transition that's backward or skips a phase.
This is the resume-safety guarantee — if compaction strikes mid-run, the
next session can `checkpoint.py status <ID>` and pick up exactly where it left off.
