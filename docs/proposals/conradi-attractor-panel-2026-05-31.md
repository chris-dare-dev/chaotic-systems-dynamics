# Conradi Trigonometric Attractor Panel — 2026-05-31

## TL;DR

A new native PySide6 analysis panel that reproduces Simone Conradi's animated
trigonometric strange-attractor renderer — the iterated map
`x' = sin(x²−y²+a)`, `y' = cos(2xy+b)` (plus a sibling family) rendered as a
density-accumulation "ink-drop" image, animated along a closed `(a,b)`
parameter-space loop, with an optional Lyapunov-exponent screening backdrop.
**10 active items** (down from 12: one dropped, one deferred), with four
foundational pieces first: **CSC-…-001** (the map), **CSC-…-002** (the density
render engine), **CSC-…-003** (a discrete-map Lyapunov estimator), and
**CSC-…-007** (the panel host). The feature needs **zero net-new runtime
dependencies** for v1 (`numpy`/`scipy`/`matplotlib`/`numba`/`imageio` are already
present; `colorcet` is optional). Obvious next ship:
`/milestone-pipeline CSC-2026-05-30-conradi-panel-001`.

## Provenance

Derived from capability-scout run `2026-05-30-conradi-panel` (synthesis →
challenge → RICE final-report under
`.claude/notes/capability-scouts/2026-05-30-conradi-panel/artifacts/`) and the two
upstream deep-analysis notes
`.claude/notes/conradi-analysis/{math-parameterization,rendering-coloration}.md`,
which were confirmed against Conradi's own source notebook
(`profConradi/Python_Simulations/Nice_orbits.ipynb`). Dispositions in this file
reflect the Phase-3 critique (1 BLOCKER → CSC-011 dropped; FLI deferred; CSC-003
and CSC-005 mitigated). Item IDs retain their original `CSC-2026-05-30-…` prefix
for traceability to the source synthesis.

## Sequencing

| Order | Item | Effort | Why first / why not |
|---|---|---|---|
| 1 | CSC-2026-05-30-conradi-panel-001 — ConradiMap (`DiscreteSystem` subclass) | S | foundational; no deps; unblocks 002, 003 |
| 2 | CSC-2026-05-30-conradi-panel-009 — Colormap registry extension | XS–S | no deps; feeds 002; cheap parallel win |
| 3 | CSC-2026-05-30-conradi-panel-002 — Density-accumulation render engine | M | depends on 001 (+009 for palettes); foundational; unblocks 005 |
| 4 | CSC-2026-05-30-conradi-panel-003 — `largest_lyapunov_discrete()` | S | depends on 001 (jacobian); foundational; unblocks 004, 010 |
| 5 | CSC-2026-05-30-conradi-panel-007 — Conradi panel scaffold + QThread worker | S | depends on 002; hosts 002/004/005 |
| 6 | CSC-2026-05-30-conradi-panel-004 — `(a,b)` Lyapunov screening overlay | M | depends on 003, 007 |
| 7 | CSC-2026-05-30-conradi-panel-005 — Closed-loop `(a,b)` animation + inset | M | depends on 002, 007 |
| 8 | CSC-2026-05-30-conradi-panel-006 — GIF + MP4 loop export | S | depends on 005 |
| 9 | CSC-2026-05-30-conradi-panel-010 — Expose discrete LLE in Lyapunov panel | XS–S | depends on 003 |
| 10 | CSC-2026-05-30-conradi-panel-008 — Clifford attractor preset | S | depends on 002, 007; additive breadth |

**Milestone grouping (from the RICE final-report):** **A — static attractor-art
MVP:** 001 → 009 → 002 → 007. **B — animation + export:** 005 → 006.
**C — Lyapunov screening:** 003 → 004 → 010. **Follow-up:** 008 (Clifford).
CSC-011 is dropped (see *Rejected at refinement*); CSC-012 (FLI) and the extra
catalog maps are deferred (see *Deferred / conditional enhancements*).

## Items

### CSC-2026-05-30-conradi-panel-001 — ConradiMap as a `DiscreteSystem` subclass

