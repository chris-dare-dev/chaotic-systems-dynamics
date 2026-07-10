# Chaotic-systems-dynamics — house design system (frontend-uplift overlay)

The repo-local house-thesis overlay required by `frontend-design-language.md` §9. The shared
canon is product-neutral; **this file is the only place** the product's thesis, its named
anti-references, and its surface map may live.

**Who reads this:**

| Consumer | When | How |
|---|---|---|
| `frontend-uplift-art-direction-scout` | Phase 1 (every mode) | Reads this before proposing the run's thesis + 3 directions; re-confirms the §10 current-state score against the visual-scout screenshots. |
| `frontend-uplift-challenger` | Phase 3, Axis 11 | Scores candidates against §9.2 anti-references + the native BAN translation in §9.5. |
| `pipeline-synthesizer` | Phase 2 | Opens `synthesis.md` with the frame anchored here. |

**Grounding.** Every claim below is traceable to the code: `src/chaotic_systems/gui/theme.py`
(palette + Fusion/QPalette/QSS), `docs/ui_design.md` (tokens + layout + FU-016 focus contract +
shortcuts), `src/chaotic_systems/gui/` (the panels), `CLAUDE.md` ("the frontend is native — do
not change that"). Where a claim is **debt** rather than a shipped fact, it is marked so — nothing
here is aspirational fiction.

---

## §9.1 — Visual thesis (one sentence)

> **A machined dark observatory for chaos: the attractor is the hero, every control reads as a
> calibrated instrument, and the chrome recedes so sensitive-dependence structure is legible at a
> glance — a native scientific tool, never a webapp in a window.**

**Swap-test.** Substitute a competitor ("napari", "a generic analytics dashboard"): the sentence
collapses — it is anchored to *chaotic dynamics* (the attractor as the object of study,
sensitive-dependence as the thing to read) and to the native-instrument invariants below, not to a
category. It passes.

**Invariants the thesis protects** (NOT a silhouette mandate — §6/§8 patterns are worked examples,
and cloning a panel's shell across the app is BAN-15):

1. **The math is the hero.** The 3D viewport / attractor is the lede; parameter chrome and
   analysis panels are visibly subordinate (`docs/ui_design.md` "Layout map", splitter stretch
   1:3:1 favouring the viewport).
2. **Instrument calm at repeat-use.** This is an all-S-2 tool used for long analysis sessions —
   no spectacle, no theatrics, no motion for its own sake.
3. **Honest scientific data-viz.** Every plot (bifurcation, Poincaré, recurrence, basin,
   conservation) answers a decision; achromatic + one accent + semantic-when-state, never a
   decorative rainbow.
4. **Numerical trust.** Tabular/mono numerals so digits don't jitter as values change; canonical
   parameters cited (`docs/ui_design.md` mono `font-mono` voice; FU-019 readout chips, FU-029
   parameter strip).
5. **Native, never web.** No browser tab, no DOM, no "open localhost". This is the product's
   hardest lock (`CLAUDE.md`).

**Current material (already largely thesis-aligned, `theme.py`).** Tokyo Night Storm dark: an
**ink** family (`#24283b` / `#1f2335` / `#16161e`) — hue-tinted near-black, NOT saturated navy —
with **one** primary accent (`#7aa2f7`) for the "Run" affordance and semantic colours reserved for
state (`success #9ece6a`, `warning #e0af68`, `error #f7768e`, `lyapunov #bb9af7`). This is the §6
"pick a material, one accent, semantic-for-state" spec already in place; the uplift's job is to
protect it, not re-skin it.

---

## §9.2 — Named anti-references (what this product must never look like)

Each is the concrete "never again" baseline for Axis 11. BAN tokens are from `frontend-design-language.md` §5.

| Anti-reference | What it looks like | BAN-N it exemplifies |
|---|---|---|
| **"SaaS dashboard in a window"** | A dark-navy + multi-neon web-console shell, sidebar-topbar-card-grid, "Welcome back" opener — the generic AI dashboard, wearing a Qt title bar. The product's defining never-again (`CLAUDE.md` bans Electron/Tauri/web frameworks). | BAN-1, BAN-2, BAN-13 |
| **"Undirected Qt-default toolkit form"** | Raw system-native widgets with no pinned Fusion style / no `theme.PALETTE` discipline — the grey/white panel-title blocks and mis-placed native dropdowns `theme.py` documents fixing on Windows. The Qt analog of the untouched default-stack look. | BAN-4 |
| **"MATLAB rainbow figure dump"** | Analysis panels rendered as decorative multi-hue matplotlib plots with no threshold, annotation, or "so what" — colour as decoration, not decision. | BAN-6, BAN-11 |
| **"Status-chip soup"** | Colored status pills scattered across parameter rows and the toolbar until the semantic palette stops meaning anything. | BAN-7 |
| **"Equal-weight card wall"** | Every panel the same visual weight, no lede — directly contradicts "the math is the hero". | BAN-5, BAN-2 |

---

## §9.3 — Surface map

The app is a **single native desktop window**; "surfaces" are its panels/views. **Every surface is
S-2 (tool)** — there is deliberately **no S-1** (no marketing/landing/brand page) and **no S-1m**
(no login, signup, onboarding, or first-run choreography). This is exactly why the
`experiential-scout` is INERT here and experiential motion (parallax/WebGL/scroll theater) is
BLOCKED across the board (design-language §3, motion-vocabulary §0).

| Surface | File(s) | Class | Notes |
|---|---|---|---|
| Main window shell (toolbar / params / viewport / mathematics / transport / status) | `gui/main_window.py` | **S-2** | The instrument frame. Toolbar QActions have stable object names; splitter 1:3:1 keeps the viewport the lede. |
| 3D attractor viewport | PyVista viewport in `gui/main_window.py`, `visualization/renderer.py` | **S-2** | The focal hero. Its motion is **data-motion** (trajectory tracing, camera) on a 16 ms / 60 Hz tick with one `Render()` per tick — a named continuity/orientation job, NOT experiential spectacle. |
| Parameter form + diagnostics (left) | `gui/main_window.py`, `gui/_panel_helpers.py`, `gui/_scrub_spinbox.py` | **S-2** | Compact instrument density; per-row FU-019 readout chips, tooltips from `Parameter.description`. |
| Mathematics panel (equations / Lagrangian-Hamiltonian / Notes) | `gui/main_window.py` (LaTeX via `visualization/latex.py`) | **S-2** | Editorial-adjacent but a tool panel: the math typeset as evidence, not marketing hero type. |
| Analysis panels: bifurcation, phase portrait, recurrence, basin, Poincaré, conradi, conservation | `gui/bifurcation_panel.py`, `gui/phase_panel.py`, `gui/recurrence_panel.py`, `gui/basin_panel.py`, `gui/poincare_panel.py`, `gui/conradi_panel.py`, `gui/conservation_panel.py` | **S-2** | Each is a decision instrument — annotated figures, semantic-when-state colour. BAN-6/11 are the live risks here. |
| Command palette | `gui/command_palette.py` | **S-2** | Ctrl+Shift+P overlay (napari/VS Code convention). |
| Preferences dialog | `gui/preferences_dialog.py` | **S-2** | Ctrl+, — where a reduced-motion toggle would live (`QSettings` already used here). |
| Empty / first-run viewport (before any Run) | `gui/main_window.py` | **S-2** (honest empty-state, NOT a cinematic threshold) | The closest thing to an S-1m "moment"; treat as a tool empty-state (cause + one action), never a choreographed intro. |

---

## §9.4 — Current-state honesty (aligned vs. debt)

The art-direction-scout must re-score against live screenshots, but the code-grounded baseline is:

**Already aligned (protect, don't churn):** ink material + one accent + semantic-for-state
(`theme.py`); authored spacing scale 4/8/12/16 (`docs/ui_design.md`); a mono data voice for
numerals; the viewport-as-lede layout; the FU-016 state-layer focus contract (explicit
`:hover` / `:focus` 2 px accent outline / `:pressed` across 8 widget families, WCAG 2.1 AA aligned);
tooltips on every parameter widget; a full keyboard map (Ctrl+R / Space / Esc / R / Ctrl+, /
Ctrl+Shift+P). The §10 current-state score is expected to be **low** — this is not a generic
dashboard; the pipeline's job here is direction + a11y debt, not a de-cliché rescue.

**Honest debt (candidate seeds — mostly the a11y-safety-debt lane):**

- **Light theme is a stub.** `assets/light.qss` does **not** exist; `theme._stylesheet_path`
  falls back to `dark.qss` for `mode="light"`. There is **no dark/light parity** — a real a11y
  item, not a cosmetic one.
- **No screen-reader accessible-name coverage.** `setAccessibleName` / `setAccessibleDescription`
  appear **0 times** in `src/chaotic_systems/gui/`. Focus rings + tooltips + object names exist,
  but assistive-tech naming does not.
- **No reduced-motion honoring.** There is **no** `QPropertyAnimation` / `QEasingCurve` and no
  reduced-motion toggle anywhere in the GUI; motion is raw `QTimer` data-motion (attractor spin,
  trajectory playback, the pill progress bar). A `QSettings` store already exists
  (`preferences_dialog.py`) as the home for a reduced-motion preference.

---

## §9.5 — Native translation of the canon (web mechanics → Qt facility)

The canon's *substance* applies fully; its *web mechanics* translate. Inapplicable axes are INERT.

| Canon axis (web form) | This repo (native Qt form) |
|---|---|
| Design tokens (CSS variables) | `theme.PALETTE` dataclass + `assets/dark.qss` + `_apply_base_style` `QPalette`; Fusion style pinned for cross-platform parity. QSS has no variable substitution — derived shades live as named `PALETTE` fields with `/* token */` comments (FU-002). |
| Motion (CSS transitions / `@media (prefers-reduced-motion)`) | `QPropertyAnimation` / `QVariantAnimation` for UI microinteractions; a **`QSettings` reduced-motion toggle** (not a media query) gating them. Native facility first; a new engine only when a named motion job (orientation / causality / feedback / continuity) needs one. |
| Performance (bundle KB) | **Startup construct-and-quit time + per-frame budget** (16 ms / 60 Hz animation tick; one `Render()` per tick; Catmull-Rom prerender — `docs/visualization.md`, `docs/prerender_design.md`). Heavy compute belongs on a `QThread` worker, never in the tick. |
| Accessibility (ARIA) | Focus/tab order, **`setAccessibleName` / `setAccessibleDescription`**, `.qss` contrast (WCAG 2.2 AA in both themes), `QShortcut` keyboard equivalence — not ARIA. |
| **INERT (do not raise a finding):** bundle-size KB · React 19/RSC compat · mobile/touch parity · experiential scroll/parallax/WebGL | No bundler, no React, desktop-only native window, no S-1 surface. Name inert if invoked; never manufacture a finding. |

---

## §9.6 — The four questions (design-language §11), answered for this repo

- **Q1 (which anti-reference removed?)** — steer away from §9.2's "SaaS dashboard in a window"
  (BAN-1/2/13) and "undirected Qt-default form" (BAN-4).
- **Q2 (which reference trait, translated?)** — the reference sites' *discipline* (hierarchy,
  typographic confidence, authored pacing, one focal idea) translated to a native instrument;
  never their scroll theater (design-language §6, "borrow discipline not spectacle").
- **Q3 (why appropriate for the surface class?)** — every surface is S-2; instrument language,
  motion only when it serves a named job.
- **Q4 (recognizably NOT a default assembly?)** — ink-observatory material + viewport-as-hero +
  mono numeric voice + annotated scientific figures reads as *this* instrument, not a stock Qt
  form or a shadcn dashboard.
