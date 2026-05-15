# Adversarial UI/UX Critique

Reviewer: hostile senior product designer. Date: 2026-05-15.
Build under review: `main` at `f20d9e2` / `282243a` / `e3d7118` / `3fee2ec`.
Local-only UI fix: `88e980c` (already applied — included in this critique).

## TL;DR

This looks like a 2014 PyQt example dressed up with a stylesheet. The Tokyo
Night palette is fine; everything else fights it. The window is dominated
by a 50%+ wide pure-black rectangle that says nothing until you find and
press Run; the left column is a top-down questionnaire of five identical
gray cards with no visual hierarchy and the "primary" Run button buried at
position five in the scroll order; transport actions appear in two places
(toolbar + bottom strip) with mismatched labels (`Run`/`Pause` vs.
`Play`/`Stop`); the LaTeX panel renders raw error tracebacks for the
double pendulum (`<LaTeX render failed: Unknown symbol: \tfrac>`); and the
viewport ships visible OpenGL repaint garbage when the splitter is
resized narrow. Overall captivating-ness: **4 / 10** — the chrome is
defensible, the content surface and information design are not.

## Screenshots captured

All under `/tmp/`:

- `critique_initial.png` — first-paint, 1400x900. Side panels are blank;
  only the toolbar and status bar drew. This is a real first-paint bug,
  not a screenshot artifact (a fresh user will see a flash of empty
  chrome).
- `critique_system_rossler.png` — Rössler selected, default Lorenz-like
  state. Representative "settled" empty state.
- `critique_system_double_pendulum.png` — DoublePendulum selected. The
  LaTeX panel renders raw `ParseFatalException: Unknown symbol: \tfrac`
  text for *both* the equation-of-motion and Lagrangian sections.
  **This is the actively visible bug a first-time user hits if they
  click anything other than Lorenz/Rössler.**
- `critique_after_run.png` — after `_on_run()`. Status chip flipped to
  `Running` (green) and progress bar shows. **Viewport overlay reads
  `LorenzPendulum`** — the previous system's overlay text wasn't
  cleared when the system was switched back, so two labels overlap.
- `critique_narrow_window.png` — window resized to 900x700 while a run
  was in flight. **The QtInteractor viewport is filled with white
  scratch-line repaint garbage** — uninitialized framebuffer bleeding
  through when the OpenGL widget is shrunk. Not subtle.
- `critique_wide_window.png` — 1800x1000. The black void in the center
  is now ~1000 px wide and 850 px tall containing literally nothing
  except a `Lorenz` chip in the top-left. Nothing on screen invites
  the user to do anything.
- `critique_collapsible.png` — Lagrangian section collapsed. The right
  panel now has an enormous empty band between the equations and the
  collapsed `> Lagrangian / Hamiltonian` header because both sections
  carry equal stretch in the QVBoxLayout, so collapsing one doesn't
  give the space back.
- `/tmp/chaotic_gui_before.png`, `/tmp/chaotic_gui_after.png` — the
  before/after the user supplied. The "after" is what this doc
  critiques.

## Visual design — critical

1. **The viewport is a black void with no content until you find the Run
   button.** ~50% of the window's pixels carry zero information on
   launch. No vector-field preview, no grid, no axis triad cue, no
   placeholder copy. Compare ParaView (always shows an orientation
   gizmo + grid even with no data) and napari (shows a checker pattern
   and an axes overlay). **`main_window.py:1079–1110`** builds the
   viewport with no empty-state content. The only thing painted is the
   `Lorenz` chip overlay at top-left.
2. **The primary action is buried.** The "Run" button at
   `main_window.py:1019–1023` lives in the *fifth* card in the left
   panel (System → Parameters → Integrator → Time range → Run). A
   first-time user scrolls past 4 cards before they hit it. The
   toolbar's `transport_run` (`main_window.py:1531–1539`) duplicates it
   but is the same width as the other 6 actions, so it doesn't read as
   primary even with `variant="primary"` — the blue pill is a 60-px
   action drowning in a 720-px toolbar row.
3. **DoublePendulum's equations render as raw exception text.** Visible
   in `critique_system_double_pendulum.png`. `\tfrac` is rejected by
   matplotlib's mathtext renderer, and the failure path at
   `main_window.py:442–443` and `main_window.py:1297–1299` dumps the
   `ParseFatalException` string into a QLabel inside the math card —
   in 12pt body text, no error styling, no recovery suggestion. The
   user sees `ParseFatalException: Unknown symbol: \tfrac, found '\'`
   and concludes the app is broken. **This is the worst single defect
   in the build.**
