---
description: Run the canonical 4-phase parallel-agent pipeline (Discover → Synthesize → Challenge → Prioritize) that visually evaluates the running native PySide6 GUI (screenshot evidence), establishes an ART-DIRECTION THESIS before ranking (visual thesis + 3 divergent directions + BAN-1..15 list + surface map, per frontend-design-language.md + the house overlay design-system.md), surveys modern desktop scientific-tool patterns + active PySide6/PyVista libraries, adversarially challenges every candidate on an 11-axis checklist (native locks + a11y + distinctiveness/anti-template), and produces a RICE-ranked report organized in portfolio lanes (a11y-safety-debt mandatory first). SURFACE-AWARE and NATIVE — default --surface tool (S-2); experiential web motion is BLOCKED and the experiential-scout is NOT dispatched. Ships nothing; NEVER auto-invokes downstream.
argument-hint: <ID> [--brief "scope"] [--mode lean|standard|deep|experiential] [--surface tool|mixed|auto] [--workflow] [--resume]
---

# /frontend-uplift

Run the canonical 4-phase pipeline:
**Discover → Synthesize → Challenge → Prioritize**

```
/frontend-uplift                                   # ask for ID
/frontend-uplift <id>
/frontend-uplift <id> --brief "..."
/frontend-uplift <id> --mode lean                  # 4-agent fast scan (drops inspiration)
/frontend-uplift <id> --mode deep                  # 5 agents; bump current-state-critic
/frontend-uplift <id> --workflow                   # opt-in Gen-2 background orchestration
/frontend-uplift <id> --resume                     # resume from current state
```

`<id>` is a free-form slug. Convention: `<YYYY-MM-DD>-<scope>` or `<release>-<surface>`
(e.g. `2026-q3-toolbar`, `2026-05-18-diag-panel`).

The pipeline answers: **"Where can the frontend become more attractive, sleek, and modern —
with a real ART-DIRECTION THESIS (not undirected polish) — without violating the project's
native / architectural / a11y locks?"** It does NOT produce code; it produces a ranked candidate
report ready to feed `/milestone-pipeline`.

> **Sibling skill.** `/frontend-design` BUILDS or RESTYLES a surface in-session (thesis →
> implement → self-score). `/frontend-uplift` (this command) produces a ranked DISCOVERY report
> and ships nothing. Use the skill to change pixels; use this to decide which pixels to change.

---

## Standing defaults (the doctrine this pipeline enforces)

**Art-direction thesis, before ranking.** The `frontend-uplift-art-direction-scout` is dispatched
in **EVERY mode** (lean included). It reads the flat canon
(`.claude/references/frontend-design-language.md`) AND this repo's house overlay
(`.claude/references/frontend-uplift/design-system.md`), then produces a visual thesis + 3
divergent directions + the active BAN-1..15 list + a surface map. Synthesis OPENS with that frame.
**Polish without direction is the failure this pipeline exists to prevent.**

**Motion-jobs test (no quota).** Every motion candidate must name the job it serves —
orientation / causality / feedback / continuity (`.claude/references/frontend-uplift-motion-vocabulary.md`
§0). No job, no motion; there is no quota to fill. Native/incumbent facility first
(`QPropertyAnimation`, the existing `QTimer` render loop); a new engine only when a named job
needs one.

**Surface awareness — this repo is S-2, NATIVE Qt.** Default `--surface tool`. Experiential
motion (parallax / scroll-scrub / WebGL / cursor theater) is **BLOCKED**; the
`frontend-uplift-experiential-scout` is **NOT dispatched** — reverse-engineering award-winning
WEBSITES has near-zero transfer to a native Qt desktop app (no DOM, no scroll surface, no WebGL
hero). Say this explicitly rather than silently dropping it.

**Translate, don't delete (web → native).** The canon's substance applies fully; its web
mechanics translate (see `design-system.md` §9.5):

| Canon (web) | This repo (native Qt) |
|---|---|
| design tokens (CSS vars) | `theme.PALETTE` + `assets/dark.qss` + `_apply_base_style` `QPalette` (Fusion pinned) |
| motion (`@media prefers-reduced-motion`) | `QPropertyAnimation` gated by a **`QSettings` reduced-motion toggle** |
| perf (bundle KB) | startup construct time + 16 ms / 60 Hz per-frame budget; heavy work on a `QThread` |
| a11y (ARIA) | focus/tab order, **`setAccessibleName`**, `.qss` contrast, `QShortcut` — not ARIA |
| **INERT axes** | bundle KB · React/RSC · mobile/touch · experiential scroll/WebGL — mark inert with a one-line reason, never a manufactured finding |

