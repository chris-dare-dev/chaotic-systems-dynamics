# Phase 3 — Challenge

## Purpose

A single adversarial sub-agent argues AGAINST every candidate in the
synthesis using a 10-axis checklist tailored to this project's locks.
Severity is calibrated: a healthy run sees 30-60% of axes return NONE,
5-15% BLOCKER, 15-30% MAJOR, 20-30% MINOR.

This is the second adversarial pass: Phase 1's internal-adversary
critiqued the EXISTING state (what's already shipped, what's vestigial);
Phase 3's challenger critiques the PROPOSED candidates against the
project's locks. They are distinct roles and must not be merged.

## Inputs

- `artifacts/synthesis.md` from Phase 2.
- All 4 Phase 1 briefs (for cross-checking citations).
- `CLAUDE.md` (architectural locks).
- `CONTEXT.md` (already-shipped).

## Output

`.claude/notes/capability-scouts/<ID>/artifacts/challenge.md`.

## Severity rubric

| Severity | Meaning | Recommended action |
|---|---|---|
| **BLOCKER** | Would prevent shipping as-is. Violates an architectural lock OR duplicates already-shipped work OR has no measurable observable. | Drop or redesign. |
| **MAJOR** | Significant concern; needs explicit mitigation in the candidate's plan. | Mitigate before shipping. |
| **MINOR** | Worth noting but not load-bearing. | Note in the candidate's plan. |
| **NONE** | Passes this axis. | Proceed. |

**Calibration**: in a healthy run, ~30-60% of axes return NONE. If you
flag > 70% MAJOR/BLOCKER, you're inflating. If < 10%, you're
soft-pedaling. The challenger's job is sharp, not friendly.

## The 10-axis checklist

### Axis 1 — Native-only

