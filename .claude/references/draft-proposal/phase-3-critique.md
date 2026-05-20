# Phase 3 — Critique (single sub-agent)

## Purpose

A single adversarial sub-agent argues AGAINST every item in the
draft using a 10-axis checklist tailored to proposal hygiene.
Severity is calibrated: a healthy run sees 30-60% NONE, 5-15% BLOCKER,
15-30% MAJOR, 20-30% MINOR.

This is the second adversarial pass in the project's pipeline
ecosystem: `/capability-scout`'s challenger critiques candidates
against architectural locks; `/draft-proposal`'s critic critiques
the DRAFT against proposal-shape locks (path conflict, citation
quality, observable presence, sizing calibration).

## Inputs

- `artifacts/draft.md` from the drafter (Phase 2).
- `artifacts/sequencing.md` from the sequencer (Phase 2).
- The source brief (Phase 1).
- `CLAUDE.md` (architectural locks).
- `CONTEXT.md` (already-shipped — the critic's highest-yield check).

## Output

`.claude/notes/draft-proposals/<ID>/artifacts/critique.md`.

## Severity rubric

| Severity | Meaning | Refiner disposition |
|---|---|---|
| **BLOCKER** | Would prevent `/milestone-pipeline` from shipping the item as-is. Examples: missing primary citation, path conflict with shipped code, web framework dep, L+ item not split, manufactured-without-source. | DROP or REDESIGN |
| **MAJOR** | Significant concern needing explicit mitigation in the refined item's "Risks / open questions". Examples: missing measurable observable, invasive core modification, un-met external dep. | MITIGATE |
| **MINOR** | Worth noting but not load-bearing. Examples: orphan category in bundle, light effort calibration drift. | PROCEED (with MINOR captured in Risks section) |
| **NONE** | Passes this axis. | — |

**Calibration**: in a healthy run, ~30-60% of axes return NONE. If
you flag > 70% MAJOR/BLOCKER, you're inflating. If < 10%, you're
soft-pedaling. The critic's job is sharp, not friendly.

## The 10-axis checklist

### Axis 1 — Source traceability

Does the item trace to a CSC ID in the synthesis (for csc-derived
runs) or to a clear excerpt of the freeform brief (for freeform
runs)?

→ **BLOCKER** if the item appears to be manufactured from the
drafter's prior knowledge with no traceable source.
→ **NONE** otherwise.

### Axis 2 — Path conflict

Does the cited `Where:` path conflict with already-shipped code?
Cross-check the file paths against CONTEXT.md "Recently shipped"
(every section) AND `git log --oneline -50`.

→ **BLOCKER** if the path is already shipped under a different
proposal ID.
→ **MAJOR** if the file exists but the proposed addition would
touch shipped logic without an "additive" declaration.
→ **NONE** if the path is new or the addition is a clear sibling.

### Axis 3 — SOTA citation quality

Is the citation a primary source (textbook + section, paper + DOI /
arXiv, or canonical URL like Sprott's catalog or Scholarpedia entry)?

→ **BLOCKER** if the citation is hand-wavy ("standard reference",
"see the literature").
→ **MAJOR** if the citation is secondary (blog post, generic
Wikipedia article without further specifics) and a primary source
is reasonable to find.
→ **NONE** if the citation is primary and verifiable.

### Axis 4 — Measurable observable

Does the Rationale (or What/Where) name at least one observable
the implementer can test against (Lyapunov value, conserved quantity,
fixed-point location, RICE-anchored test count delta)?

→ **MAJOR** if no observable is named — `/milestone-pipeline`'s
Phase 3 "Test" gate requires it.
→ **NONE** if at least one observable is named.

### Axis 5 — Effort calibration

Is the effort sizing consistent with comparable past ships?
Reference data (from CONTEXT.md "Recently shipped"):
- D1 (Lyapunov spectrum GUI surface) — S
- CSC-011 (0-1 test for chaos, numpy) — S
- CSC-012 (weighted Birkhoff average) — S
- N2 (4D Rössler hyperchaos) — S
- N1 (discrete-maps subsystem, 4 maps) — M
- N3 (Mackey-Glass DDE + new DDE integrator) — M
- D2 (bifurcation-diagram tool with new plot infra) — L
- D4 (basin-of-attraction map, depends on JAX) — L

→ **BLOCKER** if the item is sized > L without being split.
→ **MAJOR** if the sizing is off by ≥ 1 t-shirt size from the
nearest comparable.
→ **MINOR** if the sizing drifts by ≤ 1 size with reasonable
justification.
→ **NONE** if calibrated.

### Axis 6 — Native + no foreign-compile

Does the item require:
- A web framework (Flask / FastAPI / Django serving HTML)
- Electron / Tauri / WebGL
- User-side compilation of Julia / Rust / C++ / Fortran

→ **BLOCKER** if any of the above. The drafter should have caught
this — surface it as a drafter QC failure in the calibration
section.

Native GPU rendering via VisPy / ModernGL / VTK is NOT a violation.
Wheels with bundled precompiled binaries (numbalsoda, scikit-sundae,
numba) ARE acceptable.

### Axis 7 — Additive over invasive

Does the item modify a core abstraction?
- `core/base.py` `DynamicalSystem` signature
- `integrators/_protocol.py` `Integrator` protocol
- `visualization/renderer.py` `Renderer3D` per-frame contract

→ **MAJOR** if invasive without explicit justification + a
"this is additive, existing tests must pass" declaration in the
What/Where blocks.
→ **MINOR** if it adds a sibling class (e.g. `DiscreteSystem`).
→ **NONE** if purely additive (new module, new test).

### Axis 8 — Bundle coherence

Does the item belong with the other items in this proposal, or is
it an orphan category? E.g. one perf-only-refactor bundled with five
new-system items.

→ **MINOR** for orphan-category items. The refiner should either
widen the proposal title or split the item out.
→ **NONE** if the category clusters with the rest of the bundle.

### Axis 9 — Undeclared dependency

Does the item depend on something not yet shipped AND not in this
proposal? Cross-check the sequencer's DAG.

→ **MAJOR** if there's an un-met dependency that isn't called out
in the item's "Depends on" line.
→ **NONE** if dependencies are met or explicitly noted.

### Axis 10 — Risks / open questions populated

Is the item's "Risks / open questions" subsection still the
placeholder text `(populated after critique)`?

At the critique phase it SHOULD still be the placeholder. The
refiner populates it. This axis is here as a checkpoint so the
refiner can't quietly skip the step.

→ **NONE** always at critique time. If the drafter populated it
prematurely with substantive content, flag as MINOR (the refiner
will see the drafter's pre-population and decide whether to keep
it).

## Per-item output shape

For each item ID in the draft (e.g. `N1`, `D3`, `V2`):

```
### {Item ID} — {Title}

| Axis | Severity | Note |
|---|---|---|
| 1. Source traceability | NONE | Traces to CSC-2026-q2-broadening-011. |
| 2. Path conflict | NONE | `core/chaos_test.py` is new. |
| 3. SOTA citation quality | NONE | Cites Gottwald & Melbourne, arXiv 0906.1418. |
| 4. Measurable observable | NONE | "K statistic ≈ 1 for chaotic Lorenz, ≈ 0 for periodic." |
| 5. Effort calibration | NONE | S — comparable to D1 (S). |
| 6. Native + no foreign-compile | NONE | Pure numpy. |
| 7. Additive over invasive | NONE | New file. |
| 8. Bundle coherence | NONE | Diagnostic alongside other diagnostics. |
| 9. Undeclared dependency | NONE | No external deps. |
| 10. Risks / open questions populated | NONE | Placeholder present. |

**Overall:** NONE
**Recommended action:** proceed
```

## Cross-item concerns

After per-item evaluation, write a "Cross-item concerns" section:
- **Cycles** in the sequencing DAG (sequencer should have flagged;
  re-cite).
- **Path overlaps** — two items targeting the same `Where:` file.
- **Effort stacking** — > 2 L-sized items in a row in the sequencing
  table is a smell.
- **Scope creep** — items collectively expand the project surface
  beyond the proposal's stated title/scope.
- **Calibration check** — actual severity distribution vs. target.

## Output document

```
# Critique — draft-proposal <ID>

## TL;DR
(3 sentences: BLOCKER count, clean items, overall verdict.)

## Per-item axes
(Sections above, one per item.)

## Cross-item concerns
(...)

## Calibration check
- Total axes evaluated: N (= 10 × item_count)
- BLOCKER: X (target: 5-15% of total)
- MAJOR: X (target: 15-30%)
- MINOR: X (target: 20-30%)
- NONE: X (target: 30-60%)

If calibration is off (< 5% BLOCKER or > 30% BLOCKER), explain.

## Recommended dispositions

- **DROP**: <ID> — <BLOCKER axis>
- **REDESIGN**: <ID> — <BLOCKER axis + redesign hint>
- **MITIGATE**: <ID> — <MAJOR axes>
- **PROCEED**: <ID> — <NONE-only or NONE+MINOR>
```

## Hard rules

- **Walk EVERY item.** No skipping.
- **Cite file:line / source URL on every BLOCKER or MAJOR.**
- **Do NOT propose new items.**
- **Do NOT soften severity to be friendly.**
- **Do NOT inflate severity to look thorough.**

## Anti-patterns

- **Drafter-writes-the-critique.** A single role doing both misses
  ~70% of real objections (self-critique blind spot). The pipeline
  enforces separation by running the critic as a fresh sub-agent
  in worktree isolation.
- **Generic BLOCKERs.** "This feels risky" is not a BLOCKER. Cite
  the specific architectural lock, shipped commit, or missing
  citation.
- **Re-litigating the item's value.** Your job is the 10 axes,
  not "is this worth doing". RICE ranking happened in
  `/capability-scout`; you're checking proposal hygiene.
- **Soft-pedaling because the drafter is "another AI".** No.
  Calibrated criticism is the deliverable.
