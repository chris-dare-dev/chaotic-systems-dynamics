# UI design (living doc)

Status: 2026-05-20. The native PySide6 GUI started life as a vanilla
left/center/right `QSplitter`. This doc records the design tokens we
settled on when we modernized it. Keep it short and concrete — if the
look-and-feel drifts, update this file in the same commit.

## Goals

The GUI is meant to feel like a native scientific tool — closer to
napari, ParaView, Houdini, or Blender than to a webapp. Concretely:

- Dark by default. Scientific desktop apps are overwhelmingly dark in
  2025-2026 because viewports look better against a low-luminance chrome.
- Information density without clutter. Card-style group boxes give the
  parameter form structure; a toolbar collapses the run/export/transport
  controls out of the parameter scroll area.
- The math is the hero. The viewport breathes, the LaTeX panel is wide
  enough to read.

## Palette — Tokyo Night Storm (dark)

We picked Tokyo Night Storm because (a) it has a great accent ramp for
the primary "Run" action, (b) the editor / IDE community has done the
contrast math already, and (c) it pairs cleanly with viridis (the
renderer's default colormap).

| Token                | Hex       | Use                                  |
| -------------------- | --------- | ------------------------------------ |
| `--bg-window`        | `#24283b` | window background, dock surfaces     |
| `--bg-panel`         | `#1f2335` | card / group-box surface             |
| `--bg-elevated`      | `#2a2e42` | hover, input, dropdown surface       |
| `--bg-viewport`      | `#16161e` | PyVista clear color                  |
| `--border`           | `#3b4261` | card outlines, separators            |
| `--border-strong`    | `#545c7e` | focus outline                        |
| `--text-primary`     | `#c0caf5` | body text                            |
| `--text-secondary`   | `#9aa5ce` | labels, captions                     |
| `--text-muted`       | `#565f89` | disabled                             |
| `--accent`           | `#7aa2f7` | primary button, slider handle, focus |
| `--accent-strong`    | `#9eb6fb` | hover on primary                     |
| `--accent-text`      | `#1f2335` | text on `--accent` surfaces          |
| `--success`          | `#9ece6a` | status: running / ok                 |
| `--warning`          | `#e0af68` | status: degraded                     |
| `--error`            | `#f7768e` | error toast, validation              |
| `--lyapunov`         | `#bb9af7` | Lyapunov readout chip                |

**Derived interaction shades (FU-002).** QSS has no variable
substitution, so the shades below live as literals in `dark.qss` and
as named fields on `theme.PALETTE`. Inline `/* token-name */`
comments at each use site keep the binding traceable.

| Token              | Hex       | Use                                                      |
| ------------------ | --------- | -------------------------------------------------------- |
| `--bg-deep`        | `#1a1b26` | Notes code blocks; pill progress track-start; "Deep Night" preset |
| `--bg-pill-track`  | `#2a2c3a` | Pill progress-bar track-end                              |
| `--accent-hover`   | `#343a55` | Hover state for secondary QPushButton / QToolButton / QSpinBox up-down buttons / QCheckBox indicator hover / QListView item hover |
| `--accent-pressed` | `#6788d8` | Pressed state for primary QPushButton / QToolButton; pill progress chunk dark stop |
| `--accent-glow`    | `#a4c1ff` | Pill progress chunk highlight stop                       |

The light theme is a stub for now — `apply_theme(app, "light")` is wired
but the QSS is intentionally not yet shipped; we'll fill it in when the
first user asks. Dark is the default everywhere.

## Typography

Single scale, four sizes. Qt picks the system font on each OS (San
Francisco on macOS, Segoe UI on Windows, Cantarell/Inter on Linux); we
only set sizes.

| Token        | Size (pt) | Use                                |
| ------------ | --------- | ---------------------------------- |
| `font-body`  | 11        | spinboxes, sliders, status bar     |
| `font-ctrl`  | 13        | buttons, combo boxes               |
| `font-h2`    | 14        | card titles, section headings      |
| `font-h1`    | 18        | window-title overlays              |

A monospaced `font-mono` (system default monospace, 10-11 pt) is used
for the state-readout, the frame/time chip in the status bar, the FU-019
per-row parameter readout chips (`QLabel[role="readout-chip"]`), and the
FU-029 parameter strip below the equations card
(`QLabel[role="param-strip"]`) so digit widths don't jitter as values
change.

## Spacing tokens

Two outer margins and two inner spacings. No 3 / 5 / 7 px values
anywhere.

| Token     | Pixels | Use                                                |
| --------- | ------ | -------------------------------------------------- |
| `pad-xs`  | 4      | tight inline gap (icon + label inside a button)    |
| `pad-sm`  | 8      | layout `setSpacing`, intra-card row gap            |
| `pad-md`  | 12     | card padding, panel inner margin                   |
| `pad-lg`  | 16     | panel outer margin, splitter inset                 |

Card group boxes get `pad-md` padding inside, `pad-sm` between rows,
and `pad-lg` between adjacent cards. Panel outer layouts use
`setContentsMargins(pad-lg, pad-lg, pad-lg, pad-lg)`.

## Layout map

```
+--------------------------------------------------------------------------+
| QToolBar : [System v] Run [Auto] Pause Stop Jump-to-end | Export | Reset |
|                                          view | Analyse... v | Theme    |
+----------------+----------------------------+----------------------------+
|  Parameters    |                            | Mathematics                |
|  sigma  10.000 |                            |  v Equations of motion     |
|  rho    28.000 |    PyVista viewport        |    [LaTeX img]             |
|  beta    2.667 |  (Lorenz)  (overlay tag)   |    sigma = 10.000   rho =  |
|----------------|                            |    28.000   beta = 2.667   |
|  Integrator    |                            |  v Lagrangian / Hamiltonian|
|  RK45  v       |                            |    [LaTeX img]             |
|----------------|                            |  v Notes                   |
|  Time range    |                            |    educational markdown    |
|  t_end  40.0   |                            |                            |
|  dt     0.010  |                            |                            |
|----------------|                            |                            |
|  Diagnostics   |                            |                            |
|  [Lyapunov...] |                            |                            |
|  lambda1 ...   |                            |                            |
|----------------+----------------------------+----------------------------+
| Transport: [|>] [pause] Speed: [1x v] [====O====]  t = 0.000 / 0.000     |
+--------------------------------------------------------------------------+
| status: Idle | frame 1 / 4001 | t = 0.000s | lambda1 = 0.907             |
+--------------------------------------------------------------------------+
```

Minimum panel widths: left >= 300 px, right >= 340 px, viewport >= 480 px.
Splitter stretch ratio is 1 : 3 : 1 (left : viewport : right) post-FU-007
— extra width distributes proportionally so the parameter card and the
Mathematics panel keep their controls readable as the window grows.

The Export card that lived in the lower-left pre-2026-05-15 is gone;
Export now lives in the toolbar only. The FU-029 parameter strip
underneath the LaTeX rows reads as `sigma = 10.000    rho = 28.000
beta = 2.667` and updates live as the spinboxes change.

## Toolbar QAction object names

The toolbar leaves transport actions as stubs — a parallel agent owns
the animation playback wiring. Stable object names so they can be
looked up by name without re-creating the toolbar. Icons are resolved
through `chaotic_systems.gui.icons.icon_for_stem` (FU-005 — qtawesome
MDI6 glyphs); the `MDI6 glyph` column lists the resolved icon for each
stem.

| object name             | MDI6 glyph                          | label             |
| ----------------------- | ----------------------------------- | ----------------- |
| `transport_run`         | `mdi6.play`                         | Run               |
| `action_live_preview`   | `mdi6.flash`                        | Auto (FU-017)     |
| `transport_pause`       | `mdi6.pause`                        | Pause             |
| `transport_stop`        | `mdi6.stop`                         | Stop              |
| `transport_jump_end`    | `mdi6.skip-next`                    | Jump to end       |
| `action_export`         | `mdi6.file-export-outline`          | Export MP4        |
| `action_reset_view`     | `mdi6.crop-rotate`                  | Reset view        |
| `action_bifurcation`    | `mdi6.chart-bell-curve-cumulative`  | Bifurcation...    |
| `action_phase_portrait` | `mdi6.chart-scatter-plot`           | Phase portrait... |
| `action_recurrence`     | `mdi6.dots-grid`                    | Recurrence plot...|
| `action_basins`         | `mdi6.map-marker-radius`            | Basins...         |
| `action_poincare`       | `mdi6.crosshairs`                   | Poincare section..|
| `action_toggle_theme`   | `mdi6.theme-light-dark`             | Toggle theme      |

The Settings dropdown carries a gear icon (`mdi6.cog`) and exposes
secondary toggles (axes, grid, vector preview, compare-IC overlay,
Auto pill mirror, background color presets, trajectory width slider,
Preferences...). `MainWindow.transport_actions()` returns a
`dict[str, QAction]` keyed by object name; the animation agent and
the FU-014 command palette both use this for action discovery.

## Affordance rules

- "Run" is the only **app-scoped** primary-variant button — it's the
  one-click "do the headline thing" affordance. Panel-internal Compute
  buttons (Bifurcation / Recurrence / Basin / Poincare diagnostic
  panels) may also use `variant="primary"` because they are that
  panel's primary action; the scope is the panel, not the app.
- A button is disabled (not hidden) when it isn't valid for the
  current state. Pause / Stop / Jump-to-end live in `disabled` state
  until a sim is running or a trajectory exists.
- Every parameter widget gets a tooltip from the `Parameter`'s
  `description` and (if present) `units` fields; the row carries a
  live FU-019 `QLabel[role="readout-chip"]` that switches to
  scientific notation outside the 0.001-1000 magnitude band.
- The viewport corners carry a thin border (1 px, `--border`) and a
  semi-transparent system-name overlay top-left.
- State-layer contract (FU-016, kept WCAG 2.1 AA aligned): every
  interactive widget ships explicit `:hover` (accent-hover overlay),
  `:focus` (2 px accent outline), and `:pressed` (accent-pressed)
  pseudo-states. The eight widget families with the contract are
  QPushButton, QToolButton, QComboBox, QSpinBox / QDoubleSpinBox,
  QLineEdit, QSlider, QCheckBox, QListView / QListWidget. See
  `dark.qss` for the rules.

## Global keyboard shortcuts

| Shortcut         | Action                                         |
| ---------------- | ---------------------------------------------- |
| `Ctrl+R`         | Run simulation                                 |
| `Ctrl+E`         | Export trajectory to MP4                       |
| `Space`          | Toggle play / pause                            |
| `Ctrl+.`         | Stop animation                                 |
| `End`            | Jump to last frame of trajectory               |
| `Esc`            | Cancel in-flight worker (sim / export / Lyapunov) |
| `R`              | Reset 3D camera                                |
| `Ctrl+,`         | Open Preferences dialog (FU-013)               |
| `Ctrl+Shift+P`   | Open command palette (FU-014)                  |

`Ctrl+,` and `Ctrl+Shift+P` mirror the napari / VS Code / Houdini
conventions; the rest are project-local.
