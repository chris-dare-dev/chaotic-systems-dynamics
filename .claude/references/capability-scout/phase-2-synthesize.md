# Phase 2 — Synthesize

## Purpose

The main session reads EVERY brief end-to-end, deduplicates findings
across briefs, cross-links evidence, surfaces triangulation strength,
applies a fixed taxonomy + t-shirt sizing, and writes
`artifacts/synthesis.md`.

**This phase runs in the main session, NOT a sub-agent.** Synthesis
requires holding all 4 briefs in working memory simultaneously; a
sub-agent's fresh context would have to re-load every brief, which
defeats the purpose.

## Inputs

- All briefs at `.claude/notes/capability-scouts/<ID>/survey-briefs/*.md`.
- `state.json` for `agents_dispatched` / `agents_returned` (sanity check).

## Output

`.claude/notes/capability-scouts/<ID>/artifacts/synthesis.md`.

## Protocol

### 1. Read every brief end-to-end

Do NOT skim. The triangulation evidence lives in cross-brief specifics.
A candidate cited by one brief is weaker evidence than one cited by
three independent lenses.

### 2. Build the candidate catalog

Use this entry shape per candidate:

```markdown
### <ID> — <Title>

**Category:** new-system | new-integrator | new-diagnostic | performance |
visualization | workflow | educational
**Triangulation:** N briefs (list which: competitive, academic, oss,
internal-adversary)
**Foundational?:** yes if other candidates depend on this one;
otherwise no
**T-shirt:** XS (0.25d) / S (1d) / M (3d) / L (8d)

**What:** one-sentence description.

**Where:** target file paths (`src/.../foo.py`).

**Why now:** one-paragraph rationale — what makes this the right
investment given current state of the project.

**SOTA reference:** citation + URL (or file:line for internal-adversary
candidates).

**Evidence from briefs:**
- Competitive: <one-line excerpt + brief filename>
- Academic: ...
- OSS: ...
- Internal-adversary: ...

**Risks / open questions:** 2-4 bullet points the challenger should
evaluate.

**Depends on:** other candidate IDs in this synthesis (or "none").
```

### 3. Deduplicate

Multiple briefs will surface the same candidate under different names.
Merge them. Cite all the briefs that surfaced it under "Triangulation".

A candidate cited by ≥ 2 briefs gets confidence-boosted by the RICE
formula in Phase 4. A foundational candidate (one other candidates
depend on) gets a separate bonus. Both are *additive* — a foundational
candidate cited by all 4 briefs is the highest-confidence shape.

### 4. Apply the fixed taxonomy

Every candidate MUST land in one of:
- `new-system` — adds an entry under `src/chaotic_systems/systems/`
- `new-integrator` — adds an entry under `src/chaotic_systems/integrators/`
- `new-diagnostic` — adds a function/class under `src/chaotic_systems/core/`
- `performance` — speeds up existing code without changing the API
- `visualization` — touches `src/chaotic_systems/visualization/`
- `workflow` — touches `src/chaotic_systems/gui/` (panels, controls)
- `educational` — touches `docs/` / `examples/` / educational_notes

If a candidate doesn't fit, either split it into multiple candidates
or rephrase the taxonomy. Do NOT invent ad-hoc categories.

### 5. T-shirt sizing

Use this scale (calibrated to past ships):
- **XS** (0.25 person-days) — a docstring + a constant. E.g.
  "add `educational_notes` on Chua".
- **S** (1 day) — a single file. D1 and N2 were both S.
- **M** (3 days) — multiple files, one new abstraction. N3 (DDE +
  Mackey-Glass) was M.
- **L** (8 days) — a new subsystem with multiple integration points.
  Discrete-maps subsystem (proposed N1) was L. Bifurcation tool
  (proposed D2) was L.

If a candidate is > L, split it.

### 6. Surface foundationals explicitly

A candidate is foundational if ≥ 2 other candidates depend on it.
Tag them at the top of the synthesis. The Phase 4 RICE bonus is +30%.

### 7. Honor the internal-adversary's reject list

If the internal-adversary's brief lists a "reject" item, do NOT
include it in the candidate catalog. Surface the rejection in a
"Rejected by internal-adversary" section at the bottom of the
synthesis with the rationale.

## Final document structure

```markdown
# Synthesis — capability-scout <ID>

## TL;DR
(5 sentences: candidate count, foundational candidates, top 3 by
triangulation strength, dominant themes.)

## Foundational candidates
(Bullet list with IDs — these get +30% in Phase 4.)

## Candidates
(Entries in the shape above, numbered as `CSC-<ID>-001`, `-002`, etc.
where `<ID>` is the capability-scout run ID.)

## Themes across briefs
(2-4 paragraphs. What patterns recur? What's the "weather" of the
external research? E.g. "Three of four briefs cited GPU-via-JAX
paths; the academic brief's RQA/0-1-test focus suggests
diagnostic-density is the high-ROI direction.")

## Triangulation table
| Candidate | Competitive | Academic | OSS | Internal-adversary |
|---|---|---|---|---|
| CSC-...-001 | ✓ | | ✓ | |
| ... | | | | |

## Rejected by internal-adversary
(Items the internal-adversary explicitly rejected; cite their
rationale per item.)

## Cross-brief calibration notes
(If one brief dominated the candidate count, note it. If two briefs
strongly disagree on something, surface the disagreement explicitly
for the challenger to evaluate.)
```

## Hard rules

- **Every candidate must trace to ≥ 1 brief.** No manufactured
  candidates from the synthesizer's prior knowledge.
- **Cite the brief filename + line/section** for every triangulation
  link. The challenger will follow these.
- **Numbering is `CSC-<ID>-NNN`.** This is the stable ID used by
  Phase 3 (challenge) and Phase 4 (priority).
- **The synthesis is the single source of truth for the candidate
  catalog.** The challenge and final report reference it by ID.
- **Do NOT propose new categories.** Use the fixed 7.
- **Do NOT write code.** This is a meta-document.

## Failure modes

| Failure | Recovery |
|---|---|
| < 5 candidates total after dedup | The pipeline produced noise. Either re-dispatch Phase 1 with a sharper `--brief`, or treat as "no priority work this cycle" and surface accordingly. |
| > 25 candidates | You probably didn't dedupe hard enough. Re-pass and merge near-duplicates. |
| All candidates from one brief | The other 3 briefs were thin. Surface this in cross-brief calibration; consider re-dispatch with different scope. |
| Candidate doesn't fit the 7 taxonomy | Either split it or revisit the brief — sometimes the agent surfaced something out-of-scope. |

## Anti-patterns

- **Synthesizing from TL;DRs only.** Triangulation lives in the
  specifics. Read every entry of every brief.
- **Inventing candidates.** The synthesizer is a deduplicator + classifier,
  not a generator. If you think of a candidate that's not in any brief,
  it goes in a "synthesizer's note" section at the bottom, NOT in the
  catalog, and gets explicitly flagged for the challenger.
- **Over-tagging foundationals.** A candidate is foundational only if
  ≥ 2 other candidates **explicitly depend on it**. Implicit
  dependencies don't count.
- **Sparing weak candidates.** If a candidate is cited by only 1 brief
  and the case is thin, INCLUDE IT with `Triangulation: 1 brief
  (weak)` — let the challenger handle the elimination. Synthesizer
  doesn't gatekeep.
