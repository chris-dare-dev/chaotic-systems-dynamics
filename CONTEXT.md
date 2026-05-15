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

- Empty git repository on `main` branch, remote at `git@github.com:chris-dare-dev/chaotic-systems-dynamics.git`.
- This scaffolding pass establishes:
  - Directory layout under `src/chaotic_systems/` with empty packages for `core`, `systems`, `integrators`, `visualization`, `gui`.
  - Test directory mirroring the source layout.
  - Governance files: `README.md`, `CONTEXT.md`, `SECURITY.md`, `CLAUDE.md`, `LICENSE`, `pyproject.toml`, `.gitignore`, `.python-version`.
- Nothing is implemented. No dependencies are pinned. Nothing is runnable yet.

## What's next

In rough priority order:

1. **Core abstractions.** Define `DynamicalSystem` and `Integrator` base classes in `core/`. A system advertises its state dimension, its vector field $\dot{y} = f(t, y)$, optionally its Lagrangian/Hamiltonian in symbolic form, and its LaTeX representation. An integrator advances `(y, t) → (y', t')`.
2. **First system + first integrator.** Lorenz attractor + classical RK4. Smallest end-to-end slice that produces a trajectory.
3. **Visualization MVP.** A 3D plot of the trajectory using a native plotting stack (likely matplotlib's 3D axes or PyVista — choice deferred until the GUI stack is picked).
4. **GUI stack decision.** PySide6/Qt is the leading candidate for a native window that can host both a 3D viewport and LaTeX-rendered equations. Tkinter is a fallback if dependencies become a problem. **Explicitly not Electron / web-based.**
5. **Adaptive integrator.** RK45 with embedded error estimate.
6. **Symplectic integrator + double pendulum.** Demonstrates the Lagrangian path and the energy-preservation argument for symplectic methods.
7. **Lyapunov exponent estimation.** Tangent-space method.
8. **Video export.** MP4 / GIF rendering of an animated trajectory.

## Non-goals (for now)

- Web frontend. The decision to go native is explicit; do not reintroduce a browser-based UI.
- Distributed / GPU-accelerated simulation. The systems of interest are low-dimensional and CPU-bound integration is fine.
- Real-time interactive parameter tweaking with sub-millisecond latency. Smooth animation is enough.
- General-purpose ODE solver competing with `scipy.integrate.solve_ivp`. We use what `scipy` gives us where it makes sense, and only hand-roll integrators where it serves the pedagogical or symplectic goals.

## Open questions

- **GUI stack:** PySide6 (Qt) vs. Dear PyGui vs. Tkinter + matplotlib. Leaning PySide6 for the LaTeX rendering and 3D viewport story.
- **3D rendering:** matplotlib's `mpl_toolkits.mplot3d` is easy but slow. PyVista / VTK is faster and prettier but heavier. Decision deferred to the visualization phase.
- **LaTeX rendering inside the GUI:** matplotlib's mathtext is built-in and limited; full LaTeX needs a TeX install. Likely use matplotlib mathtext to start.
- **Symbolic backend:** `sympy` for symbolic Lagrangians and code-gen of vector fields. Risk: parsing user-supplied expressions safely (see `SECURITY.md`).