4. **Card titles look like body labels.** `dark.qss:49–58` styles
   `QGroupBox[variant="card"]::title` at 12pt 600-weight in
   `text-secondary` (`#9aa5ce`). The form labels inside the cards
   (e.g. `sigma`, `rho`, `beta`) are styled with `role="caption"` at
   10pt in the same color (`dark.qss:72–75`). The result: scanning the
   left panel, "System" / "Parameters" / "Integrator" don't look like
   *headings*, they look like one more label-row. There is no h1/h2/h3
   visual rhythm — the type-scale documented in `docs/ui_design.md:57–62`
   (`font-h2: 15pt`) is **not actually applied** in the QSS for card
   titles, which use 12pt instead. The docs and the stylesheet are
   out of sync.
5. **OpenGL framebuffer garbage on resize.** `critique_narrow_window.png`
   shows horizontal white streaks across the entire viewport — typical
   of a `QOpenGLWidget` whose `paintGL` isn't called for every resize
   region. The fix is wrapping the `QtInteractor.interactor` in a
   widget that triggers a `viewer.render()` on `resizeEvent`, or
   forcing `pv.global_theme.smooth_shading` / a clear-on-resize. As
   it stands, anyone who drags the splitter sees ghost frames.

## Visual design — high

6. **Two transport surfaces, mismatched labels.** Toolbar uses
   `Run / Pause / Stop / Jump to end` (`main_window.py:1531–1563`).
   Transport strip below the viewport uses `Play / Stop / End`
   (`main_window.py:1795–1806`). Same action, three different names
   on the same screen. Pick one vocabulary. If transport is the
   primary surface (per the docstring at `main_window.py:43–45`),
   delete the duplicate toolbar transport actions or convert them to
   keyboard-shortcut hints only.
7. **The accent isn't actually anchoring the eye.** `--accent`
   (`#7aa2f7`) appears on the Run button (primary), the slider fills,
   the slider handles' rings, the spinbox focus rings, the combobox
   focus rings, the progress bar chunk, and the QSS hover/focus
   borders — six places. Six accents is no accent. Look at
   `critique_system_rossler.png`: your eye doesn't go to Run, it
   wanders between three blue sliders, three blue spinbox-borders,
   the blue progress placeholder, and the blue toolbar button.
8. **"Lorenz" overlay chip is half the size of the System combo it
   duplicates.** `main_window.py:625–642` + `dark.qss:77–85`. The
   chip is just the system name in a 4×8 padded pill. The user just
   picked "Lorenz" from the dropdown 4 inches away — they don't need
   a chip to tell them what they picked. ParaView/Napari use that
   corner for a *3D orientation widget* (the little RGB axis cross).
   The chip is also bugged — `critique_after_run.png` shows
   `LorenzPendulum` because the overlay text isn't cleared when the
   system list changes. `_ViewportOverlay.set_system_name` at
   `main_window.py:636–642` calls `setText` then `adjustSize` but the
   previous text is not erased before; under some redraw orders this
   produces overlap. Fix: explicitly `self.clear()` first, or use
   `setText("")` then `setText(name)` two-phase.
9. **No visible focus rings.** `dark.qss:502–511` sets
   `outline: none` and only changes the border-color on focus. On
   a dark theme with already-blue borders for hover, focus is
   *invisible*. Keyboard-only navigation is broken-feeling. Tab
   through the left panel and you can't tell which widget has focus.
10. **The toolbar icons are 18×18 Qt-stock pixmaps.** `setIconSize(QSize(18,18))`
    at `main_window.py:1603`, paired with `SP_MediaPlay`, `SP_MediaPause`,
    `SP_MediaStop`, `SP_DialogSaveButton`, `SP_BrowserReload`,
    `SP_DesktopIcon` (`main_window.py:1531–1587`). These are macOS's
    *system* style icons — gradient triangles, a floppy disk, a
    cartoon refresh swirl, a *desktop monitor* for "Toggle theme"
    (??). They look like a Visual Basic 6 toolbar. Ship SVGs
    (Lucide, Phosphor, or Feather) and recolor via QSS so the icons
    inherit the palette.
