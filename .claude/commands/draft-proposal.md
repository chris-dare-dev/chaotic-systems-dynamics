---
description: Run the canonical multi-phase agentic pipeline that resolves CSC items (or a freeform brief) into a clean docs/proposals/<slug>-<DATE>.md file ready for /milestone-pipeline to consume. Drafter + sequencer fan out in parallel; critic + refiner run sequentially with calibrated severity. Bridges the discovery (capability-scout / frontend-uplift) and shipping (milestone-pipeline) ends of the pipeline ecosystem. NEVER auto-invokes /milestone-pipeline.
argument-hint: [slug] [--from CSC-A[,CSC-B,...]] [--brief "scope statement"] [--resume]
allowed-tools: Bash, Read, Edit, Write, Glob, Grep
---

# /draft-proposal

Run the canonical multi-phase pipeline:
**Resolve → Draft + Sequence → Critique → Refine**

Usage:

```
/draft-proposal                                 # ask for slug + source
/draft-proposal <slug>                          # draft from scratch — ask follow-up questions
/draft-proposal <slug> --from CSC-011,CSC-012   # bundle existing CSC items from the most recent synthesis
/draft-proposal <slug> --from CSC-018           # promote one CSC item to a proper proposal file
/draft-proposal <slug> --brief "..."            # use a verbatim user brief instead of CSC items
/draft-proposal <slug> --resume                 # resume from current phase
```

`<slug>` is a short kebab-case noun phrase (`next-diagnostics`,
`hyperchaos-batch`, `q3-perf`). The pipeline writes to
`.claude/notes/draft-proposals/<ID>/` where `<ID>` is `<slug>-<DATE>`.

The pipeline answers: **"Take this candidate (or these candidates,
or this user brief) and produce a clean `docs/proposals/*.md` that
`/milestone-pipeline` can consume."** It does NOT ship code; it
produces a proposal file ready for the next pipeline.

---

## Architectural rules (non-negotiable)

1. **Phase 1 (resolve) runs in the main session.** It needs
   CLAUDE.md / CONTEXT.md / synthesis-file context already in
   working memory. Sub-agent dispatch here would re-read everything
   from scratch.
2. **Phase 2 dispatch happens in ONE assistant turn** containing
   two parallel `Agent` tool blocks (drafter + sequencer). Sequential
   dispatch re-introduces the anchoring bias the parallel design
   prevents.
3. **Anti-anchoring is a prose-level contract, not an OS-level
   isolation.** The sequencer SHOULD NOT read the drafter's
   output. The OS does NOT prevent this — `isolation: worktree`
   provides a different cwd but the parent repo is reachable by
   absolute path (empirically verified 2026-05-19; see
   `_adversary-review-2026-05-19.md` D4). The prompt-level contract
   is enforced by the post-condition verifier
   (`verify.py phase-2`), which rejects sequencer outputs that
   cite or reproduce drafter content.
4. **Worktree sub-agents cannot see gitignored parent-repo files
   via relative paths.** All paths to inputs that live under
   `.claude/notes/` or `.claude/agent-memory/` (both gitignored)
   MUST be passed as **absolute** paths through the
   `{REPO_ROOT}` placeholder. Relative paths fail at first Read.
5. **The drafter does NOT also write the critique.** Distinct roles.
   The fresh-context adversary catches blind spots the drafter
   cannot see.
6. **The critic and the refiner are distinct.** The critic produces
   calibrated severity; the refiner applies dispositions. One agent
   doing both blurs the contract.
7. **Post-condition verifiers gate every phase advance.** The main
   session MUST run `.claude/scripts/draft-proposal/verify.py
   <ID> <phase>` after each phase's artefacts are written and
   BEFORE calling `checkpoint.py <ID> <next-phase>`. The verifier
   inspects artefacts on disk for required structure (headers,
   item counts, DAG well-formedness, filename-date consistency)
   and exits non-zero if the phase output is malformed.
8. **NEVER auto-invoke `/milestone-pipeline` at completion.** Phase
   5 OFFERS the handoff; the user types the next command if they
   want to proceed.
