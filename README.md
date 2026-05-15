# chaotic-systems-dynamics

A mathematically rigorous Python application for simulating and visualizing chaotic dynamical systems. The project ships both a reusable backend library and a native desktop GUI that renders trajectories in 3D, displays the underlying equations of motion in rendered LaTeX, and exports animations to video.

## Status

Functional. The full pipeline — backend (systems, integrators, Lyapunov, Poincare), visualization (PyVista 3D, LaTeX rendering, MP4 export), and native GUI (PySide6) — is implemented and exercised by 50+ tests. See `CONTEXT.md` for the current state, design decisions, and roadmap.

## Goals

- Treat chaos seriously — correct numerics, faithful equations, sensible defaults.
- Be usable two ways: as a Python library (`import chaotic_systems`) and as a desktop app.
- Keep the math visible. Every system advertises its Lagrangian/Hamiltonian/ODE form in rendered LaTeX alongside the simulation.
- Stay native. The frontend is a desktop window, not a browser tab.

## Features

### Systems library
- Lorenz attractor
- Rössler attractor
- Double pendulum (symbolic Lagrangian)
- Chua's circuit
- Duffing oscillator (driven)
- Hénon-Heiles (separable Hamiltonian)
- Extensible — adding a new system is a single file + a registry entry.

### Numerical integration
- Adaptive (scipy wrappers): RK45, RK23, DOP853, Radau, BDF, LSODA.
- Fixed-step: classical RK4, explicit Euler.
- Symplectic (separable Hamiltonians): leapfrog, velocity Verlet, Yoshida-4.

### Diagnostics
- Largest Lyapunov exponent (Benettin's two-trajectory method).
- Full Lyapunov spectrum (variational + continuous QR).
- Poincaré sections via scipy event detection.

### Visualization
- Live 3D trajectory rendering (PyVista / VTK, embedded in Qt).
- Off-screen MP4 export (imageio + bundled ffmpeg) with progress + cancel.
- Color-by-time scalar shading on the polyline.
- LaTeX equations of motion rendered into the side panel (matplotlib mathtext).

### GUI
- Native desktop window (no Electron, no browser).
- System picker, parameter sliders + spinboxes (with log scale for parameters spanning orders of magnitude).
- Integrator selection from the full registry (including symplectic methods).
- Simulation and export run on worker threads — the window stays responsive.
- **Transport controls** under the viewport: Play / Pause / Stop / Jump-to-end / speed dropdown (0.25×–8×) / frame scrubber with live `t = current / total` readout. Press *Run* and the GUI now plays the trajectory back at 1× rather than dumping the static polyline.
- **Prerender + loading bar.** Right after a simulation finishes, a background worker warms the VTK pipeline and builds a cumulative arc-length table for the trajectory; the status bar shows "Preparing animation... X%" with a determinate progress pill, then playback starts. Playback is driven by *arc-length* (Manim `point_from_proportion` style), so chaotic stretches visit slowly visually and calm regions zip past at uniform visual speed — the head moves at a constant *visual* rate regardless of how fast the underlying parametrization changes through phase space. Trajectories below ~500 samples skip the prerender step and play immediately. See `docs/prerender_design.md` for the design and prior-art research.
- **Flowing LaTeX panel** — equations scale to the panel width on resize (no horizontal scrolling); aligned environments stack one row per equation so each row scales independently.
- Keyboard shortcuts:
  | Key | Action |
  |---|---|
  | Ctrl-R | Run simulation |
  | Ctrl-E | Export video |
  | R | Reset 3D camera |
  | Esc | Cancel running simulation / export |
  | Space | Play / Pause playback |
  | Ctrl-. | Stop and rewind to frame 0 |
  | End | Jump to the last frame |

## Installation

Python 3.12 (pinned in `.python-version`). PySide6 and PyVista ship binary wheels on macOS / Linux / Windows, so no system-level Qt or VTK install is needed.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

### As a library

```python
from chaotic_systems.systems import Lorenz

lorenz = Lorenz()
traj = lorenz.simulate(t_span=(0, 40), integrator="RK45", dt=0.01)
# traj.t is (N,), traj.y is (N, 3)
```

### As a desktop app

```bash
python -m chaotic_systems.gui
# or, after `pip install -e .`:
chaotic-systems-gui
```

The left panel lets you pick a system, tweak its parameters and integrator, and run a simulation. The center is a live 3D viewport. The right panel shows the system's ODE system (and Lagrangian, if any) in rendered LaTeX. `Export video` writes an MP4 of the trajectory.

### Render a video without launching the GUI

```bash
python examples/lorenz_video.py /tmp/lorenz.mp4
```

See `docs/visualization.md` for the full architecture and `docs/numerics.md` for the integrator zoo.

## Project layout

```
src/chaotic_systems/
├── core/            base classes (DynamicalSystem, Integrator)
├── systems/         concrete chaotic systems
├── integrators/     numerical methods
├── visualization/   3D rendering and video export
└── gui/             native desktop window
```

## License

MIT. See `LICENSE`.

## Contributing

This is currently a solo project. Once it stabilizes, contribution guidelines will land in `CONTRIBUTING.md`. For security issues, see `SECURITY.md`.
