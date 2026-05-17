# Capability Roadmap — 2026-05-17

## TL;DR

The visualization layer is mature; the math/sim layer has not been touched
since the initial implementation and is the obvious place to invest. Three
directions stand out: (1) **discrete maps + a system catalog expansion**
seeded from `dysts`, which unlocks bifurcation diagrams (the single missing
diagnostic with the most pedagogical leverage) at near-zero compute cost;
(2) **the full Lyapunov spectrum is already implemented but not surfaced** —
expose it in the GUI and pair it with a hyperchaotic 4D system so the
`(+, +, 0, -)` signature is something a user can actually see; (3) an
**optional `diffrax` JAX integrator extra** that vmaps trajectory batches
on CPU/GPU, which makes basin-of-attraction maps and ensemble Lyapunov
sweeps feasible without a C/Rust dependency. All three are additive and
compatible with the no-web / Python-3.12 / ruff-clean constraints.

## Methodology

### Read in-repo
- `CLAUDE.md`, `CONTEXT.md`, `README.md`, `docs/numerics.md`,
  `docs/systems.md`, `docs/visualization.md`, `docs/prerender_design.md`,
  `docs/animation_smoothness_iter4.md`.
- All concrete systems under `src/chaotic_systems/systems/` and all
  integrators under `src/chaotic_systems/integrators/`.
- `src/chaotic_systems/core/base.py`, `core/hamiltonian.py`,
  `core/lyapunov.py`, `core/poincare.py`.
- Last 30 commits (`git log --oneline -30`) — confirms that every commit
  in the last week is UI/perf-side; the math layer hasn't shifted since
  ~2026-05-15.
- `docs/proposals/README.md` — empty proposal history; this is the first
  capability roadmap.

### Researched online (2024+ sources only)
- `dysts` v0.95, Oct 2024 — 131 systems incl. delay-differential + 10
  discrete maps.
- `diffrax` (Kidger) — vmappable JAX ODE solvers, GPU-capable.
- `pysindy` 2.1 (2025) — data-driven system discovery.
- `pynamicalsys` 1.5 (2025) — bifurcation diagrams, basins, periodic
  orbits, RTE all in a single ruff-clean numpy+numba package.
- `pykoopman` (JOSS 2024) — Koopman / DMD lifts.
- PyRQA — OpenCL-accelerated RQA, arXiv 2402.16853 (Jan 2024).
- `scikit-sundae` 1.1 (Oct 2024) — SUNDIALS bindings on PyPI wheels, no
  user compile.
- PyVista 0.45 (2025) and 0.46 (2025) changelogs — stereo rendering,
  decompose / radio-button widget, new image-resampling filter.
- 0-1 test for chaos: Gottwald & Melbourne, arXiv 0906.1418 (canonical
  reference; no maintained Python package — opportunity for a 40-line
  implementation).
- 4D Rössler hyperchaos: Stankevich & Wilczak, *Phys. Lett. A* 379
  (2015), and the *Scholarpedia* hyperchaos entry.
- Mackey-Glass DDE chaos / hyperchaos: Sprott, *Phys. Lett. A* 366
  (2007); Junges & Gallas, *Phys. Lett. A* 376 (2012).

URLs are listed at the bottom.

## Current inventory

### Systems — 6 (`src/chaotic_systems/systems/`)
| File | System | State dim | Form |
|---|---|---|---|
| `lorenz.py` | Lorenz '63 | 3 | ODE |
| `rossler.py` | Rössler | 3 | ODE |
| `double_pendulum.py` | Double pendulum | 4 | Lagrangian → ODE |
| `chua.py` | Chua's circuit | 3 | Piecewise-linear ODE |
| `henon_heiles.py` | Hénon-Heiles | 4 | Separable Hamiltonian |
| `duffing.py` | Driven Duffing | 2 | Non-autonomous ODE |

Registered through `systems/registry.py`. All continuous-time; none are
discrete maps, none are DDEs, none are hyperchaotic.

### Integrators — 11 (`src/chaotic_systems/integrators/`)
- Adaptive: `RK45`, `RK23`, `DOP853`, `Radau`, `BDF`, `LSODA`
  (`adaptive.py`, scipy wrappers).
- Fixed-step: `RK4`, `Euler` (`fixed_step.py`).
- Symplectic: `leapfrog`, `velocity_verlet`, `yoshida4`
  (`symplectic.py`, with `from_hamiltonian` adapter).
