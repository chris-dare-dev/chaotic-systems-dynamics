# Clifford Animation Loop — non-periodic parameter-path geometry — 2026-06-02

## TL;DR

One item (**CAL-001**) that lifts the last deferral of the
`conradi-map-picker-2026-06-02.md` feature set: the "Animate loop" button is
disabled for non-Conradi maps because `param_path.param_loop` wraps `(a, b)`
with `% 2*pi` — correct for the Conradi map (whose `a, b` are 2*pi-periodic
phase shifts) but **wrong for Clifford**, whose `a, b in [-3, 3]` are
frequencies, not periodic angles. CAL-001 adds a non-wrapping mode to
`param_loop`, a per-map loop geometry, threads a per-map `path_fn` through the
animation worker, generalizes the `(a, b)` inset to the active loop's range, and
re-enables Animate for every registered art-map. Effort **S** (the wrap flag is
two lines; the panel threading mirrors the CMP-002/CMP-004 patterns already in
place). With the Clifford JIT kernel already shipped (CMP-003), Clifford
animation is full-quality at the default frame budget — no lighter stopgap
needed. This is purely additive; the Conradi animation path is byte-stable.

Obvious next ship: `/milestone-pipeline CAL-001 clifford-animation-loop-2026-06-02.md`.

## Provenance

The explicit deferral recorded across CMP-002 (commit `9767af3`) and CMP-004
(commit `3c38269`) of `docs/proposals/conradi-map-picker-2026-06-02.md`:
"Animate is disabled for non-Conradi — Clifford's `(a,b)` aren't 2*pi-periodic,
so the loop geometry needs a `param_path` refactor (the proposal's sanctioned
defer)." All other items of that proposal (CMP-001..005) are shipped; this is
the one remaining follow-up to complete the "attractor studio" (render +
screening + animation for every art-map).

## Sequencing

| Order | Item | Effort | Why first / why not |
|---|---|---|---|
| 1 | CAL-001 — Clifford / non-periodic animation loop geometry | S | only item; no deps (CMP-001 plumbing, CMP-003 kernel, CMP-005 presets all shipped) |

## Items

### CAL-001 — Non-wrapping `param_loop` + per-map animation loop geometry (closes the CMP-002/CMP-004 Animate deferral)

**What:** Give `param_path.param_loop` a `wrap: bool = True` parameter (default
preserves the Conradi `% 2*pi` behaviour); add a Clifford loop geometry centred
in `[-3, 3]`; thread a per-map `path_fn` through the panel's `_AnimWorker` into
`precompute_loop_frames`; generalize the `(a, b)` animation inset to the active
loop's coordinate range; and re-enable the "Animate loop" button for non-Conradi
maps.

**Where:**
- `src/chaotic_systems/visualization/param_path.py`
  - `param_loop` (`:66-109`): add `wrap: bool = True`; when `False`, return the
    raw `(center + da, center + db)` without the `% _TWO_PI` reduction. The
    seamless-loop property (`param_loop(0) == param_loop(1)`) is independent of
    wrapping — every Fourier term is periodic in `t` — so it holds for both
    modes. Default `True` keeps the existing Conradi tests byte-stable.
  - Add a Clifford loop default: named constants `CLIFFORD_LOOP_CENTER`,
    `CLIFFORD_LOOP_RADIUS` (e.g. `(-1.4, 1.6)` / `(0.8, 0.8)`, chosen so the
    swept `(a, b)` stay strictly inside `[-3, 3]`), with no harmonics so the
    ellipse stays compact. Expose a small `clifford_param_loop` (a
    `functools.partial(param_loop, center=..., radius=..., wrap=False)`) or let
    the panel build the partial.
- `src/chaotic_systems/gui/conradi_panel.py`
  - `_AnimWorker.__init__` / `run` (`:219-265`): add a `path_fn` field, forward
    it to `precompute_loop_frames(path_fn=...)` (that kwarg already exists,
    shipped in CSC-005).
  - Panel: a per-map `self._loop_path_fn` (Conradi → `None` / the default
    `param_loop`; Clifford → the Clifford partial), set in `_on_map_changed`
    alongside `self._map_fn` / `self._extent`. `_on_animate` passes it to
    `_AnimWorker`.
  - Re-enable Animate for all maps: drop the `is_conradi` gate on
    `self.animate_button` in `_on_map_changed` and `_set_busy` (Screen was
    already ungated by CMP-004; this ungates Animate).
  - `_loop_polyline` (`:329-339`) + `_build_anim_canvas` inset
    (`:840-870`): take the active `path_fn`; derive the inset axis limits from
    the polyline's finite min/max (with a small margin) instead of the
    hard-coded `[0, _TWO_PI]`. The `% 2*pi` NaN-split is only meaningful for the
    wrapping (Conradi) loop — gate it on `wrap` (or on whether a sample-to-sample
    jump exceeds `pi`) so a smooth non-wrapping Clifford loop is not falsely cut.
