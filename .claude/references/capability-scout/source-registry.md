# Source registry — capability-scout

Curated list of sources each Phase 1 agent reaches for first. **Loaded
by sub-agents at Phase 1 start, NOT by the main session at slash-command
load.**

Bias: 2024-2026 active sources only. Anything dormant > 18 months gets
flagged in the brief (still surface it, but downgrade confidence).

---

## §1 — Competitive lens (for `capability-scout-competitive`)

Tools that occupy the same niche or adjacent niches.

| Project | URL | Language | Last release | Read for |
|---|---|---|---|---|
| dysts | https://github.com/williamgilpin/dysts | Python | 2024-10 (v0.95) | 130+ chaotic systems with parameter sets and attractor properties. Direct catalog comparison. |
| DynamicalSystems.jl | https://juliadynamics.github.io/DynamicalSystemsDocs.jl/ | Julia | active | **CONCEPTS ONLY** — do NOT propose Julia deps. Read for the *catalog of diagnostics* (lyapunovs/, attractors/, periodic_orbits/, bifurcations/, recurrences/). |
| pynamicalsys | https://github.com/mtcb-lab/pynamicalsys | Python | 2025 | Bifurcation diagrams, basins of attraction, periodic orbits, RTE — all numpy + numba. Directly relevant. |
| ChaosBook.org | https://chaosbook.org/ | Textbook | active | Cvitanović textbook + bundled code. Read for *which diagnostics are standard pedagogy*. |
| Strogatz textbook (`Nonlinear Dynamics and Chaos`, 2nd ed.) | — | textbook | 2014 | The pedagogical baseline. Anything in the textbook should be feasible in this project. |
| Sprott's chaos page | https://sprott.physics.wisc.edu/chaos/ | Reference | active | Curated catalog with parameter sets; cross-check `dysts` entries against this. |
| Wolfram Mathematica Dynamical Systems | https://reference.wolfram.com/language/guide/DynamicalSystems.html | proprietary | active | Read for *feature surface only*; we cannot use the Wolfram Engine. |
| TISEAN | https://www.pks.mpg.de/~tisean/ | C | 2006 (dormant) | Time-series analysis classical. Useful for recurrence, Lyapunov-from-data; dormant so downgrade. |
| Manim Community | https://github.com/ManimCommunity/manim | Python | active | Visualization patterns (animation pacing, point-from-proportion). Already inspired iter-4 smoothness. |

---

## §2 — Academic lens (for `capability-scout-academic`)

Where to find recent (2023+) research on chaotic systems, numerical methods, and visualization.

| Venue | Search target | Read for |
|---|---|---|
| arXiv `nlin.CD` (chaotic dynamics) | new methods 2023-2026 | Novel diagnostics, new systems, novel reductions. |
| arXiv `math.DS` (dynamical systems) | numerical methods 2024+ | Integrator design, ergodic averages, invariant measures. |
| arXiv `math.NA` (numerical analysis) | symplectic / IMEX / DDE 2023+ | Integrator schemes new to the field. |
| `Chaos` (AIP journal) | https://pubs.aip.org/aip/cha | New systems, hyperchaos, network dynamics. |
| `Physica D: Nonlinear Phenomena` | https://www.sciencedirect.com/journal/physica-d | Standard venue. |
| `Communications in Nonlinear Science and Numerical Simulation` | https://www.sciencedirect.com/journal/communications-in-nonlinear-science-and-numerical-simulation | High-throughput; check 2024+ TOCs. |
| `SIAM Journal on Applied Dynamical Systems` | https://epubs.siam.org/journal/sjaday | Theoretical rigor. |
| Kitware blog | https://www.kitware.com/category/blog/ | VTK/ParaView visualization updates; relevant to renderer evolution. |
| Manim research papers | search "manim" + "animation" 2024+ | Curve-pacing, vmobject-from-proportion. |

