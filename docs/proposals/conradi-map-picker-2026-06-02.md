# Conradi Map-Preset Picker & Multi-Map Render Pipeline — 2026-06-02

## TL;DR

Five post-completion follow-ups that turn the shipped Conradi attractor panel into
a two-map (Conradi + Clifford) attractor studio. **CMP-001** is the foundational
plumbing item: threading `map_fn` + `extent` through the three existing worker call
sites unlocks every user-visible feature that follows. The obvious next ship is
`/milestone-pipeline CMP-001` (the forwarding pass), immediately followed by
CMP-005 (preset constants, XS cost) then CMP-002 (the picker UI). CMP-003
(Clifford JIT kernel) and CMP-004 (per-map screening) are peer items that should
ship concurrently with or immediately after CMP-002: shipping the picker without
addressing the silent-wrong-LLE screening bug (CMP-004) requires at minimum a
"Screen (a,b)" disable guard for non-Conradi maps, which is a hard deliverable of
CMP-002. Zero net-new runtime dependencies across all five items.

## Sequencing

| Order | Item | Effort | Why first / why not |
|---|---|---|---|
| 1 | CMP-001 — Generalize panel worker plumbing (`map_fn` + `extent`) | S | foundational wire-up; no deps; unblocks CMP-002 and CMP-004 |
| 2 | CMP-005 — Art-map preset catalogue (named parameter sets + registry) | XS–S | no deps; feeds CMP-002; cheapest win, smaller than CMP-003 |
| 3 | CMP-003 — Clifford JIT kernel + per-map kernel registry | M | no deps; independent of picker UI; ship concurrently with CMP-002 for full-quality Clifford animation |
| 4 | CMP-002 — Map-preset picker UI (`QComboBox` + dynamic parameter form) | M | depends on CMP-001 (plumbing) and CMP-005 (presets); the user-visible payoff |
| 5 | CMP-004 — Per-map screening generalization (`lyapunov_grid` accepts a map) | M | depends on CMP-001 and CMP-002; fixes the silent-wrong-LLE bug when a non-Conradi map is selected |

## Items

### CMP-001 — Generalize panel worker plumbing (promotes CSC-2026-06-01-conradi-followups-001)

- **What:** Thread `map_fn` and `extent` through `_ConradiWorker`, `_AnimWorker`,
  `_build_figure`, and `param_path.precompute_loop_frames` so the already-general
  `attractor_density.render`/`accumulate` pipeline can render any registered art-map,
  not just Conradi.

- **Where:**
  - `src/chaotic_systems/gui/conradi_panel.py` — `_ConradiWorker.__init__` / `run`
    (add `map_fn`, `extent` fields, forward to `render`,
    `conradi_panel.py:124-171`); `_build_figure` (read `extent` arg instead of
    hard-coded `DEFAULT_EXTENT`, `conradi_panel.py:328`); `_AnimWorker` (forward to
    `precompute_loop_frames`, `conradi_panel.py:247-254`).
  - `src/chaotic_systems/visualization/param_path.py` — `precompute_loop_frames`
    gains `map_fn` + `extent` kwargs forwarded to both the pre-scan `accumulate`
    and the per-frame `render` (`param_path.py:181-202`).
  - Tests: extend `tests/visualization/test_param_path.py` (the existing
    `test_precompute_uses_fixed_count_max_for_every_frame` byte-identity contract
    must pass the same `map_fn` to both sides for the default Conradi path);
    `tests/gui/test_conradi_panel.py` (worker instantiation smoke tests).

- **SOTA reference:** N/A (internal plumbing). Anchors:
  `attractor_density.py:377-378` (render already accepts `map_fn`/`extent`); the
  four coupling points identified in the internal-adversary brief A1/A4/S1.

- **Effort:** S — mechanical forwarding across three call sites plus one test
  update; all four target lines are already identified.

- **Rationale:** Every GUI path to Clifford is currently blocked by these four
  coupling points; `attractor_density.render` already accepts both kwargs. This is
  the smallest load-bearing change and the prerequisite for CMP-002 and CMP-004.
  Shipping it first de-risks the picker and the screening generalization. All
  changes are additive with defaults that preserve the existing Conradi behavior,
  so no existing GUI test should regress. Observable: after CMP-001, manually
  passing a Clifford `map_fn` + `extent` to `_ConradiWorker` via a unit test
  produces a non-trivial multi-lobe RGBA image, and the byte-identity animation
  contract holds for the default Conradi path unchanged.

