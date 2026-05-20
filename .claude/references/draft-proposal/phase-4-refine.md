# Phase 4 — Refine (single sub-agent)

## Purpose

A single sub-agent reads draft + sequencing + critique together and
produces the final `docs/proposals/<slug>-<DATE>.md`. The refiner is
the integration point — it addresses every BLOCKER (DROP or
REDESIGN), populates every MAJOR's mitigation (MITIGATE), captures
MINORs in per-item "Risks / open questions", and pastes the
sequencer's table into the document.

This is the only sub-agent in the pipeline that writes to `docs/` —
the rest write to `.claude/notes/` (gitignored). The refiner's output
is the load-bearing artifact future contributors (and
`/milestone-pipeline`) will read.

## Why a sub-agent, not the main session

The refiner is a sub-agent (not main session) for two reasons:

1. **Fresh context**. The main session's working memory by Phase 4
   contains the draft, sequencing, and critique in the conversation
   transcript. A fresh sub-agent reads the artifacts as files,
   forcing it to verify what the refiner is supposed to verify.
2. **Worktree isolation**. The refiner writes to `docs/` — putting
   that in worktree isolation matches the project's "implementation
   happens in worktrees" pattern even when the implementation is
   only authoring a markdown file.

The TRANSITION (`refine-running` → `refine-complete` → `complete`)
still happens in the main session. The main session also runs the
Phase 5 handoff message.

## Inputs

- `artifacts/draft.md` (Phase 2 drafter).
- `artifacts/sequencing.md` (Phase 2 sequencer).
- `artifacts/critique.md` (Phase 3 critic).
- `source-brief.md` (Phase 1).
- `CLAUDE.md` (final correctness gate).

## Output

`docs/proposals/<slug>-<DATE>.md` — the canonical proposal file.

## Protocol

### 1. Read all inputs end-to-end

No skimming. The refiner is the integration point.

### 2. Apply the critic's dispositions

For each item in the draft, look up the critic's recommended
disposition (DROP / REDESIGN / MITIGATE / PROCEED) and apply it:

| Disposition | Action |
|---|---|
| **DROP** | REMOVE the item from the final proposal entirely. Add a one-line entry to the "Rejected at refinement" footer with the BLOCKER axis cited. |
| **REDESIGN** | REWRITE the item's What / Where / SOTA / Rationale to address the BLOCKER. If the redesign isn't obvious (e.g. the critic flagged "no measurable observable" and no observable can be named), DROP the item — never ship a hand-wavy refinement. |
| **MITIGATE** | KEEP the item's W/W/S/E/R verbatim. POPULATE "Risks / open questions" with a 1-2 sentence acknowledgment of the MAJOR concern + the explicit mitigation. |
| **PROCEED** | POPULATE "Risks / open questions" with any MINOR notes from the critique. If there are no MINORs, write "None identified by Phase 3 critique." |

### 3. Renumber the sequencing table

After DROPs, the sequencer's table has gaps. Renumber 1..N over the
surviving items, preserving order. Update any "depends on #N"
strings in the "Why first / why not" column to reference the new
numbering.

### 4. Assemble the final document

Use the proposal template at
`.claude/references/draft-proposal/proposal-template.md` as the
canonical skeleton. The final shape:

```
# {Proposal title} — {DATE}

## TL;DR
(Updated from the draft to reflect dropped/redesigned items.)

## Sequencing
(The sequencer's table, renumbered after DROPs.)

## Items
(In sequencer order. Each item's W/W/S/E/R verbatim from draft
or REDESIGN, with "Risks / open questions" populated per
disposition.)

## Rejected at drafting
(Unchanged from the draft.)

## Rejected at refinement
(Items the critic dropped, with the BLOCKER axis cited.)

## Reading order
(One paragraph. End with a `/milestone-pipeline {first item ID}`
suggestion — NOT auto-invoked.)
```

### 5. Verify the filename + H1 match

The filename must be `docs/proposals/<slug>-<DATE>.md` and the H1
title must include the same `<DATE>`. Future Claude sessions read
file mtime AND H1 date — they must agree.

### 6. Record + advance

```bash
.claude/scripts/draft-proposal/checkpoint.py <ID> --set final_proposal_path='"docs/proposals/<slug>-<DATE>.md"'
.claude/scripts/draft-proposal/checkpoint.py <ID> --set final_item_count=<N>
.claude/scripts/draft-proposal/checkpoint.py <ID> --set dropped_at_refinement='[...]'
.claude/scripts/draft-proposal/checkpoint.py <ID> refine-complete
```

The MAIN SESSION runs the state advance after the refiner returns;
the refiner itself doesn't touch state.json.

## Hard rules

- **Every BLOCKER must be addressed** — either by REDESIGN the
  refiner is confident in, or by DROP. No "we'll figure it out
  later".
- **Refiner does NOT downgrade severity.** If the critic said
  BLOCKER, the disposition is DROP or REDESIGN, not "actually a
  MAJOR".
- **The final file is canonical.** Make it standalone. Do NOT
  include "the drafter said..." or "the critic said..." narration
  in the proposal — that lives in `.claude/notes/`.
- **Filename and H1 date must agree.**
- **DO NOT commit the file.** Drafting is local. The user runs
  `/milestone-pipeline` after reviewing the proposal.
- **DO NOT modify any source code.** Only the proposal file.
- **DO NOT auto-invoke `/milestone-pipeline`** — that's a Phase 5
  main-session offer.

## Failure modes

| Failure | Recovery |
|---|---|
| Critic gave a BLOCKER without a clear redesign hint | DROP the item. Hand-wavy redesigns are the canonical anti-pattern. |
| Sequencer's DAG had a cycle | The critic should have flagged BLOCKER on the items in the cycle. DROP the items at the cycle's edge until the cycle resolves. |
| All items were dropped | Surface a final proposal with an empty Items section and an explicit "All proposed items were dropped at refinement; re-scope or re-source." in the TL;DR. Then advance to `complete` and let the user decide what to do. |
| Renumbering broke a "depends on #N" reference | Sweep the renumbered table; if any "Why first / why not" cell references an N that no longer exists, the dependency was on a dropped item — call out the un-met dep in the surviving item's "Risks / open questions". |

## Anti-patterns

- **Refiner re-litigates the critic.** No. The critic's calibrated
  severity is authoritative. Refiner applies; doesn't argue.
- **Refiner re-writes the W/W/S/E/R verbatim "for clarity".** No.
  Verbatim from the drafter unless the disposition is REDESIGN.
- **Refiner commits the file.** No. Phase 5 is OFFER, not commit.
- **Refiner auto-invokes `/milestone-pipeline`.** Forbidden.
