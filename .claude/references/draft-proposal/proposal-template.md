# Proposal template — draft-proposal

The skeleton the drafter produces and the refiner finalises. Format
mirrors `docs/proposals/capability-roadmap-2026-05-17.md` so that
`/milestone-pipeline` can consume both interchangeably.

Placeholders in `{braces}` are filled by the drafter / refiner.
Comments like `<!-- ... -->` are removed in the final file.

---

```markdown
# {Proposal title} — {YYYY-MM-DD}

## TL;DR

{3-5 sentences. State the proposal's theme, total item count,
foundational items called out, the "obvious next ship", and any
items the drafter / refiner rejected. The TL;DR is what a future
contributor reads first — it must stand alone.}

## Sequencing

<!-- SEQUENCING_TABLE_GOES_HERE — drafter leaves this marker, sequencer fills it in Phase 2, refiner pastes it here in Phase 4. -->

| Order | Item | Effort | Why first / why not |
|---|---|---|---|
| 1 | {Item ID} — {Title} | S | foundational + wire-up; unblocks #2, #4 |
| 2 | {Item ID} — {Title} | S | depends on #1 |
| ... | ... | ... | ... |

## Items

<!-- One section per item, in sequencer order. -->

### {Item ID} — {Title}  {(promotes CSC-... if applicable)}

- **What:** {One-sentence description.}
- **Where:** {Target file paths. Cite both src/ and tests/.}
- **SOTA reference:** {Primary citation — textbook + section, paper + DOI / arXiv, or canonical URL. NEVER hand-wavy.}
- **Effort:** {S | M | L}
- **Rationale:** {2-4 sentences. What this unlocks, why it's coherent with current direction, what observable will prove it works.}
- **Risks / open questions:**
  - {Mitigation for any MAJOR finding from Phase 3 critique.}
  - {MINOR notes from Phase 3 critique.}
  - {"None identified by Phase 3 critique." if the item passed every axis as NONE.}

### {Item ID} — {Title}

- **What:** ...
- **Where:** ...
- **SOTA reference:** ...
- **Effort:** ...
- **Rationale:** ...
- **Risks / open questions:** ...

## Rejected at drafting

<!-- The drafter writes this section: items the drafter saw in the
source brief but dropped before the critic ever ran, with the hard
rule that disqualified them. -->

- **{Original item ID or title}** — {one-line rationale referencing
  CLAUDE.md lock or shipped duplicate}.

## Rejected at refinement

<!-- The refiner writes this section: items the critic gave an
un-mitigated BLOCKER, with the BLOCKER axis cited. Empty if no items
were dropped at refinement. -->

- **{Item ID}** — {BLOCKER axis from critique.md, e.g. "axis 5
  (effort calibration) — sized L+ without a split path"}.

## Reading order

A new contributor should:

1. Read the **Sequencing** table — top to bottom.
2. For the top item, read its **Items** entry end-to-end.
3. Run `/milestone-pipeline {first item ID}` to ship it.

`/milestone-pipeline` reads the same file: it parses the **Items**
section to find the requested item ID, reads the W/W/S/E/R block,
and proceeds.
```

---

## Notes for the drafter

- Item IDs follow the proposal's domain prefix convention used in
  `capability-roadmap-2026-05-17.md`:
  - `N#` for new-system items (N1 = discrete maps, N2 = 4D Rössler)
  - `I#` for new-integrator items
  - `D#` for new-diagnostic items
  - `P#` for performance items
  - `V#` for visualization / GUI items
  - `E#` for educational items
- When promoting a CSC item, ALSO cite the CSC ID in the section
  header so future readers can trace back to the synthesis:
  `### N1 — Add Thomas attractor (promotes CSC-2026-q2-broadening-001)`
- For freeform proposals with a single item, the sequencing table
  has exactly one row and the "Why first / why not" cell says
  "single-item proposal".
- The `Risks / open questions` line is `(populated after critique)`
  at draft time. The refiner replaces this placeholder.

## Notes for the refiner

- Renumber the sequencing table AFTER applying DROPs from the
  critic's dispositions.
- If a "depends on #N" reference points to a dropped item, surface
  the un-met dep in the surviving item's `Risks / open questions`.
- The `Reading order` section's `/milestone-pipeline {first item
  ID}` references the FIRST surviving item — update after
  renumbering.
- If ALL items were dropped, the Items section is empty and the
  TL;DR explicitly says "All proposed items were dropped at
  refinement; re-scope or re-source."