- **Risks / open questions:** `test_precompute_uses_fixed_count_max_for_every_frame`
  (`test_param_path.py:62-79`) must pass the **same `map_fn`** to both the pre-scan
  `accumulate` call and the per-frame `render` call once the kwarg exists — verify
  the byte-identity contract holds for the default Conradi path unchanged. The
  draft's Rationale states this guarantee; the implementer must verify it
  explicitly in the test update, not assume it. All kwargs must carry Conradi
  defaults so no existing GUI test regresses.

---

### CMP-005 — Art-map preset catalogue: named parameter sets + registry (promotes CSC-2026-06-01-conradi-followups-005)

- **What:** A curated catalogue of named parameter sets per art-map — Bourke's
  reference Clifford sets (`(-1.4, 1.6, 1.0, 0.7)`, `(1.7, 1.7, 0.6, 1.2)`,
  `(-1.7, 1.3, -0.1, -1.21)`) and Conradi's two canonical stills (`(5.46, 4.55)`,
  `(1.7, 2.3)`) — surfaced as a per-map "Preset" `QComboBox` that populates the
  parameter controls. Code-resident as a `CLIFFORD_PRESETS` constant (and a
  symmetric `CONRADI_PRESETS`), not YAML or file I/O.

- **Where:**
  - `src/chaotic_systems/systems/clifford.py` — `CLIFFORD_PRESETS:
    list[tuple[str, float, float, float, float]]` constant near the existing
    `_DEFAULT_A / _DEFAULT_B / _DEFAULT_C / _DEFAULT_D` constants; optionally a
    symmetric `CONRADI_PRESETS` constant in `systems/conradi.py`.
  - `src/chaotic_systems/gui/conradi_panel.py` — a "Preset" `QComboBox` per map
    (consumed by CMP-002's `QStackedWidget` form), populated from the map's
    `*_PRESETS` constant.
  - Tests: `tests/systems/test_clifford.py` — `CLIFFORD_PRESETS` is a non-empty
    list; every entry renders a non-trivial figure through `attractor_density`
    (spot-check one entry at 200² resolution); each preset's parameters are
    within `CliffordMap`'s declared parameter range.

- **SOTA reference:** Paul Bourke, "Clifford Attractors",
  http://paulbourke.net/fractals/clifford/ (the reference parameter sets cited
  per entry); Sprott (1993), DOI 10.1016/0097-8493(93)90082-K (screening
  criterion confirming these are curated chaotic/aesthetic points); Conradi
  `Nice_orbits.ipynb`, github.com/profConradi/Python_Simulations (source of the
  two Conradi canonical stills).

- **Effort:** XS-S — a named-constant list plus the preset `QComboBox` in CMP-002's
  form; smallest item in the bundle.

- **Rationale:** Without curated presets the user faces a blank four-slider
  Clifford form with no starting point. This mirrors the `colormaps.available()`
  registry pattern already shipped (CSC-009): a thin list on top of the existing
  `core/base.Parameter` schema, zero new infrastructure. Keeping presets as
  code-resident constants (not YAML) avoids any file-I/O or schema dependency.
  Observable: selecting a Bourke preset from the dropdown populates the `(a, b,
  c, d)` spinboxes and a subsequent Render produces a recognizable multi-lobe
  figure. A future "Save preset" (QFileDialog + JSON) is explicitly out of scope.

- **Risks / open questions:** None identified by Phase 3 critique. Keep the list
  small (3-5 curated Clifford sets), cite Bourke per entry, and do not build the
  user-save path now (parking lot).

---

### CMP-003 — Clifford JIT kernel + per-map kernel registry (promotes CSC-2026-06-01-conradi-followups-003)

- **What:** A Clifford `@maybe_njit(cache=True)` fused iterate-and-accumulate
  kernel plus a per-map kernel registry replacing the `map_fn is conradi_map`
  identity guard in `accumulate()`, so Clifford (and any future art-map) takes the
  numba fast path instead of the ~5-10x slower NumPy fallback. Preserves the
  single-thread-no-race scatter-add contract (`NO parallel=True`), byte-
  reproducibility, and numba/NumPy aggregate-agreement.

- **Where:**
  - `src/chaotic_systems/visualization/attractor_density.py` — add
    `_accumulate_clifford_jit` sibling to `_accumulate_lattice_jit` (`:137-174`);
    replace the `accumulate()` dispatch gate `use_numba = ... and (map_fn is
    conradi_map)` (`:232-233`) with a registry keyed on map identity / subclass
    (NOT the `make_clifford_map_fn` closure — a fresh object each call always fails
    the identity check, AP1). `accumulate()` / `render()` gain a
    `map_kwargs: dict[str, float]` parameter (or the registry closes over `c, d`
    via a factory) so Clifford's kernel receives its secondary parameters.
  - Tests: `tests/visualization/test_attractor_density.py` — Clifford takes the
    numba path when numba is available; numba and NumPy paths bin equal total mass
    (`n_points² * n_iter`, since the bounded Clifford map drops nothing); per-cell
    correlation > 0.8 (the chaotic-map guard against an incorrect JIT port).