9. **No commits at any phase.** Drafting is local. The user reviews
   the final file before any commit happens (the `/milestone-pipeline`
   commit, if they run it, is downstream).
10. **Tool-allowlist enforcement is best-effort, not guaranteed.**
    The `tools:` block in each `.claude/agents/draft-proposal-*.md`
    is enforced ONLY if the Claude Code session was restarted after
    the registration files landed. The "general-purpose-via-prompt"
    fallback (used when the harness hasn't registered the
    project-local agents mid-session) inherits the PARENT session's
    full toolset — including `Bash` with `git commit` / `git push`.
    Phase 5 includes a `git log` diff check (`verify.py phase-5`)
    that detects rogue commits and refuses to advance to
    `complete` if any landed under the loose dispatch.

---

## Step 0 — Initialize state

```bash
python .claude/scripts/draft-proposal/checkpoint.py init <slug> [--from CSC-A,...] [--brief "..."]
```

The init script:
- Computes `<ID>` = `<slug>-<YYYY-MM-DD>`.
- Resolves `<slug>` collisions: if `.claude/notes/draft-proposals/<ID>/`
  already exists, prints the current phase and exits 0 (idempotent
  resume).
- Creates per-agent project memory dirs under
  `.claude/agent-memory/draft-proposal-*/`.
- Persists `source_kind`, `csc_items`, `draft_brief`, and `slug` in
  `state.json`.

```bash
python .claude/scripts/draft-proposal/checkpoint.py status <ID>
```

Inspect current phase + history before deciding which step to run.

If `<slug>` was omitted, STOP and ask the user. If both `--from`
and `--brief` were supplied, STOP and ask which one the user
intended (we don't blend the two source kinds).

---

## Step 1 — Resolve (main session)

Read `.claude/references/draft-proposal/phase-1-resolve.md` once at
phase start.

```bash
.claude/scripts/draft-proposal/checkpoint.py <ID> resolve-running
```

Main session protocol:

1. If `source_kind == "csc-items"` or `"single-csc"`:
   - Find the newest `.claude/notes/capability-scouts/*/artifacts/synthesis.md`.
   - For each requested CSC suffix (e.g. `011`), grep for the
     matching `### CSC-<RUN>-<suffix>` header.
   - If any CSC suffix doesn't resolve, FAIL LOUDLY — print which
     IDs failed + which synthesis was searched. Do NOT advance state.
   - Copy each matched section verbatim into the source brief.
2. If `source_kind == "freeform-brief"`:
   - Write the verbatim user brief at the top of the source brief.
   - Add an auto-generated "Context for drafting" section with
     CONTEXT.md "Current state" (excerpt) + the most recent
     "Recently shipped" item titles + (if present) a citation of
     the most recent `internal-adversary-brief.md`.

Source brief path:
`.claude/notes/draft-proposals/<ID>/source-brief.md`

Record + advance:

```bash
.claude/scripts/draft-proposal/checkpoint.py <ID> --set source_brief_path='".claude/notes/draft-proposals/<ID>/source-brief.md"'
.claude/scripts/draft-proposal/checkpoint.py <ID> --set resolved_csc_items='[...]'   # JSON list; empty for freeform
.claude/scripts/draft-proposal/checkpoint.py <ID> resolve-complete
```

---

## Step 2 — Draft + Sequence (parallel, 2 agents in ONE turn)

Read `.claude/references/draft-proposal/phase-2-draft.md` once at
phase start.

```bash
.claude/scripts/draft-proposal/checkpoint.py <ID> draft-running
```

### 2a — Dispatch both agents in ONE assistant turn

In ONE turn containing two `Agent` tool blocks. Each uses:

- `subagent_type: general-purpose` (the harness's agent list locks
  at session start; project-local `draft-proposal-*` agents may not
  be visible mid-session — the workaround is to dispatch via
  general-purpose and embed the brief via "act as the
  draft-proposal-<role> agent defined at
  .claude/agents/draft-proposal-<role>.md — read that file first").
- `model: sonnet` (drafter and sequencer don't need opus).
- `isolation: worktree`.
- Prompt verbatim from
  `.claude/references/draft-proposal/agent-prompts.md` §1 (drafter)
  or §2 (sequencer). Substitute all placeholders defined in that
  file's placeholder glossary (the SSoT). **`{REPO_ROOT}` MUST be
  set to the absolute parent-repo path** (`pwd` of the main
  session); every gitignored-input path the agent reads (source
  brief, lessons.md, artifacts) is built as `{REPO_ROOT}/.claude/...`
  so the worktree's relative-path Read failure mode (D4 finding,
  2026-05-19) is bypassed.

Artifact paths the dispatch passes in (absolute):
- `{DRAFT_PATH}` = `{REPO_ROOT}/.claude/notes/draft-proposals/<ID>/artifacts/draft.md`
- `{SEQUENCING_PATH}` = `{REPO_ROOT}/.claude/notes/draft-proposals/<ID>/artifacts/sequencing.md`
- `{SOURCE_BRIEF_PATH}` = `{REPO_ROOT}/.claude/notes/draft-proposals/<ID>/source-brief.md`

The worktree sub-agent's *own* output paths (the artefacts it
writes during the phase) may be relative to the worktree root —
the agent creates parent directories as needed, and Phase 2b
verifies the artefacts landed at the absolute path before
advancing.

After dispatching:

```bash
for agent in drafter sequencer; do
  .claude/scripts/draft-proposal/checkpoint.py <ID> --append agents_dispatched="\"$agent\""
done
```

### 2b — Brief return + verifier gate

As each agent returns its message:

```bash
.claude/scripts/draft-proposal/checkpoint.py <ID> --append agents_returned='"<agent-name>"'
```

When both returned (set equality), **run the post-condition
verifier BEFORE advancing the state machine**:

```bash
.claude/scripts/draft-proposal/verify.py <ID> phase-2
```

The verifier checks:
- `draft.md` and `sequencing.md` exist and are non-empty.
- `draft.md` contains the `<!-- SEQUENCING_TABLE_GOES_HERE -->`
  marker.
- `draft.md` contains an `## Items` H2 and ≥ 1 `### ` item header.
- `sequencing.md` contains a `## Sequencing table` H2 with rows
  whose count matches `draft.md`'s item count.
- The sequencing table's DAG has no cycles (each "depends on #N"
  reference points to a smaller row number).
