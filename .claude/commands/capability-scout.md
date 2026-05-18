---
description: Run the canonical 4-phase parallel-agent pipeline that catalogs current capabilities, surveys 2024-2026 state-of-the-art, adversarially challenges every candidate, and produces a RICE-ranked candidate report ready to feed /milestone-pipeline. Replaces the deprecated single-shot capability-research-scout agent. NEVER auto-invokes downstream pipelines — offers and waits.
argument-hint: <ID> [--brief "scope statement"] [--lean | --deep]
---

# /capability-scout

Run the canonical 4-phase pipeline:
**Survey → Synthesize → Challenge → Prioritize**

Usage:

```
/capability-scout                          # ask for ID
/capability-scout <id>
/capability-scout <id> --brief "..."
/capability-scout <id> --lean              # 3-agent fast scan (skip academic)
/capability-scout <id> --deep              # 4 agents; bump adversary to opus
/capability-scout <id>                     # resume from current state
```

`<id>` is a free-form slug. If no id given, STOP and ask. Typical
convention: date-tagged scope (`2026-q3-diagnostics`,
`2026-05-18-perf`).

The pipeline answers: **"What capability should we build next given
2024-2026 SOTA?"**. It does NOT produce code; it produces a ranked
candidate report ready to feed `/milestone-pipeline`.

---

## Architectural rules (non-negotiable)

1. **Phase 1 dispatch happens in ONE assistant turn** containing all N
   parallel `Agent` tool blocks. Sequential dispatch defeats the
   parallelism.
2. **Phases 2 and 4 run in the main session**, NOT as sub-agents.
   Phase 2 needs all briefs in working memory simultaneously; Phase 4
   is the user-review surface.
3. **The synthesizer (Phase 2) does NOT also write the challenge
   (Phase 3).** Distinct roles. Self-critique misses ~70% of real
   objections.
4. **NEVER auto-invoke `/milestone-pipeline` at completion.** Phase 4
   OFFERS the handoff; the user types the next command if they want
   to proceed.

---

## Step 0 — Initialize state

```bash
.claude/scripts/capability-scout/init-capability-scout.sh <ID> [--brief "..."] [--lean | --deep]
```

Idempotent — re-running on the same ID resumes from the current phase.
The script also creates per-agent project memory dirs under
`.claude/agent-memory/capability-scout-*/`.

```bash
.claude/scripts/capability-scout/status.sh <ID>
```

Inspect current phase + history before deciding which step to run.

---

## Step 1 — Survey (parallel, 4 agents in ONE turn)

Read `.claude/references/capability-scout/phase-1-survey.md` once at
phase start.

### 1a — Set mode + advance

```bash
.claude/scripts/capability-scout/checkpoint.py <ID> --set survey_mode='"standard"'
.claude/scripts/capability-scout/checkpoint.py <ID> survey-running
```

(Skip the `--set` line if the user passed `--lean` or `--deep` at
init.)

### 1b — Dispatch all agents in ONE assistant turn