11. **Card titles overlap their borders.** `dark.qss:49–58` sets
    `margin-top: 16px` on the groupbox and `top: -2px` on the title,
    making the title sit on the border line with `padding: 0 6px` to
    cut the line — a classic "fieldset title cut-out". On dark UI it
    looks visually weak: the title isn't *above* the card, it's
    *bisecting* the top border. Modern dark UI (Linear, Notion,
    Figma) puts the title *outside* the card, left-aligned, 4–6 px
    above, in `text-primary` weight 600, with the card surface
    starting clean.

## Visual design — medium

12. **Spinbox + slider rows are cramped.** Spinbox `min-width: 88`
    (`main_window.py:689`), slider takes the rest. Decimals run to 4–5
    digits (e.g. `0.20000`, `2.6667`), the field is 5–6 chars wide,
    feels jammed. Either right-align the numbers or widen to 110 px.
13. **`v` chevron and `>` chevron in the collapsible headers are
    ASCII text.** `main_window.py:610–611`:
    `arrow = "v" if expanded else ">"` — literal letters. Compare the
    real SVG chevron-down used in the combobox dropdown at
    `dark.qss:174–178`. The collapsibles need the same SVG, rotated
    90° for collapsed. Right now the "v" is rendered in the
    system font and looks like a stray lowercase letter — confusing.
14. **`Reset view` shares a 50/50 row with `Run`.** `main_window.py:1014–1030`.
    Run is the primary action of the entire app. Reset view is a
    once-in-a-while "I dragged the camera weird, put it back" action.
    They should not be the same visual weight or sit on the same row.
15. **`Export MP4` and `Cancel` share a row.** `main_window.py:1034–1050`.
    Cancel is disabled 99.9% of the time. Having a permanent red-text
    "Cancel" pill next to "Export MP4" reads like a destructive
    confirmation dialog. Hide Cancel until an export is in flight, or
    move it into the progress bar inline.
16. **`Toggle theme` is in the main toolbar with the same visual
    weight as `Run`.** `main_window.py:1581–1587`. Theme switching is
    a settings-menu action, not a top-level one. The user does it
    once a year. It pollutes the primary action surface.
17. **Status bar chips are decorative more than informative.** Three
    permanent chips — `frame 0 / 0`, `t = 0.000`, `lambda1 = -` — sit
    in the bottom-right *before* any simulation runs. They communicate
    nothing because there's no data, but they take up ~360 px of
    chrome. Hide them until there's content, or replace pre-run with
    a single "Press Ctrl-R to integrate" hint.
18. **The `Lyapunov` chip is purple even when empty.** The QSS
    selector `QStatusBar QLabel[role="chip"][highlight="lyapunov"]`
    (`dark.qss:487–490`) paints the border/text purple
    unconditionally. With value `"lambda1 = -"` the styling implies
    "this is a meaningful number". It isn't.
19. **`Mathematics` card title vs. `v Equations of motion` collapsible
    header — two different heading styles two pixels apart.**
    `main_window.py:1139–1175`. The `Mathematics` groupbox-title is a
    QGroupBox::title (Qt-default rendering), the collapsibles use a
    QPushButton with `font-weight: 600`. Two heading systems
    competing in the same panel. Pick one.

## Visual design — low

20. **Splitter handle is 1 px wide** (`main_window.py:1180`,
    `dark.qss:318–322`). Hard to grab. 4 px minimum is the modern
    standard.
21. **`narrow space + multiplication sign` in `f"{s:g}×"`**
    (`main_window.py:1810`) — looks fine, but the comment lies (no
    narrow space is actually inserted).
22. **`x_dot, y_dot, z_dot`** in LaTeX uses dots that float oddly with
    matplotlib mathtext — they appear at slightly different heights
    over different glyphs. Small, but it's the equation panel —
    *the math is supposed to be the hero*.
23. **No tooltips on cards.** Hovering `Time range` doesn't reveal
    why `dt` matters or what `t_end` does to the trajectory length.
    Tooltips exist on spinboxes; not on labels.
24. **The progress bar is always visible-when-visible.**
    `main_window.py:1051–1056` makes it 100% opacity, full width
    inside the Export card. During a sim it sits below the
    `Export MP4 | Cancel` row, looking like it's the *export
    progress* — but it's actually the *sim* progress at that point
    (and indeterminate, range 0/0). Confusing.

## UX flow — critical