- All conform to the `Integrator` protocol in `_protocol.py`.

### Diagnostics (`src/chaotic_systems/core/`)
- `largest_lyapunov_two_trajectory` (Benettin) — used in
  `examples/lyapunov_lorenz.py`.
- `lyapunov_spectrum` — full spectrum via variational + continuous QR.
  **Implemented but not wired into the GUI.**
- `poincare_section` — event-driven via `scipy.integrate.solve_ivp`.

### Visualization & GUI
- `Renderer3D` (PyVista/VTK) with Catmull-Rom oversampling, arc-length
  playback, transport controls, MP4 export via imageio-ffmpeg.
- PySide6 `MainWindow`: system picker, auto-generated parameter form,
  integrator picker, embedded 3D viewport, flowing LaTeX panel,
  prerender pipeline with loading bar.
- File formats supported: MP4 (export). No PNG snapshot, no CSV
  trajectory dump, no `.npz` round-trip, no run-history persistence.

## Gaps vs. SOTA

1. **System count: 6 vs. dysts' 131.** dysts publishes a curated JSON
   catalog of 131 chaotic systems with reference parameters and
   precomputed Lyapunov spectra (Gilpin, *Chaos as an interpretable
   benchmark*, NeurIPS 2021; database last released Oct 2024). Six is
   below the floor for a useful teaching tool.
2. **No discrete maps.** The logistic map, Hénon map, Ikeda map, and
   Chirikov standard map are the canonical pedagogical entry points to
   chaos (period-doubling cascade, stretch-and-fold, KAM tori). Cannot
   be skipped in a teaching context. Source: Crutchfield/Packard
   discrete-systems chapter, UC Davis (Reading ch. 2, csc.ucdavis.edu).
3. **No bifurcation-diagram tool.** Every comparable 2024+ Python
   toolkit ships one — `pynamicalsys.DiscreteDynamicalSystem.bifurcation_diagram`
   (Sales et al., *Chaos, Solitons & Fractals* 201, 2025), `pynamical`
   (Boeing). For a chaos teaching tool, the bifurcation diagram is at
   least as important as the strange-attractor render.
4. **No hyperchaotic system.** With only 3D-and-under autonomous flows
   plus Hénon-Heiles (4D Hamiltonian), the user cannot see a `(+, +)`
   Lyapunov signature. The 4D Rössler model (Rössler 1979; Stankevich &
   Wilczak 2015) is the standard demo.
5. **No delay-differential system.** Mackey-Glass is THE canonical DDE;
   hyperchaos for τ > 7.8 (Farmer 1982; Junges & Gallas 2012).
6. **`lyapunov_spectrum` is invisible in the GUI.** Already implemented
   in `core/lyapunov.py` lines 179–272 but never surfaced. The GUI shows
   neither the largest exponent nor the full spectrum.
7. **No 0-1 test for chaos.** Gottwald & Melbourne (arXiv 0906.1418) —
   ~40 lines of numpy; no maintained Python package exists; complements
   Lyapunov by being noise-robust on short series.
8. **No basin-of-attraction map.** The pedagogically essential picture
   for multistable systems (Datseris & Wagemakers, *Chaos* 32 (2022),
   023104, "Effortless estimation of basins of attraction").
9. **No batched / vectorized solver.** Each trajectory is a scalar
   scipy call. A basin sweep at 256×256 resolution = 65536 scipy
   invocations and dies. `diffrax` vmaps the same call to one batched
   XLA kernel; the entire Diffrax design is built around "vmappable
   _everything_, including the region of integration" (Kidger, *Fields
   Institute* talk, 2024).
10. **No file format other than MP4.** No CSV / `.npz` trajectory dump;
    no PNG snapshot of the viewport; no save/load of the parameter set
    that produced a video.

## Proposals — by category

### New systems

#### N1. Add discrete-maps subsystem with logistic / Hénon / Ikeda / standard map
- **What:** A new `DiscreteSystem` base alongside `DynamicalSystem`,
  plus four concrete maps.