---

## Architectural rules (non-negotiable)

1. **Preflight first.** `ensure_gui_bootable.py` (a `.py` — run with `python3`, never `bash`) MUST
   pass before Phase 1 dispatches. A visual-evidence pipeline can't run against a broken GUI.
2. **Art-direction fires in every mode.** Never drop it — not in `lean`, not to save time.
3. **Phase 1 dispatch happens in ONE assistant turn.** All agents fire in parallel.
4. **Phases 2 and 4 run in the main session** (Gen-1 path), NOT as sub-agents.
5. **Synthesizer and challenger are distinct roles.** Same separation as `/capability-scout`.
6. **NEVER auto-invoke `/milestone-pipeline`, `/roadmap`, or `/spike`.** Phase 4 OFFERS; the user
   types the next command. This pipeline ships no code.

---

## Arguments

Parse `$ARGUMENTS` as `<ID> [--brief "..."] [--mode lean|standard|deep|experiential]
[--surface tool|mixed|auto] [--workflow] [--resume]`.

- `<ID>` — required. If empty, STOP: "What's the scope id?"
- `--brief "..."` — free-form scope passed to scouts as `{BRIEF}`.
- `--mode` — default `standard`. `lean` drops inspiration; `deep` bumps the current-state-critic
  one tier; `experiential` is offered for parity but the experiential lens is INERT on S-2 Qt
  (the report says so). Legacy `--lean` / `--deep` are accepted as aliases.
- `--surface` — default `tool` (S-2). `mixed`/`auto` are accepted but on a single-window native
  app they resolve to `tool`; there is no S-1/S-1m surface here (`design-system.md` §9.3).
- `--workflow` — opt-in Gen-2 background orchestration (see the dedicated section). Default is the
  Gen-1 in-session path. **Never taken automatically** — the Workflow tool requires the user's
  explicit opt-in per run.
- `--resume` — skip init; resume from current state. (`--surface` re-defaults to `tool` on resume.)

---

## When to use / When NOT to use

| Use `/frontend-uplift` | Use a different path |
|---|---|
| Multi-aspect GUI audit (visual + libraries + a11y + direction) | Single fix: direct Edit |
| "Where could this UI be better?" (open question) | Known surface to restyle in-session: `/frontend-design` skill |
| Producing a ranked candidate report | Producing the code: `/milestone-pipeline` after this |
| Comparing to SOTA desktop scientific tools | Backend / numerics / integrator work |

---

## Step 0 — Initialize state

There is **no `init-uplift.sh` in this repo.** State init is `checkpoint.py init`, which creates
the notes dir (`discover-briefs/`, `screenshots/`, `artifacts/`) AND the per-agent memory dirs
inline. Idempotent — re-running prints the resume line.

```bash
# standard: python .claude/scripts/frontend-uplift/checkpoint.py init <ID> [--brief "..."]
# lean:     ... init <ID> [--brief "..."] --lean
# deep:     ... init <ID> [--brief "..."] --deep
# experiential: init standard, then:
#   python .claude/scripts/frontend-uplift/checkpoint.py <ID> --set discover_mode='"experiential"'
python .claude/scripts/frontend-uplift/checkpoint.py init <ID> [--brief "..."] [--lean | --deep]
python .claude/scripts/frontend-uplift/checkpoint.py status <ID>
```

**Canon freshness (advisory — surface loudly, never blocks):**

```bash
python3 .claude/scripts/frontend-uplift-canon-lint.py check --root .
```

If `status`/`init` prints a resume line, jump to that phase. Otherwise proceed.

---

## Step 0.5 — Preflight (REQUIRED before Phase 1 dispatch)

```bash
python3 .claude/scripts/frontend-uplift/ensure_gui_bootable.py
```