**Time-to-first-Lorenz** (empirical, from a fresh launch):

1. App opens. User sees: empty side panel cards on first paint
   (`critique_initial.png`), then default Lorenz form populated.
2. User has to know to press the blue `Run` button. Nothing animates,
   pulses, or hints. It's the 5th card on the left and the 1st
   toolbar action, both styled subtly — neither demands the eye.
3. User clicks Run. ~1–2 s sim. Polyline appears, plays back over
   10 s of wall clock.
4. Total clicks to a Lorenz render: **1 click, ~3 seconds** — but
   only because the default is preselected. Time-to-first-render is
   acceptable; time-to-first-*moment-of-delight* is not. The static
   end-state polyline (after playback finishes) is a thin 2 px
   viridis line on a near-black background. **The "wow" never lands.**

25. **No empty-state pedagogy.** A first-time user sees a black
    rectangle and a form. There's no "Try Lorenz" hint, no animated
    preview, no example screenshot, no breadcrumb that says "step 1:
    pick a system, step 2: press Run". The CLAUDE.md and README
    explain the app; the *app itself* explains nothing.
26. **Pause/Stop/End/Speed are all greyed out until you Run.** Correct
    behavior, but combined with the unmarked viewport it amplifies the
    "nothing works" feeling on first paint. Show them in a teaching
    state — "these will light up after you Run" — instead of dead grey.
27. **No way to cancel a stuck simulation.** `_on_cancel` at
    `main_window.py:1503–1515` only cancels exports; sim cancellation
    is acknowledged with the message "Simulation cannot be cancelled
    mid-step". For the default Lorenz this is sub-second so harmless.
    For DoublePendulum at t_end=1000 the user is wedged.

## UX flow — high

28. **Switching system clears the trajectory but the viewport stays
    dark-empty until the next Run.** This is correct but disorienting:
    a small "Press Run to integrate" hint inside the viewport would
    help.
29. **Scrubber and speed control are below the viewport in a row that
    breaks visual alignment with the buttons in the side panel.**
    `Play | Stop | End | Speed: | combobox | scrubber | time-readout`
    (`main_window.py:1782–1836`) — 7 elements, no grouping, no
    separators, no labels on Play/Stop/End buttons beyond the text.
    Compare QuickTime or Logic Pro: transport is a tight cluster of
    medium-large icons, then a divider, then the scrubber + time.
    Here the play and stop are 60 px text-only buttons; the scrubber
    takes ~600 px; the time label is tiny.
30. **Speed presets jump from 4× to 8× with no `½× / ¼×`** wait — they
    actually do (`0.25, 0.5, 1.0, 2.0, 4.0, 8.0` at
    `main_window.py:1780`). So far so good. But there's no visual cue
    that the dropdown is a scrub-speed; the label `Speed:` is a
    bare-text QLabel rendered at the default 11 pt body color, looking
    like a leftover form label.
31. **The Lagrangian section is shown for non-Lagrangian systems**
    (rebuild logic at `main_window.py:1257–1259` *does* collapse it
    when `lagrangian_latex` is None — good — but the placeholder text
    "(not derived from a Lagrangian)" still sits in the collapsed body
    and pops visible the moment the user expands the section out of
    curiosity. The reveal is anticlimactic).
32. **`End` button is mislabeled.** `Jump-to-end` (toolbar) becomes
    `End` (transport strip). "End" on a media transport usually means
    "skip to end of track"; on a keyboard it means "End key". The
    button at `main_window.py:1804–1806` would read better as
    `⏭ End` or `⤓ Last frame`.

## UX flow — medium

33. **Run button text doesn't change when running.** `_on_run` at
    `main_window.py:1342` only disables it. A modern pattern would
    swap label to "Running…" with a small spinner.
34. **`Export MP4` doesn't show file size estimate or duration
    preview.** Fixed at 30 fps × 10 s = 300 frames at 1280×720
    (`main_window.py:1461–1462`) but the user has no idea. A 300 MB
    file lands in their home dir with no warning.
35. **Parameters card has no "Reset to defaults" affordance.** After
    fiddling sliders, the user has to retype defaults from memory.
    Trivial to add — `default_params(system)` already exists in
    `contract.py`.

## UX flow — low

36. **Keyboard shortcut hints aren't surfaced.** The docstring lists
    Ctrl-R, Ctrl-E, R, Esc, Space, Ctrl-., End. They appear in
    tooltips (good!) but not in any menu, not in a help screen, and
    not in the status bar. No `?` overlay.