- **Where:** `src/chaotic_systems/core/discrete.py` (new abstraction),
  `src/chaotic_systems/systems/logistic.py`,
  `src/chaotic_systems/systems/henon_map.py`,
  `src/chaotic_systems/systems/ikeda.py`,
  `src/chaotic_systems/systems/standard_map.py`. Registry
  (`systems/registry.py`) gains a `map_kind: "ode" | "map"` so the GUI
  can disable integrator pickers for maps.
- **SOTA reference:** Hénon map: Wikipedia + Hénon (1976); Ikeda:
  Ikeda (1979); standard map: Chirikov (1979); Sales et al.,
  *Chaos, Solitons & Fractals* 201 (2025) (pynamicalsys treats the same
  four as the canonical pedagogical set).
- **Effort:** M. New abstraction plus four files plus tests; the maps
  themselves are 5–10 lines each. The renderer needs no changes —
  iterates are still points in R^2 / R^3.
- **Rationale:** Discrete maps are 95% of every undergraduate chaos
  course and currently 0% of this tool.

#### N2. Add 4D Rössler hyperchaos as the "two positive exponents" exemplar
- **What:** 4D Rössler with parameters (a, b, c, d) such that there are
  two positive Lyapunov exponents.
- **Where:** `src/chaotic_systems/systems/rossler_hyper.py`.
- **SOTA reference:** Stankevich & Wilczak, *Phys. Lett. A* 379 (2015);
  Scholarpedia "Hyperchaos".
- **Effort:** S. ~30 lines, same pattern as `rossler.py`.
- **Rationale:** The full `lyapunov_spectrum` machinery already exists
  but has no system that would *show* hyperchaos. This is the natural
  test case.

#### N3. Add Mackey-Glass DDE
- **What:** First DDE in the project. Needs a DDE integrator path —
  Bellen–Zennaro-style with a history buffer.
- **Where:** `src/chaotic_systems/systems/mackey_glass.py`,
  `src/chaotic_systems/integrators/dde.py`.
- **SOTA reference:** Mackey & Glass, *Science* 197 (1977); Sprott,
  *Phys. Lett. A* 366 (2007), "A simple chaotic delay differential
  equation"; Junges & Gallas, *Phys. Lett. A* 376 (2012), "Intricate
  routes to chaos in the Mackey–Glass delayed feedback system".
- **Effort:** M (the DDE integrator is the M-sized part; the system is
  S). A simple Bellen-style interpolating-history RK4 is well under
  100 lines.
- **Rationale:** DDEs are the second canonical infinite-dimensional
  setting (after PDEs) where chaos lives, and Mackey-Glass is the only
  one widely taught. Adds a *kind* of system the project doesn't have.

#### N4. Add Kuramoto N-oscillator network
- **What:** Synchronization of N coupled oscillators with random natural
  frequencies; expose `N` as a parameter.
- **Where:** `src/chaotic_systems/systems/kuramoto.py`.
- **SOTA reference:** Kuramoto (1975); see `fabridamicelli/kuramoto` for
  the typical Python implementation.
- **Effort:** S. ~50 lines.
- **Rationale:** Brings *network dynamics* (cited as a target
  phenomenology in the brief) into the catalog. With a small N=4 the
  GUI can render the (θ_1, θ_2, θ_3) projection live; the order
  parameter |R(t)| → 1 transition is visually striking.

### New integrators

#### I1. Optional `diffrax` JAX integrator backend
- **What:** A `JAX-RK45` / `JAX-Tsit5` integrator that ships behind a
  `[jax]` extra and exposes a `vmap_trajectories(system, y0_batch,
  params_batch)` helper.
- **Where:** `src/chaotic_systems/integrators/jax_backend.py` (lazy
  import — the module is only imported when the integrator is
  requested). Optional dependency added to `pyproject.toml` under a
  `jax` extra.
- **SOTA reference:** Kidger, *Diffrax* docs (`docs.kidger.site/diffrax`,
  current). The pattern is exactly the one their docs prescribe.
- **Effort:** M. The wrapper itself is small; the work is in keeping
  the optional-import boundary clean so non-JAX users don't pay.
- **Rationale:** Unlocks N3, N4, and several diagnostics below (basin
  maps, parameter sweeps) without invasive changes.

#### I2. Optional `numbalsoda` integrator backend
- **What:** A `numbalsoda`-backed LSODA integrator for users who have
  already JIT-compiled their RHS.
- **Where:** `src/chaotic_systems/integrators/numbalsoda_backend.py`,
  gated behind the existing `[performance]` extra (which already pulls
  in numba).