A `.py`, invoked with `python3` (never `bash`). It probes the venv + PySide6/PyVista imports +
a headless (`QT_QPA_PLATFORM=offscreen`) construct-and-quit of `build_application()`. If exit is
non-zero, surface the recovery hint and HALT — the visual-scout REQUIRES a live, bootable GUI;
without it the visual brief is degenerate (code-only, no screenshots).

---

## Step 1 — Discover (parallel, ONE assistant turn)

Read `.claude/references/frontend-uplift/phase-discover.md` once at phase start.

```bash
.claude/scripts/frontend-uplift/checkpoint.py <ID> discover-running
```

**Roster (art-direction in EVERY mode; experiential NOT dispatched — INERT on S-2 Qt):**

| Mode | Agents dispatched |
|---|---|
| `standard` (default) | art-direction + visual + library + inspiration + current-state-critic |
| `lean` | art-direction + visual + library + current-state-critic |
| `deep` | art-direction + visual + library + inspiration + current-state-critic (opus) |
| `experiential` | art-direction + visual + library + current-state-critic (experiential lens marked INERT in the report) |

Dispatch **ONE turn** with N parallel `Agent` blocks. Prefer the named `subagent_type`
(`frontend-uplift-visual-scout`, `-library-scout`, `-inspiration-scout`, `-current-state-critic`,
`-art-direction-scout`) so each loads its project memory; if a freshly-renamed agent fails
`subagent_type` dispatch this session (agent-registration lag), fall back to `general-purpose`
with the agent body inlined. Each uses `model: sonnet` (`--deep` bumps the critic to `opus`),
`isolation: worktree`.

- **art-direction-scout** — reads `frontend-design-language.md` + `design-system.md`; produces the
  design frame (thesis + 3 directions + BAN list + surface map + current-state §10 score). No
  `agent-prompts.md` entry.
- **visual / library / inspiration / current-state-critic** — prompts verbatim from
  `.claude/references/frontend-uplift/agent-prompts.md` §1-§4, substituting `{ID}`, `{BRIEF}`,
  `{BRIEF_PATH}`, `{SCREENSHOTS_DIR}`.

Brief paths under `.claude/notes/frontend-uplifts/<ID>/discover-briefs/`
(`art-direction-brief.md`, `visual-brief.md`, `library-brief.md`, `inspiration-brief.md`,
`current-state-critic-brief.md`); `{SCREENSHOTS_DIR}` = `.claude/notes/frontend-uplifts/<ID>/screenshots`.

Record dispatch/return:

```bash
for agent in art-direction visual library inspiration current-state-critic; do
  .claude/scripts/frontend-uplift/checkpoint.py <ID> --append agents_dispatched="\"$agent\""
done
# as each returns:
.claude/scripts/frontend-uplift/checkpoint.py <ID> --append agents_returned='"<agent>"'
.claude/scripts/frontend-uplift/checkpoint.py <ID> --append discover_briefs='"<absolute path>"'
# when all returned:
ss_count=$(ls .claude/notes/frontend-uplifts/<ID>/screenshots/*.png 2>/dev/null | wc -l)
.claude/scripts/frontend-uplift/checkpoint.py <ID> --set screenshot_count=$ss_count
.claude/scripts/frontend-uplift/checkpoint.py <ID> discover-complete
```

---

## Step 2 — Synthesize (main session)

Read `.claude/references/frontend-uplift/phase-synthesize.md` once at phase start.

```bash
.claude/scripts/frontend-uplift/checkpoint.py <ID> synthesize-running
```

**OPEN with the art-direction frame** (phase-synthesize §0): the synthesis' first section IS the
adopted thesis + chosen direction + active BAN list + surface map + the §10 current-state score,
re-confirmed against the screenshots. Then read EVERY brief end-to-end, look at every screenshot
(multimodal vision), and place each candidate relative to the frame:
`[DIRECTION-DEFINING]` / compatible / `[polish]`, with frame-conflicting ideas parked and BAN-N
cited. A frameless catalog is a Phase-3 BLOCKER.

Build the catalog at `.claude/notes/frontend-uplifts/<ID>/artifacts/synthesis.md` using the
10-category UI taxonomy + T-shirt sizing + `FU-<ID>-NNN` numbering. Tag foundationals and wire-ups.
Honor the current-state-critic's reject list.