37. **No menu bar.** macOS users expect a `File / Edit / View / Help`
    menu bar with "Export…", "Reset View", "About". Currently
    everything is in the toolbar.
38. **`y(t={t:.3f}) = [...]`** state readout (`main_window.py:2018`)
    is the only place a numeric result is shown. It's a QLabel in
    `role="caption"` styling, hidden in the scroll-area below the
    Export card — easy to miss after Run.

## Information architecture

39. **Wrong order on the left.** Today: System → Parameters →
    Integrator → Time range → Export. Better: System → Time range +
    Integrator (together, they describe the *integration*) → 
    Parameters (the *physics*) → Run as a sticky bottom row → Export
    as a separate footer or moved to the toolbar. Putting Parameters
    second forces the user past it every time they're just changing
    `t_end` to re-run.
40. **System picker doesn't belong in the side panel at all.** This
    is a top-level mode switch — like changing tools in Blender.
    Move to the toolbar as a combobox (`Lorenz ▾`) at the far left,
    where it can serve double duty as the window title's subtitle.
41. **Integrator is over-prominent.** Power users care; most users
    won't touch RK45 → LSODA. Collapse the Integrator card into the
    Time-range card as an "Advanced" disclosure.
42. **Run + Reset view shouldn't be in Time-range card.** Run is the
    primary call-to-action of the whole app; it shouldn't live
    inside a card titled "Time range" alongside `dt`. Promote it to
    a sticky footer at the bottom of the left panel that always
    stays visible regardless of scroll.
43. **The Export card belongs in the toolbar.** It has one button +
    one cancel + one progress bar. The toolbar already has
    `action_export`. Delete the side-panel card.
44. **The status-bar lyapunov chip should be promoted.** Lyapunov is
    a *scientific result*, not a piece of chrome. After a run it
    should appear as a prominent readout near the viewport — e.g.
    overlay top-right with the system name's same chip style — so the
    user actually sees "λ₁ ≈ 0.907" and recognizes "ah, that's why
    it's chaotic". Today the status bar is so visually quiet the
    user won't notice.

## The 3D viewport specifically

45. **The trajectory is a 2 px polyline.** `renderer.py:191–202`:
    `line_width: 2.0`, `render_lines_as_tubes: False`. At 1400×800 on
    a Retina display this is a hairline. Bump to `line_width: 4.0` and
    enable `render_lines_as_tubes=True` so the line has body. The
    viridis colormap exists (`renderer.py:121`, default `"viridis"`)
    but at 2 px the gradient is invisible. Modern reference: napari's
    track layer, ParaView's tube filter.
46. **`show_axes()` at `renderer.py:223,225` is the PyVista default
    bottom-left RGB triad.** It's small, low-contrast (the axes use
    primary RGB which doesn't blend with the Tokyo Night palette at
    all — bright red/green/blue against dark navy reads as a
    Christmas-tree decoration), and disappears under any moderate
    zoom. Replace with `add_orientation_widget` for the persistent
    bottom-corner gizmo and recolor the axes to palette-matching
    tones (`text-secondary` for the axis lines, `accent`/`success`/
    `warning` for the X/Y/Z labels).
47. **`show_grid` for the Henon-Heiles / DoublePendulum cases.**
    `renderer.py:218–223`. The grid uses PyVista's defaults — white
    text on the dark `bg_viewport` — but the grid *lines* are also
    white-ish and hide the trajectory. The grid needs to be 20%
    opacity, palette `--border`.
48. **No camera affordance.** No way to switch to top-down /
    side-view presets. No "front / right / top" buttons. ParaView,
    Blender, every CAD app ships these. With a 3D attractor that has
    a *strange* shape, you'd want at least one-click XY / XZ / YZ
    projections.
49. **No depth cueing / fog.** A Lorenz attractor far-side polyline
    is the same color as the near-side polyline. With fog (the
    far-side fading toward `bg_viewport`), the 3D structure pops.
50. **The head sphere is a tiny red dot** (`renderer.py:213`,
    `head_color="#d62728"`). That red doesn't match the palette at
    all — it's a matplotlib tab10 red dropped into Tokyo Night.
    Make it `accent` (`#7aa2f7`) or `lyapunov` (`#bb9af7`).
