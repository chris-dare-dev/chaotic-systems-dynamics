# UI design (living doc)

Status: 2026-05-15. The native PySide6 GUI started life as a vanilla
left/center/right `QSplitter`. This doc records the design tokens we
settled on when we modernized it. Keep it short and concrete — if the
look-and-feel drifts, update this file in the same commit.

## Goals

The GUI is meant to feel like a native scientific tool — closer to
napari, ParaView, Houdini, or Blender than to a webapp. Concretely:

- Dark by default. Scientific desktop apps are overwhelmingly dark in
  2025 because viewports look better against a low-luminance chrome.
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
| `font-h2`    | 15        | card titles, section headings      |
| `font-h1`    | 18        | window-title overlays              |

A monospaced `font-mono` (system default monospace, 11 pt) is used for
the state-readout and the frame/time chip in the status bar so digit
widths don't jitter as values change.

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
+-----------------------------------------------------------------+
| QToolBar : Run | Pause | Stop | Jump-to-end | Export | Reset    |
+----------------+----------------------------+-------------------+
|  System  v     |                            | Mathematics       |
|----------------|                            |  v Equations of   |
|  Parameters    |                            |    motion         |
|  sigma  10.000 |    PyVista viewport        |    [LaTeX img]    |
|  rho    28.000 |  (Lorenz)  (overlay tag)   |  v Lagrangian /   |
|  beta    2.667 |                            |    Hamiltonian    |
|----------------|                            |    [LaTeX img]    |
|  Integrator    |                            |                   |
|  RK45  v       |                            |                   |
|----------------|                            |                   |
|  Time range    |                            |                   |
|  t_end  40.0   |                            |                   |
|  dt     0.010  |                            |                   |
|----------------|                            |                   |
|  Export        |                            |                   |
|  [Export MP4]  |                            |                   |
|----------------+----------------------------+-------------------+
| status: Idle | frame 1 / 4001 | t = 0.000s | lambda1 = 0.907    |
+-----------------------------------------------------------------+
```

Minimum panel widths: left >= 300 px, right >= 340 px, viewport >= 480 px.

## Toolbar QAction object names

The toolbar leaves transport actions as stubs — a parallel agent owns
the animation playback wiring. Stable object names so they can be
looked up by name without re-creating the toolbar:

| object name         | icon (`QStyle.StandardPixmap`) | label         |
| ------------------- | ------------------------------ | ------------- |
| `transport_run`     | `SP_MediaPlay`                 | Run           |
| `transport_pause`   | `SP_MediaPause`                | Pause         |
| `transport_stop`    | `SP_MediaStop`                 | Stop          |
| `transport_jump_end`| `SP_MediaSkipForward`          | Jump to end   |
| `action_export`     | `SP_DialogSaveButton`          | Export MP4    |
| `action_reset_view` | `SP_BrowserReload`             | Reset view    |
| `action_toggle_theme`| `SP_DesktopIcon`              | Toggle theme  |

`MainWindow.transport_actions()` returns a `dict[str, QAction]` keyed
by object name; the animation agent can use this for wiring.

## Affordance rules

- "Run" is the only primary-variant button. Everything else uses the
  secondary variant or the toolbar's flat icon style.
- A button is disabled (not hidden) when it isn't valid for the
  current state. Pause / Stop / Jump-to-end live in `disabled` state
  until a sim is running or a trajectory exists.
- Every parameter widget gets a tooltip from the `Parameter`'s
  `description` and (if present) `units` fields.
- The viewport corners carry a thin border (1 px, `--border`) and a
  semi-transparent system-name overlay top-left.
