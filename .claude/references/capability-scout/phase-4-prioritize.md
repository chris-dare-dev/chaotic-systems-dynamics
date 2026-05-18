# Phase 4 — Prioritize

## Purpose

Main session reads `synthesis.md` + `challenge.md`, applies RICE-light
scoring with challenger penalties and foundational bonuses, writes
the final ranked candidate report to `artifacts/final-report.md`.

**Runs in the main session, NOT a sub-agent.** The user reviews the
final report directly, so it lives in the main thread.

## Inputs

- `artifacts/synthesis.md` (from Phase 2).
- `artifacts/challenge.md` (from Phase 3).

## Output

`.claude/notes/capability-scouts/<ID>/artifacts/final-report.md`.

## RICE-light formula

For each candidate `CSC-<ID>-NNN`:

```
RICE = Reach × Impact × Confidence / Effort
```

with these scales:

| Factor | Values | How to pick |
|---|---|---|
| **Reach** | 1 / 3 / 10 | 1 = niche (one system / one user workflow); 3 = many systems or workflows; 10 = touches the whole project. |
| **Impact** | 0.5 / 1 / 3 | 0.5 = polish; 1 = meaningful capability; 3 = unlocks a class of workflows previously impossible. |
| **Confidence** | 0.3 / 0.5 / 0.8 / 1.0 | By triangulation strength: 1 brief / 2 briefs / 3 briefs / 4 briefs. |
| **Effort** | 0.25 / 1 / 3 / 8 | T-shirt sizing: XS / S / M / L → person-days. |

### Penalties

After computing the raw RICE:

| Challenge severity | Action |
|---|---|
| BLOCKER (un-mitigated) | DROP — candidate is not in the final ranking |
| BLOCKER (with mitigation proposed in challenge) | RICE × 0.5 |
| MAJOR | RICE × 0.75 |
| MINOR | no change |
| NONE | no change |

### Bonuses

| Tag | Action |
|---|---|
| Foundational (≥ 2 other candidates depend on it) | RICE × 1.3 |
| Wire-up candidate (already implemented, just needs UI/docs) | RICE × 1.2 |

A candidate can have multiple bonuses; multiply them all.

## Final-report structure

```markdown
# Final report — capability-scout <ID>

## TL;DR
(5 sentences: top 5 ranked candidates, total candidate count, the
"obvious next ship", any cross-cutting themes.)

## Ranking

| Rank | ID | Title | Category | T-shirt | RICE | Notes |
|---|---|---|---|---|---|---|
| 1 | CSC-...-007 | ... | new-diagnostic | S | 24.0 | foundational + wire-up |
| 2 | CSC-...-003 | ... | new-system | S | 18.0 | triangulated 4/4 |
| ... | | | | | | |

## Top 5 — detail

For each of the top 5:

### Rank 1 — CSC-<ID>-NNN — <Title>

**RICE breakdown:**
- Reach: 10 (whole project)
- Impact: 3 (unlocks new workflow)
- Confidence: 1.0 (4-brief triangulation)
- Effort: 1 (S)
- Penalties: none
- Bonuses: foundational ×1.3, wire-up ×1.2
- **Score:** 30 × 1.3 × 1.2 = 46.8

**Why this is #1:**
(2-3 sentences synthesizing the case.)

**Challenge findings to address before shipping:**
(Bullet list of MINOR / MAJOR concerns from the challenge, with the
proposed mitigation.)

**Implementation pointer for `/milestone-pipeline`:**
(One paragraph: which file paths the implementer would touch, what
the observable success metric is, which test files to add.)

## Sequencing recommendation

(Bullet list, 5-8 items: suggested order to ship the top N candidates,
respecting foundational dependencies. Format:
`1. CSC-...-NNN — <Title> (foundational; ships first)`
`2. CSC-...-NNN — <Title> (depends on #1)`)

## Dropped candidates

(Anything from the synthesis with an un-mitigated BLOCKER. One line
per item with the BLOCKER axis cited.)

## Handoff

The top-ranked candidate is ready for `/milestone-pipeline <ID>`.
Run that command to ship it end-to-end.

**The pipeline does NOT auto-invoke `/milestone-pipeline`.** That's a
manual decision by the user reviewing this report.
```

## Hard rules

- **Rank every candidate that wasn't dropped.** No skipping.
- **Cite the RICE breakdown for each top-5 candidate.** No mystery
  numbers.
- **Drop un-mitigated BLOCKERs.** They aren't in the ranking;
  they're in "Dropped candidates" with the BLOCKER axis cited.
- **Offer the `/milestone-pipeline` handoff, but NEVER auto-invoke.**
  This is the canonical anti-pattern; printing
  "I will now invoke /milestone-pipeline ..." is forbidden.
- **Sequencing must respect foundational dependencies.** If
  candidate B depends on A, B cannot ship before A.

## Anti-patterns

- **Auto-invoking the next pipeline.** Forbidden. Always offer-and-wait.
- **Re-ranking without showing the math.** RICE breakdowns must be
  visible.
- **Quietly dropping non-BLOCKER candidates.** Even MINOR-only
  candidates rank and appear in the table.
- **Sandbagging your own confidence.** A 4-brief candidate gets
  Confidence = 1.0, not 0.8.
- **Ignoring the foundational bonus.** A 3-brief candidate that's
  foundational and wire-up can beat a 4-brief candidate that's
  greenfield. Show the math; let the numbers speak.

## After writing

1. Set `final_report_path` and `ranked_candidates` via
   `checkpoint.py --set`.
2. Advance to `complete`.
3. Print a 5-line summary to the user with the top 3 candidates +
   the `/milestone-pipeline <ID>` invocation they can run.
