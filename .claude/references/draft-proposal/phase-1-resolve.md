# Phase 1 — Resolve

## Purpose

Resolve the user's invocation into a single concrete source brief
that downstream phases (drafter, sequencer, critic, refiner) can
treat as the single load-bearing input. This phase runs in the **main
session**, not a sub-agent — it requires CLAUDE.md / CONTEXT.md /
synthesis-file context that the main session already holds.

## Inputs

- `state.json` field `slug` — the proposal slug (e.g.
  `next-diagnostics`).
- `state.json` field `source_kind` — `csc-items` / `single-csc` /
  `freeform-brief`.
- `state.json` field `csc_items` — list of CSC IDs (e.g.
  `["CSC-2026-q2-broadening-011", "CSC-2026-q2-broadening-012"]`),
  empty list for freeform.
- `state.json` field `draft_brief` — the user-supplied freeform brief,
  empty string for csc-driven runs.

## Output

`.claude/notes/draft-proposals/<ID>/source-brief.md` — the assembled
context the four downstream agents read first.

## Protocol

### 1. Resolve the synthesis (if `source_kind` is `csc-items` or `single-csc`)

The CSC items are shorthand — `CSC-011` refers to the `-011` suffix
of the most recent capability-scout synthesis. The full ID looks like
`CSC-2026-q2-broadening-011`.

Resolution steps:

1. List `.claude/notes/capability-scouts/*/artifacts/synthesis.md`,
   sorted by modification time (newest first).
2. Read the newest synthesis. Confirm it contains a section header
   matching each requested CSC suffix (e.g. `### CSC-...-011 —`).
3. If any requested CSC suffix does NOT resolve in the newest
   synthesis, FAIL LOUDLY. Print:
   - Which CSC IDs failed to resolve
   - Which syntheses were searched
   - A suggested fix (e.g. "the requested ID is from
     synthesis X; pass `--from-synthesis X`" — but for now, the
     pipeline only resolves against the newest synthesis).
   Do NOT advance the state machine on failure.

The full ID is the synthesis filename's run ID + the suffix:
`.claude/notes/capability-scouts/<RUN>/artifacts/synthesis.md` →
`CSC-<RUN>-NNN`.

### 2. Read the CSC item sections

For each resolved CSC item, copy the FULL section (from `### CSC-...`
to the next `### ` or end-of-file) into the source brief. Do NOT
paraphrase — the drafter needs the full evidence, including the
"Evidence from briefs" lines.

### 3. (freeform-brief only) Capture the verbatim brief

If `source_kind == "freeform-brief"`, the source brief contains:
- The verbatim user-supplied brief
- An auto-generated "Context for drafting" section that lists:
  - The current state from CONTEXT.md "Current state" (one-paragraph
    excerpt)
  - The most recent "Recently shipped" item titles (for the drafter
    to avoid duplicates)
  - The shipped-but-un-exposed candidates the freeform drafter
    might want to consider (cite the most recent capability-scout's
    `internal-adversary-brief.md` if present)

### 4. Write the source brief

Use this structure:

```
# Source brief — draft-proposal <ID>

## Source kind

<csc-items | single-csc | freeform-brief>

## Resolved items

<For csc-items / single-csc: one block per CSC item, full section
verbatim from the synthesis.>

<For freeform-brief: the verbatim user brief + the Context for
drafting section described above.>

## Authoritative references

- CLAUDE.md sections "The frontend is native — do not change that"
  and "Mathematical correctness"
- CONTEXT.md "Recently shipped" (most recent two rollouts)
- docs/proposals/capability-roadmap-2026-05-17.md (the format the
  drafter is matching)
- docs/proposals/README.md (naming convention)

## Notes for downstream agents

- The drafter writes per-item W/W/S/E/R blocks.
- The sequencer writes the top-of-file table; it MUST NOT read the
  drafter's output (runs in parallel).
- The critic walks the 10-axis checklist with severity calibration.
- The refiner addresses every BLOCKER (drop/redesign) and every
  MAJOR (mitigate); MINORs go in "Risks / open questions" per
  item.
```

### 5. Record + advance

```bash
.claude/scripts/draft-proposal/checkpoint.py <ID> --set source_brief_path='".claude/notes/draft-proposals/<ID>/source-brief.md"'
.claude/scripts/draft-proposal/checkpoint.py <ID> --set resolved_csc_items='["CSC-..."]'
.claude/scripts/draft-proposal/checkpoint.py <ID> resolve-complete
```

## Hard rules

- **Fail loudly on un-resolvable CSC IDs.** The drafter cannot
  invent a section from a missing CSC ID; surfacing the failure now
  saves a wasted Phase 2 dispatch.
- **Copy CSC sections verbatim.** Paraphrasing here loses the
  triangulation evidence the drafter needs.
- **Phase 1 is main-session.** No sub-agent. CONTEXT.md drift is
  already in working memory.

## Failure modes

| Failure | Recovery |
|---|---|
| Requested CSC ID isn't in the newest synthesis | STOP. Surface to user. Do not advance state. |
| Multiple syntheses contain matching suffixes | Use the newest one and surface the ambiguity in the source brief's "Notes" section so the critic can flag it if the wrong one was picked. |
| Freeform brief is empty and no CSC items given | STOP. The slash command should have caught this; if it slips through, ask the user for either a brief or a CSC list. |
| Synthesis file exists but the requested CSC section header doesn't match (typo) | Diff the requested ID against the headers in the file; surface the closest match as a suggestion. |