- **SOTA reference:** Draves & Reckase (2003), *The Fractal Flame Algorithm*,
  https://flam3.com/flame_draves.pdf (one accumulation loop per variation —
  "variation dispatch" — the architectural precedent for a per-map kernel
  registry); numba factory-closure pattern, numba readthedocs.io/en/stable/
  (BSD-2). Bannister & Nowrouzezahrai (2024), arXiv:2406.09328 (informational
  confirmation that per-kernel dispatch remains the practical standard).

- **Effort:** M — the kernel itself is ~25 lines; the structural work is the
  registry and the `map_kwargs` signature extension through `accumulate` / `render`.

- **Rationale:** `make_clifford_map_fn(c, d)` returns a new closure on every call,
  so the current identity guard permanently rejects it and Clifford silently renders
  on the slow NumPy path. The registry fix corrects this and gives a low-boilerplate
  "add a kernel per art-map" pattern for future maps. The registry MUST key on map
  identity / subclass, not the closure (AP1). Observable: with numba present,
  Clifford rendering is within ~2x of Conradi throughput; the three test contracts
  (byte-reproducible, equal total mass, correlation > 0.8) all hold.

- **Risks / open questions:**
  - **AP1 (MAJOR mitigated):** If `map_kwargs: dict[str, float]` is added to
    `accumulate()` / `render()`, specify `map_kwargs: dict[str, float] = {}` as
    the default — the 14 existing `test_attractor_density.py` tests call these
    functions with no `map_kwargs` argument and must pass unchanged. The preferred
    alternative is the factory-closure approach: key the registry on
    `DiscreteSystem` subclass and close over `c, d` in the registered factory,
    avoiding any signature change to `accumulate`/`render` entirely. Either path
    is acceptable; the implementer must commit to one before writing code and
    confirm the 14-test suite stays green.
  - **AP2:** The Clifford kernel must carry an explicit `parallel=False` to guard
    against inadvertent enabling of auto-parallel hints at the numba level.
  - The `test_numba_and_numpy_paths_agree` (correlation > 0.8) and
    `test_byte_reproducible` contracts must have Clifford counterparts added
    alongside the existing Conradi assertions.

---

### CMP-002 — Map-preset picker UI: QComboBox + dynamic parameter form (promotes CSC-2026-06-01-conradi-followups-002)

- **What:** A map-selector `QComboBox` in the Conradi panel that switches the
  renderer (and animation/screening where generalized) between registered art-maps —
  Conradi (`a`, `b`) and Clifford (`a`, `b`, `c`, `d`) — with a dynamic parameter
  form (Clifford needs `c`, `d` controls Conradi does not; `a`, `b` range changes
  from `[0, 2π]` to `[-3, 3]`), per-map render extent, and per-map default
  parameter sets. Implemented as a `QComboBox` driving a `QStackedWidget` of
  per-map `QFormLayout` pages, hand-rolled from `DiscreteSystem.parameters` — zero
  new dependencies.

- **Where:**
  - `src/chaotic_systems/gui/conradi_panel.py` — `_build_panel_class()` controls
    block (`:394-474`); worker instantiation in `_on_render` extended to pass the
    selected map's `map_fn`/`extent` (depends on CMP-001 forwarding); per-map
    animation-loop defaults for the `param_loop` centre/radius
    (`conradi_panel.py:270-286`).
  - `src/chaotic_systems/visualization/param_path.py` — `param_loop` centre/radius
    defaults are Conradi-tuned (`[0, 2π]²`); Clifford's `[-3, 3]²` domain needs
    different defaults or a suppressed inset (`param_path.py:49-60`).
  - Tests: `tests/gui/test_conradi_panel.py` — map picker exists with stable object
    names, switching maps swaps the form and updates the worker's `map_fn`/`extent`,
    selecting Clifford + Render produces a multi-lobe figure with existing panel
    tests green.