- **SOTA reference:** `pypi.org/project/numbalsoda/` (Wogan et al.).
  Note: the last release was 2022 — flag this as "useful but
  maintenance-dormant" and prefer I1 if forced to pick one.
- **Effort:** S.
- **Rationale:** Closes the "you can JIT your RHS but the outer loop is
  still Python" gap that `docs/numerics.md` already calls out as a
  known limitation.

#### I3. Optional `scikit-sundae` for stiff & DAE problems
- **What:** Add a `CVODE` integrator alias and an `IDA` one for
  Chua-like piecewise systems and any future DAE.
- **Where:** `src/chaotic_systems/integrators/sundials_backend.py`,
  gated behind a new `[sundials]` extra.
- **SOTA reference:** NREL `scikit-sundae` 1.1 (Oct 2024) — ships
  wheels with SUNDIALS 7.5 prebuilt; no user compile.
- **Effort:** S.
- **Rationale:** Production-grade alternative to scipy's `Radau` /
  `BDF`. The constraint to "no Julia/Rust/C++ deps the user would need
  to compile" is satisfied because the wheels bundle SUNDIALS.

### New diagnostics

#### D1. Surface the existing `lyapunov_spectrum` in the GUI
- **What:** A "Diagnostics" panel under the parameter form that, after
  Run, calls `lyapunov_spectrum(system, ...)` on a worker thread and
  displays `λ_1 ≥ λ_2 ≥ ... ≥ λ_n` with an indicator showing how many
  are positive.
- **Where:** New `src/chaotic_systems/gui/diagnostics_panel.py`; wired
  into `main_window.py`. Worker pattern mirrors `_SimulateWorker`.
- **SOTA reference:** Benettin et al., *Meccanica* 15 (1980) — already
  cited in the existing `core/lyapunov.py` docstring. The 2024+ angle
  is that *every* comparable tool (DynamicalSystems.jl, pynamicalsys)
  shows the full spectrum, not just λ_1.
- **Effort:** M. The compute is already there; this is just GUI wiring
  plus formatting.
- **Rationale:** Highest-ROI proposal in the document. The capability
  is built and tested; surfacing it is a UI commit. Combined with N2
  (4D Rössler) the user can *see* `(+, +, 0, -)`.

#### D2. Bifurcation-diagram tool
- **What:** A `bifurcation_diagram(system, param_name, param_range,
  n_values)` function that returns the long-time orbit sampled per
  parameter value, plus a 2D plot panel in the GUI.
- **Where:** `src/chaotic_systems/core/bifurcation.py`,
  `src/chaotic_systems/visualization/bifurcation_plot.py`,
  `src/chaotic_systems/gui/bifurcation_panel.py`. Uses matplotlib
  embedded in a `FigureCanvasQTAgg` since this is 2D, not 3D.
- **SOTA reference:** Sales et al., *Chaos, Solitons & Fractals* 201
  (2025), `pynamicalsys`; Strogatz, *Nonlinear Dynamics and Chaos* (2nd
  ed.), §10 for the canonical logistic-map presentation. Synergy with
  N1 (logistic / Hénon maps) is the obvious pairing.
- **Effort:** L. New plot infrastructure, new panel, parameter-sweep
  worker thread.
- **Rationale:** The single most-requested missing diagnostic in any
  teaching tool. Reuses the existing simulation pipeline.

#### D3. 0-1 test for chaos (Gottwald & Melbourne)
- **What:** `chaos_test_01(time_series)` returning the K statistic.
- **Where:** `src/chaotic_systems/core/chaos_test.py`. Shows up in the
  Diagnostics panel alongside D1.
- **SOTA reference:** Gottwald & Melbourne, arXiv 0906.1418 (algorithm
  spec); *SIAM J. Appl. Dyn. Syst.* 8 (2009), 129–145.
- **Effort:** S. ~40 lines of numpy.
- **Rationale:** No maintained Python implementation exists. Fills a
  real niche, and is noise-robust where the two-trajectory Lyapunov
  estimator isn't.

#### D4. Basin-of-attraction map for multistable systems
- **What:** Sample a 2D grid of initial conditions, integrate each to
  steady state, color by which attractor was reached.