Specific keyword starters: *Koopman operator*, *neural ODE*, *learned coordinate frames*, *symplectic neural networks*, *RQA / recurrence quantification*, *0-1 test for chaos*, *Mackey-Glass*, *Lyapunov spectrum*, *basin entropy*, *bifurcation diagram*, *hyperchaos*, *multistability*.

---

## §3 — OSS / library lens (for `capability-scout-oss`)

**Active Python packages with PyPI presence.** Reject anything dormant > 18 months (still surface, but downgrade).

| Library | URL | Last release | Read for |
|---|---|---|---|
| diffrax | https://github.com/patrick-kidger/diffrax | active 2025 | JAX-vmappable ODE solvers, GPU-capable. Behind a `[jax]` extra. |
| numbalsoda | https://github.com/Nicholaswogan/numbalsoda | active 2024 | Numba-jitted LSODA. Drop-in replacement for `scipy.integrate.solve_ivp` for stiff non-Hamiltonian. |
| pysindy | https://github.com/dynamicslab/pysindy | active 2025 | Sparse identification of nonlinear dynamics. Fit-from-data → visualize pipeline. |
| chaospy | https://github.com/jonathf/chaospy | active 2024 | UQ for stochastic dynamical systems. |
| pynamicalsys | https://github.com/mtcb-lab/pynamicalsys | active 2025 | Bifurcations, basins, RTE. (also in §1) |
| pykoopman | https://github.com/dynamicslab/pykoopman | active (JOSS 2024) | Koopman / DMD lifts. |
| PyRQA | https://pypi.org/project/PyRQA/ | active (arXiv 2402.16853, Jan 2024) | OpenCL-accelerated recurrence-plot analysis. |
| scikit-sundae | https://github.com/sandialabs/scikit-sundae | active 2024-10 (v1.1) | SUNDIALS bindings on PyPI wheels, no user compile. |
| pyvista | https://github.com/pyvista/pyvista | active 2025 (0.45+, 0.46) | Read the changelog — new widgets, decompose, stereo, image resampling. |
| vispy | https://github.com/vispy/vispy | active | GPU-accelerated native rendering. CLAUDE.md forbids WebGL but native GL is fair game. |
| moderngl | https://github.com/moderngl/moderngl | active | Native GL primitives, embeddable in Qt. |
| matplotlib | https://github.com/matplotlib/matplotlib | active | 2D embedded plots (bifurcation panels, Poincaré sections). |

Cite each library's last release date in your brief. Reject anything that requires user-side compilation of Julia/Rust/C++.

---

## §4 — Internal-adversary lens (for `capability-scout-internal-adversary`)

This agent reads the codebase, NOT the web. Where to look:

| Path | Read for |
|---|---|
| `CONTEXT.md` | "Recently shipped" + "What's next". Don't re-propose what just landed. |
| `docs/numerics.md` | Integrator inventory + accuracy notes. |
| `docs/systems.md` | System inventory + canonical parameters. |
| `docs/visualization.md` | Rendering architecture (Catmull-Rom, prerender cache, wall-clock pacing). |
| `docs/proposals/capability-roadmap-*.md` | Prior proposals. Many candidates here may be **already implemented but un-exposed** (D1 was the canonical example: full Lyapunov spectrum existed in code since day 1, only surfaced in GUI on 2026-05-16). |
| `src/chaotic_systems/core/*.py` | Anything in `core/` that has no GUI surface = candidate for "wire-up" not "implement". |
| `src/chaotic_systems/integrators/*.py` | What integrators ship, what's missing. |
| `src/chaotic_systems/systems/*.py` | Inventory. |
| `tests/` | Test coverage gaps — anything tested but never wired into the GUI is a "wire-up" candidate. |
| `git log --oneline -50` | What was tried, abandoned, or just shipped. |

Special prompt to the internal-adversary: **look for already-built capabilities that aren't surfaced anywhere**. D1 (the Lyapunov spectrum) was the textbook example — high ROI because the math is done, only UI is missing.

---

## Updating this file

When a new venue / library / pattern proves load-bearing in a real run,
add it here. This file IS the institutional memory of "where do we look
for X".
