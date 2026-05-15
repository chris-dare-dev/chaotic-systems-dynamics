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

- `list_systems() -> list[DynamicalSystem]` — returns ready-to-use
  *instances*, not classes. The registry constructs each system once at
  import time and hands out singletons (concrete systems are stateless
  w.r.t. simulation, so sharing is safe).
- `get_system(name: str) -> DynamicalSystem`

Each instance has:

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
The renderer maintains a single up-front allocated `pv.PolyData` with the
full trajectory in its point buffer; advancing a frame is just an int-array
swap on the `lines` connectivity. The non-blocking entry points are:

- `step(n_visible)` — cumulative count of points to display. Pass
  `current_frame + frames_per_tick` to advance the playhead.
- `seek(index)` — zero-based; jumps the playhead to frame `index` and
  moves the head marker to `points[index]`. The GUI's transport scrubber
  uses this every drag tick.
- `set_color_by_progress(enabled)` — toggle perceptually-uniform color
  shading along the trajectory (default `viridis`). Disabled mode falls
  back to a flat `line_color`.
- `head_position` / `current_frame` / `n_frames` — read-only accessors
  the GUI uses to render `t = ... / ...` labels and the scrubber range.

`render_to_video()` builds an off-screen plotter (no display required),
walks the camera around the attractor, and writes each frame to ffmpeg
via `imageio.get_writer(...)`. Output is MP4 / H.264.

## Transport controls

Once a simulation finishes, the GUI shows a transport strip directly
under the 3D viewport:

```
[Play] [Stop] [End]   Speed: [1× v]   [=====O==========]   t = 12.34 / 40.00
```

| Control | Behavior |
|---|---|
| Play / Pause | Toggle animation playback. Same widget — text flips to "Pause" while playing. Space activates it from the keyboard. |
| Stop | Pause and rewind to frame 0. Bound to Ctrl-. (Ctrl-period). |
| End | Pause and snap to the final frame, so the full attractor is visible. Bound to the End key. |
| Speed | Discrete dropdown: 0.25×, 0.5×, 1×, 2×, 4×, 8×. The "1×" preset is calibrated so the full trajectory plays back over `MainWindow.target_playback_seconds` of wall-clock time (default 10 s). |
| Scrubber | A `QSlider` over `[0, n_frames - 1]`. Pressing or dragging the slider pauses playback; releasing it resumes scrubbed-frame display. The renderer's `seek()` runs on every drag tick — no re-rasterization, no re-add_mesh. |
| t = ... / ... | Live readout of the trajectory's current and final `t` values, sourced from `trajectory.t[frame_index]`. |

The playback timer is a `QTimer` on the GUI thread. We keep the timer's
period fixed at ~33 ms (about 30 Hz) and vary the per-tick *stride*
(`frames_per_tick`) with the speed multiplier. Below ~10 ms timers
become noisy on macOS / Linux; varying stride keeps high speeds smooth
without that risk.

## LaTeX

`latex_to_array(latex)` returns an `(H, W, 4)` uint8 RGBA buffer.
`latex_to_qimage(latex)` wraps it in a `QImage` ready to paste into a
`QLabel`.

matplotlib mathtext does not support `\begin{aligned}` / `\begin{align}`
/ `\begin{cases}`. We unroll those environments and render each row
individually, then vstack them with a small padding. This covers the
common chaotic-systems case (a 3-row ODE system) without pulling in a
full TeX install.

The GUI panel hosts a `_FlowingLatex` widget that turns each row into an
independent `_LatexRow` (a `QLabel` subclass). On resize, every row
*scales its cached high-DPI pixmap* with `Qt.SmoothTransformation` —
matplotlib is never re-invoked. Rows that are already narrower than the
panel are drawn at native size; wider rows are scaled down proportionally
so the widget never overflows horizontally. If the panel shrinks below
`_FlowingLatex.MIN_WIDTH_PX` (120 px by default), the enclosing
`QScrollArea` allows *vertical* scrolling only.

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
(`_FallbackLorenz`) so the window is always launchable, even if a
broken installation knocks out the registry. The placeholder uses
`scipy.integrate.solve_ivp` and mirrors the real backend's `simulate`
signature exactly — the registered Lorenz takes priority whenever the
backend is available.

## Threading model

Both simulation and video export run on background `QThread` workers
(`_SimulateWorker`, `_ExportWorker` in `main_window.py`) so the Qt main
loop stays responsive. Workers emit `progress(current, total)` and
`finished(...)` / `error(kind, message)` signals; the export worker also
honors a `cancel()` poll so the user can abort a long render.

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