**What:** Add the Conradi trigonometric map `x' = sin(x²−y²+a)`,
`y' = cos(2xy+b)` as a new `DiscreteSystem` subclass, with an analytic Jacobian
(for Lyapunov screening) and canonical parameters `(a, b) = (5.46, 4.55)` as
named constants. Optionally expose a `zᵏ` generalization (k∈{2,3,4}) and a
per-channel trig/phase knob, flagged as a derived (non-primary-sourced) extension.

**Where:** New `src/chaotic_systems/systems/conradi.py` subclassing
`DiscreteSystem` (`src/chaotic_systems/core/discrete.py`), mirroring the existing
discrete maps under `src/chaotic_systems/systems/` (e.g. the Hénon / logistic /
standard / Ikeda map modules). Register in `systems/__init__.py`. Tests: new
`tests/systems/test_conradi.py` mirroring the existing discrete-map tests.

**SOTA reference:** Simone Conradi, `Nice_orbits.ipynb`,
github.com/profConradi/Python_Simulations (the exact map + canonical params,
read verbatim). The `z²` structure (`x²−y² = Re z²`, `2xy = Im z²`) and the
analytic Jacobian `J = [[2x cos u, −2y cos u], [−2y sin v, −2x sin v]]`
(`u = x²−y²+a`, `v = 2xy+b`) are derived in
`.claude/notes/conradi-analysis/math-parameterization.md`.

**Effort:** S — one ~30-line subclass + a Jacobian + a test, matching the size of
the existing discrete-map modules.

**Rationale:** The map is the hard prerequisite for every other item. It slots
into the existing `DiscreteSystem` abstraction with no core change, so it is
picked up by the existing system registry for free. Observable: iterates are
provably confined to `[−1,1]²` (sin/cos bound), and the analytic Jacobian must
match a finite-difference Jacobian to ~1e-6 — both unit-testable.

**Risks / open questions:** The `zᵏ` generalization and per-channel phase knob are
**derived, not present in Conradi's primary source** — ship them flagged as such
in code comments and do NOT test them against any claimed published value; if a
citation cannot be supplied, scope v1 to `k=2` only. Otherwise no concerns
(traceable to CSC-…-001; additive new file; no path conflict with shipped maps).

### CSC-2026-05-30-conradi-panel-009 — Colormap registry extension (art palettes + custom Conradi ramp)

**What:** Route the panel's colormap selection through the existing colormap
registry; add a custom black→`#ffe100` "Conradi" ramp (matching the source
notebook) and surface the existing magma/inferno; expose (do not rename) the
already-registered-but-unused `ember`/`ice` ramps. `colorcet` (a closer "fire"
match) is an optional, not required, dependency.

**Where:** `src/chaotic_systems/visualization/colormaps.py`. Tests:
`tests/visualization/test_colormaps.py`.

**SOTA reference:** Smith & van der Walt (2015), "A Better Default Colormap for
Matplotlib", SciPy 2015 (perceptually-uniform magma/inferno); Conradi
`Nice_orbits.ipynb` for the black→`#ffe100` ramp.

**Effort:** XS–S — a few palette registrations + the custom ramp; smallest item.

**Rationale:** Cheapest meaningful win, sequenced early so the render engine
(002) has its palettes ready. It also prevents the inline-`cm.get_cmap`
anti-pattern by forcing the panel's colormaps through one registry. Observable:
all panel-offered colormaps resolve through the registry; the existing `ember`/
`ice` entries are unchanged (no rename).

**Risks / open questions:** Must not rename or alter the existing `ember`/`ice`
registry entries (other code may reference them). `colorcet` stays optional with
its CC-BY-4.0 attribution noted if added. None other identified by Phase 3
critique.

### CSC-2026-05-30-conradi-panel-002 — Density-accumulation render engine

