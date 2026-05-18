---
description: Run the canonical 4-phase parallel-agent pipeline that visually evaluates the running GUI (with screenshot evidence), researches modern desktop scientific tool patterns, surveys active PySide6/PyVista landscape, adversarially challenges every candidate against architectural + a11y locks, and produces a RICE-ranked candidate report ready to feed /milestone-pipeline. Replaces the deprecated ui-upgrade-scout single-shot agent pattern. NEVER auto-invokes downstream pipelines.
argument-hint: <ID> [--brief "scope statement"] [--lean | --deep]
---

# /frontend-uplift

Run the canonical 4-phase pipeline:
**Discover → Synthesize → Challenge → Prioritize**

Usage:

```
/frontend-uplift                          # ask for ID
/frontend-uplift <id>
/frontend-uplift <id> --brief "..."
/frontend-uplift <id> --lean              # 3-agent fast scan (skip inspiration)
/frontend-uplift <id> --deep              # 4 agents; bump critic to opus
/frontend-uplift <id>                     # resume from current state
```

`<id>` is a free-form slug. Typical convention: `<YYYY-MM-DD>-<scope>`
or `<release>-<surface>` (e.g. `2026-q3-toolbar`, `2026-05-18-diag-panel`).

The pipeline answers: **"Where can the frontend become more attractive,
sleek, and modern, measured against 2024-2026 SOTA, without violating
the project's architectural + a11y locks?"** It does NOT produce code;
it produces a ranked candidate report ready to feed `/milestone-pipeline`.

---

## Architectural rules (non-negotiable)

1. **Preflight first.** `ensure-gui-bootable.sh` MUST pass before
   Phase 1 dispatches. A visual-evidence pipeline can't run against
   a broken GUI.
2. **Phase 1 dispatch happens in ONE assistant turn.** All 4 (or 3
   in --lean) agents fire in parallel.
3. **Phases 2 and 4 run in the main session**, NOT as sub-agents.
4. **Synthesizer and challenger are distinct roles.** Same separation
   as `/capability-scout`.
5. **NEVER auto-invoke `/milestone-pipeline`.** Phase 4 OFFERS;
   the user types the next command if they want to proceed.

---

## Step 0 — Initialize state

```bash
.claude/scripts/frontend-uplift/init-frontend-uplift.sh <ID> [--brief "..."] [--lean | --deep]
```

Idempotent. Also creates per-agent project memory dirs.

```bash
.claude/scripts/frontend-uplift/status.sh <ID>
```

Inspect before running each phase.

---

## Step 1 — Discover (parallel, 4 agents in ONE turn)

Read `.claude/references/frontend-uplift/phase-1-discover.md` once at
phase start.

### 1a — Preflight (REQUIRED)

```bash
.claude/scripts/frontend-uplift/ensure-gui-bootable.sh
```

If non-zero, surface the recovery hint and HALT. Do not advance the
state machine until preflight is green.

### 1b — Set mode + advance

```bash
.claude/scripts/frontend-uplift/checkpoint.py <ID> --set discover_mode='"standard"'
.claude/scripts/frontend-uplift/checkpoint.py <ID> discover-running
```

### 1c — Dispatch all agents in ONE assistant turn

ONE turn containing N parallel `Agent` tool blocks. Each uses:
- `subagent_type: general-purpose`
- `model: sonnet` (default; `--deep` bumps the critic to `opus`)
- `isolation: worktree`
- Prompt verbatim from
  `.claude/references/frontend-uplift/agent-prompts.md` §1-§4 with
  placeholders substituted

Brief paths:
- `.claude/notes/frontend-uplifts/<ID>/discover-briefs/visual-brief.md`
- `.claude/notes/frontend-uplifts/<ID>/discover-briefs/library-brief.md`
- `.claude/notes/frontend-uplifts/<ID>/discover-briefs/inspiration-brief.md`
- `.claude/notes/frontend-uplifts/<ID>/discover-briefs/current-state-critic-brief.md`

`{SCREENSHOTS_DIR}` substitutes to:
- `.claude/notes/frontend-uplifts/<ID>/screenshots`

Record dispatch:

```bash
for agent in visual library inspiration current-state-critic; do
  .claude/scripts/frontend-uplift/checkpoint.py <ID> --append agents_dispatched="\"$agent\""
done
```

`--lean` mode dispatches only `visual`, `library`,
`current-state-critic` (skip inspiration).

### 1d — Brief return

As each agent returns:

```bash
.claude/scripts/frontend-uplift/checkpoint.py <ID> --append agents_returned='"<agent>"'
.claude/scripts/frontend-uplift/checkpoint.py <ID> --append discover_briefs='"<absolute path>"'
```

When all returned:

```bash
ss_count=$(ls .claude/notes/frontend-uplifts/<ID>/screenshots/*.png 2>/dev/null | wc -l)
.claude/scripts/frontend-uplift/checkpoint.py <ID> --set screenshot_count=$ss_count
.claude/scripts/frontend-uplift/checkpoint.py <ID> discover-complete
```

---

## Step 2 — Synthesize (main session)

Read `.claude/references/frontend-uplift/phase-2-synthesize.md` once
at phase start.

```bash
.claude/scripts/frontend-uplift/checkpoint.py <ID> synthesize-running
```

Read EVERY brief end-to-end. Look at every screenshot (multimodal
vision). Build the catalog at:

```
.claude/notes/frontend-uplifts/<ID>/artifacts/synthesis.md
```

Use the 10-category UI taxonomy + T-shirt sizing + `FU-<ID>-NNN`
numbering. Tag foundationals and wire-ups. Honor the
current-state-critic's reject list.

```bash
.claude/scripts/frontend-uplift/checkpoint.py <ID> --set synthesis_path='".claude/notes/frontend-uplifts/<ID>/artifacts/synthesis.md"'
.claude/scripts/frontend-uplift/checkpoint.py <ID> --set candidate_count=<N>
.claude/scripts/frontend-uplift/checkpoint.py <ID> synthesize-complete
```

---

## Step 3 — Challenge (single sub-agent)

Read `.claude/references/frontend-uplift/phase-3-challenge.md` once at
phase start.

```bash
.claude/scripts/frontend-uplift/checkpoint.py <ID> challenge-running
```

Single `Agent` call, `subagent_type: general-purpose`, sonnet,
`isolation: worktree`. Prompt verbatim from
`agent-prompts.md` §5 with `{ID}` + `{SYNTHESIS_PATH}` substituted.

Challenger walks the 10-axis checklist (native-only, worker-thread,
token discipline, renderer pacing, hi-DPI, a11y, no GUI-test
regression, additive, already-shipped, keyboard-equivalent) and
writes to:

```
.claude/notes/frontend-uplifts/<ID>/artifacts/challenge.md
```

Record:

```bash
.claude/scripts/frontend-uplift/checkpoint.py <ID> --set challenge_path='"..."'
.claude/scripts/frontend-uplift/checkpoint.py <ID> --set challenge_finding_counts='{"critical":N,"high":N,"medium":N,"low":N}'
.claude/scripts/frontend-uplift/checkpoint.py <ID> challenge-complete
```

---

## Step 4 — Prioritize (main session)

Read `.claude/references/frontend-uplift/phase-4-prioritize.md` once
at phase start.

```bash
.claude/scripts/frontend-uplift/checkpoint.py <ID> prioritize-running
```

Run in the main session. RICE-light with the same formula as
`/capability-scout`. Foundational ×1.3, wire-up ×1.2. BLOCKER
un-mitigated → DROP; BLOCKER mitigated → ×0.5; MAJOR → ×0.75.

Write `final-report.md` with top-5 RICE breakdowns + sequencing
respecting visual-surface dependencies + `/milestone-pipeline`
handoff OFFER.

**Do NOT auto-invoke `/milestone-pipeline`.**

Record:

```bash
.claude/scripts/frontend-uplift/checkpoint.py <ID> --set final_report_path='"..."'
.claude/scripts/frontend-uplift/checkpoint.py <ID> --set ranked_candidates='[...]'
.claude/scripts/frontend-uplift/checkpoint.py <ID> complete
```

Print 5-line summary.

---

## State machine

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

`checkpoint.py` enforces forward-only single-step transitions.

---

## Common rationalizations (anti-pattern guard)

| Tempting belief | Reality |
|---|---|
| "Skip preflight, the GUI's been working." | Preflight is cheap. A broken GUI mid-pipeline wastes 30+ minutes. |
| "Skip visual-scout, the code review tells me what's wrong." | The visual evidence is load-bearing — most a11y / hi-DPI / contrast issues only show in pixels. |
| "Skip current-state-critic." | Token leaks and dead code only show from the inside. |
| "Synthesize from TL;DRs only." | Triangulation lives in cross-brief specifics. |
| "Skip challenger." | Self-critique misses ~70% of objections. |
| "Auto-invoke `/milestone-pipeline`." | NEVER. |

## Don'ts

- Don't dispatch without preflight.
- Don't run Phase 4 as a sub-agent.
- Don't let the synthesizer write the challenge.
- Don't auto-invoke `/milestone-pipeline`.
- Don't manufacture candidates.
- Don't bypass `init-frontend-uplift.sh`.
- Don't `git push` at any phase.

## Sub-agent memory

All `frontend-uplift-*` agents have `memory: project`. Memory
accumulates under `.claude/agent-memory/frontend-uplift-<role>/`
across runs.