- The sequencer's output does NOT reproduce any item-body prose
  from the drafter's output (anti-anchoring soft-contract check;
  flags mention of specific What/Where/SOTA prose copied across).

Verifier exit code 0 = advance; non-zero = STOP, do NOT advance.
The error message names the failing assertion and points the user
at re-dispatching the offending agent.

On success:

```bash
.claude/scripts/draft-proposal/checkpoint.py <ID> --set draft_path='"{REPO_ROOT}/.claude/notes/draft-proposals/<ID>/artifacts/draft.md"'
.claude/scripts/draft-proposal/checkpoint.py <ID> --set sequencing_path='"{REPO_ROOT}/.claude/notes/draft-proposals/<ID>/artifacts/sequencing.md"'
.claude/scripts/draft-proposal/checkpoint.py <ID> --set item_count=<N>
.claude/scripts/draft-proposal/checkpoint.py <ID> draft-complete
```

---

## Step 3 — Critique (single sub-agent)

Read `.claude/references/draft-proposal/phase-3-critique.md` once at
phase start.

```bash
.claude/scripts/draft-proposal/checkpoint.py <ID> critique-running
```

Single `Agent` call with `subagent_type: general-purpose`, sonnet,
`isolation: worktree`. Substitute all placeholders from
`agent-prompts.md` — note `{REPO_ROOT}` again: all input paths
(draft, sequencing, source-brief) are absolute.