**What:** A standalone render module that takes map parameters and produces an
RGBA image: a numba `@njit(parallel=True)` fused iterate-and-accumulate over an
N×N lattice of initial conditions (Conradi's method) into a high-resolution 2D
histogram, a tone-map step (`eq_hist` / `log` / `cbrt` / `linear`), a
perceptually-uniform colormap (magma/inferno) on a crisp black background, and an
optional multi-scale Gaussian bloom. Ships with a pure-NumPy `np.histogram2d`
fallback when the `[performance]` (numba) extra is absent.

**Where:** New `src/chaotic_systems/visualization/attractor_density.py`; consumes
`visualization/colormaps.py` (CSC-009) for the colormap and
`scipy.ndimage.gaussian_filter` for bloom. Render constants (`bins`, `n_iter`,
`vmin`/`vmax`) defined as named module constants per CLAUDE.md. Tests:
`tests/visualization/test_attractor_density.py`.

**SOTA reference:** Tone mapping — Draves & Reckase (2003), "The Fractal Flame
Algorithm", flam3.com/flame_draves.pdf (log-density display
`α = log(count)/log(count_max)`); histogram-equalization default per datashader's
`how='eq_hist'`. Colormap — Smith & van der Walt (2015), SciPy 2015
(magma/inferno). Pipeline + IC-lattice method documented in
`.claude/notes/conradi-analysis/rendering-coloration.md`.

**Effort:** M — the numba kernel, four tone-map modes, the bloom pass, and the
NumPy fallback, with throughput tuning (~100–500 Mpts/s single-thread target).

**Rationale:** The heart of the feature and the only piece with no existing
analogue in the codebase. Keeping it a pure arrays-in/RGBA-out module (no Qt)
makes it testable headless and reusable by both the still and animation paths.
Observable: `count==0` cells map to exact black; for a fixed seed lattice the
output is byte-reproducible across runs.

**Risks / open questions (MITIGATE):** `eq_hist` is data-dependent and flickers
across animation frames — the animation path (CSC-005) MUST use a **fixed
`count_max`** established by a low-resolution **pre-scan of the loop** before the
full render, held constant for all frames. Add a **frame-stability test**
asserting the brightness-histogram delta between two adjacent loop frames stays
below a threshold under the fixed-`count_max` contract. The `eq_hist` `argsort`
over the non-zero cells at high `bins` runs off-thread but should be benchmarked
and, if slow, replaced by a fine-binned CDF approximation. Additive new module —
no test-regression risk.

### CSC-2026-05-30-conradi-panel-003 — `largest_lyapunov_discrete()` core function

**What:** A discrete-map largest-Lyapunov-exponent estimator using tangent-map
renormalization (Benettin algorithm), with signature
`largest_lyapunov_discrete(step_fn, jacobian_fn, x0, n, n_transient)`. The
Jacobian is supplied as a **callable argument** — NOT a new abstract method on
`DiscreteSystem` — so the existing base class and its subclasses are untouched.
No `solve_ivp`; numba-friendly.

**Where:** New function in `src/chaotic_systems/core/lyapunov.py`, alongside (and
fully separate from) the existing ODE estimators (which are `solve_ivp`-based and
remain unchanged). Tests: extend `tests/core/test_lyapunov.py`.

**SOTA reference:** Benettin, Galgani, Giorgilli & Strelcyn (1980), "Lyapunov
Characteristic Exponents for smooth dynamical systems…", *Meccanica* 15:9,
DOI 10.1007/BF02128236 (the canonical tangent-map Lyapunov algorithm).

**Effort:** S — the existing ODE estimator is the structural template; this swaps
`solve_ivp` integration for a direct Jacobian-multiply + renormalize loop.

**Rationale:** The only genuinely new piece of core math. It unblocks the `(a,b)`
screening overlay (CSC-004) and, as a free side effect, enables LLE for the three
already-shipped maps (CSC-010, a D1-class wire-up). Observable: regression-anchor
against Hénon LLE ≈ 0.419; cross-check the analytic-Jacobian result against a
two-trajectory separation estimate.

**Risks / open questions (MITIGATE):** Do NOT add a `jacobian()` method to the
`DiscreteSystem` ABC — pass the Jacobian as a `jacobian_fn: Callable` argument so
the base class and its existing subclasses, and the `solve_ivp`-based ODE Lyapunov
path, are entirely untouched. The existing `tests/core/test_lyapunov.py` ODE
assertions must continue to pass unchanged; the new estimator is purely additive.

