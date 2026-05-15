# Visualization and GUI architecture

This document describes the visualization and GUI layers of
`chaotic-systems-dynamics`. The corresponding code lives in
`src/chaotic_systems/visualization/` and `src/chaotic_systems/gui/`.

## Stack

| Concern | Library | Why |
|---|---|---|
| Native window | **PySide6 (Qt 6)** | Mature, MIT-compatible (LGPLv3), great macOS support, the de facto Python desktop stack. |
| Embedded 3D viewport | **PyVista + pyvistaqt** | VTK under the hood, ships compiled wheels, integrates cleanly with a Qt widget via `QtInteractor`. |
| LaTeX rendering | **matplotlib mathtext** | No TeX install required; renders to a `QImage` we can drop in a `QLabel`. Supports the most useful subset of LaTeX. |
| Video export | **imageio + imageio-ffmpeg** | Bundles a static ffmpeg binary, so MP4 export "just works" without a system ffmpeg. |
| Numerical glue | **numpy** | Trajectory arrays. |

What we deliberately did **not** choose:

- **Electron / Tauri / browser-based UI.** Hard constraint from `CLAUDE.md`.
- **napari / Jupyter notebooks.** Notebook-first, not a native app.
- **OpenSCAD-style ModernGL.** Lower-level than we need; VTK already
  provides the scene graph, picking, axes, and color maps.
- **manim** for live rendering. Beautiful, but offline only and far too
  heavyweight for an interactive viewport. Could be added later for
  pre-rendered intros.
- **matplotlib's `mpl_toolkits.mplot3d`.** Easy but slow once the
  trajectory exceeds a few thousand points.

## Module map

```
src/chaotic_systems/visualization/
    contract.py    — interface assumed of the math-agent backend
    latex.py       — LaTeX -> ndarray / QImage rendering
    renderer.py    — Renderer3D class (animation + video export)

src/chaotic_systems/gui/
    __main__.py    — entry point: `python -m chaotic_systems.gui`
    main_window.py — MainWindow: parameter panel + 3D viewport + LaTeX panel
```

## The contract with the math agent

The visualization and GUI layers depend on a small, duck-typed surface
from `chaotic_systems.systems.registry`:

- `list_systems() -> list[SystemLike]`
- `get_system(name: str) -> SystemLike`

Each `SystemLike` has:

- `name: str`
- `latex: str` (mathtext-compatible body; `\begin{aligned}` blocks are
  unrolled into stacked rows by `latex_to_array`)
- `lagrangian_latex: str | None`
- `parameters: dict[str, Parameter]` (each `Parameter` exposes
  `default`, `min`, `max`, `description`)
- `initial_state: np.ndarray`
- `state_dim: int`
- `rhs(t, y, **params) -> np.ndarray`
- `simulate(t_span, y0, params, integrator='RK45', dt=0.01) -> Trajectory`

`Trajectory` exposes `.t: (N,)` and `.y: (N, state_dim)`. The
`as_points()` helper in `contract.py` normalizes shape orientation and
projects high-dimensional states to 3D for the viewport.

If the math agent's API ever drifts from this shape, the adapters live
in `contract.py` and `gui/main_window.py` — nowhere else.

## Renderer3D

```python
from chaotic_systems.visualization import Renderer3D

renderer = Renderer3D(trajectory, cmap="viridis")
renderer.show()                                # blocking, interactive
renderer.render_to_video("lorenz.mp4", fps=30, duration_seconds=10)
```

`Renderer3D` has two modes:

- **Owned**: `show()` opens a `pv.Plotter` window.
- **Attached**: `attach(qt_interactor)` embeds the renderer inside the
  GUI's `pyvistaqt.QtInteractor`.

Animation is implemented by incrementally enlarging the visible polyline.
`step(n_visible)` is non-blocking and is the right entry point for
driving animation from a `QTimer`.

`render_to_video()` builds an off-screen plotter (no display required),
walks the camera around the attractor, and writes each frame to ffmpeg
via `imageio.get_writer(...)`. Output is MP4 / H.264.

## LaTeX

`latex_to_array(latex)` returns an `(H, W, 4)` uint8 RGBA buffer.
`latex_to_qimage(latex)` wraps it in a `QImage` ready to paste into a
`QLabel`.

matplotlib mathtext does not support `\begin{aligned}` / `\begin{align}`
/ `\begin{cases}`. We unroll those environments and render each row
individually, then vstack them with a small padding. This covers the
common chaotic-systems case (a 3-row ODE system) without pulling in a
full TeX install.

## GUI layout

```
+---------------------+----------------------+----------------------+
| System: [Lorenz  v] |                      | Equations of motion: |
|                     |                      |   \dot{x} = ...      |
| Parameters:         |   3D viewport        |   \dot{y} = ...      |
|   sigma  [10.0  ]   |   (PyVista)          |   \dot{z} = ...      |
|   rho    [28.0  ]   |                      |                      |
|   beta   [ 2.67 ]   |                      | Lagrangian / H:      |
|                     |                      |   ...                |
| Integrator: [RK45 v]|                      |                      |
| t_end:  [40.0     ] |                      |                      |
| dt:     [ 0.01    ] |                      |                      |
|                     |                      |                      |
| [ Run ] [ Export ]  |                      |                      |
+---------------------+----------------------+----------------------+
```

The left panel auto-regenerates parameter spinboxes whenever the system
combo changes. `Run` simulates and replaces the viewport content;
`Export video` runs `Renderer3D.render_to_video()` to a user-chosen MP4.

## Fallback Lorenz

`main_window.py` ships a tiny in-GUI Lorenz placeholder
(`_FallbackLorenz`) so the window is always launchable, even before the
math agent's registry exists. The placeholder uses
`scipy.integrate.solve_ivp` and is intentionally *not* a real
implementation — the registered Lorenz takes priority as soon as the
backend is available.

## Headless / CI behavior

- The visualization tests (off-screen plotter, LaTeX, contract adapters)
  run in any environment.
- The GUI tests need a real Qt display because `pyvistaqt.QtInteractor`
  requires a working OpenGL context. Setting `CHAOTIC_GUI_TESTS_USE_DISPLAY=1`
  opts them in; otherwise they are skipped. On macOS use the default
  `cocoa` Qt platform.

## Examples

- `examples/lorenz_gui.py` — launch the GUI pre-loaded with Lorenz.
- `examples/lorenz_video.py` — render a 10-second MP4 of Lorenz with no
  GUI involvement.
