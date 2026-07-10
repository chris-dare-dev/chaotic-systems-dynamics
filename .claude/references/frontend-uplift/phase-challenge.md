# Phase 3 — Challenge

## Purpose

A single adversarial sub-agent argues AGAINST every candidate in the
synthesis using a fixed 11-axis checklist tailored to this project's
visual locks. Severity calibrated: 30-60% NONE, 5-15% BLOCKER.

Distinct from Phase 1's current-state-critic: the critic surveyed
the EXISTING GUI for inconsistencies; the challenger evaluates
PROPOSED candidates against architectural and accessibility locks.

## Inputs

- `artifacts/synthesis.md`.
- All 4 Phase 1 briefs.
- Screenshots under `screenshots/`.
- `CLAUDE.md`, `docs/ui_design.md`, `CONTEXT.md`.

## Output

`.claude/notes/frontend-uplifts/<ID>/artifacts/challenge.md`.

## Severity rubric

| Severity | Meaning | Recommended action |
|---|---|---|
| **BLOCKER** | Violates an architectural lock OR duplicates shipped work OR has no measurable observable. | Drop or redesign. |
| **MAJOR** | Significant concern; needs explicit mitigation. | Mitigate before shipping. |
| **MINOR** | Worth noting but not load-bearing. | Note in the plan. |
| **NONE** | Passes this axis. | Proceed. |

Calibration: in a healthy run, ~30-60% NONE. If > 70% MAJOR/BLOCKER,
you're inflating. If < 10%, you're soft-pedaling.

## The 11-axis checklist

### Axis 1 — Native-only

Native PySide6 / Qt only. No web frameworks, Electron, Tauri, WebGL,
"open the browser to localhost". GPU rendering via VTK / VisPy /
ModernGL is fine.

→ **BLOCKER** if web/Electron/Tauri/WebGL.

### Axis 2 — Worker-thread discipline

The animation tick budget is 16 ms (60 Hz). Candidates that add cost
inside the QTimer-driven loop would break the Catmull-Rom + wall-clock
pacing contract. Heavy compute belongs on a `QThread` worker.

→ **BLOCKER** if it adds > 5 ms per-frame cost. **MAJOR** if 1-5 ms.
**NONE** if off-thread or out-of-loop.

### Axis 3 — Token discipline

All colors / spacing values must come from `theme.PALETTE` (and the
spacing tokens declared in `docs/ui_design.md`). Hex literals or
arbitrary px values are leaks.

→ **MAJOR** if it introduces new leaks. **MINOR** if it doesn't
remove existing leaks but doesn't add new ones. **NONE** if it
strictly uses tokens.

### Axis 4 — Renderer pacing contract

The renderer's contract is documented in `docs/visualization.md`:
single pre-allocated `pv.PolyData`, connectivity slice per frame,
arc-length cache + 4× Catmull-Rom oversample at prerender, exactly
one `Render()` per tick. Candidates that touch this contract need
explicit justification.

→ **BLOCKER** if it adds a second `Render()` per tick. **MAJOR** if
it modifies the cache. **NONE** if it doesn't touch the renderer.

### Axis 5 — Hi-DPI / theme-aware

The user is on Retina (DPR=2). Candidates that bake in screen-pixel
sizes or hard-coded light/dark colors fail this axis. Use logical
pixels via `QFontMetrics` or `devicePixelRatio()`-aware paths.

→ **MAJOR** if it pins a px value that's wrong at 1× or 3×.
**NONE** if DPR-aware.

### Axis 6 — Accessibility (WCAG 2.1 AA)

Focus rings visible on every interactive widget. Contrast ratio
≥ 4.5:1 for body text, ≥ 3:1 for large text. Tab order sensible.
Tooltips on toolbar actions and parameter sliders.

→ **BLOCKER** if it removes focus rings. **MAJOR** if contrast fails
or tooltips missing. **MINOR** if tab order is unconventional.

### Axis 7 — No GUI-test regression