### CSC-2026-05-30-conradi-panel-007 — Conradi panel scaffold + QThread worker

**What:** The native PySide6 panel that hosts the renderer, the parameter
controls, the colormap/tone-map pickers, the animation transport, the `(a,b)`
inset, and the optional Lyapunov backdrop — with all heavy compute on a worker
thread (finished/progress/error/cancel signals). Registered as a first-class panel
reachable from the main window's Analyse menu.

**Where:** New `src/chaotic_systems/gui/conradi_panel.py` mirroring the existing
analysis panels (e.g. the Lyapunov / phase-space panels); uses the shared
scaffolding in `gui/_panel_helpers.py` and the `QObject.moveToThread(QThread)`
worker pattern already used by the existing Lyapunov worker in `gui/main_window.py`.
Embeds a matplotlib `FigureCanvasQTAgg`. Registered alongside the other panels in
`gui/main_window.py`.

**SOTA reference:** N/A (GUI integration); follows the existing panel conventions
(the D1 Lyapunov panel) verbatim.

**Effort:** S — scaffolding is fully established; this is wiring, not invention.

**Rationale:** This panel, reachable from the Analyse menu under the existing dock
idiom, is what the user asked for ("a new panel/tab selectable at the top"). It
deliberately does NOT introduce a top-level `QTabWidget` (there is none in the app
today — see *Rejected at refinement*). Observable: opening/closing the panel
leaves the existing panels' dock lifecycle and the GUI test suite green; long
renders never freeze the UI (worker-thread contract).

**Risks / open questions:** When the `[performance]` numba extra is absent the
panel must degrade gracefully to the pure-NumPy preview path (lower point budget),
not error. Single-brief-sourced (internal-adversary only), but it is pure wiring
over established patterns, so confidence is high.

### CSC-2026-05-30-conradi-panel-004 — `(a,b)` Lyapunov screening heatmap + path routing

**What:** Compute the largest Lyapunov exponent on a vectorized
`(a,b) ∈ [0,2π]²` grid (via CSC-003) and render it as a heatmap that serves as the
backdrop of the parameter-path editor, so the user can route the animation loop
through chaotic (high-LLE) territory — Sprott-style aesthetic screening. A
standard-deviation floor rejects collapsed point attractors.

**Where:** New screening helper (e.g. in `attractor_density.py` or a small
`visualization/attractor_screen.py`) consuming `core/lyapunov.py` (CSC-003);
displayed in the panel (CSC-007). The 2D-raster + click-to-pick UI idiom is
reused from the existing basin-of-attraction panel (`gui/basin_panel.py`). Heavy
compute runs on the panel's QThread worker (CSC-007).

**SOTA reference:** Sprott, J.C. (1993), "Automatic generation of strange
attractors", *Computers & Graphics* 17(3):325–332,
DOI 10.1016/0097-8493(93)90082-K (LLE-threshold + coverage aesthetic screening).
Benettin (1980) for the underlying estimator.

**Effort:** M — the grid sweep + heatmap widget + path-overlay interaction + the
std-floor degeneracy guard.

**Rationale:** The differentiator no competitor (datashader/Panel, Chaotica)
offers: a live "where is it interesting" map under the parameter path.
Observable: on a coarse grid the high-LLE mask must reach **≥90% agreement with a
~20-sample hand-labelled chaotic/quiet validation set**. Caveat to document: LLE
predicts dynamical richness, not the exact lattice appearance.

**Risks / open questions:** The "agrees with hand-labelled samples" criterion is
made quantitative above (≥90% on a fixed 20-sample set) to give a testable
observable. Depends on CSC-003 and CSC-007, both sequenced earlier — no
undeclared dependency. Grid compute must stay on the worker thread to keep the UI
responsive.

### CSC-2026-05-30-conradi-panel-005 — Closed-loop `(a,b)` parameter-path animation + inset