The critic walks the **9-axis** checklist (axes 6, 8, 10 of the
original 10-axis ported-from-/capability-scout rubric were retired
after the 2026-05-19 adversary review found them either vestigial
or already drafter-enforced; new axes targeting *proposal-hygiene*
specifically — filename-date consistency, sequencing-renumber
integrity, `/milestone-pipeline` parseability, TL;DR-Items count —
replace them). The critic also emits a **confidence** column
(high / med / low) alongside each severity, so the refiner can
treat low-confidence BLOCKERs as user-escalations rather than
auto-DROPs. Output:

```
{REPO_ROOT}/.claude/notes/draft-proposals/<ID>/artifacts/critique.md
```

Severity rubric: BLOCKER (5-15%), MAJOR (15-30%), MINOR (20-30%),
NONE (30-60%) in a healthy run.

**Run the verifier before advancing:**

```bash
.claude/scripts/draft-proposal/verify.py <ID> phase-3
```

The verifier checks:
- `critique.md` exists, non-empty, contains a `## Per-item axes`
  H2 and a `## Calibration check` H2.
- Each item from `draft.md` has its own `### ` subsection in the
  critique.
- Per-item axes table has exactly 9 rows (the new axis count).
- Calibration check sums to `9 × item_count`.

On success:

```bash
.claude/scripts/draft-proposal/checkpoint.py <ID> --set critique_path='"{REPO_ROOT}/.claude/notes/draft-proposals/<ID>/artifacts/critique.md"'
.claude/scripts/draft-proposal/checkpoint.py <ID> --set critique_finding_counts='{"blocker":N,"major":N,"minor":N,"none":N}'
.claude/scripts/draft-proposal/checkpoint.py <ID> --set critique_cycle=1
.claude/scripts/draft-proposal/checkpoint.py <ID> critique-complete
```

---

## Step 4 — Refine (single sub-agent)

Read `.claude/references/draft-proposal/phase-4-refine.md` once at
phase start.

```bash
.claude/scripts/draft-proposal/checkpoint.py <ID> refine-running
```

Single `Agent` call with `subagent_type: general-purpose`, sonnet,
`isolation: worktree`. All input paths absolute via `{REPO_ROOT}`.

The refiner:
- Reads draft + sequencing + critique + **source brief** end-to-end
  (the source-brief re-read is mandatory for any REDESIGN
  disposition — see `agent-prompts.md` §4 REDESIGN protocol).
- Applies each item's disposition (DROP / REDESIGN / MITIGATE /
  PROCEED). LOW-confidence BLOCKERs from the critic are NOT
  auto-DROPped — they're surfaced in a "Contested findings"
  block the user reads at Phase 5 handoff.
- Renumbers the sequencing table after DROPs, AND validates
  cross-references: any "depends on #N" pointing at a dropped row
  triggers a renumber-reconciliation in the same pass.
- Cross-checks the sequencer's table against the drafter's
  "Rejected at drafting" footer (the E2 reconciliation gap) and
  drops sequencer rows that reference drafter-dropped items.
- Writes the final proposal to `docs/proposals/<slug>-<DATE>.md`.

The MAIN SESSION advances the state after the refiner returns.

**Run the verifier before advancing:**

```bash
.claude/scripts/draft-proposal/verify.py <ID> phase-4
```

The verifier checks:
- `docs/proposals/<slug>-<DATE>.md` exists, non-empty.
- H1 title's `— {DATE}` suffix matches the filename's `-<DATE>.md`.
- The TL;DR's claimed item count matches the count of `### ` item
  headers in the `## Items` section.
- Every item's "Risks / open questions" is populated (no
  `(populated after critique)` placeholders left).
- Every "depends on #N" in the Sequencing table points to a valid
  row number `<= N_items`.
- No item ID appears twice across `## Items` + `## Rejected at
  drafting` + `## Rejected at refinement`.

### Re-critique loop (up to 3 cycles)

Modern self-correcting agentic pipelines (Reflexion / Aider / OpenDevin
pattern) re-run the critic against the refiner's output to catch
REDESIGN-introduced regressions. After Phase 4 verifies, run the
critic ONE MORE TIME against the **final file**:

```bash
# Re-critique cycle (max 3 total cycles including the initial one)
.claude/scripts/draft-proposal/checkpoint.py <ID> recritique-running
```

