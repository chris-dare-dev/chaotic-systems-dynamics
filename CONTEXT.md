# CONTEXT.md

Living document. Update this whenever the project's direction, current state, or near-term plan shifts. Future Claude sessions read this first.

## What this project is

`chaotic-systems-dynamics` is a Python application — backend library plus native desktop GUI — for simulating and visualizing chaotic dynamical systems with mathematical rigor.

The intended audience is people who actually want to *see* and *manipulate* the math: students working through nonlinear dynamics, hobbyists exploring strange attractors, and the author (Chris Dare) using it as a sandbox for the math he wants to internalize.

## Mathematical territory covered

The project lives at the intersection of:

- **Ordinary differential equations** — most systems of interest are autonomous ODE systems on $\mathbb{R}^n$.
- **Hamiltonian and Lagrangian mechanics** — for systems like the double pendulum, the equations of motion are derived from a Lagrangian; symplectic integrators preserve phase-space volume and energy on long timescales.
- **Chaos theory proper** — sensitive dependence on initial conditions, the butterfly effect, strange attractors with fractal structure (Lorenz, Rössler), bifurcations, periodic windows.
- **Lyapunov exponents** — quantifying chaos via the exponential rate of separation of nearby trajectories. The largest Lyapunov exponent is the canonical numerical witness of chaos.
- **Phase space and Poincaré sections** — geometric structure that makes chaos visible even when the equations look unassuming.
- **Numerical analysis** — choice of integrator matters. Stiff systems, energy drift in non-symplectic schemes, step-size control via embedded error estimates (RK45/Dormand-Prince).

The project should *render the math*, not hide it. Every system displays its governing equations (LaTeX) alongside the simulation.

## Current state (2026-05-15)

The math and visualization layers landed in parallel passes on the same day.

**Math / numerics** (`core/`, `integrators/`, `systems/`):
- `DynamicalSystem`, `Parameter`, `Trajectory` base types
  (`core/base.py`).
- `LagrangianSystem` — sympy Lagrangian -> Euler-Lagrange equations ->
  `lambdify`-d fast numerical RHS. Drives `DoublePendulum`.
- `HamiltonianSystem` — sympy Hamiltonian -> Hamilton's equations, with
  separable-system support (kinetic / potential split) for symplectic
  integrators. Drives `HenonHeiles`.