- **SOTA reference:** HoloViz `attractors.py` per-attractor class hierarchy with
  auto-regenerated controls (MIT,
  https://raw.githubusercontent.com/holoviz-topics/examples/main/attractors/attractors.py);
  ParaView `pqPropertyWidgetDecorator` hide/show idiom (BSD-3, concepts only). The
  internal model is the existing `colormaps.available()` / `get()` registry pattern
  (CSC-009, already shipped).

- **Effort:** M — the dynamic `QStackedWidget` form is the bulk; range and default
  swaps are mechanical once CMP-001 forwarding and CMP-005 presets are in place.

- **Rationale:** This is the user-visible payoff of the entire bundle. `CliffordMap`
  (CSC-008) ships full render glue and is registered in `list_maps()` but is
  completely unreachable from the GUI today. The panel already hand-rolls a
  `QFormLayout`; extending it to swap on map selection follows the established
  pattern across all five analysis panels. This item is a wire-up of already-shipped
  Clifford glue (a D1-class connection), not a re-implementation. Observable:
  selecting Clifford + Render in the panel produces a non-trivial multi-lobe figure;
  switching back to Conradi restores the canonical still at `(5.46, 4.55)` with all
  existing panel tests green. The silent-wrong-LLE risk (shipping without CMP-004)
  is mitigated by a required disabled "Screen (a,b)" button for non-Conradi maps
  until CMP-004 lands.

- **Risks / open questions:**
  - **Widget attribute stability (MAJOR mitigated):** The `QStackedWidget` restructure
    of `_build_panel_class()` (`:394-474`) moves the existing Conradi controls into
    a stacked page. All existing `ConradiPanel` instance attributes — `self.a_spin`
    (`objectName="conradi_a"`), `self.b_spin` (`objectName="conradi_b"`),
    `self.n_points_spin`, `self.n_iter_spin`, `self.bins_spin`, `self.cmap_box`,
    `self.tone_box`, `self.bloom_check` — MUST remain as panel-level attributes
    after the restructure (i.e., stored on `self`, not buried inside the stacked
    page without a panel-level reference). The 10 CSC-007 tests in
    `tests/gui/test_conradi_panel.py` access these widgets by attribute and by
    `objectName`; all 10 must pass unchanged. If the `QStackedWidget` wraps them in
    a nested layout, the implementer must explicitly re-assign `self.a_spin = ...`
    etc. after construction.
  - **"Screen (a,b)" disable guard (MAJOR mitigated, hard deliverable):** Shipping
    CMP-002 without CMP-004 creates a silent-wrong-LLE display: `_ScreenWorker`
    calls `lyapunov_grid(self._grid)` with no map argument, so it always shows
    Conradi's LLE plane regardless of the selected map. Disabling the "Screen (a,b)"
    button for any non-Conradi map selection is a **required deliverable** of this
    item — not an optional mitigation. The button must re-enable only when Conradi
    is selected, until CMP-004 lands and generalizes the screening path.
  - **Per-map animation-loop defaults:** The `(a,b)` animation inset
    (`_loop_polyline`, `param_loop` defaults centred on `(5.46, 4.55)` / `[0, 2π]²`)
    is wrong for Clifford's `[-3, 3]²` domain. Implement per-map loop defaults or
    suppress the inset for Clifford until a Clifford loop geometry is defined.
  - **Clifford animation quality without CMP-003:** If CMP-003 is not shipped
    concurrently, the NumPy fallback at `_ANIM_N_POINTS=220` will be slow for
    Clifford animation; use Clifford-specific lighter animation defaults (AP4) as a
    stopgap.

---

### CMP-004 — Per-map screening generalization: `lyapunov_grid` accepts a map (promotes CSC-2026-06-01-conradi-followups-004)

- **What:** Generalize `attractor_screen.lyapunov_grid` (currently inlines the
  Conradi recurrence and its analytic Jacobian over `(grid, grid)` arrays) to
  accept a vectorized map step and a vectorized Jacobian-push (`J·v` product per
  cell), so "Screen (a, b)" computes the selected map's LLE landscape rather than
  always Conradi's. Includes per-map sweep domain (`SCREEN_A_RANGE` /
  `SCREEN_B_RANGE` are currently hardcoded to `(0, 2π)` for Conradi).

