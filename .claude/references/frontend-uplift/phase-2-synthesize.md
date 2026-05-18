# Phase 2 — Synthesize

## Purpose

Main session reads EVERY brief end-to-end (+ inspects the screenshots
where useful), deduplicates findings, cross-links visual evidence with
code citations, and writes `artifacts/synthesis.md`.

**Runs in the main session, NOT a sub-agent.**

## Inputs

- All briefs at `.claude/notes/frontend-uplifts/<ID>/discover-briefs/*.md`.
- Screenshots at `.claude/notes/frontend-uplifts/<ID>/screenshots/`.
- `state.json` for `agents_dispatched` / `agents_returned`.

## Output

`.claude/notes/frontend-uplifts/<ID>/artifacts/synthesis.md`.

## Protocol

### 1. Read every brief + look at every screenshot

Skim is not enough. The triangulation evidence lives in cross-brief
specifics: when visual-scout cites a screenshot showing toolbar
crowding and current-state-critic cites file:line where the toolbar
layout is computed and library-scout cites a `superqt` pattern that
would simplify it, the candidate has 3-brief triangulation.

### 2. Candidate entry shape

```markdown
### FU-<ID>-NNN — <Title>

**Category:** layout | typography | color-theme | iconography |
motion | affordance | accessibility | information-architecture |
workflow | educational

**Triangulation:** N briefs (list which: visual, library, inspiration,
current-state-critic)

**Foundational?:** yes if other candidates depend on this one.

**Wire-up?:** yes if the capability already exists in code (e.g.
declared in theme.PALETTE) but the GUI hand-rolls a different value.

**T-shirt:** XS / S / M / L (0.25d / 1d / 3d / 8d)

**What:** one-sentence description.

**Where:** file paths in src/chaotic_systems/gui/.

**Why now:** one-paragraph rationale.

**Visual evidence:** screenshot path + 1-line callout.

**Inspiration reference:** which tool / library / pattern this borrows
from (cite source).

**Evidence from briefs:**
- Visual: <one-line excerpt + brief filename>
- Library: ...
- Inspiration: ...
- Current-state-critic: ...

**Risks / open questions:** 2-4 bullets for the challenger.

**Depends on:** other FU-<ID>-NNN candidates (or "none").
```

### 3. Deduplicate + apply taxonomy

Same protocol as capability-scout's phase-2-synthesize, but with the
10-category UI taxonomy (above). Numbering is `FU-<ID>-NNN`.

### 4. Honor the current-state-critic's reject list

Any candidate the critic explicitly rejected → drop from the catalog,
surface in "Rejected by current-state-critic" with the rationale.

### 5. Surface foundationals + wire-ups

A candidate is **foundational** if ≥ 2 others depend on it (e.g.
"adopt a 4/8/12/16/24px spacing scale" is foundational for several
subsequent layout candidates).

A candidate is **wire-up** if the capability already exists in code
(e.g. `theme.PALETTE.accent_2` is defined but unused) and only the
application is missing.

Both get bonuses in Phase 4: foundational ×1.3, wire-up ×1.2.

## Final document structure

Mirror the capability-scout synthesis structure, with these
adjustments:

- "Foundational candidates" section.
- "Wire-up candidates" section (UI-specific concept; doesn't exist in
  capability-scout).
- "Visual-evidence index" — table mapping each screenshot to the
  candidates that cite it. Useful for the challenger.
- "Anti-patterns" from the current-state-critic must be cited
  explicitly so the challenger evaluates against them.

## Hard rules

- Every candidate traces to ≥ 1 brief.
- Every visual claim cites a screenshot.
- Cite file:line for every code change.
- Numbering is `FU-<ID>-NNN`.
- Do NOT write code.
- Do NOT propose new categories beyond the 10.

## Anti-patterns

- Synthesizing from TL;DRs only — triangulation lives in specifics.
- Inventing candidates the briefs didn't surface.
- Over-tagging foundationals (only counts if ≥ 2 others EXPLICITLY
  depend on it).
- Including duplicate "modernize the look" candidates without
  specifics. Vague candidates produce vague challenges.