51. **The viewport background is darker than the surrounding panel
    chrome** — `bg_viewport: #16161e` vs. `bg_panel: #1f2335`. Good
    — visual depth. But the 1 px border around the frame
    (`dark.qss:522–527`) is `--border` (`#3b4261`), which makes the
    viewport look "framed" like a TV. Drop the border entirely and
    use a 2 px inner shadow, or widen the gap to 8 px so the frame
    reads as floating.

## Onboarding & empty states

52. **First-paint side panels are blank.** Confirmed in
    `critique_initial.png` — even after `processEvents()` + 400 ms
    qWait, the side panels showed up as cropped empty cards. This is
    a real visible flash. Likely caused by the lazy LaTeX render
    blocking the first paint, or the splitter sizes being set after
    the show. Either way: bad first impression.
53. **No welcome / "what is this app" surface.** A `View → Welcome`
    or a dismissible card on first launch would explain: "This is a
    chaotic-systems explorer. Pick a system → set parameters →
    press Run." Three lines, links to the README, dismiss-forever
    checkbox.
54. **The default Lorenz is good** (sensible σ=10, ρ=28, β=8/3) but
    the user doesn't know that. A subtitle on the Parameters card —
    "Defaults shown produce the canonical butterfly attractor" —
    would land the hook in one sentence.
55. **No example videos / preview images.** When the user
    selects a system from the dropdown, there's no preview thumbnail.
    They have to commit to a Run to find out what Chua looks like.

## What's actually working well

Do not regress these — they're the parts where the design earns its
keep:

- **Tokyo Night palette is a good choice.** Coherent with viridis,
  good contrast against the LaTeX rendering, scientific-tool vibe.
  Keep.
- **The `_FlowingLatex` widget's caching is excellent.**
  `main_window.py:362–548` — render-once, scale-on-resize. This is
  the right architecture. The earlier (pre-`e3d7118`) implementation
  re-rendered through matplotlib on every resize.
- **Status-chip state machine in QSS** (`dark.qss:472–490`) is
  cleanly factored — `state="running"` / `"error"` / `"exporting"`
  attribute-driven colors are a modern pattern.
- **Transport state separation** — animation timer, frame index,
  scrubber two-way binding (`main_window.py:1907–1996`) — is solid
  and worker-thread-safe.
- **Tooltips on every interactive control** — present, useful, with
  keyboard shortcut hints. Not advertised enough but they exist.
- **Spinbox + slider compound widget with log scale**
  (`main_window.py:648–769`) is genuinely thoughtful for parameters
  that span decades.

## Concrete fix list for the next agent

Ordered by impact. Each item names the file:line so the fixer can act.

### P0 — must fix before next demo

1. **Make the LaTeX `\tfrac` error go away.** `main_window.py:442–443` /
   `main_window.py:1297–1299`. Either: (a) preprocess `\tfrac` →
   `\frac` before handing to matplotlib (mathtext understands `\frac`,
   not `\tfrac`); or (b) swap the renderer to use a real LaTeX
   backend (`flatlatex`, `sympy.latex` via `usetex=True` with a
   `dvipng` install check). Today the DoublePendulum and any system
   using `\tfrac` / `\dfrac` / unsupported macros explodes in the
   user's face.

2. **Fix the viewport overlay double-write.**
   `main_window.py:636–642`. Add `self.clear()` before `setText`, or
   move the overlay text into a Qt rich-text label with an explicit
   clear-and-set pattern.

3. **Fix the OpenGL framebuffer-on-resize garbage.** The
   `QtInteractor.interactor` widget inside the `QFrame[role=
   "viewport-frame"]` (`main_window.py:1103–1110`) needs to force a
   `viewer.render()` (and probably a `viewer.update()`) on its
   `resizeEvent`. The shrink-to-narrow case in
   `critique_narrow_window.png` is unacceptable on a desktop app.

4. **Add a non-empty viewport empty state.** `main_window.py:1079–1110`.
   Render a wireframe vector-field preview (sparse 8×8×8 cones) for
   the current system on idle; clear and switch to trajectory on Run.
   Or, as a cheap alternative, draw a big light "Press Run to
   integrate (Ctrl-R)" text overlay centered in the viewport before
   any sim has run.

### P1 — visual hierarchy that's actually fixable in a day