- **Where:** `src/chaotic_systems/core/basins.py`,
  `src/chaotic_systems/visualization/basin_plot.py`, GUI panel.
  Hard requirement: needs I1 (diffrax/vmap) to be tractable at
  interactive resolutions.
- **SOTA reference:** Datseris & Wagemakers, *Chaos* 32 (2022) 023104,
  "Effortless estimation of basins of attraction".
- **Effort:** L.
- **Rationale:** Most visually striking diagnostic missing from the
  tool; the natural pairing with the Duffing system (already shipped)
  is iconic.

#### D5. Recurrence-plot + RQA (lightweight, no PyRQA)
- **What:** Pure-numpy recurrence matrix `R_ij = Θ(ε − ||x_i − x_j||)`,
  plus the standard RQA scalars (RR, DET, LAM, L_max, V_max, ENTR).
- **Where:** `src/chaotic_systems/core/recurrence.py`,
  `src/chaotic_systems/visualization/recurrence_plot.py`.
- **SOTA reference:** PyRQA, arXiv 2402.16853 (Jan 2024) — *but* it
  requires an OpenCL toolchain we deliberately don't want as a hard
  dep. A 200-line numpy implementation suffices for the
  N ≤ 10000 trajectories the GUI handles.
- **Effort:** M.
- **Rationale:** Recurrence plots make the geometric structure of a
  trajectory visually obvious in a way the 3D render doesn't. Modest
  effort, high pedagogical payoff.

### Performance

#### P1. JAX-vmap basin / parameter sweeps (depends on I1)
- See D4 — basin maps are intractable without vectorized integration.
  This is really the same investment as I1.
- **Reference:** `diffrax` "vmappable everything" design.
- **Effort:** Already counted under I1.

#### P2. AOT-compiled RHS helper
- **What:** Implement the `compile_rhs(system)` helper that
  `CONTEXT.md` already calls out as future work — `numba.njit` the
  symbolic `_rhs` of every system that uses sympy `lambdify` (double
  pendulum, Hénon-Heiles).
- **Where:** `src/chaotic_systems/core/_numba.py` (extend).
- **SOTA reference:** Same numba pattern already documented in
  `docs/numerics.md`.
- **Effort:** M.
- **Rationale:** Resolves the open item in `CONTEXT.md` "What's next" #6.

### Visualization & workflow

#### V1. 2D phase-portrait panel
- **What:** A second matplotlib-backed panel that plots arbitrary 2D
  projections (e.g. (x, ẋ) for the Duffing, the (x, p_x) Hénon-Heiles
  section) alongside the 3D viewport. Already listed in `CONTEXT.md`
  "What's next" #1 but un-built.
- **Where:** `src/chaotic_systems/visualization/phase_plot.py`,
  `src/chaotic_systems/gui/phase_panel.py`.
- **SOTA reference:** Standard everywhere — Strogatz (2015) figures
  passim.
- **Effort:** M.
- **Rationale:** 2D phase portraits are how chaos is *taught* before
  the strange-attractor render. Closing the docs/code gap is overdue.

#### V2. Side-by-side trajectory comparison (two ICs or two integrators)
- **What:** A "compare" toggle that runs the same system twice with
  perturbed IC or different integrator, renders both polylines in the
  same viewport with distinct colors.
- **Where:** `src/chaotic_systems/visualization/renderer.py` (multi-line
  support), `src/chaotic_systems/gui/main_window.py` (UI affordance).
- **SOTA reference:** Standard pedagogy for "sensitive dependence on
  initial conditions" — Strogatz (2015) §9.
- **Effort:** M.
- **Rationale:** Makes the butterfly effect a single-click demo.

#### V3. Conservation overlay for Hamiltonian / Lagrangian flows
- **What:** A small graph below the viewport showing E(t) − E(0),
  L(t) − L(0) for the systems where conserved quantities exist
  (double pendulum, Hénon-Heiles, Duffing-without-forcing).
- **Where:** `src/chaotic_systems/visualization/conservation_plot.py`,
  GUI panel.
- **SOTA reference:** This is the headline argument for symplectic
  integrators in `docs/numerics.md` — Hairer, Lubich, Wanner (2006).
- **Effort:** S–M.
- **Rationale:** Validates the *reason* the symplectic family exists.
  Currently shipping symplectic integrators with no in-GUI way to see
  what makes them special.

