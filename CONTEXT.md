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

The scaffolding and the visualization MVP are done. Open follow-ups:

1. **2D phase-space panels.** Add a second tab (or a docked widget)
   showing Poincare sections and arbitrary 2D projections via
   matplotlib or PyQtGraph.
2. **Lyapunov display.** Surface the largest Lyapunov exponent
   (already implemented in `core/lyapunov.py`) somewhere in the GUI —
   probably a status-bar widget that updates after each Run.
3. **Persistent settings.** Remember the last-used system, parameters,
   and integrator across launches (`QSettings`).
4. **Real-time parameter rebinding.** Today, changing a slider doesn't
   re-simulate until you press Run. A "live" mode that re-integrates
   a short window on every change would be nice for exploration.
5. **CI for the GUI smoke tests.** Today the GUI tests are skipped
   without a display. A `xvfb` job (Linux) or a macOS runner with a
   logged-in user could turn them back on.
6. **Numba-JIT'd hot loops for production runs.** Today the fixed-step
   integrators don't JIT the outer loop because numba can't infer
   arbitrary Python `rhs` types. A future pass could expose a
   `compile_rhs(system)` helper that returns a numba-typed RHS and an
   inner loop matching, e.g., the `rk4_step` API.
7. **Pre-rendered intros (manim).** Out-of-scope today but a nice
   future direction for tutorial videos that explain each system before
   the live simulation runs.

## Recently shipped (2026-05-15, after the param-form fix)

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