5. **Pull `Run` out of the Time-range card.** Move it to a sticky
   bottom row of the left panel (use `QVBoxLayout.addStretch` then
   `addWidget(run_row)` outside the scroll area, or pin it to the
   bottom of the panel below the scroll). `main_window.py:929–1074`.
   Make it 100% wide, 36 px tall, primary blue, with the keyboard
   hint "Run · Ctrl-R" inside the label.

6. **Delete the duplicate transport actions from the toolbar.**
   `main_window.py:1531–1563`. Keep `Run` (since it doubles as
   primary CTA) and `Export MP4`. Move Pause/Stop/Jump-to-end to
   the transport strip only. Or vice-versa: delete the bottom
   strip's text buttons and use only the toolbar. Two surfaces is
   confusing.

7. **Replace Qt stock icons with SVG icons.** `main_window.py:1531–1587`.
   The toolbar already has SVG asset support (`dark.qss:175,247,253`
   reference `url(assets/icons/...)`). Drop in Lucide
   play/pause/stop/skip-forward/download/refresh-cw and color-match
   to `--text-primary`.

8. **Fix card heading hierarchy.** `dark.qss:49–58`: bump
   `font-size` to 13pt, weight 600, color `--text-primary` (not
   secondary), and *move the title outside the card* by removing
   the negative `top: -2px` and increasing the QGroupBox `margin-top`
   to 24 px so the title sits above the border. Match
   `docs/ui_design.md:60` which already documents `font-h2: 15pt`.

9. **Add a real focus ring.** `dark.qss:502–511`. Use a 2 px
   `outline-style: solid; outline-color: --accent;` (or a
   QSS-supported equivalent — Qt's QSS doesn't fully support
   `outline`, so use `border: 2px solid #7aa2f7;` with a matching
   `margin: -1px;` on focus). Test by tabbing through.

10. **Fix the collapsed-section empty void.** `main_window.py:1174–1176`.
    Either give the ODE section a fixed `setSizePolicy`
    Preferred/Preferred while the Lagrangian collapses to its
    header's natural height, or use a `QSplitter(Qt.Vertical)`
    inside the right panel with `setStretchFactor(0, 1), setStretchFactor(1, 0)`
    when the Lagrangian collapses.

### P2 — meaningful polish

11. **Swap the head sphere color to the palette.**
    `renderer.py:213` head_color `"#d62728"` → `theme.PALETTE.accent`
    or `lyapunov`. Plumb the renderer through theme.py instead of
    matplotlib defaults.

12. **Thicker trajectory line with tube rendering.**
    `renderer.py:191–202`: `line_width: 4.0`,
    `render_lines_as_tubes: True`. Verify performance with
    a 4000-frame Lorenz; it'll be fine.

13. **Replace ASCII `v` / `>` chevrons in collapsibles.**
    `main_window.py:610–611`. Reuse the SVG chevron-down from
    `assets/icons/chevron-down.svg`, rotated when collapsed.

14. **Move System combobox into the toolbar.**
    `main_window.py:949–961`. Adds discoverability and frees the
    left panel for parameters-first IA.

15. **Hide the lyapunov chip until a value exists.**
    `main_window.py:1701–1706`. Also rename "lambda1 = -" to
    "λ₁ = —" with a real lambda glyph.

16. **Show progress in the status bar, not in the side panel.**
    `main_window.py:1051–1056` progress bar lives in the Export
    card. Move to the bottom statusbar (Qt natively supports a
    permanent progress widget) so the side panel stops shuffling
    its layout during a run.

17. **Promote the state readout.** `main_window.py:1067–1070`
    `state_label`. It's the only numeric output and it sits hidden
    in caption-grey text below the Export card. Move it to a chip
    or overlay near the viewport so users see what they computed.

18. **Style the status bar's idle state.** When state=idle, hide the
    `frame 0 / 0` / `t = 0.000` / `lambda1 = -` chips entirely
    (`main_window.py:1701–1711`) — they're noise pre-run.

### P3 — nice-to-haves

19. **Camera preset buttons** (top / front / right / iso) overlaid
    on the viewport top-right.
20. **Vector field preview on idle** — sparse cones colored by
    `|f(x)|`, replaced by the trajectory on Run.
21. **Welcome card** dismissible on first launch with a 3-step
    "pick a system → set parameters → press Run" intro.
22. **Reset-to-defaults** button per parameter card
    (`default_params(system)` already exists in contract.py).
23. **Fog / depth cueing** in the renderer.

---

End of critique.
