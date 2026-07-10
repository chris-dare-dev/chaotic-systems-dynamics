# Phase 4 — Prioritize

## Purpose

Main session reads `synthesis.md` + `challenge.md`, applies RICE-light
ranking with challenger penalties and foundational + wire-up bonuses,
writes `artifacts/final-report.md`.

**Runs in the main session, NOT a sub-agent.**

## Inputs

- `artifacts/synthesis.md` (from Phase 2).
- `artifacts/challenge.md` (from Phase 3).

## Output

`.claude/notes/frontend-uplifts/<ID>/artifacts/final-report.md`.

## Portfolio lanes (assign BEFORE ranking — RICE is only valid WITHIN a lane)

Cross-lane RICE mathematically buries structural design under XS polish (a ×1.3 bonus cannot beat a
32× effort ratio), so assign every non-dropped candidate to EXACTLY ONE lane, then compute
RICE-light only within each lane and rank within lanes only. Present lanes in this order:

1. **`a11y-safety-debt`** — MANDATORY lane, listed FIRST, NEVER ranked away. Every WCAG / focus /
   contrast / keyboard / reduced-motion finding lands here (e.g. missing `setAccessibleName`
   coverage, the light-theme stub with no dark/light parity, any reduced-motion gap). These ship on
   their own merit, not against RICE.
2. **`signature-direction`** — `[DIRECTION-DEFINING]` candidates that realize the adopted thesis.
3. **`foundations`** — shared tokens / helpers others depend on (spacing scale, `theme.PALETTE`
   wire-ups).
4. **`workflow`** — new affordances that unlock a task (command-palette entries, panel actions).
5. **`polish`** — everything else. A top-5 that is all `polish` MUST say so explicitly.

## RICE-light formula

Same as capability-scout's:

```
RICE = Reach × Impact × Confidence / Effort
```

| Factor | Values | How to pick |
|---|---|---|
| **Reach** | 1 / 3 / 10 | 1 = one panel; 3 = several surfaces; 10 = global theme / spacing scale touching every widget. |
| **Impact** | 0.5 / 1 / 3 | 0.5 = polish; 1 = meaningful affordance; 3 = unlocks a new workflow (e.g. "command palette" — first-class new UX). |
| **Confidence** | 0.3 / 0.5 / 0.8 / 1.0 | 1 brief / 2 / 3 / 4. |
| **Effort** | 0.25 / 1 / 3 / 8 | XS / S / M / L. |

### Penalties

| Challenge severity | Action |
|---|---|
| BLOCKER (un-mitigated) | DROP |
| BLOCKER (with mitigation) | × 0.5 |
| MAJOR | × 0.75 |
| MINOR | no change |
| NONE | no change |

### Bonuses

| Tag | Action |
|---|---|
| Foundational | × 1.3 |
| Wire-up (capability exists in code, only application missing) | × 1.2 |

A candidate can stack both bonuses.

## Final-report structure

Identical to capability-scout's, with these additions:

- **Top-5 detail** sections include the relevant screenshot path
  inline so the reader can see the evidence without leaving the
  report.
- **Sequencing recommendation** explicitly notes which candidates
  share visual surfaces (so sequencing avoids merge conflicts).
- The handoff line offers `/milestone-pipeline <ID>` for shipping
  the top candidate — same as capability-scout. **NEVER auto-invoke.**

## Hard rules

- Rank every non-dropped candidate.
- Cite RICE breakdowns for the top 5.
- Drop un-mitigated BLOCKERs (cite the axis).
- OFFER `/milestone-pipeline`; do NOT auto-invoke.
- Sequencing respects foundational + visual-surface dependencies.

## After writing

```bash
.claude/scripts/frontend-uplift/checkpoint.py <ID> --set final_report_path='"..."'
.claude/scripts/frontend-uplift/checkpoint.py <ID> --set ranked_candidates='[...]'
.claude/scripts/frontend-uplift/checkpoint.py <ID> complete
```

Print 5-line summary with:
1. Top 3 candidate IDs + titles + RICE.
2. Total candidate count + severity distribution.
3. Foundational chain summary.
4. Path to `final-report.md`.
5. Suggested `/milestone-pipeline <ID>` invocation (not auto-run).