**What:** Animate the attractor by sweeping a **closed** parametric path
`(a(t), b(t))` through parameter space (a truncated-Fourier / epicycle generator,
seamless by construction), recomputing the density render per frame, with a small
synchronized upper-right inset that draws the loop and a moving marker. Transport
controls (play/pause/scrub); optional user-editable control points fitted to a
periodic spline.

**Where:** Panel logic in `gui/conradi_panel.py` (CSC-007); the parameter-sweep UI
idiom is reused from the existing bifurcation panel (`gui/bifurcation_panel.py`);
frames come from CSC-002. The `param_loop` generator is specified in
`.claude/notes/conradi-analysis/math-parameterization.md`.

**SOTA reference:** Closed-curve / truncated-Fourier parameterization of a smooth
loop (`param_loop` derivation in the math-parameterization note); the
seamless-loop animation pattern follows Conradi's posted animations.

**Effort:** M — the path generator + inset widget + transport + frame scheduling.

**Rationale:** The signature behaviour from the reference images — a closed loop
guarantees a seamless GIF/MP4. Observable: `param_loop(0)` equals `param_loop(1)`
to machine precision (proving seamlessness).

**Risks / open questions (MITIGATE):** Density is expensive; do NOT compute it
inside the 60 Hz UI tick. **Precompute all frames on the worker thread**, then
play them back via a `QTimer` from an in-memory frame buffer. Pair this with the
CSC-002 fixed-`count_max`-across-loop contract so brightness does not flicker
between frames. Provide a cancel path so a long precompute can be aborted.

### CSC-2026-05-30-conradi-panel-006 — GIF + MP4 loop export

**What:** Export the animation as a seamless loop in MP4 (reusing the existing
imageio writer) and GIF (new branch, `loop=0`). Feed the CSC-002 density frames
into the same writer abstraction used by the existing renderer.

**Where:** Factor the frame-writing loop in
`src/chaotic_systems/visualization/renderer.py` (the existing
`imageio.v2.get_writer` MP4/libx264 path) so the Conradi panel can reuse it; add a
GIF branch. Wire to the panel's export action (CSC-007).

**SOTA reference:** N/A (engineering); `imageio`/`imageio-ffmpeg` are already
project dependencies (used by the V4 export work).

**Effort:** S — reuse the MP4 path; the only new code is the GIF branch.

**Rationale:** Shareable seamless loops are the payoff of the whole feature, and
the export machinery already exists — a reuse, not a rebuild. Observable: a
round-trip GIF re-read yields the same frame count; the first and last frames are
identical (seamless).

**Risks / open questions:** GIF is limited to a 256-color palette — quantize the
magma frames and document the slight banding vs MP4. Add a guard test that the new
GIF branch does NOT alter the existing MP4 (libx264) export path that other
features depend on. Refactoring the shared frame-writing loop must keep the
existing renderer export tests green.

### CSC-2026-05-30-conradi-panel-010 — Expose discrete-map LLE in the existing Lyapunov panel

**What:** Once CSC-003 lands, wire the discrete-map LLE for the already-shipped
Hénon / logistic / standard maps into the existing Lyapunov panel's system
dropdown — surfacing capability that becomes available "for free".

**Where:** `src/chaotic_systems/gui/lyapunov_panel.py` (currently ODE-oriented);
tests in `tests/core/test_lyapunov.py` / a GUI smoke test.

**SOTA reference:** Benettin (1980), DOI 10.1007/BF02128236 (same estimator as
CSC-003); Hénon (1976), "A two-dimensional mapping with a strange attractor",
*Commun. Math. Phys.* 50:69, for the LLE ≈ 0.419 anchor value.

**Effort:** XS–S — a dropdown wire-up + a regression test, contingent on CSC-003.

**Rationale:** A high-credibility, low-cost wire-up (the D1 pattern) that
validates the new estimator on textbook cases before it is trusted on the Conradi
grid. Observable: the panel reports Hénon LLE ≈ 0.419 and logistic-at-r=4
LLE ≈ ln 2. Must not regress the existing ODE Lyapunov path.