- Integrators (`integrators/`) all conforming to a single
  `Integrator` protocol with a shared `integrate(rhs, t_span, y0, dt=,
  n_points=, rtol=, atol=)` signature:
  - **Adaptive** (scipy wrappers): RK45, RK23, DOP853, Radau, BDF, LSODA.
  - **Fixed-step**: RK4, Euler (with `_NUMBA_AVAILABLE` shim — numba is
    used for hand-JIT'd inner loops when callers want it).
  - **Symplectic** (separable Hamiltonians): leapfrog, velocity_verlet,
    yoshida4. Hand-coded, with a `from_hamiltonian()` adapter that
    builds the `grad_T` / `grad_V` callables from a
    `HamiltonianSystem`. Energy is bounded over 1000+ periods of the
    SHO; yoshida4 holds `|E - E0| < 1e-6`.
- `largest_lyapunov_two_trajectory` (Benettin two-trajectory method) and
  `lyapunov_spectrum` (variational + continuous QR). Lorenz returns
  ~0.907 against the canonical 0.9056 in 5 seconds.
- `poincare_section` — event-driven section-collector built on
  `scipy.integrate.solve_ivp` event detection.
- Concrete systems: Lorenz, Rossler, DoublePendulum, Chua, HenonHeiles,
  Duffing — exposed through `chaotic_systems.systems.registry` with a
  stable display order.
- **Tests** (`tests/core`, `tests/integrators`, `tests/systems`): 38
  unit / numerical-accuracy tests covering the base classes, every
  adaptive / fixed-step / symplectic integrator, the simple-pendulum
  reduction of `LagrangianSystem`, energy conservation on the double
  pendulum and Hénon-Heiles, exponential divergence and largest
  Lyapunov on Lorenz, Poincaré section finiteness, and registry
  round-trip.
- **Examples** (`examples/`): `lyapunov_lorenz.py`,
  `double_pendulum_energy.py`, `poincare_henon.py`.
- **Docs**: `docs/numerics.md` (integrator zoo + trade-offs) and
  `docs/systems.md` (each system + reference).

**Visualization + GUI** (`visualization/`, `gui/`):
- `Renderer3D` (PyVista + VTK) with progressive-reveal animation,
  attachable to a `pyvistaqt.QtInteractor` for embedding in the GUI.
- `Renderer3D.render_to_video()` writes MP4s via `imageio-ffmpeg`,
  off-screen — no display required.
- LaTeX rendering via matplotlib mathtext, with automatic unrolling of
  `\begin{aligned}` blocks into stacked rows. `latex_to_qimage()` feeds
  the GUI panels.
- `chaotic_systems.gui.MainWindow` — PySide6 main window:
  system picker, parameter spinboxes auto-generated from each system's
  parameter schema, integrator picker, t_end / dt controls, Run +
  Export Video buttons, embedded 3D viewport, right-hand LaTeX panel
  showing ODE system (and Lagrangian, if any).
- Entry point: `python -m chaotic_systems.gui` (or
  `chaotic-systems-gui` after `pip install -e .`).
- Demos: `examples/lorenz_gui.py`, `examples/lorenz_video.py`.

**Dependencies pinned** in `pyproject.toml`: numpy, scipy, sympy, numba,
matplotlib, PySide6, pyvista, pyvistaqt, imageio, imageio-ffmpeg. Dev
extras: pytest, pytest-qt, pytest-benchmark, hypothesis, ruff, mypy.

**Tests**: 38 math/integrator tests under `tests/core`,
`tests/integrators`, `tests/systems`; 13+ visualization tests (contract
adapter, LaTeX rendering, end-to-end off-screen video export); 3 GUI
smoke tests (window builds, parameter widgets generate from registry,
LaTeX panel populates). GUI tests are gated behind
`CHAOTIC_GUI_TESTS_USE_DISPLAY=1` because `pyvistaqt.QtInteractor`
needs a real OpenGL context. The `tests/gui/conftest.py` hook now
filters strictly to items under `tests/gui/`, so a plain
`pytest tests/` from the repo root runs the 51 backend/visualization
tests and only skips the GUI smoke tests.

## What's next

The scaffolding and the visualization MVP are done. The first two
items on this list (2D phase-space panels and a Lyapunov display)
shipped via roadmap proposals V1 and D1 respectively; see the
``Recently shipped`` sections below. Remaining open follow-ups:

1. **Persistent settings.** Remember the last-used system, parameters,
   and integrator across launches (`QSettings`).
2. **Real-time parameter rebinding.** Today, changing a slider doesn't
   re-simulate until you press Run. A "live" mode that re-integrates
   a short window on every change would be nice for exploration.
   (Roadmap proposal E2.)
3. **CI for the GUI smoke tests.** Today the GUI tests are skipped
   without a display. A `xvfb` job (Linux) or a macOS runner with a
   logged-in user could turn them back on.
4. **Numba-JIT'd hot loops for production runs.** Today the fixed-step
   integrators don't JIT the outer loop because numba can't infer
   arbitrary Python `rhs` types. A future pass could expose a
   `compile_rhs(system)` helper that returns a numba-typed RHS and an
   inner loop matching, e.g., the `rk4_step` API. (Roadmap proposal P2.)
5. **Pre-rendered intros (manim).** Out-of-scope today but a nice
   future direction for tutorial videos that explain each system before
   the live simulation runs.

## Recently shipped (2026-05-17, capability roadmap rollout cont'd)

- **E2 — live parameter-slider preview.** Settings dropdown gains a
  checkable "Live preview (slider drag re-simulates)" action;
  default off. When toggled on, every change to any parameter
  spinbox or slider restarts a 200 ms debounce timer; on timeout a
  low-res preview sim fires (300 samples × 8 s of integrated time,
  ~50-100 ms wall-clock per Lorenz preview) and overlays the
  resulting attractor in the viewport. The preview pipeline is
  surgically separated from the full Run pipeline:
  ``_last_trajectory`` is NOT updated (exports, diagnostics,
  comparisons still reference the user's most recent explicit
  Run); no prerender; no autoplay. ``_fire_preview`` suppresses
  itself when a full Run is in flight; ``_cancel_preview_in_flight``
  disconnects the in-flight worker's signals so a stale result
  can't paint over a newer preview. Toggling the setting off
  drops any pending debounce + in-flight worker. Hooks live in
  ``_rebuild_for_current_system`` so a system flip re-wires the
  preview hooks correctly. 11 new tests pin the toggle, debounce,
  setting-off cancel, full-Run suppression, and the
  ``_last_trajectory``-stays-untouched contract. Commit ``1b131e2``.
- **D5 — recurrence plots + RQA scalars.** Three new modules, pure
  numpy compute, zero new runtime deps. ``core/recurrence.py``
  ships ``recurrence_matrix(trajectory, *, epsilon, norm, theiler)``
  → boolean ``(N, N)`` matrix, ``rqa(matrix, *, l_min, v_min)`` →
  ``RQAStats`` (RR / DET / LAM / L_max / V_max / L_mean / TT / ENTR
  per Marwan et al. 2007 §3), and ``suggest_epsilon(trajectory,
  fraction=0.1)`` — bbox-diagonal heuristic.
  ``visualization/recurrence_plot.py`` renders the matrix as a
  black-and-white image with an optional RQA-stats overlay
  (Tokyo Night dark mode by default, paper-mode toggle). ``gui/
  recurrence_panel.py`` wraps it in a ``RecurrencePanel`` (epsilon /
  l_min / v_min spinboxes, embedded ``FigureCanvasQTAgg``, initial
  render at suggested epsilon, recompute button) plus
  ``build_recurrence_dialog()``. Long trajectories are subsampled
  uniformly to ``_MAX_PLOT_N = 800`` so the panel stays interactive.
  Main window grows a single ``action_recurrence`` toolbar action,
  gated on having a trajectory (mirrors phase-portrait pattern).
  Signature observables: periodic unit circle (2 periods, 200
  samples) → DET > 0.95, LAM > 0.95, L_max > 150 (almost full
  diagonal stripe); IID Gaussian noise → DET < 0.35, L_max < 10
  (essentially no long structure). Exactly-periodic test
  (200 samples on exactly 2 periods, sample[i] = sample[i+100])
  → ENTR = 0 to machine precision (Marwan §3.5: "for periodic
  dynamics ENTR = 0"). 39 new tests across core/viz/GUI. Commit
  ``c9e3d3f``.
- **D4 — basin-of-attraction map.** The headline missing diagnostic;
  three new modules + a toolbar action. ``core/basins.py`` ships
  ``BasinDiagram`` dataclass + ``basin_diagram(rhs, *, x_axis, y_axis,
  attractors, fixed_state, n_grid, t_end, classify_tol, backend)``.
  Supervised classification: caller supplies the attractor centers,
  each grid orbit is assigned to the nearest one (or
  ``UNCLASSIFIED_LABEL = -1`` if the orbit hasn't converged).
  Backends: scipy (default — one ``solve_ivp`` per grid point) and
  jax (opt-in, uses I1's ``vmap_trajectories`` to fuse the whole
  grid into one XLA kernel). ``visualization/basin_plot.py`` renders
  the basin as an imshow with Tokyo-Night-aligned categorical palette,
  attractor-marker stars, and a legend. ``gui/basin_panel.py`` ships
  ``BasinPanel`` (preloaded with the canonical undriven double-well
  Duffing demo + ``_BasinWorker`` on a QThread with progress and
  cancel) plus ``build_basin_dialog``. Main window grows a single
  ``action_basins`` toolbar action. Reference observable: on a 32×32
  (x, v) grid in [-2, 2]², the undriven Duffing (alpha=-1, beta=1,
  delta=0.2) basin is ≥ 100 pixels per well, roughly symmetric
  (|n_left - n_right| < 25% of the grid), with < 25% unclassified.
  The signature low-energy observable: for ICs at rest with
  |x0| < √2 (below the saddle energy), sign(x0) determines the well
  — every test grid point passes. JAX-backend parity test (gated on
  [jax] extra): scipy and jax classifications agree on > 95% of
  pixels for a 16×16 grid. 27 new tests across core/viz/GUI.
  Commit ``ae79478``.
- **I1 — optional JAX / diffrax integrator backend.** New
  ``chaotic_systems.integrators.jax_backend`` module ships two
  ``Integrator``-protocol classes (``JaxRK45`` = diffrax Dopri5;
  ``JaxTsit5`` = diffrax Tsit5) and a ``vmap_trajectories(rhs,
  t_span, y0_batch, ...)`` helper that runs a batch of trajectories
  in one JIT-compiled XLA kernel — the prerequisite for D4 (basin-
  of-attraction map) and arbitrary parameter sweeps. JAX and
  diffrax are an **optional** ``[jax]`` extra in ``pyproject.toml``
  (``jax>=0.4.30``, ``diffrax>=0.6``); the module imports cleanly
  without them, raising ``ImportError`` with a ``pip install -e
  '.[jax]'`` hint only when ``integrate()`` is called.
  ``has_jax_backend()`` and a ``lorenz_jax_rhs()`` reference
  callable round out the public surface. Registered as
  ``"JAX-RK45"`` / ``"JAX-Tsit5"`` in the integrator registry.
  Reference observables: JAX-Tsit5 matches scipy DOP853 on Lorenz
  over t in [0, 5] to L2 endpoint error < 1e-3; ``vmap_trajectories``
  runs a 4-IC batch through Lorenz in a single vmapped call and
  recovers Lyapunov divergence (max pairwise separation > 1.0 at
  t = 10 starting from on-attractor ICs with offsets up to 1e-1).
  Side-effect at import: JAX 64-bit mode is enabled
  (``jax.config.update("jax_enable_x64", True)``) since float32 is
  unusable for chaotic-systems work at any meaningful tolerance.
  10 new tests, all gated on the ``[jax]`` extra so contributors
  without it see them as skips rather than failures. Commit
  ``3703bfb``.
- **V2 — side-by-side trajectory comparison (perturbed-IC overlay).**
  ``Renderer3D`` grows ``add_overlay_trajectory(traj, color, opacity)``
  and ``clear_overlays()`` — static secondary polylines that share
  the primary's plotter but have no head sphere and aren't driven by
  the animation loop. The Settings dropdown gains a checkable
  "Compare: perturbed initial condition" action; when on, the next
  Run integrates the same system twice (primary with the user's
  ``y0``, secondary with ``y0[0] += 1e-3``) and overlays the
  secondary on the primary's viewport in Tokyo Night red-pink. A
  status line surfaces the late-time L2 separation as a numerical
  observable ("Final separation: 17.86" or similar on Lorenz).
  Reference observable in the test suite: integrate Lorenz from an
  on-attractor IC vs ``y0[0] += 1e-3``, t=15 — separation > 5.0 (and
  early-time t=2 separation < 1.0, so the divergence is visually
  unambiguous on screen). Closes the V2 proposal; +15 tests covering
  the renderer-side overlay API + the GUI compare-setting wiring.
  Commit ``f9862b0``.
- **E1 — per-system educational notes.** Both ``DynamicalSystem``
  and ``DiscreteSystem`` gain an ``educational_notes: str`` class
  attribute (markdown). All 11 registered systems now ship
  ~25-line annotations citing canonical textbook references
  (Strogatz / Ott / Sprott / Lichtenberg-Lieberman / etc.), the
  chaotic-regime parameters worth trying, and what to watch for
  (period-doubling cascade in Duffing, KAM tori in the standard
  map, the (+, +, 0, -) Lyapunov signature in 4D Rössler, ...).
  The right-side Mathematics card grows a collapsible "Notes"
  section below the existing LaTeX panels — a ``QTextBrowser``
  driven by ``QTextBrowser.setMarkdown`` (Qt 5.14+, no new
  dependency). Notes re-render on system change via
  ``_set_educational_notes``; an empty-notes system shows a
  friendly placeholder. 30 new tests pin: every registered
  system has non-empty notes, each notes blob cites at least one
  canonical author from a literature whitelist, panel widget
  exists / is read-only / opens external links externally,
  panel refreshes on system change, markdown round-trips through
  ``setMarkdown`` into the plain-text view. Commit ``4a2a883``.
- **V1 — 2D phase-portrait panel.** Closes the longest-standing item
  on ``CONTEXT.md`` "What's next" (formerly #1). New
  ``visualization/phase_plot.py`` ships ``plot_phase_portrait(
  trajectory, ix, iy, ...)`` returning a matplotlib Figure with the
  ``y[:, ix]`` vs ``y[:, iy]`` projection (Agg-safe; Tokyo-Night
  facecolor aware; supports any ``state_dim >= 2``). New
  ``gui/phase_panel.py`` wraps that in ``PhasePanel`` with two
  axis combos, an "Equal aspect" toggle, a Plot button, and an
  embedded ``FigureCanvasQTAgg``; ``build_phase_dialog()`` packages
  it as a top-level window. Main window grows one
  ``action_phase_portrait`` toolbar action that grabs the current
  ``_last_trajectory`` and opens the dialog — gated on
  ``state_dim >= 2`` and on a simulation having run. Reference
  observable: harmonic oscillator (omega=1, IC (1, 0)) integrated
  with RK45 over 2 periods, ``max|sqrt(x^2 + v^2) - 1| < 5e-4`` —
  a unit circle to integrator tolerance, exactly Strogatz Fig 6.1.1.
  25 new tests. Commit ``f241284``.
- **D2 — bifurcation-diagram tool (discrete-map v1).** Three new
  modules, the headline pedagogical diagnostic added to the project.
  ``core/bifurcation.py`` ships ``bifurcation_diagram(system,
  param_name, param_values, n_record, n_transient, ...)`` returning a
  ``BifurcationDiagram`` dataclass; ``visualization/bifurcation_plot.py``
  renders it as a dense Feigenbaum-style scatter via matplotlib
  (Agg-safe for worker threads, Tokyo-Night palette aware); and
  ``gui/bifurcation_panel.py`` exposes ``BifurcationPanel`` (embedded
  ``FigureCanvasQTAgg`` + ``QThread`` worker with progress + cancel)
  plus ``build_bifurcation_dialog()`` that bundles a map picker over
  the four N1 maps. Main window grows a single ``action_bifurcation``
  toolbar QAction that opens the dialog. Numerical observables
  pinned: logistic fixed point ``1 - 1/r = 0.6`` at r=2.5 to 1e-10;
  period-2 cycle at r=3.2 hits Strogatz eq. 10.3.3 to 1e-6;
  period-4 at r=3.5; period-3 window at r=3.835; chaotic regime at
  r=3.9 has >50 distinct iterates. 29 new tests across core / viz /
  GUI. ODE-flow bifurcation via Poincaré sampling is documented as
  future work (it needs a separate "which plane / which projection"
  control surface). Commit ``73ce5e3``.
- **N1 — discrete-maps subsystem with logistic / Hénon / Ikeda /
  Chirikov standard map.** New ``DiscreteSystem`` base class lives
  alongside ``DynamicalSystem`` in ``core/discrete.py``; both expose
  a ``kind`` class attribute (``"ode"`` / ``"map"``) so the GUI can
  switch on the integrator-picker affordance. Four concrete maps
  ship under ``systems/{logistic,henon_map,ikeda,standard_map}.py``,
  each citing its canonical source (May 1976, Hénon 1976,
  Ikeda 1979, Chirikov 1979). Registry gains ``list_maps`` /
  ``get_map`` / ``list_all_systems`` / ``get_any_system``; the
  existing ``list_systems`` surface continues to return only
  ODE flows. Numerical observables pinned: logistic period-2 cycle
  at r=3.2 hits the analytic ``((r+1) ± √((r-3)(r+1)))/(2r)``
  points; Hénon Jacobian determinant equals ``-b`` to 1e-6;
  Ikeda Jacobian determinant equals ``u²`` everywhere (the
  ``t(x,y)`` dependence drops out); Chirikov ``det J = 1`` at
  every interior point and ``p`` is exactly conserved at K=0.
  33 new tests, all green. Commit ``e82d955``.

## Recently shipped (2026-05-16, capability roadmap rollout)

- **D1 — full Lyapunov spectrum in the GUI Diagnostics card.** The
  Benettin / continuous-QR ``lyapunov_spectrum`` compute existed in
  ``core/lyapunov.py`` since the initial implementation but was never
  surfaced. Now a "Diagnostics" card on the left panel runs the
  spectrum on a ``_LyapunovWorker`` thread and classifies the regime
  (Regular / Chaotic / Hyperchaotic). Verified on default Lorenz at
  +0.9032 / -0.0056 / -14.5643 (canonical: +0.9056 / 0 / -14.5723).
  Status-bar ``lyapunov_chip`` now mirrors λ_1. Commit ``b9780dd``.
- **N2 — 4D Rössler hyperchaos.** First system in the project with
  *two* positive Lyapunov exponents. Pairs with D1: select it, click
  Compute, and the GUI shows the canonical hyperchaotic (+, +, 0, -)
  signature directly. Measured spectrum
  ``+0.1188 / +0.0171 / -0.0019 / -21.1464`` matches Rössler 1979 and
  Stankevich & Wilczak 2015 within ~10% on the leading exponents.
- **Project-local scout agents + first capability roadmap.** Added
  ``.claude/agents/{ui-upgrade-scout,capability-research-scout}.md`` and
  the ``/milestone-pipeline`` slash command. First roadmap landed at
  ``docs/proposals/capability-roadmap-2026-05-17.md``; D1 and N2 are
  the first two items shipped from it.

## Recently shipped (2026-05-15, iteration 4 smoothness)

- **Catmull-Rom polyline + wall-clock pacing.** The animation now
  renders against a 4x-oversampled centripetal Catmull-Rom spline
  through the integration samples (built at prerender time, stored on
  ``Renderer3D._smooth_points``). The polyline body reads as a
  C^1-smooth curve instead of a chain of line segments — max
  per-segment angle drops from ~20 deg (visibly faceted) to ~5 deg
  on a default Lorenz playback. The GUI's animation tick is now
  *wall-clock paced*: each tick computes the target arc-length from
  ``time.perf_counter() - play_start``, so missed/dropped frames
  catch up on the next render instead of accumulating drift. See
  ``docs/animation_smoothness_iter4.md`` for the full investigation
  and ``tools/validate_smoothness.py`` for the A/B validator. New
  tests in ``tests/visualization/test_smoothness.py`` pin the
  spline math, the dense-buffer contract, and the 5 ms per-frame
  seek budget.

## Recently shipped (2026-05-15, after the param-form fix)

- **Prerender pipeline + loading bar.** A new ``_PrerenderWorker``
  warms ``Renderer3D``'s VTK pipeline and builds a cumulative
  arc-length table before user-visible playback. For trajectories ≥
  ``MainWindow._PRERENDER_MIN_FRAMES`` (500), the status bar shows
  "Preparing animation... X%" with a determinate progress pill while
  the worker runs. Playback then drives by *arc-length* (Manim
  ``point_from_proportion`` style) so chaotic stretches visit slowly
  visually and calm regions zip past at uniform visual speed.
  Renderer gained ``build_prerender_cache``, ``seek_arc_length``,
  ``has_prerender_cache``, ``total_arc_length``, ``_invalidate_cache``.
  Cache invalidates on ``set_line_width`` / ``set_color_by_progress``
  / re-attach. Cancellation precedence in the toolbar Cancel button is
  now export → prerender → sim. See ``docs/prerender_design.md`` for
  the prior-art research (ParaView Cinema, napari prefetching, Manim
  arc-length, VTK shader-cache warming) and design rationale.
- **Transport controls + scrubbing playback** in the GUI. The viewport
  now has a play / pause / stop / jump-to-end / speed / scrubber strip;
  pressing *Run* simulates, then plays the trajectory back at 1× from
  frame 0 instead of dumping a static polyline. Renderer gained
  `seek(index)`, `set_color_by_progress(bool)`, `head_position`,
  `n_frames`, `current_frame`. A single `QTimer` on the GUI thread
  ticks `Renderer3D.step()`; the per-tick stride scales with the speed
  preset so high speeds stay smooth without sub-10 ms timer noise.
  Shortcuts: Space (play/pause), Ctrl-. (stop), End (jump-to-end).
- **Flowing LaTeX panel.** The `_FlowingLatex` widget replaces the
  fixed-size `QLabel + QScrollArea` pattern; equations scale to the
  panel's current width via `Qt.SmoothTransformation` on the cached
  high-DPI pixmap (matplotlib is never re-invoked on resize). Multi-row
  aligned environments stack one row per equation, each scaling
  independently.
- Tests: `tests/visualization/test_animation.py` (renderer step/seek
  contract), `tests/gui/test_transport.py` (transport-control smoke
  tests, gated behind `CHAOTIC_GUI_TESTS_USE_DISPLAY=1`),
  `tests/gui/test_latex_wrap.py` (flowing LaTeX never overflows).

## Non-goals (for now)

- Web frontend. The decision to go native is explicit; do not reintroduce a browser-based UI.
- Distributed / GPU-accelerated simulation. The systems of interest are low-dimensional and CPU-bound integration is fine.
- Real-time interactive parameter tweaking with sub-millisecond latency. Smooth animation is enough.
- General-purpose ODE solver competing with `scipy.integrate.solve_ivp`. We use what `scipy` gives us where it makes sense, and only hand-roll integrators where it serves the pedagogical or symplectic goals.

## Open questions

- **Symbolic backend:** `sympy` is the symbolic engine for Lagrangians
  and LaTeX prettification. Parsing user-supplied expressions safely is
  still an open risk — see `SECURITY.md` and revisit when the GUI grows
  a "custom system" expression box.
- **Full LaTeX vs. mathtext.** Today we render via matplotlib mathtext,
  which covers the chaotic-systems case but not exotic typography. If
  the project grows to display textbook excerpts, an opt-in path via
  `matplotlib.rcParams["text.usetex"] = True` (requires a TeX install)
  is the natural escape hatch.

## Resolved decisions (2026-05-15)

- **GUI stack:** PySide6 + PyVista (via pyvistaqt) + matplotlib for
  LaTeX. The Tkinter and Dear PyGui alternatives are off the table.
- **3D rendering:** PyVista / VTK. matplotlib's `mpl_toolkits.mplot3d`
  is too slow once trajectories exceed a few thousand points.
- **Video export:** `imageio` with the `imageio-ffmpeg` plugin (it
  bundles a static ffmpeg, so users do not need a system install).