The frontend is native PySide6 / Qt (see CLAUDE.md "The frontend is
native — do not change that"). Any candidate that proposes:
- A web framework (Flask / FastAPI / Django serving HTML)
- Electron / Tauri
- WebGL / Three.js
- "Open the browser to localhost:something" UX

→ **BLOCKER**.

Native GPU rendering via Vispy / ModernGL / VTK is **NOT** a violation.

### Axis 2 — No foreign-compile

The user installs via `pip install -e ".[dev]"`. Candidates that
require user-side compilation of Julia / Rust / C++ / Fortran are
rejected. Wheels with bundled precompiled binaries (numbalsoda,
scikit-sundae, numba) are ACCEPTABLE.

→ **BLOCKER** if foreign-compile required, **NONE** if precompiled
wheels exist.

### Axis 3 — Python 3.12 + ruff-clean

The project is pinned to Python 3.12. Candidates must:
- Use modern type hints (`list[int]` not `List[int]`, `X | None` not
  `Optional[X]`)
- Have all public APIs typed
- Pass `ruff check src/ tests/` with the existing config
- Module docstrings present

→ **BLOCKER** if it pins < 3.12 or > 3.13; **MAJOR** if untyped public
APIs; **MINOR** if it touches `# noqa` discipline.

### Axis 4 — No test-suite regression

The project ships 184+ tests. Candidates that touch hot paths
(`Renderer3D`, integrators, core abstractions) must include a path
for not regressing existing tests.

→ **MAJOR** if it touches `core/base.py` / `integrators/_protocol.py`
/ `visualization/renderer.py` without an explicit "this is additive"
declaration; **NONE** if it adds a new module under
`src/chaotic_systems/.../<new>.py`.

### Axis 5 — Mathematical correctness

This is a math project. Every candidate that touches numerics MUST
cite a primary source (textbook + section, or paper + DOI/arXiv)
AND must have at least one measurable observable to verify
correctness (energy conservation, Lyapunov spectrum match, fixed
point location, etc.).

→ **BLOCKER** if no citation. **MAJOR** if citation present but no
measurable observable. **NONE** if both.

### Axis 6 — Per-frame cost

The animation tick budget is 16 ms (60 Hz). Candidates that add cost
inside the QTimer-driven render loop (e.g. "compute Lyapunov on every
frame") would break the Catmull-Rom + wall-clock pacing contract.

→ **BLOCKER** if it adds > 5 ms per-frame cost. **MAJOR** if 1-5 ms.
**NONE** if it runs off-thread (`_*Worker` pattern) or out-of-loop.

### Axis 7 — Renderer integration

The renderer's contract is:
- One `pv.PolyData` allocated up-front
- Per-frame: slice the pre-allocated connectivity buffer + write the
  fractional tail point
- Arc-length cache + 4× Catmull-Rom oversample at prerender time
- VTK `Render()` called exactly once per tick

Candidates that propose alternate rendering paths (e.g. "use ImGui
instead of Qt", "draw via VisPy") need to address how they slot in.

→ **MAJOR** if it duplicates or replaces the renderer; **NONE** if it
extends.

### Axis 8 — Additive over invasive

CLAUDE.md says "Prefer additive proposals (new modules, new optional
extras in `pyproject.toml`) over invasive refactors". Candidates that
require modifying existing `core/` abstractions need explicit
justification.

→ **MAJOR** if it modifies `core/base.py`'s `DynamicalSystem`
signature; **MINOR** if it adds a sibling class (e.g.
`DiscreteSystem(DynamicalSystem)`); **NONE** if purely additive.

### Axis 9 — Already shipped

Cross-check against:
- `CONTEXT.md` "Recently shipped"
- Recent git log (`git log --oneline -50`)
- Prior `docs/proposals/capability-roadmap-*.md`

If a candidate duplicates an already-shipped item:

→ **BLOCKER**. Note the shipped commit SHA.

### Axis 10 — Dependency hygiene

A candidate that adds a dependency must:
- Pin a reasonable lower bound
- Be available on PyPI with a wheel for Apple Silicon
- Have a permissive license (MIT / BSD / Apache-2.0 / similar)
- Last release within 18 months
- Not conflict with existing deps' version ranges

→ **BLOCKER** for AGPL / dormant > 18 months / no Apple Silicon wheel.
**MAJOR** for GPL or > 12 months dormant. **MINOR** for tight version
ranges. **NONE** otherwise.

## Per-candidate output shape

For each candidate ID in the synthesis (e.g. `CSC-2026-05-18-001`):

```markdown
### CSC-<ID>-NNN — <Title>

| Axis | Severity | Note |
|---|---|---|
| 1. Native-only | NONE | Pure backend addition. |
| 2. No foreign-compile | NONE | Pure Python. |
| 3. Python 3.12 + ruff | NONE | Matches existing patterns. |
| 4. No test regression | MAJOR | Touches core/lyapunov.py — see line ... |
| 5. Math correctness | NONE | Cites Benettin 1980; observable = spectrum sum. |
| 6. Per-frame cost | NONE | Runs in worker thread. |
| 7. Renderer integration | NONE | No renderer touch. |
| 8. Additive over invasive | NONE | New file under core/. |
| 9. Already shipped | NONE | Not in shipped set. |
| 10. Dependency hygiene | NONE | No new deps. |

**Overall:** MAJOR (axis 4)
**Recommended action:** mitigate — add an explicit "additive only,
no signature change" declaration to the candidate's plan, plus a
test confirming existing lyapunov tests still pass.
```

## Cross-candidate concerns

After per-candidate evaluation, write a "Cross-candidate concerns"
section listing:
- **Conflicts** — pairs of candidates that contradict each other.
- **Ordering dependencies** — if candidate B requires A's
  abstractions, A must ship first; surface this.
- **Scope creep** — if multiple candidates collectively expand the
  project's surface beyond what its current docs describe, surface.
- **Calibration check** — actual severity distribution vs. the
  target. If off, explain why.

## Output document

```markdown
# Challenge — capability-scout <ID>

## TL;DR
(3 sentences: which candidates have BLOCKERs, which are clean,
overall health of the synthesis.)

## Per-candidate axes
(Sections above, one per candidate.)

## Cross-candidate concerns
(...)

## Calibration check
- Total axes evaluated: N (= 10 × candidate_count)
- BLOCKER: X (target: 5-15% of total)
- MAJOR: X (target: 15-30%)
- MINOR: X (target: 20-30%)
- NONE: X (target: 30-60%)

If calibration is off:
- < 5% BLOCKER → re-read CLAUDE.md locks; you may be soft-pedaling
- > 30% BLOCKER → you may be inflating; re-read the rubric
```

## Hard rules

- **Walk EVERY candidate.** No skipping.
- **Cite file:line / source URL on every BLOCKER or MAJOR.**
- **Do NOT propose new candidates.** That's not your role.
- **Do NOT soften severity to be friendly.** The pipeline's value
  depends on calibrated criticism.
- **Do NOT inflate severity to look thorough.** Calibration matters.

## Anti-patterns

- **Synthesizer-writes-the-challenge.** A single role doing both
  misses ~70% of real objections (self-critique blind spot). The
  pipeline enforces separation by running the challenger as a fresh
  sub-agent.
- **Generic BLOCKERs.** "This is risky" is not a BLOCKER. Cite the
  specific architectural lock or shipped commit that it violates.
- **Re-litigating the candidate's value.** Your job is the 10
  axes, not "is this worth doing". Phase 4's RICE ranking handles
  value.
