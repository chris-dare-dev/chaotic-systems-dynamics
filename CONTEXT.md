# CONTEXT.md

Living document. Update this whenever the project's direction, current state, or near-term plan shifts. Future Claude sessions read this first.

## What this project is

`chaotic-systems-dynamics` is a Python application — backend library plus native desktop GUI — for simulating and visualizing chaotic dynamical systems with mathematical rigor.

The intended audience is people who actually want to *see* and *manipulate* the math: students working through nonlinear dynamics, hobbyists exploring strange attractors, and the author (Chris Dare) using it as a sandbox for the math he wants to internalize.

## Mathematical territory covered

The project lives at the intersection of:

- **Ordinary differential equations** — most systems of interest are autonomous ODE systems on $\mathbb{R}^n$.
- **Hamiltonian and Lagrangian mechanics** — for systems like the double pendulum, the equations of motion are derived from a Lagrangian; symplectic integrators preserve phase-space volume and energy on long timescales.
- **Chaos theory proper** — sensitive dependence on initial conditions, the butterfly effect, strange attractors with fractal structure (Lorenz, Rössler), bifurcations, periodic windows.
- **Lyapunov exponents** — quantifying chaos via the exponential rate of separation of nearby trajectories. The largest Lyapunov exponent is the canonical numerical witness of chaos.
- **Phase space and Poincaré sections** — geometric structure that makes chaos visible even when the equations look unassuming.
- **Numerical analysis** — choice of integrator matters. Stiff systems, energy drift in non-symplectic schemes, step-size control via embedded error estimates (RK45/Dormand-Prince).

The project should *render the math*, not hide it. Every system displays its governing equations (LaTeX) alongside the simulation.

## Current state (2026-05-15)

The math and visualization layers landed in parallel passes on the same day.

**Math / numerics** (`core/`, `integrators/`, `systems/`):
- `DynamicalSystem`, `Parameter`, `Trajectory` base types
  (`core/base.py`).
- `LagrangianSystem` — sympy Lagrangian -> Euler-Lagrange equations ->
  `lambdify`-d fast numerical RHS. Drives `DoublePendulum`.
- `HamiltonianSystem` — sympy Hamiltonian -> Hamilton's equations, with
  separable-system support (kinetic / potential split) for symplectic
  integrators. Drives `HenonHeiles`.
- Integrators (`integrators/`) all conforming to a single
  `Integrator` protocol with a shared `integrate(rhs, t_span, y0, dt=,
  n_points=, rtol=, atol=)` signature:
  - **Adaptive** (scipy wrappers): RK45, RK23, DOP853, Radau, BDF, LSODA.
  - **Fixed-step**: RK4, Euler (with `_NUMBA_AVAILABLE` shim — numba is
    used for hand-JIT'd inner loops when callers want it).
  - **Symplectic** (separable Hamiltonians): leapfrog, velocity_verlet,
    yoshida4. Hand-coded, with a `from_hamiltonian()` adapter that
    builds the `grad_T` / `grad_V` callables from a
    `HamiltonianSystem`. Energy is bounded over 1000+ periods of the
    SHO; yoshida4 holds `|E - E0| < 1e-6`.
- `largest_lyapunov_two_trajectory` (Benettin two-trajectory method) and
  `lyapunov_spectrum` (variational + continuous QR). Lorenz returns
  ~0.907 against the canonical 0.9056 in 5 seconds.
- `poincare_section` — event-driven section-collector built on
  `scipy.integrate.solve_ivp` event detection.
- Concrete systems: Lorenz, Rossler, DoublePendulum, Chua, HenonHeiles,
  Duffing — exposed through `chaotic_systems.systems.registry` with a
  stable display order.
- **Tests** (`tests/core`, `tests/integrators`, `tests/systems`): 38
  unit / numerical-accuracy tests covering the base classes, every
  adaptive / fixed-step / symplectic integrator, the simple-pendulum
  reduction of `LagrangianSystem`, energy conservation on the double
  pendulum and Hénon-Heiles, exponential divergence and largest
  Lyapunov on Lorenz, Poincaré section finiteness, and registry
  round-trip.
- **Examples** (`examples/`): `lyapunov_lorenz.py`,
  `double_pendulum_energy.py`, `poincare_henon.py`.
- **Docs**: `docs/numerics.md` (integrator zoo + trade-offs) and
  `docs/systems.md` (each system + reference).

**Visualization + GUI** (`visualization/`, `gui/`):
- `Renderer3D` (PyVista + VTK) with progressive-reveal animation,
  attachable to a `pyvistaqt.QtInteractor` for embedding in the GUI.
- `Renderer3D.render_to_video()` writes MP4s via `imageio-ffmpeg`,
  off-screen — no display required.
- LaTeX rendering via matplotlib mathtext, with automatic unrolling of
  `\begin{aligned}` blocks into stacked rows. `latex_to_qimage()` feeds
  the GUI panels.
- `chaotic_systems.gui.MainWindow` — PySide6 main window:
  system picker, parameter spinboxes auto-generated from each system's
  parameter schema, integrator picker, t_end / dt controls, Run +
  Export Video buttons, embedded 3D viewport, right-hand LaTeX panel
  showing ODE system (and Lagrangian, if any).
- Entry point: `python -m chaotic_systems.gui` (or
  `chaotic-systems-gui` after `pip install -e .`).
- Demos: `examples/lorenz_gui.py`, `examples/lorenz_video.py`.

**Dependencies pinned** in `pyproject.toml`: numpy, scipy, sympy, numba,
matplotlib, PySide6, pyvista, pyvistaqt, imageio, imageio-ffmpeg. Dev
extras: pytest, pytest-qt, pytest-benchmark, hypothesis, ruff, mypy.

**Tests**: 38 math/integrator tests under `tests/core`,
`tests/integrators`, `tests/systems`; 13+ visualization tests (contract
adapter, LaTeX rendering, end-to-end off-screen video export); 3 GUI
smoke tests (window builds, parameter widgets generate from registry,
LaTeX panel populates). GUI tests are gated behind
`CHAOTIC_GUI_TESTS_USE_DISPLAY=1` because `pyvistaqt.QtInteractor`
needs a real OpenGL context. The `tests/gui/conftest.py` hook now
filters strictly to items under `tests/gui/`, so a plain
`pytest tests/` from the repo root runs the 51 backend/visualization
tests and only skips the GUI smoke tests.

## What's next

The scaffolding and the visualization MVP are done. Items #1, #2,
and #4 from earlier revisions of this list have all shipped — and
the "persistent settings" item that was #1 in the prior revision
landed as FU-013 (see ``Recently shipped`` below). Remaining open
follow-ups:

1. **CI for the GUI smoke tests.** Today the GUI tests are skipped
   without a display. A `xvfb` job (Linux) or a macOS runner with a
   logged-in user could turn them back on.
2. **Pre-rendered intros (manim).** Out-of-scope today but a nice
   future direction for tutorial videos that explain each system before
   the live simulation runs.

## Recently shipped (2026-05-20, chaos-indicator-suite-gui rollout)

- **CIS-1 — Chaos Indicator Suite Diagnostics-card section.**
  S-sized GUI wire-up that completes the "Chaos Indicator Suite"
  cluster the 2026-q2-broadening capability-scout challenger
  earmarked for a single batched section
  (``docs/proposals/chaos-indicator-suite-gui-2026-05-20.md``;
  drafted by the ``/draft-proposal`` skill — its inaugural
  end-to-end run, which caught a real defect: the drafter
  initially used ID ``D2`` and the critic flagged it as a
  collision with the already-shipped bifurcation tool, leading
  to a clean REDESIGN to ``CIS-1`` before any code was written).
  Surfaces the four shipped scalar chaos indicators
  (``chaos_zero_one_test`` / ``chaos_weighted_birkhoff`` /
  ``chaos_permutation_entropy`` / ``chaos_hurst`` from
  CSC-011/012/013/014) in the GUI's Diagnostics card via a
  single ``button_chaos_indicators`` push button + a new
  ``_ChaosIndicatorsWorker`` ``QObject`` run on a ``QThread``,
  with four indicator chips and a sampling-rate guard banner.
  New worker class lives next to ``_LyapunovWorker`` in
  ``gui/main_window.py``; new module-level helper
  ``_format_chaos_indicators(payload) -> (text, oversampling)``
  formats the dict payload with ``NaN``-as-``"n/a"`` rendering
  for partial-failure cases (e.g. Hurst on a constant signal).
  The sampling-rate guard threshold is
  ``_CHAOS_SAMPLING_DT_THRESHOLD = 0.1``, calibrated against the
  ``chaos_zero_one_test`` docstring (Lorenz at ``dt = 0.04``
  gives ``K ~ 0.025``; ``dt >= 0.5`` lands ``K ~ 0.998``); when
  ``traj.dt < 0.1`` the new ``chaos_indicators_banner`` becomes
  visible with a downsample hint. Worker dispatches the four
  indicator functions on the first-component column of
  ``_last_trajectory.y``; per-indicator ``try/except`` so a
  single math failure (e.g. constant-signal ``ValueError`` from
  Hurst) surfaces as ``NaN`` for that scalar while the other
  three still populate. Per-indicator floors enforce a total
  failure when the trajectory is below 200 samples (the
  most-restrictive WBA/Hurst minimum). Click-to-compute pattern
  per the proposal's brief — explicitly NOT the ``CSC-033``
  ``post_sim_diagnostics`` hook, because running all four
  indicators on every Run would tax the 16 ms tick budget.
  System-change reset hides the banner + clears the result
  label following the same ``hasattr`` guard pattern as
  ``lyapunov_result_label`` (D1) and ``system_observables_label``
  (CSC-033). Reference observables
  (``tests/gui/test_chaos_indicators.py``, 9 tests gated on
  ``PySide6`` + ``pyvistaqt``): formatter renders chaotic
  Lorenz-like payload (``K = 0.998``, ``digit-loss = 2.4``,
  ``H_PE = 0.99``, ``H_Hurst = 0.56`` at ``dt = 1.0``) with
  warn=False; oversampled payload (``dt = 0.04``) sets warn=True
  and the banner text contains ``"oversampled"`` +
  ``"downsample"``; partial-failure payload renders
  ``H_Hurst = n/a`` (not ``"nan"``); compute without a
  trajectory surfaces a "Run a simulation first" hint without
  starting a worker; system-switch clears the result label and
  hides the banner. Worker integration test runs the real
  worker on an 800-sample IID-Gaussian synthetic trajectory and
  asserts all six keys (``K`` / ``digit_loss`` / ``H_PE`` /
  ``H_Hurst`` / ``dt`` / ``n_samples``) appear in the finished
  payload. Non-GUI suite unchanged at 354 passed / 10 skipped /
  0 failed (no core changes). ruff clean. Code-side landed in
  commit ``c66f94d`` (mixed with FU-020 due to a parallel-session
  ``git add`` race that swept up the in-flight CIS-1 main_window.py
  edits); docs + tests + proposal landed cleanly in ``aa9ecfe``.

## Recently shipped (2026-05-19, frontend-uplift 2026-05-19-initial rollout)

- **FU-010 — Force LaTeX reflow on ``showEvent`` + via deferred
  ``singleShot``.** S-sized typography / motion fix from the
  2026-05-19-initial frontend-uplift (RICE 0.30 — NONE severity
  on every axis;
  ``.claude/notes/frontend-uplifts/2026-05-19-initial/artifacts/final-report.md``).
  Pre-FU-010 the ``_FlowingLatex`` widget rendered rows
  immediately during ``set_latex`` and measured ``self.width()``
  *at that moment* to decide whether each row pixmap needed
  scaling down. When ``set_latex`` ran during window construction
  (before the parent layout had settled the widget's final
  width), the row pixmap was sized against a stale measurement
  and the first row clipped at the card edge on initial render
  — visible on DoublePendulum's kinetic-energy expression
  (visual scout F-07, ``screenshots/double-pendulum-latex.png``).
  Post-FU-010 the timing is patched in two places:
  ``set_latex`` now queues a deferred ``QTimer.singleShot(0,
  self._reflow_all)`` after the row inserts so Qt's layout pass
  has a chance to settle before each row pixmap is re-measured;
  and an overridden ``showEvent`` queues a second
  ``singleShot(0, self._reflow_all)`` as a belt-and-suspenders
  backstop so the *first* paint after the parent dock / scroll
  area assigns a real width still picks up the corrected
  layout. The new ``_reflow_all`` helper iterates ``self._rows``
  and calls ``_LatexRow._reflow`` on each — idempotent because
  ``_reflow`` short-circuits when the pixmap already fits at
  the current width. Empty-LaTeX inputs short-circuit before
  scheduling (no rows to reflow). The widget's underlying
  algorithm is untouched — FU-010 only changes *when* the
  reflow fires, not the result. Reference observables
  (tests/gui/test_latex_reflow_on_show.py — 5 new tests):
  ``_reflow_all`` exists and is callable; ``set_latex`` queues
  at least one deferred ``_reflow_all`` call (caught via a
  ``processEvents`` + spy pattern); empty ``set_latex`` does
  *not* schedule (regression-guards the early-return path);
  ``showEvent`` queues a deferred ``_reflow_all`` once the
  widget becomes visible; and the F-07 behavioural fix —
  rendering LaTeX at a squeezed 200 px width then resizing to
  900 px and reflowing now produces a row pixmap that fits at
  the new width (pre-FU-010 it stayed clipped at the stale
  200 px scale). Full backend + visualization + GUI suite at
  758 passed / 14 skipped (was 753), ruff clean. Commit
  ``f1bd5c7``.
- **FU-004 — ``_CollapsibleSection`` ``variant="section-toggle"``
  QSS rule.** S-sized theme / typography fix from the
  2026-05-19-initial frontend-uplift (RICE 0.30 — MINOR severity;
  ``.claude/notes/frontend-uplifts/2026-05-19-initial/artifacts/final-report.md``).
  Pre-FU-004 ``_CollapsibleSection.__init__`` carried an inline
  ``setStyleSheet`` with two leaks: a literal ``color: #c0caf5``
  bypassing PALETTE and a ``font-size: 12pt`` that contradicted
  the spec (``docs/ui_design.md §typography`` lists
  ``font-ctrl=13pt`` for buttons and ``font-h2=14pt`` for card
  titles + section headings; 12pt was neither). Post-FU-004 the
  rule lives in ``assets/dark.qss`` under
  ``QPushButton[variant="section-toggle"]`` so a future
  light-theme stylesheet can override it without touching Python,
  the colour routes through ``PALETTE.text_primary`` (``#c0caf5``)
  in QSS rather than as a Python literal, and the font size is
  pinned at the canonical ``font-ctrl=13pt`` per the synthesis's
  content-hierarchy call (section headers are buttons, not card
  titles). The remaining visual semantics
  (``text-align: left``, ``padding: 4px 6px``, ``font-weight: 600``,
  ``border: none``, ``background: transparent``) are preserved
  verbatim. A companion ``:hover`` / ``:pressed`` / ``:focus`` /
  ``:checked`` block re-pins ``background: transparent`` /
  ``border: none`` so the borderless affordance doesn't inherit
  the default ``QPushButton:hover`` ``#343a55`` pill (visual scout
  F-04). The toggle's ``setProperty("variant", "section-toggle")``
  remains the matching selector for the QSS rule.
  ``_CollapsibleSection`` is closure-local inside
  ``_build_window_class()``, so the contract tests reach it via
  ``window._ode_section`` (the ODE Mathematics-panel section,
  always present). Reference observables
  (tests/gui/test_collapsible_section_qss.py — 7 new tests): the
  toggle button's inline stylesheet is empty (the rule moved to
  QSS); the ``variant="section-toggle"`` property is preserved;
  ``dark.qss`` declares the ``QPushButton[variant="section-toggle"]``
  rule; the rule's colour matches ``PALETTE.text_primary``; the
  rule pins ``font-size: 13pt`` (no ``12pt`` literal anywhere in
  the rule body); the ``:hover`` / ``:pressed`` overrides exist
  (otherwise the default hover pill bleeds through); the
  collapse / expand behavioural contract survives the refactor
  (toggle state ↔ body visibility, chevron glyph switching). Full
  backend + visualization + GUI suite at 753 passed / 14 skipped,
  ruff clean. Commit ``b4399f9``.