**Risks / open questions:** The existing Lyapunov panel is ODE-oriented; verify
discrete maps slot into the dropdown without regressing the ODE code path or its
GUI tests. Depends on CSC-003 (sequenced earlier). None other identified.

### CSC-2026-05-30-conradi-panel-008 — Clifford attractor preset

**What:** Add the Clifford attractor as a second `DiscreteSystem` art-map preset
so the panel is a small "attractor studio" rather than a one-off, sharing the
entire render / animate / screen pipeline. (Additional maps are deferred — see
*Deferred / conditional enhancements*.)

**Where:** New `src/chaotic_systems/systems/clifford.py` (~20 lines mirroring the
existing discrete-map modules); register in `systems/__init__.py`. Tests:
`tests/systems/test_clifford.py`.

**SOTA reference:** Paul Bourke, "Clifford Attractors",
http://paulbourke.net/fractals/clifford/ (the canonical map
`x' = sin(a y) + c cos(a x)`, `y' = sin(b x) + d cos(b y)` and its reference
parameter sets). dysts is explicitly NOT used as the primary source.

**Effort:** S — one small map subclass + a test; ships only Clifford for v1.

**Rationale:** Clifford shares the exact lattice-render / animate / Lyapunov
pipeline, proving the pipeline generalizes for the cost of one map. Scoping v1 to
Clifford-only (with a primary citation) avoids the multi-map citation debt the
challenge flagged. Observable: Clifford renders through the same
`attractor_density` path and produces its known multi-lobe figure at the Bourke
reference parameters.

**Risks / open questions:** Clifford is unbounded in general (unlike the
sin/cos-bounded Conradi map), so the render extent must be computed per-parameter
(auto-fit bounding box) rather than fixed at `[−1,1]²`. None other identified by
Phase 3 critique.

## Rejected at drafting

None — no item violated a hard rule (native PySide6, no web/Electron/Tauri/WebGL,
no foreign-compile deps) at draft time.

## Rejected at refinement

- **CSC-2026-05-30-conradi-panel-011 — Top-level tabbed navigation refactor.**
  **DROP** (Phase-3 critique BLOCKER, axis 6 *additive over invasive*, high
  confidence): it would rewrite `gui/main_window.py`'s central `QSplitter`/viewport
  layout and every existing `*_panel.py` dock lifecycle, and the app has **no
  `QTabWidget` today**. App-wide regression surface across all shipped panels. The
  user's "tab at the top" intent is satisfied **functionally** by CSC-007 — a
  first-class Conradi panel reachable from the Analyse menu under the existing dock
  idiom. A genuine top-level tab strip should be raised as its own standalone UX
  RFC, not bundled into this feature.

## Deferred / conditional enhancements

- **CSC-2026-05-30-conradi-panel-012 — FLI fast-Lyapunov-indicator variant.**
  A finite-time Fast Lyapunov Indicator (no renormalization) as a cheaper
  alternative to a full LLE per grid node. **Build only if** the CSC-004 grid sweep
  proves too slow interactively. Lives additively in `core/lyapunov.py` beside
  CSC-003. Cite: Froeschlé, Lega & Gonczi (1997), "Fast Lyapunov indicators.
  Application to asteroidal motion", *Celestial Mechanics & Dyn. Astron.* 67:41–62,
  DOI 10.1007/BF00692141.
- **Additional art-attractor maps** (de Jong, Hopalong, an Ikeda variant,
  Gumowski-Mira). Deferred from CSC-008 until the Clifford preset proves the
  pipeline. Each requires its own primary citation (textbook/paper or Paul Bourke
  page) before implementation — dysts (a software catalog) is not an acceptable
  primary source per CLAUDE.md "Mathematical correctness".

## Reading order

Ship items in the Sequencing-table order via `/milestone-pipeline <Item ID>`. The
four foundational items (001 map, 002 render engine, 003 discrete Lyapunov, 007
panel host) come first; the static attractor-art MVP is 001 → 009 → 002 → 007.
Start with:

```
/milestone-pipeline CSC-2026-05-30-conradi-panel-001
```

(Offer only — not auto-invoked.)