In ONE turn containing N `Agent` tool blocks. Each uses:
- `subagent_type: general-purpose` (the harness's agent list locks at
  session start; project-local `capability-scout-*` agents may not be
  visible mid-session — the workaround is to dispatch via
  general-purpose and embed the brief via "act as the
  capability-scout-<role> agent defined at
  .claude/agents/capability-scout-<role>.md — read that file first").
- `model: sonnet` (default; `--deep` mode bumps the adversary to
  `opus`).
- `isolation: worktree`.
- Prompt verbatim from
  `.claude/references/capability-scout/agent-prompts.md` §1-§4 with
  `{ID}`, `{BRIEF}`, `{BRIEF_PATH}` substituted.

Brief paths follow this pattern:
- `.claude/notes/capability-scouts/<ID>/survey-briefs/competitive-brief.md`
- `.claude/notes/capability-scouts/<ID>/survey-briefs/academic-brief.md`
- `.claude/notes/capability-scouts/<ID>/survey-briefs/oss-brief.md`
- `.claude/notes/capability-scouts/<ID>/survey-briefs/internal-adversary-brief.md`

After dispatching:

```bash
for agent in competitive academic oss internal-adversary; do
  .claude/scripts/capability-scout/checkpoint.py <ID> --append agents_dispatched="\"$agent\""
done
```

(For `--lean` mode: dispatch only `competitive`, `oss`,
`internal-adversary`.)

### 1c — Brief return

As each agent returns its message:

```bash
.claude/scripts/capability-scout/checkpoint.py <ID> --append agents_returned='"<agent-name>"'
.claude/scripts/capability-scout/checkpoint.py <ID> --append survey_briefs='"<absolute brief path>"'
```

When all dispatched agents have returned (set equality):

```bash
.claude/scripts/capability-scout/checkpoint.py <ID> survey-complete
```

---

## Step 2 — Synthesize (main session)

Read `.claude/references/capability-scout/phase-2-synthesize.md` once
at phase start.

```bash
.claude/scripts/capability-scout/checkpoint.py <ID> synthesize-running
```

Read EVERY brief end-to-end. Build the unified candidate catalog at:

```
.claude/notes/capability-scouts/<ID>/artifacts/synthesis.md
```

Use the fixed taxonomy (new-system / new-integrator / new-diagnostic /
performance / visualization / workflow / educational), T-shirt sizing
(XS/S/M/L), candidate IDs `CSC-<ID>-NNN`. Dedupe. Surface foundational
candidates explicitly.

```bash
.claude/scripts/capability-scout/checkpoint.py <ID> --set synthesis_path='".claude/notes/capability-scouts/<ID>/artifacts/synthesis.md"'
.claude/scripts/capability-scout/checkpoint.py <ID> --set candidate_count=<N>
.claude/scripts/capability-scout/checkpoint.py <ID> synthesize-complete
```

---

## Step 3 — Challenge (single sub-agent)

Read `.claude/references/capability-scout/phase-3-challenge.md` once
at phase start.

```bash
.claude/scripts/capability-scout/checkpoint.py <ID> challenge-running
```

Single `Agent` call with `subagent_type: general-purpose`, sonnet,
`isolation: worktree`. Prompt verbatim from
`.claude/references/capability-scout/agent-prompts.md` §5 with `{ID}`
and `{SYNTHESIS_PATH}` substituted.

The challenger walks the 10-axis checklist for every candidate and
writes to:

```
.claude/notes/capability-scouts/<ID>/artifacts/challenge.md
```

Severity rubric: BLOCKER → critical, MAJOR → high, MINOR → medium,
NONE → low.

Record:

```bash
.claude/scripts/capability-scout/checkpoint.py <ID> --set challenge_path='".claude/notes/capability-scouts/<ID>/artifacts/challenge.md"'
.claude/scripts/capability-scout/checkpoint.py <ID> --set challenge_finding_counts='{"critical":N,"high":N,"medium":N,"low":N}'
.claude/scripts/capability-scout/checkpoint.py <ID> challenge-complete
```

---

## Step 4 — Prioritize (main session)

Read `.claude/references/capability-scout/phase-4-prioritize.md` once
at phase start.

```bash
.claude/scripts/capability-scout/checkpoint.py <ID> prioritize-running
```

Run in the **main session**. RICE-light rank:

**RICE = Reach × Impact × Confidence / Effort**

- Reach: 1 / 3 / 10
- Impact: 0.5 / 1 / 3
- Confidence: 0.3 / 0.5 / 0.8 / 1.0 (by triangulation: 1 / 2 / 3 / 4 briefs)
- Effort: 0.25 / 1 / 3 / 8 (XS / S / M / L)

Penalties: DROP on un-mitigated BLOCKER; ×0.5 on mitigated BLOCKER;
×0.75 on MAJOR. Bonuses: ×1.3 foundational, ×1.2 wire-up.

Write `final-report.md` with: top-5 RICE breakdowns, full ranking
table, sequencing recommendation respecting foundational deps,
dropped candidates with cited BLOCKER axis, and a `/milestone-pipeline`
handoff OFFER.

**Do NOT auto-invoke `/milestone-pipeline`.** Print the suggested
invocation; let the user decide.

Record:

```bash
.claude/scripts/capability-scout/checkpoint.py <ID> --set final_report_path='".claude/notes/capability-scouts/<ID>/artifacts/final-report.md"'
.claude/scripts/capability-scout/checkpoint.py <ID> --set ranked_candidates='[...]'
.claude/scripts/capability-scout/checkpoint.py <ID> complete
```

Print 5-line final summary with:
1. Top 3 candidate IDs + titles + RICE.
2. Total candidate count + BLOCKER/MAJOR/MINOR/NONE distribution.
3. Foundational dependency chain summary.
4. Path to `final-report.md`.
5. Suggested `/milestone-pipeline <ID>` invocation (not auto-run).

---

## State machine

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

`checkpoint.py` enforces forward-only single-step transitions. If the
session compacts mid-run, `status.sh <ID>` shows where to resume.

---

## Common rationalizations (anti-pattern guard)

| Tempting belief | Reality |
|---|---|
| "Skip the internal-adversary." | It's the single highest-ROI agent. D1 came from the internal-adversary lens. |
| "Fire agents one at a time so I can react." | Sequential dispatch doubles wall-clock and kills diversity. ONE turn. |
| "Synthesize from TL;DRs only." | Triangulation lives in cross-brief specifics. |
| "Skip the challenger — synthesis is good enough." | Synthesis is biased toward aspirational candidates. ~70% of real objections only surface under a separate adversarial pass. |
| "Auto-invoke `/milestone-pipeline`." | NEVER. The whole point of the pipeline is to give the user a ranked report to review. |
| "Inflate severity to surface more findings." | Calibrated runs see 30-60% NONE on challenger axes. |

## Don'ts

- Don't run Phase 4 as a sub-agent.
- Don't let the synthesizer write the challenge.
- Don't auto-invoke `/milestone-pipeline` or any downstream pipeline.
- Don't manufacture candidates (every entry must trace to ≥ 1 brief).
- Don't bypass `init-capability-scout.sh`.
- Don't `git push` at any phase (artifacts are gitignored).

## Sub-agent memory

All `capability-scout-*` agents have `memory: project`. Memory
accumulates under `.claude/agent-memory/capability-scout-<role>/` across
runs. Do NOT clear or overwrite — agents read their lessons file at
the start of every run.