#### V4. PNG snapshot, CSV / NPZ trajectory dump, JSON run history
- **What:** Three new file formats: PNG (current viewport),
  `.csv` / `.npz` (the `Trajectory` object), and a `.json` per-run
  manifest (system, params, integrator, dt, t_span, output paths).
- **Where:** `src/chaotic_systems/visualization/snapshot.py`,
  `src/chaotic_systems/io/trajectory.py`,
  `src/chaotic_systems/io/run_history.py`. GUI: Export menu.
- **SOTA reference:** Convention — every comparable tool does this.
- **Effort:** S.
- **Rationale:** Trivial to add, real workflow win for "I want to put
  this trajectory in a paper."

### Education / explanatory features

#### E1. Textbook annotations on each system
- **What:** Per-system `educational_notes` markdown rendered in a
  collapsible panel below the LaTeX. Reference where to look up the
  system in Strogatz / Ott / Sprott, what to watch for (period-doubling
  cascade in Duffing, KAM tori in standard map, etc.).
- **Where:** Each `systems/*.py` gains an `educational_notes: str`
  attribute; new `_NotesPanel` in `main_window.py`.
- **SOTA reference:** Strogatz, *Nonlinear Dynamics and Chaos* (2nd
  ed., 2015); Ott, *Chaos in Dynamical Systems* (2nd ed., 2002);
  Sprott, *Chaos and Time-Series Analysis* (2003).
- **Effort:** M (mostly content writing).
- **Rationale:** This tool is built for the author "to internalize
  math". The notes are the lever for that.

#### E2. "Live parameter slider" exploration mode
- **What:** A low-resolution preview re-simulation (~100 steps, no
  prerender) fires on every parameter spinbox change; the user gets
  immediate visual feedback. Full-fidelity Run still requires a button.
- **Where:** `src/chaotic_systems/gui/main_window.py` — debounce on the
  parameter form `valueChanged` signals, separate `_PreviewWorker`.
- **SOTA reference:** Already on `CONTEXT.md` "What's next" #4.
- **Effort:** M.
- **Rationale:** Turns the GUI from "set up a run, look at the result"
  into "drag a slider, watch the attractor breathe." This is what
  Strogatz-on-a-laptop should feel like.

## Sequencing

A defensible 8-week order. Each step is independently shippable.

| Order | Item | Effort | Why first / why not |
|---|---|---|---|
| 1 | D1 — surface `lyapunov_spectrum` in GUI | M | The capability is already built. Highest-ROI single commit. |
| 2 | N2 — 4D Rössler hyperchaos | S | Pairs with D1: gives the user a system where the spectrum reveals something non-trivial. |
| 3 | V4 — snapshot / CSV / NPZ / JSON exports | S | Trivial, but fills the most-asked workflow gap. |
| 4 | V3 — conservation overlay | S–M | Validates the symplectic integrator story already shipped. |
| 5 | D3 — 0-1 test | S | Standalone, ~40 lines, complements D1. |
| 6 | N1 — discrete maps subsystem (4 maps) | M | Prereq for D2; large pedagogical win. |
| 7 | D2 — bifurcation-diagram tool | L | Headline feature. Depends on N1 and a new 2D-plot panel. |
| 8 | V1 — 2D phase-portrait panel | M | Reuses the plot infra from D2. |
| 9 | E1 — educational notes per system | M | Best done after the catalog stabilizes (after N1). |
| 10 | V2 — side-by-side trajectory comparison | M | Renderer needs multi-line support. |
| 11 | I1 — optional diffrax JAX backend | M | Unblocks D4. Optional extra, so users without JAX are unaffected. |
| 12 | D4 — basin-of-attraction map | L | Depends on I1. The visually most striking missing diagnostic. |
| 13 | D5 — recurrence plot + RQA | M | Standalone; ship anytime after E1. |
| 14 | E2 — live parameter slider preview | M | Best after the diagnostic panels exist so previews can pipe into them. |
| 15 | N3 — Mackey-Glass DDE + DDE integrator | M | Architecturally interesting; lower urgency than the above. |
| 16 | N4 — Kuramoto network | S | Nice-to-have; not on the critical path. |
| 17 | P2 — AOT-compile sympy `_rhs` | M | Performance only. Defer until profiling motivates it. |
| 18 | I2 / I3 — numbalsoda / scikit-sundae | S each | Defer until a real stiff problem motivates one. |