- Tests:
  - `tests/visualization/test_param_path.py`: `param_loop(0, wrap=False) ==
    param_loop(1, wrap=False)` to machine precision (seamless, non-wrapping); a
    Clifford loop sampled over `t in [0, 1)` keeps all `(a, b)` within
    `[-3, 3]` (no wrap corruption); `precompute_loop_frames(path_fn=clifford
    loop, map_fn=make_clifford_map_fn(c, d), extent=clifford_extent(c, d))`
    returns the requested number of frames, each byte-identical to
    `render(..., count_max=...)` with the same args (the fixed-`count_max`
    contract holds for the Clifford loop too).
  - `tests/gui/test_conradi_panel.py`: selecting Clifford leaves Animate
    **enabled**; `_on_anim_finished` on a small precomputed Clifford loop stores
    the frames and builds the inset without error; the inset axis range tracks
    the Clifford loop (not `[0, 2*pi]`).

**SOTA reference:** The truncated-Fourier / epicycle closed-curve
parameterization in `.claude/notes/conradi-analysis/math-parameterization.md`
(the `param_loop` derivation, already cited for CSC-005). No new external
reference — this is a generalization of the existing seamless-loop construction
(the wrap is an output post-processing choice, not part of the closure
property). Clifford parameter regime: Paul Bourke, "Clifford Attractors",
http://paulbourke.net/fractals/clifford/.

**Effort:** S — the `wrap` flag is ~2 lines; the per-map `path_fn` threading and
button-ungating mirror the CMP-002 (`_active_render_spec`) and CMP-004
(`_active_screen_fns`) patterns already in `conradi_panel.py`; the inset-range
generalization is the only genuinely new logic.

**Rationale:** Completes the "attractor studio" — Clifford already renders
(CMP-002), renders fast (CMP-003), and screens (CMP-004); animation is the only
capability still Conradi-only. The blocker is narrow and well understood: a
single Conradi-specific `% 2*pi` in `param_loop`. Because the Clifford JIT
kernel shipped (CMP-003), Clifford animation runs at the full default frame
budget (no lighter stopgap, retiring CMP-002's AP4 concern). Observable:
`param_loop(0, wrap=False) == param_loop(1, wrap=False)` to ~1e-12; a Clifford
animation loop's sampled `(a, b)` all lie within `[-3, 3]`; and in the panel,
selecting Clifford and pressing Animate then Play produces a seamless morphing
Clifford loop with a correctly-scaled `(a, b)` inset.

**Risks / open questions:**
- **Conradi byte-stability:** `wrap=True` is the default, so `param_loop` and the
  existing animation tests (`test_param_path.py`, the CSC-005 seamlessness + the
  CMP-001 forwarding tests) must pass unchanged. Verify explicitly.
- **Clifford loop stays in-range:** pick `CLIFFORD_LOOP_RADIUS` (and any
  harmonics) so `center ± (radius + sum|harmonics|)` is strictly within
  `[-3, 3]` on both axes; otherwise the swept `(a, b)` could leave the
  CliffordMap parameter range. The proposed `(-1.4, 1.6)` centre / `(0.8, 0.8)`
  radius / no harmonics gives `a in [-2.2, -0.6]`, `b in [0.8, 2.4]` — safe.
- **Inset NaN-split false positives:** the existing `_loop_polyline` inserts
  NaN where `|diff| > pi` to break the Conradi wrap. For a non-wrapping Clifford
  loop this must NOT fire on the smooth curve — gate the split on the wrapping
  mode, or derive the threshold from the loop's own range, so the Clifford inset
  draws as one continuous closed curve.
- **GIF/MP4 export of a Clifford loop:** the export path (CMP-006/CSC-006
  `write_frames`) already consumes whatever frames the panel precomputed, so it
  works for a Clifford loop with no change — but add a quick smoke check that a
  Clifford loop exports a non-empty GIF if export coverage is desired.

## Reading order

Single item — read CAL-001 and ship it with
`/milestone-pipeline CAL-001 clifford-animation-loop-2026-06-02.md`. It depends
on nothing unshipped (CMP-001 worker plumbing, CMP-003 Clifford JIT kernel, and
CMP-005 presets are all on `main`). Optionally run `/draft-proposal
clifford-animation-loop --brief "..."` first if an independent adversarial pass
on this scope is wanted; otherwise it is ready for the milestone pipeline as-is.