```bash
.claude/scripts/frontend-uplift/checkpoint.py <ID> --set synthesis_path='".claude/notes/frontend-uplifts/<ID>/artifacts/synthesis.md"'
.claude/scripts/frontend-uplift/checkpoint.py <ID> --set candidate_count=<N>
.claude/scripts/frontend-uplift/checkpoint.py <ID> synthesize-complete
```

---

## Step 3 — Challenge (single sub-agent, 11-axis)

Read `.claude/references/frontend-uplift/phase-challenge.md` once at phase start.

```bash
.claude/scripts/frontend-uplift/checkpoint.py <ID> challenge-running
```

Single `Agent` call, `subagent_type: frontend-uplift-challenger` (fallback `general-purpose`),
`isolation: worktree`. Prompt from `agent-prompts.md` §5 with `{ID}` + `{SYNTHESIS_PATH}`.

The challenger walks the **11-axis** checklist (native-only, worker-thread, token discipline,
renderer pacing, hi-DPI, a11y WCAG, no GUI-test regression, additive, already-shipped,
keyboard-equivalent, **+ Axis 11 distinctiveness/anti-template**). For Axis 11 it Reads
`.claude/references/frontend-design-language.md` DIRECTLY and scores each candidate — and the
synthesis as a whole — against §5 BAN-1..15 + the §10 rubric (native tells in
`phase-challenge.md`). **A frameless synthesis is a run-level BLOCKER**; a projected §10 score of
6+ is a BLOCKER, 3-5 a MAJOR. Web-only axes (bundle KB, React/RSC, mobile, experiential motion)
are INERT — never scored. Writes `.claude/notes/frontend-uplifts/<ID>/artifacts/challenge.md`.

```bash
.claude/scripts/frontend-uplift/checkpoint.py <ID> --set challenge_path='"..."'
.claude/scripts/frontend-uplift/checkpoint.py <ID> --set challenge_finding_counts='{"critical":N,"high":N,"medium":N,"low":N}'
.claude/scripts/frontend-uplift/checkpoint.py <ID> challenge-complete
```

---

## Step 4 — Prioritize (main session, portfolio lanes)

Read `.claude/references/frontend-uplift/phase-prioritize.md` once at phase start.

```bash
.claude/scripts/frontend-uplift/checkpoint.py <ID> prioritize-running
```

**Assign every non-dropped candidate to EXACTLY ONE portfolio lane, then compute RICE-light only
WITHIN a lane** (cross-lane RICE buries structural design under XS polish). Lane order:

1. **`a11y-safety-debt`** — MANDATORY, listed FIRST, never ranked away (WCAG / focus / contrast /
   keyboard / reduced-motion; e.g. the missing `setAccessibleName` coverage, the `light.qss` stub
   with no dark/light parity, any reduced-motion gap — all real, see `design-system.md` §9.4).
2. **`signature-direction`** — `[DIRECTION-DEFINING]` candidates realizing the adopted thesis.
3. **`foundations`** — shared tokens/helpers others depend on (foundational ×1.3, wire-up ×1.2).
4. **`workflow`** — new affordances unlocking a task.
5. **`polish`** — everything else. A top-5 that is all `polish` MUST say so.

RICE = Reach × Impact × Confidence / Effort. Penalties: un-mitigated BLOCKER → DROP; mitigated
BLOCKER ×0.5; MAJOR ×0.75. Write `final-report.md` opening with the design frame, lane-ordered,
with top-5 RICE breakdowns + sequencing respecting visual-surface dependencies + a
`/milestone-pipeline` handoff **OFFER**.

```bash
.claude/scripts/frontend-uplift/checkpoint.py <ID> --set final_report_path='"..."'
.claude/scripts/frontend-uplift/checkpoint.py <ID> --set ranked_candidates='[...]'
.claude/scripts/frontend-uplift/checkpoint.py <ID> complete
```

Print a 5-line summary (top-3 IDs + RICE; candidate count + severity distribution; a11y-debt lane
size; report path; suggested — not auto-run — `/milestone-pipeline <ID>`).

---

## Optional Gen-2 path (`--workflow`) — opt-in per run

When `--workflow` is passed, Step 0 (init) and Step 0.5 (preflight `ensure_gui_bootable.py`) still
run in the MAIN session (the Workflow JS has no exec / browser access), then the orchestrator
invokes the **Workflow tool**:

```
Workflow({
  scriptPath: ".claude/scripts/frontend-uplift-workflow.mjs",
  args: { id: "<ID>", brief: "<BRIEF>", mode: "<mode>", surface: "tool" }
})
```

It runs Discover → Synthesize → Challenge → Prioritize as a deterministic background workflow,
offloading Synthesize/Prioritize to the cost-capped `pipeline-synthesizer` / `pipeline-prioritizer`
agents. **Two caveats for this native repo:** (1) the Workflow tool requires the user's explicit
opt-in per run — never take `--workflow` automatically; (2) the workflow's visual-scout drives a
**browser preview** (`preview_start` at a URL) — a Qt desktop app has no such URL, so its visual
lens will likely return `screenshot_count: 0` (a degraded NO-SCREENSHOT run). The **Gen-1
in-session path (default) is the one that captures real GUI screenshots** via the native
visual-scout + `ensure_gui_bootable.py`. Prefer Gen-1 here; reach for `--workflow` mainly to
offload the synthesize/prioritize reasoning off the main thread.

> **No Workflow tool in this session?** Some harness builds lack it. Do NOT re-inline the phases —
> fall back to the Gen-1 in-session path (Steps 1-4 above), which is this repo's default anyway.

---

## State machine

```
init
  → discover-running    (preflight + Phase 1 dispatch — all agents in ONE turn)
  → discover-complete   (all briefs + screenshots returned)
  → synthesize-running
  → synthesize-complete
  → challenge-running
  → challenge-complete
  → prioritize-running
  → complete            (final-report.md; offer /milestone-pipeline)
```

`checkpoint.py` enforces forward-only single-step transitions. (The Gen-2 `--workflow` path owns
its own journal; Step 0/0.5 remain main-session preconditions before it.)

---

## Common rationalizations (anti-pattern guard)

| Tempting belief | Reality |
|---|---|
| "Skip preflight, the GUI's been working." | Preflight is cheap. A broken GUI mid-pipeline wastes 30+ minutes. |
| "Skip the art-direction-scout in lean mode — it's just taste." | Taste IS the deliverable gap. It fires in EVERY mode; dropping it re-creates the undirected default look. |
| "Better cards, nicer shadows — that's the uplift." | Polish on an undirected layout is still generic. The frame (thesis + direction + BAN list) comes first, THEN candidates. |
| "Skip visual-scout, the code review tells me what's wrong." | Visual evidence is load-bearing — most a11y / hi-DPI / contrast issues only show in pixels. |
| "Synthesize from TL;DRs only." | Triangulation lives in cross-brief specifics + the adopted frame. |
| "Skip the challenger." | Self-critique misses ~70% of objections; Axis 11 blocks frameless/template output. |
| "Propose parallax/WebGL/scroll-zoom because an award site does it." | INERT/BLOCKED on this S-2 native surface — there is no DOM, no S-1 surface. Name it inert; do not score it. |
| "Rank everything in one RICE list." | Cross-lane RICE buries structural design under XS polish. RICE is valid only WITHIN a lane; a11y-safety-debt is its own mandatory lane. |
| "Auto-invoke `/milestone-pipeline`." | NEVER. OFFER and WAIT. |
| "Take `--workflow` automatically to look modern." | The Workflow tool needs explicit user opt-in per run, and its visual lens is degraded on a native Qt app. Default is Gen-1. |

## Don'ts

- Don't dispatch without preflight. Don't drop art-direction. Don't run Phase 4 as a sub-agent.
- Don't let the synthesizer write the challenge. Don't accept a frameless synthesis.
- Don't dispatch the experiential-scout or propose experiential web motion (INERT/BLOCKED on S-2).
- Don't manufacture findings from INERT axes (bundle KB, React/RSC, mobile, experiential).
- Don't bypass `checkpoint.py init`. Don't auto-invoke `/milestone-pipeline`. Don't `git push`.

## Sub-agent memory

All `frontend-uplift-*` agents have `memory: project`. Memory accumulates under
`.claude/agent-memory/frontend-uplift-<role>/` across runs (the scouts are keyed by their
`-scout` names — `frontend-uplift-{art-direction,visual,library,inspiration}-scout`,
`frontend-uplift-{current-state-critic,challenger}`). Do NOT clear.