Dispatch the critic again with `{DRAFT_PATH}` pointing at the
final file. If the re-critique returns 0 BLOCKERs, advance to
`recritique-complete` and continue to Phase 5. If it returns ≥ 1
BLOCKER:

- If `critique_cycle < 3`: increment the cycle, re-dispatch the
  refiner, loop back. Each cycle's critique is archived as
  `critique-cycle-<N>.md`.
- If `critique_cycle == 3`: STOP. The pipeline refuses to advance
  to `complete`. Print a "draft-proposal needs human review"
  banner with the BLOCKERs and the path to all three critique
  files. The user must either manually edit the proposal or
  re-run the pipeline with a sharper source brief.

```bash
.checkpoint.py <ID> --set final_proposal_path='"docs/proposals/<slug>-<DATE>.md"'
.checkpoint.py <ID> --set final_item_count=<N>
.checkpoint.py <ID> --set dropped_at_refinement='[...]'
.checkpoint.py <ID> recritique-complete   # only when re-critique returns 0 BLOCKERs
```

---

## Step 5 — Handoff (main session)

**Final guardrail check — `git log` diff:**

```bash
.claude/scripts/draft-proposal/verify.py <ID> phase-5
```

The verifier compares the current `git rev-parse HEAD` against the
HEAD recorded at `init` time (stored in `state.json` as
`init_head_sha`). If any commit landed during the pipeline run
(the G4 tool-allowlist subversion check), REFUSE to advance to
`complete` — print a banner identifying the rogue commits + the
phase they landed in. The user must either revert or explicitly
acknowledge before re-running.

On success:

```bash
.claude/scripts/draft-proposal/checkpoint.py <ID> complete
```

Print a 5-line summary to the user with:

1. The proposal file path.
2. Final item count (after refinement DROPs).
3. Items dropped at drafting + at refinement, with one-line
   rationale each.
4. The first item ID in the sequencing table.
5. The suggested `/milestone-pipeline <first-item-id>` invocation
   the user can run if they want to ship.

**Do NOT auto-invoke `/milestone-pipeline`.** Print the suggested
invocation; let the user decide. This is the canonical anti-pattern
shared with `/capability-scout` and `/frontend-uplift`.

---

## State machine

```
init
  → resolve-running       (Phase 1 — main session resolves source kind into source-brief.md)
  → resolve-complete      (source brief written; verify.py phase-1 passed)
  → draft-running         (Phase 2 — drafter + sequencer dispatched in ONE turn)
  → draft-complete        (draft.md + sequencing.md returned; verify.py phase-2 passed)
  → critique-running      (Phase 3 — critic dispatched as single sub-agent)
  → critique-complete     (critique.md returned; verify.py phase-3 passed; critique_cycle=1)
  → refine-running        (Phase 4 — refiner dispatched as single sub-agent)
  → refine-complete       (final proposal written; verify.py phase-4 passed)
  → recritique-running    (re-critique against the FINAL file; cycle ≤ 3)
  → recritique-complete   (re-critique returned 0 BLOCKERs)
  → complete              (Phase 5 — main session prints handoff offer; verify.py phase-5 git-log check passed)
```

`checkpoint.py` enforces forward-only single-step transitions
EXCEPT for the re-critique loop: from `recritique-running` the
state can move to either `recritique-complete` (BLOCKER-free) or
back to `refine-running` (BLOCKERs found, cycle < 3). The
`critique_cycle` counter is the loop bound; `checkpoint.py`
refuses any `refine-running` re-entry when `critique_cycle >= 3`.

If the session compacts mid-run, `checkpoint.py status <ID>` shows where to
resume. For any `*-running` phase, `checkpoint.py status` additionally
inspects the expected artefacts on disk and surfaces "agents
appear to have completed — run verify.py + checkpoint.py to
advance" vs. "no artefacts on disk — re-dispatch the phase's
agents".

---

## Common rationalizations (anti-pattern guard)