Existing GUI tests (`test_main_window`, `test_transport`,
`test_settings`, `test_lyapunov_panel`, `test_latex_wrap`,
`test_export_estimate`, `test_theme`) pin specific widgets and
their object names.

→ **MAJOR** if it renames widgets or changes object names.
**NONE** if it adds new widgets without touching old ones.

### Axis 8 — Additive over invasive

CLAUDE.md prefers additive proposals. Modifying `main_window.py`'s
layout structure or `_build_window_class` is invasive.

→ **MAJOR** if it restructures `_build_window_class`. **MINOR** if
it adds a new card/panel. **NONE** if it's a new helper widget in
its own file.

### Axis 9 — Already shipped

Cross-check against the current-state-critic's reject list +
CONTEXT.md "Recently shipped" + recent git log.

→ **BLOCKER** with shipped commit SHA cited.

### Axis 10 — Keyboard equivalent for every pointer affordance

Per WCAG 2.1 SC 2.1.1. If a candidate adds a click-only feature with
no keyboard shortcut / tab focus, it fails.

→ **MAJOR** if no keyboard path. **NONE** if `QShortcut` / focusable.

### Axis 11 — Distinctiveness / anti-template (the anti-cookie-cutter lock)

Read `.claude/references/frontend-design-language.md` directly (no reference-fetch MCP tool on
this fleet — Read the file) and score the candidate — and the synthesis as a whole — against the
§5 BAN-1..15 list and the §10 cookie-cutter rubric, translated to this native Qt tool. The live
tells on this surface:

- **BAN-1** — a generic dark-navy "SaaS dashboard in a window" shell instead of the app's ink
  instrument material (Tokyo Night Storm, one accent, semantic-for-state).
- **BAN-4** — falling back to the undirected Qt-default toolkit look: raw system-native widgets,
  no pinned Fusion style, no `theme.PALETTE` / `dark.qss` discipline.
- **BAN-5** — equal panel weight, no lede (the house thesis is "the math is the hero").
- **BAN-6 / BAN-11** — decorative rainbow analysis plots; semantic colors used for decoration.
- **BAN-7** — status-chip soup. **BAN-14** — uniform density. **BAN-15** — cloning another
  panel's shell as this one's identity without a product reason.

Also check the run-level gate: does the synthesis OPEN with the adopted design frame (thesis +
direction + BAN list)? A **frameless catalog is a run-level BLOCKER.** Does the proposed end state
score ≤ 2 on the §10 rubric?

→ **BLOCKER** if the synthesis is frameless OR the proposed state scores 6+ on §10. **MAJOR** if
3-5, or if the candidate introduces a BAN tell with no thesis-argued reason. **NONE** if it is
frame-consistent and ≤ 2.

**INERT axes (web-only — never manufacture a finding from these):** bundle-size KB budget (no
bundler — Python app), React 19 / RSC compatibility (no React), mobile / touch parity (desktop-only
native window), and experiential scroll/parallax/WebGL motion (BLOCKED on S-2; there is no S-1
surface). Name an axis inert if a candidate somehow invokes it; do not score it.

## Per-candidate output shape

Identical to capability-scout's `phase-3-challenge.md`. For each
`FU-<ID>-NNN`, walk the 11 axes, assign severity, set Overall, set
Recommended action.

## Cross-candidate concerns

Same as capability-scout. Include:
- Layout conflicts (candidate A relocates the toolbar; candidate B
  adds icons to it — they intersect).
- Theme conflicts (one candidate adds a new accent color; another
  uses the existing one).
- A11y compound effects (e.g. several candidates add focus rings;
  do they collide visually?).

## Output document

Mirror capability-scout's challenge structure.

## Hard rules

- Walk every candidate.
- Cite a screenshot OR a file:line on every BLOCKER / MAJOR.
- Do NOT propose new candidates.
- Calibration: 30-60% NONE.

## Anti-patterns

- "This looks ugly" is not a severity. Cite the axis.
- Inflating MAJOR to look thorough — calibrate against the rubric.
- Re-litigating the candidate's value. That's Phase 4's job.