## Out of scope / explicitly rejected

- **`pysindy` / `pykoopman` integration.** Both are mature 2024+ libraries
  that would let users *fit* a system from data and visualize it. Brilliant
  research direction but adds a "data → model" loop that's a different
  product than "explore a known model"; out of scope today.
- **PyRQA.** Best-in-class RQA, but the OpenCL dependency is a hard sell
  on macOS Metal. D5 ships a numpy-only RQA instead.
- **napari embedding.** napari is excellent but the project is committed
  to PySide6 + PyVistaQt; bringing in napari's Qt event loop alongside is
  a portability and conflict risk for marginal benefit.
- **`DynamicalSystems.jl` as a backend.** Excellent reference for *what*
  to build (basins, periodic orbits, KAM tools), but the brief excludes
  Julia.
- **AUTO-07p / PyCoBi.** Continuation software is the right tool for
  *parametric* bifurcation analysis (Hopf, saddle-node, period-doubling
  branches as a function of two parameters). It needs a Fortran compile
  and a steep learning curve. Defer until D2 is shipped and the user
  actually wants more than naive parameter sweeps.
- **Custom-system expression box.** Already flagged in `SECURITY.md` /
  `CONTEXT.md` as needing a safe-eval sandbox before it can ship.
- **Anything web / Electron / Tauri.** Hard constraint.

## References

### Libraries
- dysts (Gilpin): https://github.com/williamgilpin/dysts
- dysts dataset on HuggingFace: https://huggingface.co/datasets/williamgilpin/dysts
- diffrax (Kidger): https://docs.kidger.site/diffrax/
- diffrax getting started: https://docs.kidger.site/diffrax/usage/getting-started/
- pysindy: https://github.com/dynamicslab/pysindy
- pykoopman: https://github.com/dynamicslab/pykoopman
- pynamicalsys docs: https://pynamicalsys.readthedocs.io/en/stable/
- pynamicalsys arXiv (2025): https://arxiv.org/abs/2506.14044
- pynamical (Boeing): https://github.com/gboeing/pynamical
- PyRQA arXiv (Jan 2024): https://arxiv.org/abs/2402.16853
- PyRQA repo: https://github.com/szhan/pyrqa
- scikit-sundae: https://github.com/NREL/scikit-sundae
- scikit-sundae docs: https://scikit-sundae.readthedocs.io/en/stable/
- numbalsoda: https://github.com/Nicholaswogan/numbalsoda
- PyCoBi (Auto-07p Python wrapper): https://github.com/pyrates-neuroscience/PyCoBi
- VisPy: https://vispy.org/
- napari (tracks layer): https://napari.org/dev/howtos/layers/tracks.html
- DynamicalSystems.jl (basins reference): https://juliadynamics.github.io/DynamicalSystems.jl/dev/tutorial/

### PyVista 2024-2025 releases
- PyVista 0.45 discussion: https://github.com/pyvista/pyvista/discussions/7442
- PyVista 0.46 docs: https://docs.pyvista.org/
- PyVista releases page: https://github.com/pyvista/pyvista/releases

### Papers / theory
- Gilpin (2021), *Chaos as an interpretable benchmark*: https://arxiv.org/abs/2110.05266
- Sales et al., *pynamicalsys* in *Chaos, Solitons & Fractals* 201 (2025): https://www.sciencedirect.com/science/article/pii/S0960077925012822
- Gottwald & Melbourne, 0-1 test arXiv: https://arxiv.org/abs/0906.1418
- Datseris & Wagemakers (2022), *Chaos* 32, 023104, basins: https://pubs.aip.org/aip/cha/article/32/2/023104/2835640/Effortless-estimation-of-basins-of-attraction
- Hyperchaos (Scholarpedia): http://www.scholarpedia.org/article/Hyperchaos
- 4D Rössler (Stankevich & Wilczak, 2015 preprint): https://ww2.ii.uj.edu.pl/~wilczak/papers/2015_BMSW.pdf
- Mackey-Glass equation (Scholarpedia): http://www.scholarpedia.org/article/Mackey-Glass_equation
- Sprott, *A simple chaotic delay differential equation* (2007): https://sprott.physics.wisc.edu/pubs/paper304.pdf
- PyKoopman JOSS paper (2024): https://joss.theoj.org/papers/10.21105/joss.05881
