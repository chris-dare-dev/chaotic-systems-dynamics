# Source registry — frontend-uplift

Curated list of sources each Phase 1 agent reaches for first. **Loaded
by sub-agents at Phase 1 start, NOT by the main session.**

Bias: 2024-2026 active sources only. Anything dormant > 18 months gets
flagged in the brief (still surface it, downgrade confidence).

---

## §1 — Visual lens (for `frontend-uplift-visual`)

The visual-scout boots the GUI and screenshots it from multiple states.
**Tools:** `screencapture` (macOS) for live-window captures, plus
`window.grab()` for off-screen widget captures. The computer-use MCP
is the cross-platform fallback if `screencapture` isn't available.

Standard screenshot script outline (the agent writes its own driver):

```python
from PySide6.QtCore import QTimer
from chaotic_systems.gui.main_window import build_application

app, window = build_application([])
window.resize(1400, 900)
window.show()
# Cycle states, screencapture or window.grab().save() at each.
QTimer.singleShot(<delay_ms>, app.quit)
app.exec()
```

States to cover:
1. Initial (no sim run yet)
2. Lorenz selected, mid-animation
3. RosslerHyper selected, Diagnostics card showing the spectrum
4. Settings menu open
5. Narrow window (900×700) — verify layout adapts
6. Wide window (1800×1100) — verify viewport scales
7. Long-LaTeX system (double pendulum) — verify Mathematics panel doesn't overflow

Output path: `.claude/notes/frontend-uplifts/<ID>/screenshots/<state>.png`.

---

## §2 — Library lens (for `frontend-uplift-library`)

Active Python GUI / 3D-rendering / theming libraries.

| Library | URL | Last release | Read for |
|---|---|---|---|
| PySide6 / Qt 6 | https://doc.qt.io/qtforpython-6/ | active (Qt 6.7+) | Read recent QML / Quick Controls news; native widget improvements; QAbstractAnimation. |
| PyVista | https://github.com/pyvista/pyvista | 0.45 (2025), 0.46 | Changelog — new widgets, decompose, stereo, image resampling. Already pinned in deps. |
| pyvistaqt | https://github.com/pyvista/pyvistaqt | active 2024+ | QtInteractor improvements. |
| qtawesome | https://github.com/spyder-ide/qtawesome | active 2024+ | Material / FontAwesome icon packs for Qt — relevant for toolbar polish. |
| qdarkstyle | https://github.com/ColinDuquesnoy/QDarkStyleSheet | active 2024+ | Pre-built dark-theme QSS — compare against the hand-rolled Tokyo Night current state. |
| qfluentwidgets | https://github.com/zhiyiYo/PyQt-Fluent-Widgets | active 2025 | Microsoft Fluent design system for Qt; modern look. |
| superqt | https://github.com/pyapp-kit/superqt | active 2024+ | Higher-order Qt widgets (sliders, labeled inputs) used in napari. |
| napari | https://github.com/napari/napari | active 2024+ | Reference implementation for modern PyQt scientific UI. Theme system, layer-list pattern, command palette. |
| napari-graph | https://github.com/napari/napari-graph | active | Patterns for graph overlays — may inspire diagnostic panels. |
| matplotlib | https://github.com/matplotlib/matplotlib | active 2025 | FigureCanvasQTAgg for embedded 2D plots (bifurcation, phase portraits). |
| vispy | https://github.com/vispy/vispy | active 2024+ | GPU-accelerated rendering in Qt. Alternative to PyVista for 2D-heavy panels. |
| moderngl | https://github.com/moderngl/moderngl | active | Native GL primitives, embeddable in Qt. |

---

## §3 — Inspiration lens (for `frontend-uplift-inspiration`)

Modern desktop scientific / creative tools to study for patterns.

| Tool | URL | Read for |
|---|---|---|
| napari | https://napari.org/ | Layer-list, command palette, dock-widget pattern, theme switching. |
| ParaView | https://www.paraview.org/ | Animation timeline / cinema controls. |
| Houdini | https://www.sidefx.com/products/houdini/ | Information density, panel system, node-graph affordances. |
| Blender | https://www.blender.org/ | Color picker, slider conventions, modal vs. non-modal. |
| Logic Pro / Ableton | https://www.apple.com/logic-pro/ | Transport controls, mixer, peripheral controls. The current transport bar is already in this vocabulary. |
| Mathematica Notebooks | https://www.wolfram.com/mathematica/ | Equation-rendering panels — Mathematics card peer. |
| Plotly Dash (Desktop) | https://plotly.com/dash/ | Read for *feature surface only* — we're not adopting it. |
| Manim Editor / Manim Studio | https://github.com/ManimCommunity/manim_editor | Animation-pacing UI patterns. |
| Apple HIG 2025 | https://developer.apple.com/design/human-interface-guidelines/ | Spacing, type scale, accent usage. macOS desktop conventions. |
| Microsoft Fluent 2 | https://fluent2.microsoft.design/ | Modern accent + state-color conventions. |
| Material 3 (M3) | https://m3.material.io/ | Token vocabulary; useful even though we're not Material. |

---

## §4 — Internal lens (for `frontend-uplift-current-state-critic`)

This agent reads the GUI code + the screenshots produced by the
visual-scout and surfaces what's wrong from the inside. Tools: Read,
Grep, Glob, image-reading.

| Path | Read for |
|---|---|
| `src/chaotic_systems/gui/main_window.py` | The whole file. Find: redundant widgets, dead branches, inconsistent spacing values, hard-coded colors. |
| `src/chaotic_systems/gui/theme.py` | Palette tokens. Anything used in code but not declared here is a leak. |
| `src/chaotic_systems/gui/assets/dark.qss` | The actual stylesheet. Compare against `docs/ui_design.md` — discrepancies between declared tokens and applied selectors are findings. |
| `src/chaotic_systems/gui/assets/icons/*.svg` | Inventory. Check consistency (size, stroke, fill). |
| `docs/ui_design.md` | Design intent. Cross-reference vs. actual implementation. |
| Recent screenshots (Phase 1's `screenshots/`) | Visual evidence. Look at the actual pixels, not just the code. |
| `git log --oneline -50` | What's recently shipped; don't propose duplicates. |
| `CONTEXT.md` "Recently shipped" | Same as above. |
| `UI_CRITIQUE.md` (if present) | Historical issues that already got fixed; don't re-litigate. |

Special prompt: the current-state-critic is the analog of
capability-scout-internal-adversary, but visual. Find:
- **Inconsistencies** between `docs/ui_design.md` and the rendered UI.
- **Token leaks** — hex colors in QSS that aren't from the palette.
- **Dead code** — widgets created but never shown.
- **Anti-patterns** to warn other scouts about.

---

## Updating this file

When a new venue / library / pattern proves load-bearing, add it here.
This file IS the institutional memory of "where do we look for X" for
the visual side of the project.