- **FU-008 — "Analyse…" toolbar submenu.** S-sized information-
  architecture / affordance fix from the 2026-05-19-initial
  frontend-uplift (RICE 1.13 — MAJOR severity at synthesis time;
  ``.claude/notes/frontend-uplifts/2026-05-19-initial/artifacts/final-report.md``).
  Pre-FU-008 the five analytics actions (Bifurcation / Phase
  portrait / Recurrence plot / Basins / Poincaré section) lived
  as flat ``QAction``s on the main toolbar, consuming ~300 px of
  horizontal real estate at 1400 px (visual-brief F-08) and
  *truncating off entirely* at 900 px (``screenshots/narrow.png``).
  Post-FU-008 the five collapse into a single ``QToolButton``
  ("Analyse…", ``objectName = "button_analyse"``,
  ``mdi6.chart-multiple`` glyph) with an ``InstantPopup``
  ``QMenu`` (``objectName = "menu_analyse"``) that holds all
  five in spec order. ParaView's "Filters" menu / napari's
  "Plugins" menu vocabulary; gated on FU-001's ``QMenu`` QSS
  rules (shipped 2026-05-19) so the popup renders dark on
  Windows instead of system-native white. The button uses
  ``Qt.FocusPolicy.StrongFocus`` (challenger §6 MINOR a11y
  mitigation — Tab-reachable; arrow keys navigate the menu
  natively). CC-01 mitigation (critical regression risk): all
  five analytics ``QAction``s remain registered in
  ``self._transport_actions`` under their canonical keys
  (``action_bifurcation``, ``action_phase_portrait``,
  ``action_recurrence``, ``action_basins``, ``action_poincare``)
  and remain parented to the window, so
  ``window.transport_actions()[<key>]`` still resolves them and
  ``window.findChildren(QAction)`` (FU-014's command palette)
  still discovers them — preserving the 5 panel-test files
  (``test_phase_panel.py:163`` / ``test_basin_panel.py:144`` /
  ``test_recurrence_panel.py:140`` /
  ``test_poincare_panel.py:338`` /
  ``test_bifurcation_panel.py:143``) that look the actions up by
  name. New ``_MainWindow._build_analyse_button`` helper mirrors
  ``_build_settings_button``'s pattern. Toolbar layout reads
  ``[System ▾] | Run Auto Pause Stop Jump-end | Export | Reset
  view Analyse… Theme | Settings`` — Analyse… sits where the
  five actions used to crowd. Reference observables
  (tests/gui/test_analyse_submenu.py — 12 new tests):
  ``button_analyse`` exists on ``toolbar_main`` with text
  ``"Analyse…"``; popup mode is ``InstantPopup`` (single click
  opens menu); focus policy is ``StrongFocus`` (Tab reachable);
  the menu carries exactly the 5 analytics actions in spec
  order; all 5 keys remain in ``transport_actions()`` (5
  parametrised tests — CC-01 contract); the 5 analytics actions
  are *no longer* direct toolbar actions (otherwise the change
  would be no-op); the 8 non-analytics actions (Run / Pause /
  Stop / Jump-end / Export / Reset view / Theme / Auto) still
  surface at the top level; Analyse… button carries a
  non-null icon (AP-04 contract). Full backend + visualization
  + GUI suite at 746 passed / 14 skipped, ruff clean. Commit
  ``cb98773``.
- **FU-018 — Promote 5 dialog panels to QDockWidget.** M-sized
  interaction-pattern migration from the 2026-05-19-initial
  frontend-uplift (RICE 0.71 — MAJOR severity at synthesis time;
  ``.claude/notes/frontend-uplifts/2026-05-19-initial/artifacts/final-report.md``).
  Pre-FU-018 the analysis dialogs (Phase / Basin / Bifurcation /
  Recurrence / Poincaré) shipped as standalone ``QMainWindow``
  instances that floated independently and could not be docked to
  the main viewport — the user could only see one analysis at a
  time without manually overlapping windows. Post-FU-018 each
  ``build_*_dialog`` factory returns a ``QDockWidget`` (still
  preserving its canonical ``objectName`` — ``"phase_dialog"`` /
  ``"basin_dialog"`` / ``"bifurcation_dialog"`` /
  ``"recurrence_dialog"`` / ``"poincare_dialog"`` — and its
  panel attribute — ``.phase_panel`` / ``.basin_panel`` /
  ``.map_picker`` / ``.recurrence_panel`` / ``.poincare_panel``
  — so the FU-014 command palette, the ``docs/ui_design.md``
  layout-spec assertions, and 53 pre-existing panel tests keep
  working). The dock carries the synthesis-prescribed feature
  flags (``DockWidgetMovable | DockWidgetFloatable |
  DockWidgetClosable``) and allows all four dock areas (Left /
  Right / Top / Bottom). A new ``_MainWindow._open_as_floating_dock(dock)``
  helper attaches the dock to ``RightDockWidgetArea``, calls
  ``setFloating(True)``, and shows — preserving the default UX
  (the panel still opens as a separate floating window) while
  letting the user drag it back to dock beside the 3D viewport.
  All 5 ``_on_open_*_dialog`` handlers in ``main_window.py`` are
  rewritten from ``dialog.show()`` to
  ``self._open_as_floating_dock(dialog)``. CC-1 mitigation
  (Windows-native dock title bar): ``dark.qss`` ships explicit
  ``QDockWidget {…}``, ``QDockWidget::title``,
  ``QDockWidget::close-button``, and ``QDockWidget::float-button``
  rules, all PALETTE-routed (``bg_panel`` for the body,
  ``bg_window`` for the title bar, ``text_primary`` for the
  caption, ``border`` for the frame, ``accent_hover`` /
  ``accent_pressed`` for the corner buttons). napari's
  ``add_dock_widget`` pattern (PR #5483) is the SOTA reference.
  Reference observables (tests/gui/test_dock_widgets.py — 23 new
  tests): each ``build_*_dialog`` factory returns a
  ``QDockWidget`` (was ``QMainWindow``);
  ``objectName()`` survives the migration across all 5 panels;
  every panel attribute (``.phase_panel`` / ``.basin_panel`` /
  ``.map_picker`` / ``.recurrence_panel`` / ``.poincare_panel``)
  is present; the three feature flags (Movable / Floatable /
  Closable) are set; all four dock areas are allowed; ``dark.qss``
  carries the three required selectors with PALETTE tokens (no
  hex-literal leak); ``_MainWindow._open_as_floating_dock`` exists,
  is callable, attaches the dock as a child of the main window,
  and sets ``isFloating() == True``. Full backend + visualization
  + GUI suite at 734 passed / 14 skipped, ruff clean. Commit
  ``fc63fd2``.
- **FU-006 — superqt adoption (system picker only; partial ship).**
  S-sized library uplift from the 2026-05-19-initial
  frontend-uplift (RICE 0.68 — MAJOR severity at synthesis time;
  ``.claude/notes/frontend-uplifts/2026-05-19-initial/artifacts/final-report.md``).
  Adds ``superqt>=0.8`` (pyapp-kit, BSD-3-Clause, ~0.8 MB wheel,
  deps on ``qtpy`` only) to the runtime ``dependencies`` list in
  ``pyproject.toml``. Migrates the system picker
  (``self.system_box``, the toolbar's ``QComboBox`` over the 13+
  registered systems Lorenz / Rossler / RosslerHyper /
  DoublePendulum / Chua / Duffing / HenonHeiles / Kuramoto /
  MackeyGlass / logistic / henon_map / ikeda / standard_map)
  from a plain ``QComboBox`` to ``superqt.QSearchableComboBox``,
  which subclasses ``QComboBox`` and adds a type-to-filter
  completer on the dropdown — past the scroll-vs-search
  threshold the project has crossed since CSC-029 / N3 / N4
  landed. **Reduced scope vs the synthesis's full FU-006**: the
  challenger's MAJOR-severity concern about
  ``QLabeledDoubleSlider`` lacking log-scale support was
  verified directly against ``superqt 0.8.2``
  (``hasattr(QLabeledDoubleSlider(), 'setLogarithmic') == False``);
  per the challenger's mitigation #1, the ``_ParamWidget``
  migration is DEFERRED because Kuramoto's K parameter (range
  ``0.01-50``, 4 decades, currently log-scale via
  ``_ParamWidget._use_log``) would silently lose precision
  otherwise. The Notes-section ``QCollapsible`` migration is
  also deferred — the existing custom ``_CollapsibleSection``
  works correctly and replacing it would be churn without a
  clear user win. ``superqt`` is added to runtime deps now so
  any future migration (drag-to-scrub spinboxes per FU-015,
  Notes ``QCollapsible`` once a clear win surfaces, log-scale
  via a future superqt release) ships as a one-import change.
  ``QSearchableComboBox`` is a drop-in: full ``QComboBox`` API
  (``addItem``, ``findText``, ``setCurrentIndex``,
  ``currentIndexChanged``) so no caller changes are needed; the
  picker's tooltip is updated to mention "Type to filter."
  Reference observables (tests/gui/test_system_picker.py):
  ``test_system_box_is_a_searchable_combobox`` pins the
  migration contract; ``test_system_box_is_still_a_qcombobox``
  pins backwards-compat for external callers that introspect
  the picker as a ``QComboBox``;
  ``test_system_box_keeps_canonical_object_name`` pins
  ``"system_picker"`` for FU-014's command palette + the
  ``docs/ui_design.md`` table; the canonical 5 system names
  (Lorenz / Rossler / DoublePendulum / HenonHeiles / Kuramoto)
  still appear in the picker; ``currentIndexChanged`` still
  drives ``_on_system_changed``;
  ``test_searchable_combobox_carries_a_completer`` pins the
  user-visible value of the migration (a non-null completer);
  ``test_preselect_argument_still_works`` pins the
  ``preselect="Rossler"`` kwarg's continued effect. 7 new
  tests; full backend + visualization + GUI suite at 711
  passed / 14 skipped, ruff clean. Commit ``f3ec4a8``.
- **FU-003 — Theme-aware Notes-panel document stylesheet.** S-sized
  wire-up from the 2026-05-19-initial frontend-uplift (RICE 0.60 —
  MINOR severity on the test-grep axis;
  ``.claude/notes/frontend-uplifts/2026-05-19-initial/artifacts/final-report.md``).
  Closes the visual scout's F-05 finding: pre-FU-003 the Notes
  ``QTextBrowser``'s document stylesheet was applied once at
  widget construction with the dark-theme ``PALETTE`` values
  (FU-002 had already PALETTE-routed the literals); toggling to
  light theme via the toolbar action left every paragraph
  rendering as dark-grey-on-light, every heading as
  lavender-on-white, and code blocks as black-on-near-black —
  the highest-risk light-theme regression in the project. New
  static method ``_MainWindow._notes_document_stylesheet(mode)``
  branches on ``"dark"`` / ``"light"`` / unknown-fallback-to-dark
  and returns the appropriate CSS. The dark branch continues
  FU-002's token discipline — every ``color`` / ``background``
  routes through ``PALETTE.text_primary`` / ``text_secondary`` /
  ``success`` / ``bg_deep`` / ``warning`` / ``lyapunov`` /
  ``accent``. The light branch ships Tokyo-Night-Light-inspired
  defaults standalone (since ``light.qss`` is still a stub):
  near-black ``#1a1b26`` for headings, dim ``#3b4261`` for
  paragraphs / lists, forest-green ``#33635c`` for code on a
  cream ``#e8e4d8`` background — the chromatic accents
  (``warning``, ``lyapunov``, ``accent``) stay PALETTE-sourced
  in both branches because they read well on both surfaces and
  define the cross-theme visual vocabulary. ``main_window.py``
  swaps the construction-time inline f-string for
  ``self.notes_widget.document().setDefaultStyleSheet(self._notes_document_stylesheet(current_theme()))``.
  ``_on_toggle_theme`` grows a re-apply hook between the
  ``apply_theme(app, new_mode)`` call and the
  ``_rebuild_for_current_system()`` call — the ordering matters
  because the rebuild triggers ``setMarkdown``, which re-renders
  against whatever default stylesheet is in effect at that
  moment. Reference observables
  (tests/gui/test_notes_theme.py):
  ``test_notes_stylesheet_helper_branches_on_mode`` pins that
  ``("dark")`` and ``("light")`` produce different strings;
  ``test_dark_branch_uses_palette_tokens`` iterates the 7
  load-bearing tokens and asserts each appears verbatim;
  ``test_light_branch_uses_dark_text_on_light_background`` pins
  the cream/near-black light contract + asserts no
  ``text_primary`` / ``text_secondary`` dark hex appears in the
  light branch (catches dark/light cross-contamination);
  ``test_light_branch_chromatic_accents_match_palette`` pins the
  cross-theme chromatic tokens; ``test_notes_widget_uses_helper_at_construction``
  asserts the live widget's ``defaultStyleSheet`` matches the
  helper output (no stale duplicate code path);
  ``test_on_toggle_theme_reapplies_notes_stylesheet`` — the
  headline behavioural pin: toggle from dark to light, assert
  the document stylesheet equals the light-branch output;
  ``test_toggle_back_to_dark_restores_dark_stylesheet`` exercises
  the round trip; ``test_unknown_mode_falls_back_to_dark`` pins
  the defensive fallback (matches ``theme.apply_theme``'s
  unknown-mode convention). 8 new tests; full backend +
  visualization + GUI suite at 704 passed / 14 skipped, ruff
  clean. Commit ``2faccf1``.
- **FU-020 — Scrubber timestamp tooltip while dragging.** XS-sized
  affordance polish from the 2026-05-19-initial frontend-uplift
  (RICE 0.60 — MINOR severity on the AP-03 import-discipline axis;
  ``.claude/notes/frontend-uplifts/2026-05-19-initial/artifacts/final-report.md``).
  Borrows the Ableton 12 arrangement-view + ParaView animation-
  timeline pattern (inspiration brief P12): while the user drags
  the transport scrubber, a floating ``QToolTip`` anchored to the
  cursor shows ``t = 12.345 / 40.000 s    frame 1234 / 4001``
  — the same readout the status bar carries, kept close to the
  interaction point so the user doesn't have to dart their eyes
  to the bottom of the window mid-drag. New ``_ScrubSlider``
  subclass of ``QSlider`` lives at factory scope (near
  ``_ViewportOverlay``), takes a ``format_fn(value: int) -> str``
  callback injected by the host, and overrides ``mousePressEvent``
  / ``mouseMoveEvent`` to call ``QToolTip.showText`` while
  ``isSliderDown()``. Empty/``None`` return suppresses the
  tooltip — useful pre-Run when no trajectory exists. Per AP-03
  every PySide6 import stays at module level
  (``QToolTip`` joins the existing PySide6.QtWidgets import block
  alongside ``QSlider``); a dedicated test parses the class
  source and asserts no ``from PySide6`` lines appear inside the
  event-handler bodies. ``main_window.py`` swaps the prior
  plain ``QSlider`` at ``frame_scrubber`` construction for
  ``_ScrubSlider`` and wires ``set_format_fn(self._scrubber_tooltip_text)``.
  The host-side formatter reads ``_last_trajectory.t`` (saturated
  to the renderer's frame count), returns the empty string when no
  trajectory exists, and clamps out-of-range indices to the final
  frame. ``_MainWindow`` side-attaches ``_ScrubSlider`` so tests
  can introspect the class without re-entering the factory.
  Reference observables (tests/gui/test_scrubber_tooltip.py):
  ``_ScrubSlider`` is a real ``QSlider`` subclass (pinned via
  ``issubclass`` walk); ``frame_scrubber`` on the live window
  ``isinstance(_, _ScrubSlider)`` (migration contract);
  ``_format_fn`` defaults to ``None`` and ``set_format_fn`` stores
  the callback; ``_scrubber_tooltip_text`` returns ``""`` pre-Run
  (suppresses tooltip) and renders the canonical ``"t = X.XXX /
  X.XXX s    frame I / N"`` for a synthetic trajectory + frame
  index of 2 (also pins the saturate-past-end behaviour at index
  999 → ``frame 11 / 11``); the slider's ``_show_tooltip``
  is a safe no-op without a format fn (defensive); the AP-03
  inline-import scan confirms ``mousePressEvent`` /
  ``mouseMoveEvent`` / ``_show_tooltip`` carry no
  ``from PySide6`` lines. 9 new tests; full backend +
  visualization + GUI suite at 684 passed / 14 skipped, ruff
  clean. Commit ``c66f94d``.
- **FU-011 — Viewport hint label showEvent anchoring.** XS-sized
  layout hardening from the 2026-05-19-initial frontend-uplift
  (RICE 0.60 — NONE on every challenger axis;
  ``.claude/notes/frontend-uplifts/2026-05-19-initial/artifacts/final-report.md``).
  Closes visual-scout finding F-10: the viewport "Press Ctrl-R to
  simulate" hint was positioned once at construction via
  ``QTimer.singleShot(0, self._reposition_overlay)``. Under the
  offscreen Qt platform plugin (CI / screenshot runs) the first
  paint sometimes happened *before* the layout pass finished, so
  the hint sat at its initial ``(0, 0)`` position until the next
  resize event re-anchored it — exactly the regression visible
  in the visual scout's ``screenshots/initial.png``.
  ``_MainWindow`` gains a ``showEvent`` override that calls
  ``super().showEvent(event)`` (preserving Qt's first-paint
  machinery) then ``self._reposition_overlay()`` (anchors the
  hint to the viewport's bottom-center). ``showEvent`` fires
  AFTER Qt has computed the window's final geometry, so this is
  the reliable anchor point — the prior single-shot timer is
  kept as a belt-and-suspenders backstop for builds that never
  call ``show()`` (headless tests). Reference observables
  (tests/gui/test_viewport_hint.py):
  ``test_main_window_overrides_show_event`` walks the
  ``_MainWindow`` MRO and pins the override-locally contract
  (a future refactor that removes it surfaces immediately);
  ``test_show_event_calls_super_and_repositions`` spies on
  ``_reposition_overlay`` and verifies the override drives it
  on every ``showEvent`` invocation;
  ``test_show_positions_hint_near_bottom_of_viewport``
  resizes the window to 1200x800, calls ``show()``, processes
  events, and asserts the hint widget's ``y()`` is in the
  viewport frame's bottom half (the F-10 regression placed it
  in the top half pre-FU-011, so this is the headline
  behavioural pin); ``test_reposition_overlay_method_exists``
  sanity-checks the slot name. 4 new tests; full backend +
  visualization + GUI suite at 675 passed / 14 skipped, ruff
  clean. Commit ``7f61d9e``.
- **FU-025 — Sync ``docs/ui_design.md`` to current code.** XS-sized
  doc fix from the 2026-05-19-initial frontend-uplift (RICE 0.72 —
  NONE on every challenger axis;
  ``.claude/notes/frontend-uplifts/2026-05-19-initial/artifacts/final-report.md``).
  Closes the five spec-vs-impl drifts the current-state-critic
  catalogued (SD-01 / SD-02 / SD-03 / SD-04 / SD-05) plus a sweep
  of additions made since the doc's 2026-05-15 date stamp. The
  fixes: (SD-01) the toolbar QAction table now lists 13 actions —
  the original 7 transport entries plus 5 analytics
  (``action_bifurcation`` / ``action_phase_portrait`` /
  ``action_recurrence`` / ``action_basins`` / ``action_poincare``)
  plus the FU-017 ``action_live_preview`` ("Auto" pill) inserted
  between Run and Pause — and the icon column is rewritten from
  the obsolete ``QStyle.StandardPixmap`` vocabulary to the MDI6
  glyph IDs the FU-005 qtawesome migration resolves through; the
  obsolete ``theme.svg`` row is now ``mdi6.theme-light-dark`` and
  the Settings gear is documented as ``mdi6.cog`` in prose.
  (SD-02) the ASCII layout map drops the dead "Export" card from
  the lower-left column (Export has lived on the toolbar only
  since 2026-05-15) and gains the Diagnostics card + transport
  strip + FU-029 parameter-strip line under the equations card.
  (SD-03) ``font-h2`` corrects to ``14pt`` — the shipped QSS is
  authoritative, the prior ``15pt`` spec number was the stale
  end. (SD-04) icon column rewritten as above. (SD-05) primary-
  variant rule clarified: "Run is the only **app-scoped**
  primary; panel-internal Compute buttons may also use
  ``variant='primary'`` because they are that panel's primary
  action; the scope is the panel, not the app." Beyond the
  critic-flagged drifts, the doc also gains: an FU-002 "Derived
  interaction shades" subsection enumerating ``bg_deep`` /
  ``bg_pill_track`` / ``accent_hover`` / ``accent_pressed`` /
  ``accent_glow`` with their canonical hex values + use sites; a
  splitter stretch-ratio note (1 : 3 : 1 per FU-007); FU-019 +
  FU-029 monospace-chip mentions in the Typography section; an
  FU-016 state-layer contract paragraph in the Affordance rules
  (eight widget families pinned to ``:hover`` + ``:focus`` +
  ``:pressed`` per WCAG 2.1 AA); a new "Global keyboard
  shortcuts" table at the end of the doc capturing Ctrl-R /
  Ctrl-E / Space / Ctrl-. / End / Esc / R plus the new FU-013
  Ctrl+, (Preferences) and FU-014 Ctrl+Shift+P (command palette)
  bindings. Status line bumps from 2026-05-15 to 2026-05-20.
  Doc-only — zero source changes. Full backend + visualization
  + GUI suite at 671 passed / 14 skipped (no test count delta;
  the existing ``test_theme.py`` source-grep tests still pin
  the live tokens against the doc's narrative). Ruff clean.
  Commit ``ebcb79c``.
- **FU-024 — Clear dialog window references on close.** XS-sized
  hygiene fix from the 2026-05-19-initial frontend-uplift (RICE 0.72
  — NONE on every challenger axis;
  ``.claude/notes/frontend-uplifts/2026-05-19-initial/artifacts/final-report.md``).
  Closes the critic's DV-03 finding: all five analysis dialogs
  (Bifurcation / Recurrence / Basin / Poincaré / Phase) are
  constructed with ``Qt.WA_DeleteOnClose``, so closing the dialog
  frees the underlying C++ object — but the main window's
  ``self._<name>_window`` Python attribute kept pointing at the
  dangling shiboken wrapper, raising ``RuntimeError: wrapped C++
  object has been deleted`` on any access between close and reopen.
  The synthesis flagged only ``_poincare_window`` and
  ``_phase_window`` but auditing showed all 5 dialogs have the same
  bug since CSC-029 (Poincaré) landed; this commit fixes the whole
  family for consistency. ``_MainWindow.__init__`` now declares all
  5 ``_*_window`` attributes as ``None`` up front so introspection
  before the user opens the dialog (e.g. Preferences-dialog readers,
  the FU-014 command palette, tests) gets a clean ``None`` rather
  than ``AttributeError``. New helper ``_wire_window_cleanup(dialog,
  attr_name)`` connects ``QObject.destroyed`` so closing the dialog
  resets ``self.<attr_name>`` back to ``None`` at the right moment
  (the lambda captures ``attr_name`` as a default argument to dodge
  Python's late-binding closure trap that would otherwise make
  multiple wires in the same scope collide on the last-bound name).
  All 5 ``_on_open_*`` slots gain a single ``self._wire_window_cleanup
  (dialog, "_<name>_window")`` line between the reference stamp and
  the ``dialog.show()`` call. No public API changed. Reference
  observables (tests/gui/test_dialog_cleanup.py):
  ``test_all_five_dialog_window_attrs_default_to_none`` — every
  attribute pre-exists as ``None`` after construction (no more
  pre-open ``AttributeError``); ``test_wire_window_cleanup_resets_attr_on_destroyed``
  — emitting ``destroyed`` on a wired dialog nulls the named
  attribute; ``test_wire_window_cleanup_handles_multiple_dialogs_independently``
  — wires two fake dialogs to different attrs and destroys them
  independently, pinning the default-argument late-binding fix
  (a naïve closure capture would make Dialog A's destroy null
  Dialog B's attr — this test would catch that regression);
  ``test_wire_window_cleanup_accepts_every_documented_attr``
  iterates all 5 canonical attribute names and exercises each
  destroy path end-to-end. 5 new tests; full backend +
  visualization + GUI suite at 671 passed / 14 skipped, ruff
  clean. Commit ``fcc60ff``.
- **FU-029 — Inline parameter labels under equation rows.**
  S-sized educational uplift from the 2026-05-19-initial
  frontend-uplift (RICE 0.90 — MINOR severity on token discipline;
  ``.claude/notes/frontend-uplifts/2026-05-19-initial/artifacts/final-report.md``).
  Closes the inspiration brief's A5 anti-pattern ("equation panel
  as pure read-only display") at S cost — the cheap 80%-of-FU-028
  variant the synthesis explicitly named as worth keeping when
  full LaTeX hit-testing was parked. New ``self._param_strip``
  ``QLabel`` lives BELOW the rendered LaTeX rows but INSIDE the
  "Equations of motion" ``_CollapsibleSection`` so the strip
  folds with the equations. Renders a single monospace line such
  as ``sigma = 10.000    rho = 28.000    beta = 2.667`` —
  parameter tokens joined by four spaces (pinned by test).
  Format reuses the FU-019 ``_format_param_readout`` helper so
  the three-decimals / scientific-notation contract is identical
  to the parameter-row chips; the strip is the system-level
  rollup of the per-row chips. ``main_window.py`` grows
  ``_refresh_param_strip()``: reads ``self._param_widgets`` in
  registration order, builds tokens, joins with the 4-space
  separator, hides the strip when no parameters exist (defensive
  for future parameterless systems). Hooked from
  ``_on_param_changed_for_preview`` (every spinbox change refreshes
  regardless of live-preview being armed — the strip is a passive
  display, not a compute trigger) and from the end of
  ``_rebuild_for_current_system`` (system flips rebuild the
  strip's contents). Mathematics-card construction grows a thin
  ``ode_wrapper`` ``QWidget`` that holds ``self.ode_scroll`` +
  ``self._param_strip`` in a 4 px-spaced ``QVBoxLayout``; the
  wrapper is passed to ``_CollapsibleSection("Equations of
  motion", …)`` so collapsing the section hides the strip too.
  ``assets/dark.qss`` adds a ``QLabel[role="param-strip"]`` rule
  using ``PALETTE.text_secondary`` (the strip reads as
  supplementary information, not as a competing focus with the
  rendered LaTeX above) + the same monospace font cascade as the
  FU-019 chip. Reference observables
  (tests/gui/test_param_strip.py): strip widget exists with
  ``role="param-strip"``; Lorenz at startup renders all three
  canonical parameter tokens with their default values
  (``sigma = 10.000``, ``rho = 28.000``, ``beta = 2.667``);
  the 4-space-separator contract is pinned;
  ``setValue`` on a parameter spinbox refreshes the strip live
  with live-preview off (proves the strip refreshes regardless
  of the E2 compute path); switching to Rossler rebuilds the
  strip with ``a = ... b = ... c = ...`` (different parameter
  names); the QSS rule routes through ``PALETTE.text_secondary``
  + a monospace font; ``_refresh_param_strip`` is idempotent.
  7 new tests; full backend + visualization + GUI suite at 666
  passed / 14 skipped, ruff clean. Commit ``10e2821``.
- **FU-017 — Promote live-preview to a toolbar "Auto" pill.**
  S-sized discoverability uplift from the 2026-05-19-initial
  frontend-uplift (RICE 1.08 — NONE on every challenger axis;
  ``.claude/notes/frontend-uplifts/2026-05-19-initial/artifacts/final-report.md``).
  Wire-up candidate: the E2 backend (commit ``1b131e2``) ships
  the debounce + preview pipeline; FU-017 is purely a UI
  relocation. Closes the inspiration brief's P02 pattern
  ("ParaView's 'Auto Apply' vocabulary"). Pre-FU-017 the
  toggle lived inside the Settings dropdown as a long action
  ``"Live preview (slider drag re-simulates)"`` — two clicks
  deep and easy to miss; post-FU-017 it surfaces as a
  checkable "Auto" pill adjacent to Run on the main toolbar
  with a lightning-bolt icon (``mdi6.flash`` via the FU-005
  qtawesome stack). The same ``action_live_preview`` QAction
  is added to both surfaces — Qt's multi-host model lets the
  Settings-menu entry stay (for users who learned to look
  there) and stay state-synced with the toolbar pill
  automatically. ``icons.STEM_TO_GLYPH`` grows a
  ``"live-preview" -> "mdi6.flash"`` entry — synthesis-
  prescribed glyph. ``main_window.py``: ``_build_toolbar``
  now creates the QAction inline (before the spec loop)
  and inserts it onto the toolbar inside the Run-action
  branch of the spec loop, so the pill always lands at
  exactly position-after-Run regardless of how the spec list
  reorders. ``_build_settings_button`` drops its prior local
  creation block and just calls ``menu.addAction(
  self.action_live_preview)`` — the QAction's now defined
  earlier in the build flow. The tooltip is shortened and
  re-grounded against ParaView's vocabulary so the pill reads
  the same way as comparable scientific tools. Reference
  observables (tests/gui/test_live_preview.py — 4 new tests
  appended to the existing 11):
  ``test_live_preview_is_on_the_main_toolbar`` asserts the
  QAction appears in ``toolbar_main.actions()``;
  ``test_live_preview_pill_text_is_auto`` pins the
  synthesis-prescribed "Auto" label;
  ``test_live_preview_pill_has_lightning_icon`` verifies the
  ``mdi6.flash`` mapping + non-null rasterisable icon;
  ``test_live_preview_pill_sits_adjacent_to_run`` pins the
  exact-position contract (``action_live_preview`` index is
  ``transport_run`` index + 1). All 11 pre-existing E2 tests
  continue to pass — the state-machine wiring is unchanged.
  4 new tests; full backend + visualization + GUI suite at
  659 passed / 14 skipped, ruff clean. Commit
  ``559e372``.
- **FU-019 — Inline parameter value readout chip.** XS-sized
  pedagogical polish from the 2026-05-19-initial frontend-uplift
  (RICE 1.80 — MINOR severity on token-discipline axis only;
  ``.claude/notes/frontend-uplifts/2026-05-19-initial/artifacts/final-report.md``).
  Borrows the Houdini channel list / napari layer-properties
  pattern (inspiration brief P08): every parameter row now ends
  with a monospace ``QLabel`` showing ``name = value`` formatted
  to three decimals in the readable band (0.001 ≤ |v| < 1000)
  and to scientific notation outside it. Particularly valuable
  for systems like Kuramoto where the coupling K spans several
  decades — the spinbox itself rounds at the parameter's
  derived ``decimals`` granularity, but the readout chip
  collapses to ``K = 1.000e-3`` style without losing readability.
  ``main_window.py`` grows the ``_format_param_readout(name,
  value) -> str`` helper at the same lexical scope as
  ``_ParamWidget`` (so it survives the lazy class-build cycle)
  with a guarded magnitude check —
  ``av != 0.0 and (av >= 1000 or av < 0.001)`` —  so zero renders
  as ``"0.000"`` rather than the noisy ``"0.000e+00"``. Each
  ``_ParamWidget`` gains a ``self._readout`` field at the right
  edge of the row layout (``[spin][slider][readout]``), wired to
  ``self._spin.valueChanged`` so the chip updates live as the
  user drags the slider or types in the spinbox. The chip carries
  ``objectName=f"param_readout_{p.name}"`` so external agents can
  introspect it via ``findChild``. ``_format_param_readout`` is
  side-attached to ``_MainWindow`` as a staticmethod so tests
  exercise it without rebuilding the window factory.
  ``assets/dark.qss`` grows a ``QLabel[role="readout-chip"]``
  rule mirroring the status-bar chip vocabulary (``bg-elevated``
  background, ``border`` outline, 8 px corner radius, 96 px min-
  width) plus an explicit monospace ``font-family`` cascade so
  digits stay column-stable as values change. Pairs naturally
  with FU-007 (left-panel stretch) — the readout adds ~96 px to
  the row, which the now-wider left column accommodates without
  clipping. Reference observables (tests/gui/test_param_readout.py):
  five formatter-unit tests cover the three-decimal band,
  scientific-high (|v| >= 1000), scientific-low (0 < |v| <
  0.001), the zero edge case, and negative variants; three
  integration tests build a real ``_ParamWidget`` and verify the
  ``_readout`` label exists with the canonical role, that its
  text matches the default value, that ``setValue`` on the
  spinbox updates the chip live, and that the readout sits
  last in the row layout (per the synthesis "right of the
  spinbox" positioning); one wide-range integration test pins
  the scientific-low branch end-to-end with an eps-style
  parameter; one QSS-discipline test parses the
  ``QLabel[role="readout-chip"]`` block out of ``dark.qss`` and
  asserts ``PALETTE.text_primary`` / ``bg_elevated`` / ``border``
  + ``monospace`` font-family all appear — closes the synthesis
  token-discipline MINOR risk. 10 new tests; full backend +
  visualization + GUI suite at 655 passed / 14 skipped, ruff
  clean. Commit ``7245bcf``.
- **FU-007 — Left-panel splitter stretch factor.** XS-sized layout
  fix from the 2026-05-19-initial frontend-uplift (RICE 1.44 —
  NONE on every challenger axis;
  ``.claude/notes/frontend-uplifts/2026-05-19-initial/artifacts/final-report.md``).
  Closes the wide-window regression the visual scout caught at
  ``screenshots/wide.png``: at 1800x1100 the left panel was
  measured at ~125 px because the central ``QSplitter`` carried
  ``setStretchFactor(0, 0)`` — every extra pixel went to the
  viewport (stretch 3) + right Mathematics panel (stretch 1) in
  3 : 1, leaving the parameter card with its initial 320 px
  capped (and visibly clipped in practice). Single-integer change
  at ``src/chaotic_systems/gui/main_window.py:1893``:
  ``setStretchFactor(0, 0)`` → ``setStretchFactor(0, 1)``. The
  new ratio is 1 : 3 : 1 (left : viewport : right) — extra width
  at wide windows distributes 20% / 60% / 20% rather than the
  pre-FU-007 0% / 75% / 25%. Viewport still grows fastest
  because attractor visuals benefit most from extra pixels, but
  the parameter card now keeps full rows readable as the window
  grows past 1500 px. Pre-existing safeguards preserved:
  ``setChildrenCollapsible(False)`` (handle can't be dragged to
  zero width), ``left.setMinimumWidth(300)`` (300 px floor), and
  ``setSizes([320, 800, 340])`` (initial layout still gives
  viewport the dominant share at startup). Reference observables
  (tests/gui/test_layout.py — new module):
  ``test_splitter_stretch_ratio_is_left_one_viewport_three_right_one``
  parses the splitter-construction block out of
  ``main_window.py`` and pins the three ``setStretchFactor``
  literals (Qt's ``QSplitter`` doesn't expose a public stretch-
  factor getter, so we anchor the contract via source-grep —
  brittle to whitespace but bulletproof against a future change
  that re-zeroes the left column);
  ``test_left_panel_keeps_minimum_width_when_window_shrinks``
  pins the orthogonal contracts that ``childrenCollapsible``
  stays False and the left widget's
  ``minimumWidth() >= 300``. 2 new tests; full backend +
  visualization + GUI suite at 645 passed / 14 skipped, ruff
  clean. Commit ``1d9aad0``.
- **FU-005 — Adopt qtawesome; retire the hand-rolled SVG icon set.**
  S-sized iconography uplift from the 2026-05-19-initial
  frontend-uplift (RICE 1.80 — MAJOR severity mitigated by FU-002
  landing first;
  ``.claude/notes/frontend-uplifts/2026-05-19-initial/artifacts/final-report.md``).
  Closes the visual scout's F-02 finding ("Five analysis toolbar
  actions have no SVG icons") and the current-state-critic's
  AP-04 anti-pattern ("icon stems reference non-existent SVG
  files; silent-skip degrades to text-only buttons"). Adds
  ``qtawesome>=1.4`` (MIT, ~12 MB; pure Python — bundles MDI6 +
  FontAwesome 6 + Codicons font packs, no compiled extensions)
  to ``pyproject.toml`` runtime deps. New module
  ``chaotic_systems.gui.icons`` ships ``STEM_TO_GLYPH`` — a
  stable 13-entry mapping from the project's legacy icon-stem
  vocabulary (``run`` / ``pause`` / ``stop`` / ``jump-end`` /
  ``export`` / ``reset-view`` / ``theme`` / ``gear`` /
  ``bifurcation`` / ``phase-portrait`` / ``recurrence`` /
  ``basins`` / ``poincare``) to MDI6 glyph IDs (``mdi6.play``,
  ``mdi6.chart-scatter-plot``, etc.), plus ``icon_for_stem(stem,
  color=None)`` that returns a ``QIcon`` tinted from
  ``PALETTE.text_primary`` at call time. The mapping pins the
  contract that a missing glyph raises ``KeyError`` at
  construction time rather than silently degrading — so the
  five orphan stems can never go un-iconned again. Two call sites
  in ``main_window.py`` migrated: the toolbar-action loop
  (replaces ``QIcon(QFile(stem.svg))`` with
  ``icon_for_stem(stem)``) and ``_build_settings_button`` (gear
  glyph). The unused ``QIcon`` import is removed.
  ``assets/dark.qss`` drops three ``image: url(assets/icons/
  chevron-*.svg)`` references — ``QComboBox::down-arrow`` and
  ``QDoubleSpinBox::up/down-arrow`` now render via Qt's native
  chevron glyphs (same approach FU-001 used for ``QMenu::
  indicator``), so no missing-SVG silent-degradation surface
  remains in the shipped QSS. The 10-line URL-rewriting block
  in ``theme.apply_theme`` (lines 154-163 pre-FU-005) is deleted
  — no asset directory is touched anywhere on the QSS hot path.
  Ten SVG files under ``assets/icons/`` deleted (``run`` /
  ``pause`` / ``stop`` / ``jump-end`` / ``export`` / ``reset-view``
  / ``theme`` / ``gear`` / ``chevron-up`` / ``chevron-down``).
  Challenger-flagged CC-2 mitigation honored: a smoke test fires
  ``_on_toggle_theme`` and verifies every toolbar action's icon
  still rasterises to a non-null 16x16 pixmap (catches qtawesome
  cache-invalidation regressions). CC-06 (chevron migration risk)
  found to be moot for this codebase — the project's
  ``_CollapsibleSection`` chevrons are Unicode glyphs
  (``▾`` / ``▸``), not SVGs, so no QSS-to-setIcon migration was
  needed there. Reference observables (tests/gui/test_icons.py):
  ``STEM_TO_GLYPH`` covers every stem ``_toolbar_action_specs``
  declares (pinned dynamically against the live spec list);
  every glyph value starts with ``mdi6.`` (single-font-pack
  invariant); ``icon_for_stem("run")`` returns a non-null
  ``QIcon`` with a rasterisable 16x16 pixmap; unknown stems
  raise ``KeyError`` (no silent degradation);
  ``test_every_toolbar_action_has_a_non_null_icon`` checks every
  action surfaced via ``window.transport_actions()`` — pre-FU-005
  this test would fail with 5 missing icons (the headline
  behavioural fix); the theme-toggle smoke test verifies icons
  survive a re-theme; the ``assets/icons/`` directory has no
  ``.svg`` left; ``theme.apply_theme`` source no longer
  contains the icon-URL-rewriting hack. 8 new tests; full
  backend + visualization + GUI suite at 643 passed / 14
  skipped, ruff clean. Commit ``883519c``.
- **FU-016 — State-layer hover / focus / pressed QSS overlays.**
  S-sized accessibility uplift from the 2026-05-19-initial
  frontend-uplift (RICE 3.00 — MINOR on every challenger axis;
  ``.claude/notes/frontend-uplifts/2026-05-19-initial/artifacts/final-report.md``).
  Material Design 3, Microsoft Fluent 2, and Apple HIG 2025 all
  formalised the same state-layer contract in 2024-2025 —
  visible focus indicators are now a WCAG 2.1 AA baseline,
  not a premium polish item. The project's ``border_strong``
  token had been defined as the focus colour but was not
  applied consistently. ``assets/dark.qss`` grows two new
  state-layer blocks:
  - **QCheckBox** — full state machine (``::indicator`` default
    / ``:hover`` / ``:checked`` / ``:checked:hover`` / ``:disabled``
    + ``:focus`` outline). Consumer: the FU-013 Preferences
    dialog's "Remember last-used parameters" /
    "Save window layout on close" checkboxes — pre-FU-016 they
    rendered with the system-light indicator on Windows.
  - **QListView / QListWidget** (standalone, complements the
    existing ``QComboBox QAbstractItemView`` rule) — ``::item``
    default / ``:hover`` / ``:selected`` / ``:selected:hover`` /
    ``:disabled`` + a 2 px ``:focus`` outline on the list
    itself. Consumer: the FU-014 command palette's search-
    result list (every other ``QListView`` consumer in the
    project also benefits automatically).
  Existing focus-ring block (QPushButton / QToolButton /
  QComboBox / QSpinBox / QDoubleSpinBox / QLineEdit +
  QSlider::handle:horizontal) is preserved; the FU-016 commit
  anchors the previously-bare ``#7aa2f7`` literals with
  inline ``/* accent */`` comments and rewrites the
  ``QComboBox QAbstractItemView`` block with the same anchor
  pattern so the FU-002 token discipline is uniform across
  every selector. ``dark.qss`` header grows a "State-layer
  pseudo-state contract (FU-016)" subsection enumerating the
  eight widget families that ship the contract. Tokens used:
  ``accent`` (focus outline + selection background),
  ``accent_text`` (selection foreground), ``accent_hover``
  (FU-002 — indicator hover + item hover row), ``accent_strong``
  (checked:hover + selected:hover), ``bg_panel`` /
  ``bg_elevated`` / ``border`` / ``border_strong`` / ``text_muted``
  — every value routes through a declared ``PALETTE`` token.
  Reference observables (tests/gui/test_theme.py):
  ``test_state_layer_focus_rules_cover_every_interactive_widget``
  asserts every load-bearing widget family
  (QPushButton, QToolButton, QComboBox, QSpinBox /
  QDoubleSpinBox, QLineEdit, QSlider, QCheckBox, QListView /
  QListWidget) has at least one ``:focus`` selector — without
  these the keyboard focus indicator is invisible (WCAG 2.1
  SC 2.4.7 violation); ``test_state_layer_hover_rules_cover_new_widgets``
  pins the new QCheckBox + QListView/QListWidget hover rules;
  ``test_state_layer_consumes_palette_tokens`` parses the
  QCheckBox and QListView blocks out of dark.qss and asserts
  ``PALETTE.accent`` + ``PALETTE.accent_hover`` appear in
  each — a future palette change is forced to update the
  state-layer rules too; ``test_qcheckbox_renders_with_dark_indicator``
  verifies the application's stylesheet references
  ``QCheckBox`` so the dialog widget actually picks up our
  rule. 4 new tests; full backend + visualization + GUI suite
  at 635 passed / 14 skipped, ruff clean. Completes PR-1 +
  PR-2 + PR-3 of the recommended sequencing — every
  foundational + a11y candidate from the top-5 has now
  shipped. Commit ``8a793bd``.
- **FU-014 — Command palette (Ctrl+Shift+P).** Foundational M-sized
  discoverability surface from the 2026-05-19-initial frontend-uplift
  (RICE 4.88 — tied for highest in the synthesis;
  ``.claude/notes/frontend-uplifts/2026-05-19-initial/artifacts/final-report.md``).
  Closes the convergent C3 pattern the inspiration brief catalogues
  across napari (PR #5483), VS Code, and Houdini: every app that
  outgrows its toolbar discovers menus become a UX cliff; the
  command palette is the standard answer. The chaotic-systems
  toolbar carries 12 actions today, putting it squarely in
  "needs a palette" territory. New module
  ``chaotic_systems.gui.command_palette`` ships a
  ``CommandPalette(QDialog)`` modal opened on Ctrl+Shift+P, plus
  the ``collect_actions(host)`` helper that gathers every named
  ``QAction`` via :meth:`QWidget.findChildren(QAction)` — the
  canonical napari PR #5483 pattern (filters out anonymous /
  textless actions, dedupes by ``objectName`` so a single
  ``QAction`` appearing in both toolbar and menu surfaces once,
  alphabetises case-insensitively). The palette ships a
  ``QLineEdit`` filter (case-insensitive substring; clear-button
  enabled), a ``QListWidget`` of matched rows, and an event
  filter on the search field that routes Up/Down/Enter to the
  list so the user never has to leave the keyboard. Each row
  surfaces the action's text, its keyboard shortcut (when
  defined), and an ``(unavailable)`` suffix + tooltip on
  disabled actions so users see what *exists* even when guards
  haven't been satisfied — the synthesis explicitly called for
  this. ``main_window`` grows a ``Ctrl+Shift+P`` shortcut + an
  ``_open_command_palette()`` slot. Challenger-flagged
  theme-container concern mitigated via FU-002 (already shipped):
  the dialog's ``setStyleSheet`` binds the frame to
  ``PALETTE.bg_panel`` so the popup matches dark Tokyo Night
  chrome on Windows instead of falling back to the system-light
  frame. No "central registry" refactor needed (the challenger's
  worry) — ``findChildren`` is a one-liner. Reference
  observables (tests/gui/test_command_palette.py): the canonical
  Ctrl+Shift+P binding via ``palette_shortcut()``;
  ``collect_actions`` dedupes a QAction shared by toolbar+menu;
  textless and anonymous actions are filtered; full alphabetical
  order; the palette built against the real main window
  discovers all seven documented transport actions
  (``transport_run`` / ``transport_pause`` / ``transport_stop`` /
  ``transport_jump_end`` / ``action_export`` /
  ``action_reset_view`` / ``action_toggle_theme``) plus
  FU-013's ``action_preferences``; case-insensitive filter
  narrows the list; Enter triggers the selected action and
  accepts the dialog; disabled actions appear with the
  ``(unavailable)`` suffix and cannot be triggered. 10 new
  tests; full backend + visualization + GUI suite at 614 passed
  / 14 skipped, ruff clean. Commit ``7d4aaa0``.
- **FU-013 — Persistent settings via ``QSettings`` + Preferences dialog.**
  Foundational M-sized workflow uplift from the 2026-05-19-initial
  frontend-uplift (RICE 4.88 — highest in the synthesis;
  ``.claude/notes/frontend-uplifts/2026-05-19-initial/artifacts/final-report.md``).
  Closes the longest-standing item on ``CONTEXT.md`` "What's next" #1
  — "Persistent settings. Remember the last-used system, parameters,
  and integrator across launches (``QSettings``)." Three convergent
  inspirations (napari / ParaView / Blender) all split a Preferences
  dialog into Appearance / Defaults / Restore-on-launch sections;
  this ships the same layout. New module
  ``chaotic_systems.gui.preferences_dialog`` exposes a
  ``PersistedSettings`` dataclass + ``load_settings()`` /
  ``save_settings()`` helpers (canonical ``QSettings`` with
  ``IniFormat`` + ``UserScope`` — Windows registry deliberately
  bypassed so users can inspect / delete their config) +
  ``PreferencesDialog`` with the three sections + a
  ``build_preferences_dialog`` factory matching the existing
  ``build_*_dialog`` pattern. Schema-version key
  (``SETTINGS_VERSION = 1``) in the settings file gates a clean
  reset on mismatch — bumping the version is the documented way
  to invalidate stale keys when a knob's meaning changes.
  ``main_window`` grows three private methods —
  ``_load_persisted_settings_at_startup`` (called at the tail of
  ``__init__`` after every widget is built),
  ``_persisted_settings_snapshot`` (reads live state into a
  ``PersistedSettings``), ``_apply_persisted_settings`` (writes a
  snapshot back into the live window, with an ``at_startup`` flag
  distinguishing boot-restore from dialog-OK paths) —
  ``_open_preferences_dialog`` (modal dialog wired so OK
  persists + re-applies), Ctrl+, shortcut, and a "Preferences..."
  action in the Settings dropdown. Persisted surface:
  ``theme`` / ``bg_color`` / ``last_system`` / ``last_integrator``
  / ``last_t_end`` / ``last_dt`` / per-system parameter dicts /
  window ``saveGeometry`` + ``saveState`` bytes — the geometry /
  state fields are already wired so FU-018 (undockable diagnostic
  panels) only adds *what* to remember, not *how*.
  Challenger-flagged race condition mitigated: ``closeEvent``
  persists settings AFTER the existing sim / export / prerender
  worker-cancel block, so no worker can race ``saveGeometry`` /
  ``QSettings.setValue``. ``tests/gui/conftest.py`` gains two
  autouse fixtures (session-scoped path redirection via
  ``QSettings.setPath`` + per-test ``QSettings.clear()``) so the
  test session never touches the developer's real settings file
  and tests start from a clean slate. Reference observables
  (tests/gui/test_preferences.py): save → load round-trips every
  field (including per-system parameter dicts + bytes ``window_*``
  payloads); schema-version mismatch resets to defaults; a saved
  snapshot that drops a previously-saved system removes its stale
  keys; the main window registers an ``action_preferences`` with
  Ctrl+, shortcut and ``_persisted_settings_snapshot()`` reads
  the live picker values. 11 new tests; full backend +
  visualization + GUI suite at 584 passed / 14 skipped, ruff
  clean. Foundational for FU-018 (dock-state persistence
  consumer) and FU-014 (command palette container styling now
  benefits from the persisted theme). Commit ``8fe6a40``.
- **FU-002 — Promote ``#1a1b26`` + interaction shades to ``theme.PALETTE``.**
  Foundational S-sized token-discipline pass from the 2026-05-19-initial
  frontend-uplift (RICE 3.25 — NONE on every challenger axis;
  ``.claude/notes/frontend-uplifts/2026-05-19-initial/artifacts/final-report.md``).
  Adds five derived-interaction-shade fields to the ``Palette``
  dataclass — ``bg_deep`` (#1a1b26), ``bg_pill_track`` (#2a2c3a),
  ``accent_hover`` (#343a55), ``accent_pressed`` (#6788d8), and
  ``accent_glow`` (#a4c1ff) — each anchored with a single-line
  comment naming the use site so a future palette migration knows
  where to follow. ``assets/dark.qss`` grows a "Derived interaction
  shades (FU-002)" sub-section in the header comment block and
  inline-comment annotations at every literal use (lines for
  ``QPushButton:hover``, ``QPushButton[variant="primary"]:pressed``,
  ``QToolButton[variant="primary"]:pressed``, the spinbox up/down
  hover, and both pill-progress gradient stops). ``main_window.py``
  migrates four token-leak sites: ``_BusySpinner`` default color
  resolves lazily to ``PALETTE.accent``; Notes ``QTextBrowser``
  document stylesheet routes every literal through PALETTE tokens
  (and restores ``text_secondary`` for paragraph/list — the prior
  ``#a9b1d6`` had drifted off-palette per critic TL-02);
  ``_on_compare_finished`` overlay color resolves through
  ``PALETTE.error``; ``_BG_PRESETS`` becomes a static method
  ``_bg_presets()`` whose dark-mode presets ("Tokyo Night", "Deep
  Night") source from PALETTE tokens at call time, with "Paper
  Cream" explicitly documented as a future ``light.qss`` stub.
  Vocabulary borrows from Material Design 3 / Fluent 2 state-token
  naming. Reference observable (tests/gui/test_theme.py):
  ``test_palette_carries_derived_interaction_shades`` asserts every
  new field exists on ``PALETTE`` and resolves to its canonical
  Tokyo-Night-derived hex; ``test_dark_qss_header_documents_derived_shades``
  parses the dark.qss header comment and asserts each token name +
  expected hex is present, so a header drift fails the test.
  Closes critic findings TL-02 / TL-04 / TL-06 (the seven cited
  leak sites) and is the foundation FU-016 (state-layer hover/focus
  QSS) and FU-003 (theme-aware Notes stylesheet) depend on. +2
  tests; backend + visualization + GUI suite at 546 passed / 14
  skipped, ruff clean. Commit ``1a25fcd``.
- **FU-001 — ``QMenu`` dark-theme QSS rules.** Top-of-sequencing
  foundational S-sized theme fix from the 2026-05-19-initial
  frontend-uplift (RICE 3.12 — NONE on every challenger axis;
  ``.claude/notes/frontend-uplifts/2026-05-19-initial/artifacts/final-report.md``).
  Closes the regression the visual scout caught at
  ``screenshots/settings-open.png`` and the current-state-critic
  flagged as anti-pattern AP-01: the Settings dropdown (and any
  future menu-bearing affordance) was rendering with the
  platform-native white background on Windows, jarring against the
  Tokyo Night dark chrome. Adds a single block to
  ``src/chaotic_systems/gui/assets/dark.qss`` covering ``QMenu`` +
  ``QMenu::item`` + ``QMenu::item:selected`` + ``QMenu::item:disabled``
  + ``QMenu::separator`` + ``QMenu::indicator`` + ``QMenu::right-arrow``,
  mirroring the existing ``QComboBox QAbstractItemView`` vocabulary
  (popup surfaces feel uniform). Tokens used: ``bg_panel`` (#1f2335)
  for the menu background, ``text_primary`` (#c0caf5) for items,
  ``accent`` (#7aa2f7) + ``accent_text`` (#1f2335) for the selected
  row, ``border`` (#3b4261) for the frame, ``text_muted`` (#565f89)
  for disabled items — every value resolves to a declared
  ``theme.PALETTE`` token, no new hex literals. ``QMenu::indicator``
  and ``QMenu::right-arrow`` deliberately omit ``image: url(...)``
  references so Qt's native glyphs render in the foreground
  color (no missing-SVG silent-degradation per critic AP-04).
  Reference observable
  (``tests/gui/test_theme.py::test_dark_stylesheet_contains_qmenu_rules``):
  after ``apply_theme(qapp, "dark")`` the installed stylesheet
  contains all four load-bearing selectors (``QMenu``,
  ``QMenu::item``, ``QMenu::item:selected``, ``QMenu::separator``);
  a second test parses the QMenu block out of ``dark.qss`` and
  asserts ``PALETTE.bg_panel`` / ``text_primary`` / ``border`` /
  ``accent`` / ``accent_text`` / ``text_muted`` all appear in it,
  pinning the token-discipline contract so a future palette change
  is forced to update the QMenu rule too. Unblocks FU-008 (the
  "Analyse…" toolbar submenu the synthesis sequences next) and
  FU-014's command palette container. +2 tests, all green; backend
  + visualization + GUI suite at 538 passed / 14 skipped. Commit
  ``6e38df0``.

## Recently shipped (2026-05-18, capability-scout 2026-q2-broadening rollout)

- **CSC-014 — Hurst exponent via rescaled-range (R/S) analysis.**
  Fourth and final inhabitant of the
  ``chaotic_systems.core.diagnostics`` module from the
  2026-q2-broadening capability-scout (RICE 3.0;
  ``.claude/notes/capability-scouts/2026-q2-broadening/artifacts/final-report.md``)
  — completes the "Chaos Indicator Suite" cluster
  (CSC-011/012/013/014) the challenger's cross-candidate note
  earmarked for an eventual single batched Diagnostics-card
  section. Implements Hurst's 1951 R/S statistic via the modern
  Feder 1988 (*Fractals*, Plenum, ch. 8) recipe: partition the
  series into ``N // n`` non-overlapping chunks of size ``n``;
  for each chunk compute the cumulative-deviation range
  :math:`R = \\max Y - \\min Y` and the per-chunk std
  :math:`\\sigma`; average :math:`R/\\sigma` across chunks of
  equal size; repeat over a 20-point geometric ladder of ``n``
  from ``min_chunk=8`` up to ``N//2``; fit
  :math:`\\log(R/S)_n = H \\log n + c` by ``np.polyfit`` linear
  regression — the slope is the Hurst exponent ``H``. The
  indicator separates regimes by *memory* (not chaos vs. noise
  directly): ``H ~ 0.5`` memoryless IID Gaussian, ``H > 0.5``
  persistent (long-range positive correlation), ``H < 0.5``
  anti-persistent (mean-reverting), ``H ~ 1`` ballistic /
  fully-integrated Brownian-motion accumulation. New public
  surface:
  ``chaotic_systems.core.chaos_hurst(timeseries, *, min_chunk=8,
  max_chunk=None, num_chunks=20) -> float``, re-exported from
  ``chaotic_systems.core``. Module-level constants enforce
  ``min_chunk >= 8`` (Feder §8.3: smaller chunks are
  noise-dominated), ``max_chunk <= N // 2`` (so each size has
  at least 2 chunks for the average), and ``N >= 200`` (the
  two-decade ladder needs that floor). Reference observables
  (``tests/core/test_chaos_hurst.py``, 17 tests): IID standard
  Gaussian noise (length 4000) → ``H = 0.5607`` (clearly in
  the random-walk band; the upward bias above 0.5 is the
  well-known Annis-Lloyd 1976 small-sample bias of the R/S
  estimator); Brownian motion (cumsum of IID Gaussian) →
  ``H = 0.9881`` (ballistic, > 0.9); AR(1) with positive lag-1
  coefficient ``phi = 0.85`` (persistent short-memory) →
  ``H = 0.7292`` (> 0.6); Lorenz x at the canonical IC,
  sampled at dt~1 → ``H = 0.5570`` (random-walk band, distinct
  from the clearly-ballistic Brownian regime). Brownian-vs-IID
  separation is at least 0.2 of Hurst units
  (``test_brownian_motion_well_above_iid_gaussian``). Edge
  cases pinned: constant signal raises
  ``ValueError("undefined")`` — including the subtle
  float-precision case where chunks that don't divide N evenly
  produce std ~ 1e-15 noise (the implementation uses a
  signal-level ``chunk.max() == chunk.min()`` guard to catch
  these before they pollute the regression); too-short input
  (< 200 samples) raises with a Feder §8.3 hint; malformed
  ``min_chunk`` / ``max_chunk`` / ``num_chunks`` all raise
  with clear messages; Python list input accepted; return type
  is Python ``float``; chunk-ladder density is robust (the
  regression agrees to within 0.1 between ``num_chunks=10`` and
  ``num_chunks=30`` on the same input). Module docstring carries
  an explicit Annis-Lloyd 1976 small-sample-bias caveat and
  notes that for high-precision Hurst on long series the DFA
  family is generally preferred (out of scope for this
  indicator module). With CSC-014 the four-indicator suite is
  complete: ``chaos_zero_one_test`` + ``chaos_weighted_birkhoff``
  + ``chaos_permutation_entropy`` + ``chaos_hurst`` form a
  coherent diagnostic set that can be invoked from a single
  Diagnostics-card section the GUI will batch in a follow-up
  milestone. Non-GUI suite up to 354 passed / 10 skipped / 0
  failed (+17 new tests). ruff clean. Commit ``07dbc8d``.

- **CSC-013 — Bandt-Pompe permutation entropy chaos indicator.**
  Third inhabitant of the ``chaotic_systems.core.diagnostics``
  module from the 2026-q2-broadening capability-scout (RICE 3.0;
  ``.claude/notes/capability-scouts/2026-q2-broadening/artifacts/final-report.md``).
  Implements the ordinal-pattern Shannon entropy from Bandt &
  Pompe, *Phys. Rev. Lett.* 88 (2002) 174102. For each sliding
  window of ``order`` samples taken at lag ``delay``, the window
  reduces to its *ordinal pattern* — the permutation that sorts
  its values — and the indicator is the normalised Shannon
  entropy of the empirical pattern distribution. Output is in
  ``[0, 1]`` (normalised, default) or ``[0, ln(m!)]`` (raw):
  ``0`` means strictly regular (one pattern dominates), ``1``
  means maximally random (broad pattern distribution). New
  public surface:
  ``chaotic_systems.core.chaos_permutation_entropy(timeseries, *,
  order=4, delay=1, normalize=True) -> float``, re-exported from
  ``chaotic_systems.core``. Default order is 4 (24 patterns;
  sweet spot for ~2000-sample trajectories per Bandt-Pompe §3).
  Module-level constants enforce ``order in [2, 7]`` (m=8 needs
  N >> 40320 samples per the paper) and ``5 * m!`` minimum
  sliding windows (Bandt-Pompe §3 rule of thumb). The
  implementation uses ``argsort(kind="stable")`` + Lehmer-code
  hashing
  (``digit_i = sum(remaining[:, i+1:] < pos[:, None], axis=1)``)
  for ``O(N * m^2)`` time and ``O(m!)`` space — fast enough for
  sub-millisecond evaluation on Lorenz-scale trajectories.
  Reference observables
  (``tests/core/test_chaos_permutation_entropy.py``, 20 tests):
  constant signal → ``H = 0`` exactly; strictly monotonic ramp
  (increasing or decreasing) → ``H = 0`` exactly; logistic at
  ``r = 3.5`` (period-4 cycle) → ``H = log(4)/log(24) ~ 0.4368``
  to 0.01 (the theoretical value for 4 cyclically-shifted
  patterns equally likely with m=4); logistic at ``r = 4`` (hard
  chaos with forbidden patterns) → ``H in (0.6, 0.85)`` per
  Bandt-Pompe Fig. 2 — the dip below 1 is characteristic of the
  logistic family's forbidden patterns; IID uniform noise →
  ``H > 0.99``; Lorenz x at dt~1 → ``H > 0.99``; oversampled
  sine (5-period sampled at 2000 points) → ``H < 0.5``.
  Parametrised tests confirm the indicator approaches 1 on noise
  at every order m ∈ {3, 4, 5, 6} with the ``5 * m!`` minimum
  sample count. The unnormalised path is also tested: with
  ``normalize=False`` the output lands in ``[0, log(m!)]`` and
  the normalised value equals the raw divided by ``log(m!)``
  exactly. Edge cases pinned: order outside ``[2, 7]`` raises
  with a Bandt-Pompe §3 hint; delay < 1 raises; too-short input
  raises with a "Lower the order or run the system longer" hint;
  Python list input accepted; return type is Python ``float``.
  Ties broken by ``argsort(kind="stable")`` so a constant input
  maps every window to ``(0, 1, ..., m-1)`` and gives ``H = 0``
  as expected. GUI surface still deferred — the PE is the third
  of four scalar chaos indicators (CSC-011, CSC-012, CSC-013,
  pending CSC-014 Hurst) earmarked for a single batched "Chaos
  Indicator Suite" Diagnostics-card section; one more indicator
  and the cluster is complete. Non-GUI suite up to 337 passed /
  10 skipped / 0 failed (+20 new tests). ruff clean. Commit
  ``670001c``.

- **CSC-012 — Weighted Birkhoff Average chaos indicator
  (Sander-Yorke).** Second inhabitant of the
  ``chaotic_systems.core.diagnostics`` module from the
  2026-q2-broadening capability-scout (RICE 3.0;
  ``.claude/notes/capability-scouts/2026-q2-broadening/artifacts/final-report.md``).
  Implements the super-Gaussian Weighted Birkhoff Average from
  Sander & Yorke (Int. J. Bifurc. Chaos 22 (2012) 1250022) and
  Das et al. (Europhys. Lett. 114 (2016) 40005) and exposes it as
  a *digit-loss* chaos indicator: the WBA on the full trajectory
  is compared against the WBA on the first half, and the negative
  log10 of their difference becomes the indicator scalar in
  ``[0, ~16]``. Regular (Diophantine quasi-periodic) orbits show
  super-exponential WBA convergence → the two halves agree to
  near machine precision → digit-loss saturates at 16; chaotic
  orbits show only polynomial WBA convergence → the two halves
  disagree at the 1e-2 to 1e-5 level → digit-loss ~2-5. New
  public surface:
  ``chaotic_systems.core.chaos_weighted_birkhoff(timeseries, *,
  observable=None) -> float``, re-exported from
  ``chaotic_systems.core``. Default observable is
  ``cos(2 pi x)`` per Das et al. 2016 §3 — smooth, bounded,
  oscillatory, well behaved for ``[0, 1)``-wrapped iterates.
  Module-level constants ``_WBA_MAX_DIGITS = 16`` (the float64
  precision cap) and ``_WBA_MIN_SAMPLES = 200`` (the two-halves
  test needs each half to contain the super-Gaussian's support).
  Reference observables (``tests/core/test_chaos_weighted_birkhoff.py``,
  14 tests): the canonical golden-ratio rotation
  ``x_{n+1} = x_n + (sqrt(5)-1)/2 (mod 1)`` → digit-loss
  saturates at 16; the logistic map at the period-4 cycle
  ``r = 3.5`` → digit-loss saturates at 16 (also regular); the
  logistic map at ``r = 4`` (Lebesgue-ergodic hard chaos) →
  digit-loss = 1.688; IID uniform noise → digit-loss = 1.336;
  Lorenz x-coordinate at the canonical IC, integrated to t=1000
  and wrapped to [0, 1) → digit-loss = 2.404. All regular
  classifications are at least 5 digits above all chaotic
  classifications on this test set
  (``test_regular_and_chaotic_classifications_are_well_separated``).
  Module docstring carries an explicit numerical caveat: the
  doubling map ``x_{n+1} = 2 x_n (mod 1)``, while
  *theoretically* chaotic, gives a misleadingly high digit-loss
  (~8.8) because float64 loses precision after ~52 iterates — a
  well-known artefact in the Sander-Yorke literature that is
  computational, not dynamical, and the logistic map at
  ``r = 4`` is the correct hard-chaos test case to use instead.
  Edge cases pinned: constant signal → digit-loss = 16 exactly
  (two halves bit-identical); custom-observable hook accepts a
  ``Callable[[ndarray], ndarray]`` and rejects observables that
  return the wrong length with a clear ``ValueError``; too-short
  input (< 200 samples) raises with a "Run the system longer"
  hint; Python list input accepted; return type is Python
  ``float``. GUI surface still deferred — the WBA is the second
  of four scalar chaos indicators (CSC-011, CSC-012, plus
  pending CSC-013 permutation entropy and CSC-014 Hurst) that
  the challenger's cross-candidate note earmarked for a single
  batched "Chaos Indicator Suite" Diagnostics-card section.
  Non-GUI suite up to 317 passed / 10 skipped / 0 failed (+14
  new tests). ruff clean. Commit ``c1938ce``.

- **CSC-011 — 0-1 test for chaos (Gottwald-Melbourne).** S-sized
  scalar chaos indicator from the 2026-q2-broadening
  capability-scout (RICE 3.0;
  ``.claude/notes/capability-scouts/2026-q2-broadening/artifacts/final-report.md``).
  First inhabitant of a new ``chaotic_systems.core.diagnostics``
  module, which the challenger's "Chaos Indicator Suite" framing
  earmarked as the right home for the cluster of small
  scalar-chaos-indicator functions (WBA, permutation entropy,
  Hurst — pending CSC-012/013/014). Complementary to
  :func:`lyapunov_spectrum` and :func:`largest_lyapunov_two_trajectory`
  in two ways: (1) the input is a *scalar* projection (e.g. just
  ``x(t)`` of Lorenz), not the full state vector, so it works on
  exported single-column data; (2) the output is a single
  ``K in [0, 1]`` that classifies regime directly without
  per-exponent interpretation. New public surface:
  ``chaotic_systems.core.chaos_zero_one_test(timeseries, *, n_c=100,
  c_range=(pi/5, 4 pi/5), n_cut=None, rng=None) -> float`` re-exported
  from ``chaotic_systems.core``. The implementation follows
  Gottwald-Melbourne 2009 §3 eqs. 4-13 verbatim: build the
  auxiliary translation variables
  ``p_c(n) = cumsum(phi(j) cos(c j))`` and
  ``q_c(n) = cumsum(phi(j) sin(c j))``; compute the *modified*
  mean-square displacement
  ``D_c(n) = M_c(n) - <phi>^2 (1 - cos(c n)) / (1 - cos(c))`` for
  lags ``n = 1..n_cut`` (the oscillatory subtraction in eq. 11
  isolates the growth rate); take the Pearson correlation of
  ``(n, D_c(n))`` to get the single-c statistic ``K_c``; report
  the **median** of ``K_c`` over ``n_c=100`` random ``c`` draws
  in ``(pi/5, 4 pi/5)``. Default seed (``0xC0FFEE``) makes outputs
  reproducible without an explicit rng. Reference observables
  (``tests/core/test_chaos_zero_one_test.py``, 13 tests):
  ``sin(2 pi t / 10)`` on ``t in [0, 200]`` with 2000 samples →
  ``K = 0.0000`` (periodic, regular); IID standard-normal noise
  of length 2000 → ``K = 0.9980`` (random walk in ``(p_c, q_c)``);
  Lorenz canonical IC integrated to ``t = 2000`` and downsampled
  to ``dt ~ 1`` (one sample per natural orbital period) → ``K =
  0.998+`` (canonical chaotic Lorenz, Sprott Table 5.1).
  Docstring carries an explicit oversampling warning: at
  ``dt = 0.04`` the same Lorenz trajectory gives ``K = 0.025``
  (the oscillatory autocorrelation dominates ``M_c``); the user
  must downsample to roughly one sample per dominant oscillation
  period before calling. Edge cases pinned by tests:
  zero-variance / constant-signal input → ``K = 0`` exactly via
  the degenerate Pearson-correlation branch; too-short input
  (< 100 samples) raises ``ValueError`` with a "Run the system
  longer" hint; malformed ``c_range`` (outside ``(0, 2 pi)`` or
  inverted) raises; ``n_cut`` outside ``[1, N-1]`` raises;
  Python list input is accepted; the return type is Python
  ``float`` (not ``np.floating``) so ``f"K = {K}"`` renders cleanly.
  GUI surface deliberately deferred — the challenger's
  cross-candidate note endorsed batching the four scalar
  chaos indicators (CSC-011 + CSC-012 + CSC-013 + CSC-014)
  behind a single Diagnostics-card section, so this milestone
  ships the core function + tests without touching ``main_window.py``;
  the GUI button lands when the cluster is complete. Non-GUI
  suite up to 303 passed / 10 skipped / 0 failed (+13 new tests).
  ruff clean. Commit ``463dd6c``.

- **CSC-032 [T1] — Quick λ₁ GUI toggle.** XS wire-up from the
  2026-q2-broadening capability-scout (tied for RICE 7.20 with the
  ``docs/systems.md`` refresh that already shipped as CSC-034;
  ``.claude/notes/capability-scouts/2026-q2-broadening/artifacts/final-report.md``).
  ``largest_lyapunov_two_trajectory`` has shipped at
  ``core/lyapunov.py:52`` since day one and is tested
  (``tests/systems/test_lorenz.py:55``); this milestone surfaces it
  in the Diagnostics card as an alternative to the full Lyapunov
  spectrum. New widget:
  ``quick_lyapunov_checkbox`` (``QCheckBox``, objectName
  ``checkbox_quick_lyapunov``) lives directly below the existing
  ``button_lyapunov`` in the Diagnostics card. Default state
  unchecked — the full spectrum stays the default per the
  challenger's recommendation, so existing tests and any
  publication-grade output paths are unchanged. When the user
  ticks the box and clicks Compute, the ``_LyapunovWorker`` gains
  a ``mode="quick"`` branch that calls
  ``largest_lyapunov_two_trajectory(system, ...)`` instead of the
  QR-spectrum path; a second
  ``quick_finished = Signal(float)`` signal carries the single λ₁
  back to ``_on_quick_lyapunov_finished``, which renders the
  one-line ``Chaotic (quick estimate, two-trajectory method) ⏎  λ1
  = +0.9072`` summary via the new ``_format_quick_lyapunov``
  module helper. The output deliberately omits any per-exponent
  spectrum lines and any ``D_KY`` line — Kaplan-Yorke needs the
  whole spectrum (CSC-008), so the quick mode is honest about
  what it can and cannot compute. Status-bar λ₁ chip mirrors the
  scalar exactly as the full-spectrum path does. Default settings
  (``t_transient=50``, ``t_total=500``, ``dt=1.0``) match the
  ``lyapunov_spectrum`` worker so the user can compare modes on
  the same window; the quick mode runs in ~5 s on Lorenz vs.
  ~30-60 s for the full spectrum (Benettin two-trajectory vs.
  variational QR, same compute window). Reference observables
  (``tests/gui/test_lyapunov_panel.py``): ``_format_quick_lyapunov(0.9072)``
  returns text with ``"Chaotic"`` + ``"quick estimate"`` + ``"λ1 =
  +0.9072"`` and no ``"D_KY"`` substring; the
  ``_on_quick_lyapunov_finished(0.9072)`` slot updates
  ``lyapunov_result_label.text()`` to that block and sets the
  λ₁ chip to ``"λ₁ = +0.9072"`` exactly. NaN input falls into a
  ``"non-finite λ₁"`` branch with ``leading = 0.0`` so the chip
  doesn't display garbage. Quick-mode preference is sticky across
  system switches (``test_quick_toggle_survives_system_change``);
  the result label resets to its prompt copy on system change
  but the toggle does not. 7 new tests total: 4 pure-function tests
  on ``_format_quick_lyapunov`` (chaotic / regular / marginal /
  non-finite) and 3 GUI wiring tests (widget existence,
  quick-finished signal flow, toggle-sticky-on-system-change).
  Non-GUI suite unchanged at 290 passed / 10 skipped / 0 failed;
  ruff clean. Commit ``e3abbc3``.

- **CSC-033 [T3] — ``PostSimDiagnosticProvider`` hook + per-system
  observables in the Diagnostics card.** Foundational M-sized
  workflow change from the 2026-q2-broadening capability-scout
  (RICE 3.51 — foundational + wire-up;
  ``.claude/notes/capability-scouts/2026-q2-broadening/artifacts/final-report.md``).
  Closes the internal-adversary brief's T3 + T2 gaps in one
  protocol-shaped change: Kuramoto's order parameter ``|r|``,
  HénonHeiles' conserved energy + drift, and DoublePendulum's
  energy + drift now display as chips in the Diagnostics card after
  every Run. Per the Phase-3 challenger's recommendation the hook
  uses a **runtime-checkable Protocol** in a new module
  ``chaotic_systems.core.diagnostics_protocol`` rather than adding
  a method to the ``abc.ABC`` ``DynamicalSystem``, so the change
  is zero-impact on the 9 systems that don't implement it (Lorenz,
  Rossler, Chua, Duffing, RosslerHyper, MackeyGlass, + the 4
  discrete maps all keep their existing Diagnostics-card behaviour
  unchanged). Public surface:
  ``PostSimDiagnosticProvider`` (Protocol with
  ``post_sim_diagnostics(trajectory) -> Mapping[str, str]``) and
  ``format_post_sim_diagnostics(dict) -> str``, both re-exported
  from ``chaotic_systems.core``. Implementations:
  ``Kuramoto.post_sim_diagnostics`` returns
  ``{"|r|": "{r:.4f}", "ψ": "{psi:+.4f}"}`` computed on the final
  trajectory frame via the existing ``order_parameter`` static
  method (Kuramoto/Strogatz "From Kuramoto to Crawford", Physica D
  143 (2000) 1-20); ``HenonHeiles.post_sim_diagnostics`` and
  ``DoublePendulum.post_sim_diagnostics`` return
  ``{"E": "...", "|ΔE/E₀|": "..."}`` derived from the existing
  ``energy()`` method on first and last frames (Hairer-Lubich-
  Wanner *Geometric Numerical Integration* 2006 §V provides the
  expected ~1e-7 drift signature for ``yoshida4`` on HénonHeiles).
  All three providers return ``{}`` on empty trajectories so the
  Diagnostics card stays uncluttered. GUI wiring: new
  ``system_observables_label`` ``QLabel`` lives in the existing
  Diagnostics card immediately below ``lyapunov_result_label``,
  starts hidden, populated via the new
  ``_refresh_system_observables(traj)`` helper called from
  ``_on_sim_finished``. ``isinstance(system, PostSimDiagnosticProvider)``
  is the gate; the label hides on system change so the previous
  system's stale chips never appear. Reference observables
  (``tests/core/test_post_sim_diagnostics_protocol.py``, 19 tests):
  the Protocol's ``isinstance`` check returns True for Kuramoto /
  HenonHeiles / DoublePendulum and False for Lorenz / Rossler /
  Chua / Duffing (parametrised); Kuramoto with all phases aligned
  returns ``|r| = 1.0000``; Kuramoto with evenly spaced phases
  returns ``|r| = 0`` to atol=1e-12; HenonHeiles on a stationary
  trajectory returns ``|ΔE/E₀| = 0`` exactly; DoublePendulum picks
  up ``trajectory.params`` when present and falls back to defaults
  otherwise. GUI-side wiring tests
  (``tests/gui/test_post_sim_diagnostics_panel.py``, 6 tests,
  gated on ``CHAOTIC_GUI_TESTS_USE_DISPLAY=1`` + ``PySide6`` +
  ``pyvistaqt``): label has stable ``objectName``, starts hidden,
  populates with ``|r|`` and ``ψ`` lines after a Kuramoto Run,
  stays hidden after a Lorenz Run, resets to hidden on system
  switch, and HenonHeiles populates ``E`` + ``|ΔE/E₀|`` chips.
  Non-GUI suite: 290 passed / 10 skipped / 0 failed (up from 271 —
  the +19 are all the new protocol tests, no regressions). ruff
  clean. Commit ``eb3bccd``.

- **CSC-029 [W1] — Poincaré section panel (the "next D1").** Top-of-
  sequencing M-sized wire-up from the 2026-q2-broadening
  capability-scout (RICE 4.68 — foundational + wire-up;
  ``.claude/notes/capability-scouts/2026-q2-broadening/artifacts/final-report.md``).
  Closes the exact gap the internal-adversary brief flagged at W1:
  ``poincare_section()`` has shipped in ``core/poincare.py:42`` since
  day one and is tested at ``tests/systems/test_henon_heiles.py:33``,
  but had **zero GUI surface** — no panel, no toolbar action, no
  matplotlib visualization. This is the textbook "next D1" by the
  internal-adversary's framing: the compute existed; only the UI
  wrapper was missing. New modules:
  ``chaotic_systems.visualization.poincare_plot`` (pure-matplotlib
  scatter renderer in the same Agg-safe pattern as ``phase_plot.py``
  / ``basin_plot.py``, with Tokyo-Night facecolor support and an
  empty-result annotation) and ``chaotic_systems.gui.poincare_panel``
  (PoincarePanel widget + ``_PoincareWorker`` QThread worker +
  ``build_poincare_panel`` / ``build_poincare_dialog`` constructors).
  Controls: section-axis combo (axis-aligned only, per the
  challenger's "defer arbitrary-normal until users ask"), offset
  spinbox, direction picker (upward / downward / both, mirroring
  scipy.integrate event.direction semantics), ``t_end`` /
  ``t_transient`` spinboxes, display-axis pickers for the 2D
  projection (defaults exclude the section axis — for HenonHeiles
  with section-axis = ``x``, picks ``(y, p_y)`` for the canonical
  Hénon & Heiles 1964 Fig. 4 image), equal-aspect toggle, Compute
  / Cancel buttons, status label. The compute runs through the
  existing ``solve_ivp`` event-detection path (``DOP853``,
  rtol=1e-9, atol=1e-12, max_step=0.5) on a QThread so the UI
  stays responsive. Cancellation is cooperative (the underlying
  ``solve_ivp`` is opaque, so cancel flips a flag that takes effect
  at the next completed compute). Wired into the main-window
  toolbar as ``action_poincare`` (enabled by default — the panel
  runs its own compute, no prior Run required), positioned after
  ``action_basins`` and before ``action_toggle_theme``.
  ``_on_open_poincare`` slot mirrors ``_on_open_basins`` / ``_on_open
  _phase_portrait`` with state_dim >= 2 guard and a Tokyo-Night
  facecolor pass-through via ``viewport_background()``. Reference
  observable (``tests/gui/test_poincare_panel.py``,
  ``test_henon_heiles_section_observable``): with HenonHeiles at
  the canonical default IC ``[0, 0.1, 0.45, 0]`` (E ≈ 0.125),
  section through ``x = 0`` with upward crossings and
  ``t_end = 200``, the panel's worker collects >= 20 crossings (
  measured: 31), all on the hyperplane to atol=1e-8, all with
  ``|p_y| < 1`` (mixed-phase-space scale). The synthesis's
  long-window >= 50 claim is pinned in a second test at
  ``t_end = 500``. 13 new GUI tests covering widget existence,
  default-value pinning, section-axis-change repositioning the
  display defaults, finished/cancelled/error handlers, the
  ``t_transient >= t_end`` guard, error-via-signal on bad normal
  shape, and the ``action_poincare`` toolbar entry. Non-GUI suite
  unchanged at 271 passed / 10 skipped / 0 failed; GUI panel tests
  gated on ``CHAOTIC_GUI_TESTS_USE_DISPLAY=1`` and on
  ``pytest.importorskip("PySide6")`` / ``"pyvistaqt"``. ruff clean.
  Commit ``5efc305``.

- **CSC-034 [V3] — ``docs/systems.md`` refresh covers all 13 registered
  systems.** Tied-for-#3 RICE pick from the 2026-q2-broadening
  capability-scout (RICE 7.20 — XS wire-up;
  ``.claude/notes/capability-scouts/2026-q2-broadening/artifacts/final-report.md``).
  Pure documentation hygiene — closes the gap the internal-adversary
  brief identified at ``docs/systems.md:4`` (7 systems documented vs.
  13 registered in ``registry.py:73-93``). New sections cover
  ``MackeyGlass`` (DDE), ``Kuramoto`` (N-oscillator network),
  ``Logistic``, ``HenonMap``, ``Ikeda``, and ``StandardMap`` (the four
  discrete maps from N1). The table is split into "ODE flows" (9
  entries) and "Discrete maps" (4 entries) so the registry's ``kind``
  attribute lines up with the doc layout. Existing entries refreshed:
  Lorenz cites D_KY ≈ 2.062 (CSC-008 shipped same day), RosslerHyper
  cross-references the new Kaplan-Yorke diagnostic. The "Adding a new
  system" checklist is rewritten to cover the `DiscreteSystem` /
  ``DynamicalSystem`` split, the ``_DEFAULT_*`` constant convention,
  the ``educational_notes`` "what / where to read / why it matters /
  what to try" structure used by all shipped systems, and the
  ``jax_backend.py`` JAX-RHS factory companion (CSC-027 shipped same
  day) for polynomial systems. No code change, no test change. Commit
  ``21fe521``.

- **CSC-027 [W5] — JAX-traceable RHS for all polynomial systems.**
  Foundational performance candidate from the 2026-q2-broadening
  capability-scout (RICE 14.04 — foundational + wire-up;
  ``.claude/notes/capability-scouts/2026-q2-broadening/artifacts/final-report.md``).
  Resolves the "JAX backend dead code for everything except Lorenz"
  anti-pattern flagged in the internal-adversary brief (AP3): until
  this landed, only ``lorenz_jax_rhs`` existed, so any
  ``vmap_trajectories`` or ``basin_diagram(backend='jax')`` call on
  Rossler / Chua / Duffing / 4D-Rossler would fail to JIT-trace
  through the numpy ``_rhs`` (which uses ``np.array(...)``). New
  factories shipped alongside ``lorenz_jax_rhs`` in
  ``chaotic_systems.integrators.jax_backend``:
  ``rossler_jax_rhs(a=0.2, b=0.2, c=5.7)``,
  ``chua_jax_rhs(alpha=15.6, beta=28.0, m0=-1.143, m1=-0.714)``
  (with the piecewise-linear Chua-diode nonlinearity traced through
  ``jnp.abs``), ``duffing_jax_rhs(alpha=-1, beta=1, delta=0.2,
  gamma=0.3, omega=1.0)`` (non-autonomous, ``jnp.cos(omega*t)``
  drive), and ``rossler_hyper_jax_rhs(a=0.25, b=3.0, c=0.5, d=0.05)``.
  Each factory closes over its system's canonical default parameters
  (matching the corresponding ``DynamicalSystem`` subclass exactly)
  and returns a ``rhs(t, y, args=None)`` callable in the diffrax-
  friendly 3-arg shape. Module docstring cites Lorenz 1963, Rossler
  1976 + 1979, Matsumoto/Chua/Komuro 1985, and Duffing 1918 / Moon
  1987 verbatim. Reference observable
  (``tests/integrators/test_jax_polynomial_rhs.py``, gated on the
  ``[jax]`` extra): for each system at the canonical IC and across
  a 20-point random ``(state, t)`` grid sampled from
  ``[-5, 5]^state_dim x [0, 5]``, the JAX RHS output matches the
  numpy ``_rhs`` output to ``atol=1e-6, rtol=0`` (the floor absorbs
  any float32-default JIT casts; with ``jax_enable_x64`` the error
  collapses to 0). Edge cases tested explicitly: Chua's diode across
  all three regions (probes ``x in {-2.5, -1.0, -0.25, 0.0, 0.25,
  1.0, 2.5}``); Duffing's drive flipping sign across half a period
  (``cos(0) - cos(pi) = 2``, so the v-component RHS differs by
  ``2*gamma``); 3-arg ``rhs(t, y, args)`` form parity with the
  2-arg form. The pre-existing ``lorenz_jax_rhs`` and its scipy-
  parity test in ``test_jax_backend.py`` are unchanged. Hénon-Heiles
  and DoublePendulum (sympy.lambdify-backed) are out of scope here
  — they need a separate JAX-grad-H path that mirrors P2's
  ``CompiledRHS`` pattern. The module still imports cleanly without
  the ``[jax]`` extra (deferred-import pattern preserved). 26 new
  parametrized tests (5 canonical-IC, 5 random-grid, 7 Chua-diode,
  1 Duffing-time, 5 three-arg-signature, 3 import-import-import
  smoke), 271 passed in the non-GUI suite. Commit ``f2639fd``.

- **CSC-008 — Kaplan-Yorke (Lyapunov) dimension diagnostic.** Top-RICE
  pick from the 2026-q2-broadening capability-scout
  (``.claude/notes/capability-scouts/2026-q2-broadening/artifacts/final-report.md``,
  RICE 24.0 — wire-up + broken docstring fix). New
  ``kaplan_yorke_dimension(spectrum) -> float`` lives next to
  ``lyapunov_spectrum`` in ``core/lyapunov.py``. Formula
  ``D_KY = k + (sum_{i=1..k} lambda_i) / |lambda_{k+1}|`` where ``k``
  is the largest index with non-negative cumulative sum (Kaplan &
  Yorke 1979, LNM 730; Sprott *Chaos and Time-Series Analysis*
  Oxford 2003, Table 5.1). The function handles the four canonical
  regimes by construction: fixed point -> ``0.0``; limit cycle ->
  ``1.0``; chaotic flow with one contracting direction -> ``k + frac``;
  no contraction (all cumulative sums non-negative) -> ``float(n)``.
  Surfaced in the GUI Diagnostics card by
  ``_format_lyapunov_spectrum`` (``gui/main_window.py``), which now
  appends ``D_KY = X.XXX`` as the last line of the spectrum readout,
  fixing the broken docstring promise that proposal CSC-008
  identified at ``main_window.py:207``. Reference observable
  (``tests/core/test_kaplan_yorke.py``): on the Sprott Table 5.1
  reference spectrum ``(0.9056, 0, -14.572)``, ``kaplan_yorke_dimension``
  returns ``2 + 0.9056 / 14.572 = 2.0621...`` to machine precision; on
  an end-to-end ``lyapunov_spectrum(Lorenz, t_total=120)`` run,
  ``D_KY`` lands in ``(2.0, 2.2)``, comfortably bracketing the Sprott
  value 2.062; on 4D hyperchaos ``(0.16, 0.03, 0, -25)`` returns
  ``3 + 0.19 / 25 ~= 3.008``. 10 new unit tests (``tests/core``) plus
  two updated GUI panel tests (``tests/gui/test_lyapunov_panel.py``)
  pin the integer-regime edge cases (empty spectrum raises, all-
  negative -> 0, limit cycle -> 1) and the degenerate
  ``lambda_{k+1} ~= 0`` fallback. Commit ``d241092``.

## Recently shipped (2026-05-17, capability roadmap rollout cont'd)

- **I3 — optional ``scikit-sundae`` (SUNDIALS) CVODE + IDA backend.**
  New ``chaotic_systems.integrators.sundials_backend`` module ships
  three production-grade SUNDIALS integrators: ``"CVODE"``
  (multistep BDF — default for stiff problems, drop-in alternative
  to scipy's ``Radau`` / ``BDF``), ``"CVODE-Adams"`` (multistep
  Adams-Moulton — non-stiff variant, predictor-corrector counterpart
  of LSODA), and ``IDA`` (index-1 DAE solver, exposed as the
  ``ida_solve`` free function because its residual + ``yp0``
  signature doesn't fit the ODE-only ``Integrator`` protocol).
  CVODE / CVODE-Adams register in the integrator picker; IDA is
  reachable only by callers that need DAE semantics. NREL
  ``scikit-sundae`` 1.1.3 (Mar 2026) ships wheels with SUNDIALS
  7.5 prebuilt, so the brief's "no Julia / Rust / C++ deps the
  user would need to compile" constraint is satisfied — the new
  ``[sundials]`` extra in ``pyproject.toml`` never triggers a
  local C compile. The module imports cleanly without the extra;
  ``has_sundials_backend()`` reports install state; calling
  ``integrate`` / ``ida_solve`` without the extra raises a clear
  ``ImportError`` with the canonical ``pip install -e '.[sundials]'``
  hint. The RHS adapter (``_make_rhsfn``) auto-wraps the project's
  standard ``rhs(t, y) -> dy/dt`` form into sksundae's in-place
  ``rhsfn(t, y, yp) -> None`` shape, so user code doesn't have to
  learn a new RHS convention; native in-place rhsfn pass through
  unchanged. ``lorenz_sundials_rhsfn`` and ``robertson_residual``
  ship as canonical reference callables, citing Lorenz 1963 and
  Robertson 1966 (Hairer-Wanner II §IV.1 stiff-DAE benchmark) in
  the module docstring. Reference observables
  (tests/integrators/test_sundials_backend.py, gated on the extra):
  CVODE-BDF and CVODE-Adams on Lorenz from (1,1,1) over t in [0, 5]
  at rtol=1e-10/atol=1e-12 each agree with scipy DOP853 at the
  endpoint to L2 < 1e-3 (same precision floor I1 / I2 enforce);
  IDA on Robertson's DAE preserves the algebraic conservation
  ``y0 + y1 + y2 = 1`` to < 1e-8 across the integration and drives
  the fast-decaying middle species ``y1 < 1e-3`` at t = 1, the
  classical quasi-steady-state observable (Hairer-Wanner II Fig.
  1.1). 18 new tests (12 always-on + 6 gated on ``[sundials]``);
  backend suite goes 248 -> 271 collected (271 passed / 9 skipped
  locally with the extra installed). Closes row 18 of the roadmap's
  sequencing table — every "Defer until motivated" item is now
  shipped. Commit ``2a18f3c``.
- **I2 — optional ``numbalsoda`` LSODA integrator backend.** New
  ``chaotic_systems.integrators.numbalsoda_backend`` module ships a
  single ``Integrator``-protocol instance (``"NumbaLSODA"``) wrapping
  Wogan et al.'s ``numbalsoda.lsoda`` — a numba-callable LSODA that
  auto-detects stiffness (Adams ↔ BDF) and runs the integration loop
  entirely in native code, closing the "you can JIT your RHS but the
  outer loop is still Python" gap that ``docs/numerics.md`` calls
  out as a known limitation of the fixed-step JIT recipe.
  ``numbalsoda`` is **maintenance-dormant** (last release Sep 2022)
  but still correct because the underlying ODEPACK LSODA is itself
  frozen-spec; the module's docstring flags this and points new
  optional-backend work at I1's diffrax / JAX path instead. The RHS
  must be a ``numba.cfunc(numbalsoda.lsoda_sig)``-decorated callable
  (plain Python ``rhs(t, y)`` cannot cross the Fortran boundary and
  is rejected with a clear ``TypeError`` pointing at the recipe in
  the module docstring); :func:`lorenz_numbalsoda_rhs` ships as the
  canonical reference cfunc, with parameters passed through
  numbalsoda's ``data=`` channel (``p[0]/p[1]/p[2]`` = sigma/rho/
  beta). ``numbalsoda`` and ``numba`` are bundled into the existing
  ``[performance]`` extra of ``pyproject.toml`` — the module imports
  cleanly without them, ``has_numbalsoda_backend()`` reports
  install state, and calling ``integrate`` without the extra raises
  ``ImportError`` with a ``pip install -e '.[performance]'`` hint.
  Registered as ``"NumbaLSODA"`` in the integrator registry so the
  GUI picker advertises it uniformly. Reference observable
  (tests/integrators/test_numbalsoda_backend.py, gated on the
  extra): NumbaLSODA's Lorenz trajectory from (1,1,1) over t in
  [0, 5] at rtol=1e-10/atol=1e-12 agrees with scipy DOP853 at the
  endpoint to L2 < 1e-3 (same precision floor I1 enforces — chaos
  amplifies any per-step discrepancy fast). 15 new tests (10
  always-on + 5 gated on the ``[performance]`` extra), all green.
  Commit ``0209bef``.
- **P2 — AOT-compile sympy ``_rhs`` via numba.** Closes the
  open ``CONTEXT.md`` "What's next" #4 item (and matches the P2
  proposal in the roadmap). ``chaotic_systems.core._numba`` grows
  ``compile_rhs(system) -> CompiledRHS``: detects whether a system
  is backed by a ``LagrangianSystem`` (DoublePendulum's ``_lsys``)
  or a ``HamiltonianSystem`` (HenonHeiles's ``hamiltonian``) and
  ``numba.njit``\\s the inner ``sp.lambdify`` callable, returning
  a uniform ``(t, y, params) -> dy/dt`` adapter. Pure-numpy systems
  (Lorenz / Rossler / Kuramoto / ...) go through a passthrough
  wrapper. Numba unavailable or JIT compile failure → silent
  fallback to ``system.rhs``; the contract holds in every
  environment. Reference observable: ``compile_rhs(dp)(t, y, params)
  == dp.rhs(t, y, **params)`` to machine precision (max
  absolute error = 0.0) at the canonical IC and over a 20-point
  random grid of (state, parameter) pairs; same for HenonHeiles.
  Pure-numpy passthrough: exact bitwise equality with ``sys.rhs``.
  Performance: ~1.2× speedup on the double pendulum's RHS (the
  array-assembly Python overhead bounds further gains; the bulk of
  the win comes from numba inlining the CSE'd algebraic expressions
  in the lambdified body). 15 new tests, all green. Commit ``28bd53b``.
- **N4 — Kuramoto N-oscillator network.** First *network* dynamical
  system in the project — fills the "network dynamics" slot the
  brief calls out as a target phenomenology. Single new module
  ``systems/kuramoto.py`` (~190 lines incl. docstring + educational
  notes). State vector is the phase angles
  ``(θ_1, ..., θ_N)`` with ``N`` set per-instance (default 10).
  Natural frequencies are Lorentzian (Cauchy) draws seeded at
  construction time — quenched disorder, reproducible across runs.
  RHS uses the **mean-field reformulation**
  ``dθ_i/dt = ω_i + K r sin(ψ - θ_i)`` (exact via trig identity,
  O(N) per call instead of O(N²)). Public helpers:
  ``order_parameter(theta) -> (|r|, ψ)`` and ``omega`` (read-only
  copy of the frequency vector). Reference observable
  (tests/systems/test_kuramoto.py): with ``N = 20`` Lorentzian
  ``γ = 0.5`` (so ``K_c = 2γ = 1.0``), late-time mean ``|r|``
  over t in [80, 100] is < 0.4 at subcritical ``K = 0.1`` and
  > 0.85 at supercritical ``K = 5.0`` — the canonical Kuramoto
  synchronization transition. K=0 dynamics match the analytic
  ``θ_i(t) = θ_i(0) + ω_i t`` exactly. 13 new tests, all green.
  Commit ``4d009ed``.
- **N3 — Mackey-Glass DDE + Bellen-style DDE integrator.** First
  delay-differential equation in the project — adds an
  architecturally new *kind* of system (infinite-dimensional
  phase space; chaos lives on the history manifold).
  ``integrators/dde.py`` ships ``BellenRK4`` — a single-delay
  Bellen-Zennaro-style RK4 with a linearly-interpolated history
  buffer. ``systems/mackey_glass.py`` ships ``MackeyGlass``
  (canonical β=0.2, γ=0.1, n=10, τ=17 chaotic regime; default IC
  x(0)=1.2), which overrides ``DynamicalSystem.simulate`` to
  dispatch to BellenRK4 regardless of the GUI's integrator-picker
  choice (no ODE integrator is applicable). ``_rhs`` is a
  static-history-approximation shim so the existing parametrized
  registry test and any other ODE-style probe see a finite, well-
  defined return rather than an exception. Reference observables
  (tests/integrators/test_dde.py + tests/systems/test_mackey_glass.py):
  (1) linear DDE ``x'(t) = -x(t-1)`` with constant-1 history hits
  the piecewise-analytic ``x(1) = 0``, ``x(2) = -1/2`` to 1e-6;
  (2) MackeyGlass at τ=2 converges to the analytic fixed point
  ``x* = (β/γ - 1)^(1/n) = 1`` to 1e-4; (3) canonical τ=17 stays
  bounded in (0.1, 2.0) with non-trivial late-time spread
  std/mean > 0.05 (chaotic). 26 new tests, all green. Commit
  ``c95ba50``.
- **E2 — live parameter-slider preview.** Settings dropdown gains a
  checkable "Live preview (slider drag re-simulates)" action;
  default off. When toggled on, every change to any parameter
  spinbox or slider restarts a 200 ms debounce timer; on timeout a
  low-res preview sim fires (300 samples × 8 s of integrated time,
  ~50-100 ms wall-clock per Lorenz preview) and overlays the
  resulting attractor in the viewport. The preview pipeline is
  surgically separated from the full Run pipeline:
  ``_last_trajectory`` is NOT updated (exports, diagnostics,
  comparisons still reference the user's most recent explicit
  Run); no prerender; no autoplay. ``_fire_preview`` suppresses
  itself when a full Run is in flight; ``_cancel_preview_in_flight``
  disconnects the in-flight worker's signals so a stale result
  can't paint over a newer preview. Toggling the setting off
  drops any pending debounce + in-flight worker. Hooks live in
  ``_rebuild_for_current_system`` so a system flip re-wires the
  preview hooks correctly. 11 new tests pin the toggle, debounce,
  setting-off cancel, full-Run suppression, and the
  ``_last_trajectory``-stays-untouched contract. Commit ``1b131e2``.
- **D5 — recurrence plots + RQA scalars.** Three new modules, pure
  numpy compute, zero new runtime deps. ``core/recurrence.py``
  ships ``recurrence_matrix(trajectory, *, epsilon, norm, theiler)``
  → boolean ``(N, N)`` matrix, ``rqa(matrix, *, l_min, v_min)`` →
  ``RQAStats`` (RR / DET / LAM / L_max / V_max / L_mean / TT / ENTR
  per Marwan et al. 2007 §3), and ``suggest_epsilon(trajectory,
  fraction=0.1)`` — bbox-diagonal heuristic.
  ``visualization/recurrence_plot.py`` renders the matrix as a
  black-and-white image with an optional RQA-stats overlay
  (Tokyo Night dark mode by default, paper-mode toggle). ``gui/
  recurrence_panel.py`` wraps it in a ``RecurrencePanel`` (epsilon /
  l_min / v_min spinboxes, embedded ``FigureCanvasQTAgg``, initial
  render at suggested epsilon, recompute button) plus
  ``build_recurrence_dialog()``. Long trajectories are subsampled
  uniformly to ``_MAX_PLOT_N = 800`` so the panel stays interactive.
  Main window grows a single ``action_recurrence`` toolbar action,
  gated on having a trajectory (mirrors phase-portrait pattern).
  Signature observables: periodic unit circle (2 periods, 200
  samples) → DET > 0.95, LAM > 0.95, L_max > 150 (almost full
  diagonal stripe); IID Gaussian noise → DET < 0.35, L_max < 10
  (essentially no long structure). Exactly-periodic test
  (200 samples on exactly 2 periods, sample[i] = sample[i+100])
  → ENTR = 0 to machine precision (Marwan §3.5: "for periodic
  dynamics ENTR = 0"). 39 new tests across core/viz/GUI. Commit
  ``c9e3d3f``.
- **D4 — basin-of-attraction map.** The headline missing diagnostic;
  three new modules + a toolbar action. ``core/basins.py`` ships
  ``BasinDiagram`` dataclass + ``basin_diagram(rhs, *, x_axis, y_axis,
  attractors, fixed_state, n_grid, t_end, classify_tol, backend)``.
  Supervised classification: caller supplies the attractor centers,
  each grid orbit is assigned to the nearest one (or
  ``UNCLASSIFIED_LABEL = -1`` if the orbit hasn't converged).
  Backends: scipy (default — one ``solve_ivp`` per grid point) and
  jax (opt-in, uses I1's ``vmap_trajectories`` to fuse the whole
  grid into one XLA kernel). ``visualization/basin_plot.py`` renders
  the basin as an imshow with Tokyo-Night-aligned categorical palette,
  attractor-marker stars, and a legend. ``gui/basin_panel.py`` ships
  ``BasinPanel`` (preloaded with the canonical undriven double-well
  Duffing demo + ``_BasinWorker`` on a QThread with progress and
  cancel) plus ``build_basin_dialog``. Main window grows a single
  ``action_basins`` toolbar action. Reference observable: on a 32×32
  (x, v) grid in [-2, 2]², the undriven Duffing (alpha=-1, beta=1,
  delta=0.2) basin is ≥ 100 pixels per well, roughly symmetric
  (|n_left - n_right| < 25% of the grid), with < 25% unclassified.
  The signature low-energy observable: for ICs at rest with
  |x0| < √2 (below the saddle energy), sign(x0) determines the well
  — every test grid point passes. JAX-backend parity test (gated on
  [jax] extra): scipy and jax classifications agree on > 95% of
  pixels for a 16×16 grid. 27 new tests across core/viz/GUI.
  Commit ``ae79478``.
- **I1 — optional JAX / diffrax integrator backend.** New
  ``chaotic_systems.integrators.jax_backend`` module ships two
  ``Integrator``-protocol classes (``JaxRK45`` = diffrax Dopri5;
  ``JaxTsit5`` = diffrax Tsit5) and a ``vmap_trajectories(rhs,
  t_span, y0_batch, ...)`` helper that runs a batch of trajectories
  in one JIT-compiled XLA kernel — the prerequisite for D4 (basin-
  of-attraction map) and arbitrary parameter sweeps. JAX and
  diffrax are an **optional** ``[jax]`` extra in ``pyproject.toml``
  (``jax>=0.4.30``, ``diffrax>=0.6``); the module imports cleanly
  without them, raising ``ImportError`` with a ``pip install -e
  '.[jax]'`` hint only when ``integrate()`` is called.
  ``has_jax_backend()`` and a ``lorenz_jax_rhs()`` reference
  callable round out the public surface. Registered as
  ``"JAX-RK45"`` / ``"JAX-Tsit5"`` in the integrator registry.
  Reference observables: JAX-Tsit5 matches scipy DOP853 on Lorenz
  over t in [0, 5] to L2 endpoint error < 1e-3; ``vmap_trajectories``
  runs a 4-IC batch through Lorenz in a single vmapped call and
  recovers Lyapunov divergence (max pairwise separation > 1.0 at
  t = 10 starting from on-attractor ICs with offsets up to 1e-1).
  Side-effect at import: JAX 64-bit mode is enabled
  (``jax.config.update("jax_enable_x64", True)``) since float32 is
  unusable for chaotic-systems work at any meaningful tolerance.
  10 new tests, all gated on the ``[jax]`` extra so contributors
  without it see them as skips rather than failures. Commit
  ``3703bfb``.
- **V2 — side-by-side trajectory comparison (perturbed-IC overlay).**
  ``Renderer3D`` grows ``add_overlay_trajectory(traj, color, opacity)``
  and ``clear_overlays()`` — static secondary polylines that share
  the primary's plotter but have no head sphere and aren't driven by
  the animation loop. The Settings dropdown gains a checkable
  "Compare: perturbed initial condition" action; when on, the next
  Run integrates the same system twice (primary with the user's
  ``y0``, secondary with ``y0[0] += 1e-3``) and overlays the
  secondary on the primary's viewport in Tokyo Night red-pink. A
  status line surfaces the late-time L2 separation as a numerical
  observable ("Final separation: 17.86" or similar on Lorenz).
  Reference observable in the test suite: integrate Lorenz from an
  on-attractor IC vs ``y0[0] += 1e-3``, t=15 — separation > 5.0 (and
  early-time t=2 separation < 1.0, so the divergence is visually
  unambiguous on screen). Closes the V2 proposal; +15 tests covering
  the renderer-side overlay API + the GUI compare-setting wiring.
  Commit ``f9862b0``.
- **E1 — per-system educational notes.** Both ``DynamicalSystem``
  and ``DiscreteSystem`` gain an ``educational_notes: str`` class
  attribute (markdown). All 11 registered systems now ship
  ~25-line annotations citing canonical textbook references
  (Strogatz / Ott / Sprott / Lichtenberg-Lieberman / etc.), the
  chaotic-regime parameters worth trying, and what to watch for
  (period-doubling cascade in Duffing, KAM tori in the standard
  map, the (+, +, 0, -) Lyapunov signature in 4D Rössler, ...).
  The right-side Mathematics card grows a collapsible "Notes"
  section below the existing LaTeX panels — a ``QTextBrowser``
  driven by ``QTextBrowser.setMarkdown`` (Qt 5.14+, no new
  dependency). Notes re-render on system change via
  ``_set_educational_notes``; an empty-notes system shows a
  friendly placeholder. 30 new tests pin: every registered
  system has non-empty notes, each notes blob cites at least one
  canonical author from a literature whitelist, panel widget
  exists / is read-only / opens external links externally,
  panel refreshes on system change, markdown round-trips through
  ``setMarkdown`` into the plain-text view. Commit ``4a2a883``.
- **V1 — 2D phase-portrait panel.** Closes the longest-standing item
  on ``CONTEXT.md`` "What's next" (formerly #1). New
  ``visualization/phase_plot.py`` ships ``plot_phase_portrait(
  trajectory, ix, iy, ...)`` returning a matplotlib Figure with the
  ``y[:, ix]`` vs ``y[:, iy]`` projection (Agg-safe; Tokyo-Night
  facecolor aware; supports any ``state_dim >= 2``). New
  ``gui/phase_panel.py`` wraps that in ``PhasePanel`` with two
  axis combos, an "Equal aspect" toggle, a Plot button, and an
  embedded ``FigureCanvasQTAgg``; ``build_phase_dialog()`` packages
  it as a top-level window. Main window grows one
  ``action_phase_portrait`` toolbar action that grabs the current
  ``_last_trajectory`` and opens the dialog — gated on
  ``state_dim >= 2`` and on a simulation having run. Reference
  observable: harmonic oscillator (omega=1, IC (1, 0)) integrated
  with RK45 over 2 periods, ``max|sqrt(x^2 + v^2) - 1| < 5e-4`` —
  a unit circle to integrator tolerance, exactly Strogatz Fig 6.1.1.
  25 new tests. Commit ``f241284``.
- **D2 — bifurcation-diagram tool (discrete-map v1).** Three new
  modules, the headline pedagogical diagnostic added to the project.
  ``core/bifurcation.py`` ships ``bifurcation_diagram(system,
  param_name, param_values, n_record, n_transient, ...)`` returning a
  ``BifurcationDiagram`` dataclass; ``visualization/bifurcation_plot.py``
  renders it as a dense Feigenbaum-style scatter via matplotlib
  (Agg-safe for worker threads, Tokyo-Night palette aware); and
  ``gui/bifurcation_panel.py`` exposes ``BifurcationPanel`` (embedded
  ``FigureCanvasQTAgg`` + ``QThread`` worker with progress + cancel)
  plus ``build_bifurcation_dialog()`` that bundles a map picker over
  the four N1 maps. Main window grows a single ``action_bifurcation``
  toolbar QAction that opens the dialog. Numerical observables
  pinned: logistic fixed point ``1 - 1/r = 0.6`` at r=2.5 to 1e-10;
  period-2 cycle at r=3.2 hits Strogatz eq. 10.3.3 to 1e-6;
  period-4 at r=3.5; period-3 window at r=3.835; chaotic regime at
  r=3.9 has >50 distinct iterates. 29 new tests across core / viz /
  GUI. ODE-flow bifurcation via Poincaré sampling is documented as
  future work (it needs a separate "which plane / which projection"
  control surface). Commit ``73ce5e3``.
- **N1 — discrete-maps subsystem with logistic / Hénon / Ikeda /
  Chirikov standard map.** New ``DiscreteSystem`` base class lives
  alongside ``DynamicalSystem`` in ``core/discrete.py``; both expose
  a ``kind`` class attribute (``"ode"`` / ``"map"``) so the GUI can
  switch on the integrator-picker affordance. Four concrete maps
  ship under ``systems/{logistic,henon_map,ikeda,standard_map}.py``,
  each citing its canonical source (May 1976, Hénon 1976,
  Ikeda 1979, Chirikov 1979). Registry gains ``list_maps`` /
  ``get_map`` / ``list_all_systems`` / ``get_any_system``; the
  existing ``list_systems`` surface continues to return only
  ODE flows. Numerical observables pinned: logistic period-2 cycle
  at r=3.2 hits the analytic ``((r+1) ± √((r-3)(r+1)))/(2r)``
  points; Hénon Jacobian determinant equals ``-b`` to 1e-6;
  Ikeda Jacobian determinant equals ``u²`` everywhere (the
  ``t(x,y)`` dependence drops out); Chirikov ``det J = 1`` at
  every interior point and ``p`` is exactly conserved at K=0.
  33 new tests, all green. Commit ``e82d955``.

## Recently shipped (2026-05-16, capability roadmap rollout)

- **D1 — full Lyapunov spectrum in the GUI Diagnostics card.** The
  Benettin / continuous-QR ``lyapunov_spectrum`` compute existed in
  ``core/lyapunov.py`` since the initial implementation but was never
  surfaced. Now a "Diagnostics" card on the left panel runs the
  spectrum on a ``_LyapunovWorker`` thread and classifies the regime
  (Regular / Chaotic / Hyperchaotic). Verified on default Lorenz at
  +0.9032 / -0.0056 / -14.5643 (canonical: +0.9056 / 0 / -14.5723).
  Status-bar ``lyapunov_chip`` now mirrors λ_1. Commit ``b9780dd``.
- **N2 — 4D Rössler hyperchaos.** First system in the project with
  *two* positive Lyapunov exponents. Pairs with D1: select it, click
  Compute, and the GUI shows the canonical hyperchaotic (+, +, 0, -)
  signature directly. Measured spectrum
  ``+0.1188 / +0.0171 / -0.0019 / -21.1464`` matches Rössler 1979 and
  Stankevich & Wilczak 2015 within ~10% on the leading exponents.
- **Project-local scout agents + first capability roadmap.** Added
  ``.claude/agents/{ui-upgrade-scout,capability-research-scout}.md`` and
  the ``/milestone-pipeline`` slash command. First roadmap landed at
  ``docs/proposals/capability-roadmap-2026-05-17.md``; D1 and N2 are
  the first two items shipped from it.

## Recently shipped (2026-05-15, iteration 4 smoothness)

- **Catmull-Rom polyline + wall-clock pacing.** The animation now
  renders against a 4x-oversampled centripetal Catmull-Rom spline
  through the integration samples (built at prerender time, stored on
  ``Renderer3D._smooth_points``). The polyline body reads as a
  C^1-smooth curve instead of a chain of line segments — max
  per-segment angle drops from ~20 deg (visibly faceted) to ~5 deg
  on a default Lorenz playback. The GUI's animation tick is now
  *wall-clock paced*: each tick computes the target arc-length from
  ``time.perf_counter() - play_start``, so missed/dropped frames
  catch up on the next render instead of accumulating drift. See
  ``docs/animation_smoothness_iter4.md`` for the full investigation
  and ``tools/validate_smoothness.py`` for the A/B validator. New
  tests in ``tests/visualization/test_smoothness.py`` pin the
  spline math, the dense-buffer contract, and the 5 ms per-frame
  seek budget.

## Recently shipped (2026-05-15, after the param-form fix)

- **Prerender pipeline + loading bar.** A new ``_PrerenderWorker``
  warms ``Renderer3D``'s VTK pipeline and builds a cumulative
  arc-length table before user-visible playback. For trajectories ≥
  ``MainWindow._PRERENDER_MIN_FRAMES`` (500), the status bar shows
  "Preparing animation... X%" with a determinate progress pill while
  the worker runs. Playback then drives by *arc-length* (Manim
  ``point_from_proportion`` style) so chaotic stretches visit slowly
  visually and calm regions zip past at uniform visual speed.
  Renderer gained ``build_prerender_cache``, ``seek_arc_length``,
  ``has_prerender_cache``, ``total_arc_length``, ``_invalidate_cache``.
  Cache invalidates on ``set_line_width`` / ``set_color_by_progress``
  / re-attach. Cancellation precedence in the toolbar Cancel button is
  now export → prerender → sim. See ``docs/prerender_design.md`` for
  the prior-art research (ParaView Cinema, napari prefetching, Manim
  arc-length, VTK shader-cache warming) and design rationale.
- **Transport controls + scrubbing playback** in the GUI. The viewport
  now has a play / pause / stop / jump-to-end / speed / scrubber strip;
  pressing *Run* simulates, then plays the trajectory back at 1× from
  frame 0 instead of dumping a static polyline. Renderer gained
  `seek(index)`, `set_color_by_progress(bool)`, `head_position`,
  `n_frames`, `current_frame`. A single `QTimer` on the GUI thread
  ticks `Renderer3D.step()`; the per-tick stride scales with the speed
  preset so high speeds stay smooth without sub-10 ms timer noise.
  Shortcuts: Space (play/pause), Ctrl-. (stop), End (jump-to-end).
- **Flowing LaTeX panel.** The `_FlowingLatex` widget replaces the
  fixed-size `QLabel + QScrollArea` pattern; equations scale to the
  panel's current width via `Qt.SmoothTransformation` on the cached
  high-DPI pixmap (matplotlib is never re-invoked on resize). Multi-row
  aligned environments stack one row per equation, each scaling
  independently.
- Tests: `tests/visualization/test_animation.py` (renderer step/seek
  contract), `tests/gui/test_transport.py` (transport-control smoke
  tests, gated behind `CHAOTIC_GUI_TESTS_USE_DISPLAY=1`),
  `tests/gui/test_latex_wrap.py` (flowing LaTeX never overflows).

## Non-goals (for now)

- Web frontend. The decision to go native is explicit; do not reintroduce a browser-based UI.
- Distributed / GPU-accelerated simulation. The systems of interest are low-dimensional and CPU-bound integration is fine.
- Real-time interactive parameter tweaking with sub-millisecond latency. Smooth animation is enough.
- General-purpose ODE solver competing with `scipy.integrate.solve_ivp`. We use what `scipy` gives us where it makes sense, and only hand-roll integrators where it serves the pedagogical or symplectic goals.

## Open questions

- **Symbolic backend:** `sympy` is the symbolic engine for Lagrangians
  and LaTeX prettification. Parsing user-supplied expressions safely is
  still an open risk — see `SECURITY.md` and revisit when the GUI grows
  a "custom system" expression box.
- **Full LaTeX vs. mathtext.** Today we render via matplotlib mathtext,
  which covers the chaotic-systems case but not exotic typography. If
  the project grows to display textbook excerpts, an opt-in path via
  `matplotlib.rcParams["text.usetex"] = True` (requires a TeX install)
  is the natural escape hatch.

## Resolved decisions (2026-05-15)

- **GUI stack:** PySide6 + PyVista (via pyvistaqt) + matplotlib for
  LaTeX. The Tkinter and Dear PyGui alternatives are off the table.
- **3D rendering:** PyVista / VTK. matplotlib's `mpl_toolkits.mplot3d`
  is too slow once trajectories exceed a few thousand points.
- **Video export:** `imageio` with the `imageio-ffmpeg` plugin (it
  bundles a static ffmpeg, so users do not need a system install).