- **Where:**
  - `src/chaotic_systems/visualization/attractor_screen.py` — `lyapunov_grid`
    gains `step_fn=None` / `jacobian_fn=None` additive kwargs; default `None`
    → Conradi path (byte-stable for existing tests). Clifford's vectorized
    Jacobian-push over `(grid, grid)` arrays is a new helper (not the existing
    scalar `CliffordMap.jacobian` at `clifford.py:161-188` — reusing the scalar
    method would destroy vectorization, AP3). Clifford sweeps `(a, b)` with
    `(c, d)` fixed; sweep domain becomes per-map.
  - `src/chaotic_systems/gui/conradi_panel.py` — `_ScreenWorker` (`:191`)
    currently calls `lyapunov_grid(self._grid)` with no map argument, silently
    producing Conradi's plane regardless of the selected map (the sharpest
    correctness finding of the scout run). CMP-004 passes the selected map's
    `step_fn` / `jacobian_fn` through; as a stopgap inside CMP-002, the "Screen
    (a, b)" button is disabled for non-Conradi maps until this item lands.
  - Tests: `tests/visualization/test_attractor_screen.py` — existing Conradi
    tests pass unchanged (default signature backward-compatible); new Clifford
    screening test at canonical params `(-1.4, 1.6)` reports a positive LLE
    (confirming the Clifford chaotic regime, per `test_clifford.py`).

- **SOTA reference:** Sprott, J.C. (1993), "Automatic generation of strange
  attractors", *Computers & Graphics* 17(3):325-332,
  DOI 10.1016/0097-8493(93)90082-K (the LLE-screening principle, already cited in
  `attractor_screen.py`); Benettin et al. (1980), *Meccanica* 15:9,
  DOI 10.1007/BF02128236 (the tangent-map estimator). Clifford analytic Jacobian
  source: `CliffordMap.jacobian`, `clifford.py:161-188`.

- **Effort:** M — the vectorized Clifford Jacobian-push is the non-trivial part
  (the per-cell `(grid, grid)` tangent-vector propagation over Clifford's
  sinusoidal partial derivatives); the signature generalization and per-map domain
  wiring are mechanical.

- **Rationale:** This item closes a silent correctness bug: `_ScreenWorker` calls
  `lyapunov_grid(self._grid)` with no map argument, so selecting Clifford and
  pressing "Screen (a, b)" would silently display Conradi's LLE plane with no
  error. The existing `test_attractor_screen.py` suite must stay fully green
  (additive `step_fn=None` / `jacobian_fn=None` defaults preserve the Conradi
  path). Observable: a Clifford screening at canonical params `(-1.4, 1.6, 1.0,
  0.7)` reports a positive LLE (chaotic, matching `test_clifford.py` CSC-008
  observable λ₁ ≈ 0.29).

- **Risks / open questions:**
  - **AP3 (vectorized Jacobian, MINOR noted):** `step_fn` must handle the **full
    loop body** — transient discard + accumulation + spread tracking at
    `attractor_screen.py:125-168` — not only the per-step recurrence. The Clifford
    vectorized Jacobian-push is a new helper implementing
    `new_vx = -c·a·sin(a·x)·vx + a·cos(a·y)·vy`,
    `new_vy = b·cos(b·x)·vx - d·b·sin(b·y)·vy` over `(grid, grid)` arrays.
    Do NOT reuse the scalar `CliffordMap.jacobian` (`clifford.py:161-188`) — it
    would destroy vectorization.
  - **Conradi byte-stability:** The default (Conradi) `lyapunov_grid()` signature
    must stay byte-stable with `step_fn=None` / `jacobian_fn=None` defaults so
    `test_attractor_screen.py` passes unchanged. Verify additive kwargs preserve
    the Conradi path exactly.
  - **AP3 push note (vectorized Jacobian):** A future performance uplift could
    vectorize the Jacobian-push across the entire grid as a batched matrix multiply
    — defer to a follow-up item; confirm the scalar-per-cell formulation above is
    correct first.
  - **Conradi `lyapunov_grid` signature byte-stability:** Any additive default
    added to `lyapunov_grid` must use `step_fn=None` / `jacobian_fn=None` (not
    positional), so existing callers that pass only `self._grid` remain correct
    without modification.

---

## Rejected at drafting

None — all five items target native PySide6 + pure-Python extensions of shipped
files, introduce no Julia / Rust / C++ user-compile dependencies, and each
target path is a genuine extension of already-shipped code rather than a
duplicate.

## Rejected at refinement

None — zero BLOCKERs in the Phase 3 critique.

## Reading order

A new contributor should read the **Sequencing** table top to bottom, then read
the **Items** entry for the top item end-to-end before touching any code. The
dependency chain is: CMP-001 (foundational plumbing, no deps) → CMP-005 (preset
constants, no deps, cheapest first) → CMP-003 (Clifford JIT kernel, no deps,
ship concurrently with CMP-002) → CMP-002 (picker UI, depends on CMP-001 +
CMP-005) → CMP-004 (per-map screening, depends on CMP-001 + CMP-002). The two
MAJORs from the Phase 3 critique are both resolved in CMP-002's and CMP-003's
"Risks / open questions" blocks and require no redesign. Run
`/milestone-pipeline CMP-001` to ship the top item.