| Tempting belief | Reality |
|---|---|
| "Skip Phase 1, just dispatch the drafter with the CSC IDs." | The drafter needs the FULL synthesis sections; Phase 1's job is to fail loudly on un-resolvable IDs *before* a wasted Phase 2 dispatch. |
| "Fold the sequencer into the drafter — one agent can do both." | Anti-anchoring matters even though the OS doesn't enforce it: the sequencer reasoning must start from the source brief alone, not from whatever order the drafter happened to author. The post-condition verifier checks for prose copy-across. |
| "`isolation: worktree` means the sequencer literally cannot see the drafter's file." | Empirically false (2026-05-19 D4 probe). Worktrees give a different cwd but absolute parent-repo paths bypass the boundary entirely. Treat anti-anchoring as a prose contract enforced by the verifier, not by the OS. |
| "Pass relative paths in the dispatch prompts." | Gitignored inputs (source brief, lessons.md) are absent from the worktree by relative path. ALL gitignored-input paths in dispatch prompts MUST be absolute via `{REPO_ROOT}`. |
| "Skip the critic, the drafter is competent enough." | The fresh-context adversary catches blind spots the drafter cannot see. Architectural rule, not motivational. |
| "Inflate critic severity to look thorough." | Calibrated runs see 30-60% NONE. Inflation makes the refiner drop items that should have shipped. |
| "Refiner can downgrade a BLOCKER to MAJOR if it seems harsh." | No. Critic severity is authoritative. Disposition is DROP / REDESIGN / MITIGATE / PROCEED — never "actually a MAJOR". LOW-confidence BLOCKERs go to user-escalation, not to silent downgrade. |
| "Promote a CSC item without re-reading its source section." | The synthesis is a deduplication; the items' Evidence-from-briefs lines are the load-bearing evidence. Drafter MUST re-read at draft time AND the refiner MUST re-read at REDESIGN time. |
| "Skip the re-critique loop, the refiner is reliable." | REDESIGN dispositions can introduce NEW BLOCKERs the original critique never saw (fabricated citations under pressure is the headline failure mode). The re-critique pass catches them; max 3 cycles bounds the loop. |
| "Skip `verify.py` between phases — the agent returned successfully." | "Agent returned" ≠ "agent succeeded". The verifier inspects the artefact on disk for required structure. Trusting the LLM's word is exactly what adversarial pipelines exist to disprove. |
| "Auto-invoke `/milestone-pipeline` once the file lands." | NEVER. The whole point of the pipeline is to give the user a reviewable proposal. |
| "`git push` the proposal file at the end." | NEVER. Drafting is local. `/milestone-pipeline` is what commits and pushes — and only after the user explicitly invokes it. The Phase 5 `git log` diff check catches rogue agent commits. |

## Don'ts

- Don't run Phase 1 (resolve) as a sub-agent.
- Don't let the drafter write the sequencing table.
- Don't let the sequencer read the drafter's output (prose-level
  contract; `verify.py phase-2` checks for prose copy-across).
- Don't let the drafter write the critique.
- Don't bundle items whose categories conflict. The critic flags
  category drift; the refiner splits.
- Don't auto-invoke `/milestone-pipeline` or any downstream
  pipeline.
- Don't manufacture items (every entry must trace to ≥ 1 CSC item
  or a clear excerpt of the freeform brief — critic axis 1).
- Don't bypass `checkpoint.py init`.
- Don't `git push` at any phase. Don't `git commit` either — the
  proposal file gets committed downstream by `/milestone-pipeline`
  when the first item ships. The Phase 5 `git log` diff check
  refuses to advance if any commit landed under the loose dispatch.
- Don't skip the post-condition verifier (`verify.py`) between
  phases. Forward state advance is conditional on verifier exit 0.
- Don't loop more than 3 critique cycles. If the refiner can't
  produce a BLOCKER-free output in 3 tries, surface to user for
  manual review.

## Sub-agent memory

All `draft-proposal-*` agents have `memory: project`. Memory
accumulates under `.claude/agent-memory/draft-proposal-<role>/`
across runs. Do NOT clear or overwrite — agents read their lessons
file at the start of every run.
