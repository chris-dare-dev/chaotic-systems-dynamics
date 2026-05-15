# chaotic-systems-dynamics

A mathematically rigorous Python application for simulating and visualizing chaotic dynamical systems. The project ships both a reusable backend library and a native desktop GUI that renders trajectories in 3D, displays the underlying equations of motion in rendered LaTeX, and exports animations to video.

## Status

Early scaffolding stage. The directory layout, governance files, and package skeleton are in place; the systems, integrators, visualization, and GUI implementations have not been written yet. See `CONTEXT.md` for the current state and roadmap.

## Goals

- Treat chaos seriously — correct numerics, faithful equations, sensible defaults.
- Be usable two ways: as a Python library (`import chaotic_systems`) and as a desktop app.
- Keep the math visible. Every system advertises its Lagrangian/Hamiltonian/ODE form in rendered LaTeX alongside the simulation.
- Stay native. The frontend is a desktop window, not a browser tab.

## Planned features

### Systems library
- Lorenz attractor
- Rössler attractor
- Double pendulum (Lagrangian-derived)
- Chua's circuit
- Duffing oscillator
- Henon-Heiles
- (extensible — adding a new system is a single file)

### Numerical integration
- Classical RK4
- Adaptive RK45 (Dormand-Prince)
- Symplectic integrators (Verlet, leapfrog) for Hamiltonian systems
- User-selectable step size and tolerance

### Visualization
- Real-time 3D trajectory animation
- Phase-space projections
- Offline video / GIF export
- Lyapunov exponent estimation and display
- LaTeX rendering of system equations

### GUI
- Native desktop window (no Electron, no browser)
- System picker, parameter sliders, initial-condition controls
- Integrator selection
- Play/pause/scrub timeline
- Export to MP4/GIF

## Installation

_To be filled in once dependencies are pinned._

```bash
# placeholder — not yet runnable
pip install -e .
```

## Usage

### As a library

```python
# placeholder — not yet implemented
from chaotic_systems.systems import Lorenz
from chaotic_systems.integrators import RK45

system = Lorenz(sigma=10, rho=28, beta=8/3)
trajectory = RK45(system).integrate(y0=[1, 1, 1], t_span=(0, 100), dt=0.01)
```

### As a desktop app

```bash
# placeholder — not yet implemented
python -m chaotic_systems.gui
```

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
