# Chaos Indicator Suite — Diagnostics Card Section — 2026-05-20

## TL;DR

This proposal surfaces four already-shipped, already-tested scalar chaos indicators
(`chaos_zero_one_test`, `chaos_weighted_birkhoff`, `chaos_permutation_entropy`,
`chaos_hurst` — all live in `src/chaotic_systems/core/diagnostics.py`) into the
GUI's Diagnostics card via a single "Compute indicators" button backed by a new
`_ChaosIndicatorsWorker` QThread. The result is four chips (K, digit-loss, H_PE,
H_Hurst) plus a sampling-rate guard banner, completing the "Chaos Indicator Suite"
cluster the 2026-q2-broadening challenger explicitly earmarked for a single batched
section. One item, S effort. No new modules required; no existing module signatures
changed. The obvious first (and only) ship is CIS-1 below.

## Sequencing

| Order | Item | Effort | Why first / why not |
|---|---|---|---|
| 1 | CIS-1 — Chaos Indicator Suite Diagnostics-card section | S | the only item, ships on its own; all underlying functions and the worker pattern are already in the codebase |

## Items

### CIS-1 — Chaos Indicator Suite Diagnostics-card section

- **What:** Add a new expandable "Chaos Indicators" sub-section to the existing
  Diagnostics card in `main_window.py`, containing a single "Compute indicators"
  button, a `_ChaosIndicatorsWorker` QObject run on a `QThread`, and four result
  chips (K / digit-loss / H_PE / H_Hurst), plus a sampling-rate guard banner that
  warns when the trajectory's `dt` is likely causing the 0-1 test to underestimate K.

- **Where:**
  - `src/chaotic_systems/gui/main_window.py` — the Diagnostics card block starting
    at line 1655. The new `_ChaosIndicatorsWorker` class (≈ 60 lines) lives
    alongside `_LyapunovWorker` (currently defined at lines 1166–1278). The new
    UI widgets (`self.chaos_indicators_button`, `self.chaos_indicators_banner`,
    `self.chaos_indicators_result_label`) are added to `diag_layout` after
    `self.system_observables_label` (line 1713) and before
    `cards_layout.addWidget(diag_card)` (line 1714). Reset logic follows the same
    `hasattr` guard pattern used for `lyapunov_result_label` and
    `system_observables_label` in `_rebuild_for_current_system`.
  - `tests/gui/test_chaos_indicators.py` — new test module mirroring
    `tests/gui/test_lyapunov.py`. Reference observables: button exists with
    `objectName="button_chaos_indicators"`; after a mock worker signal, the result
    label populates with the four chip values; the sampling-rate banner appears when
    `dt` exceeds the Lorenz-natural-period threshold; system-switch resets the result
    label and hides the banner; worker dispatches to a `QThread` (not the GUI thread).
  - No changes to `src/chaotic_systems/core/diagnostics.py` — all four functions are
    consumed as-is via their default kwargs.

- **SOTA reference:**
  The proposal is a GUI wire-up; the mathematical SOTA is in the underlying
  implementations. Four primary citations (each already in `diagnostics.py`'s module
  docstring):
  1. **0-1 test (K):** G. A. Gottwald, I. Melbourne, *On the Implementation of the
     0-1 Test for Chaos*, SIAM J. Appl. Dyn. Sys. 8 (2009), 129-145.
     DOI: 10.1137/080718851. arXiv:0906.1418.
  2. **Weighted Birkhoff Average (digit-loss):** E. Sander & J. A. Yorke,
     *Connecting period-doubling cascades to chaos*, Int. J. Bifurc. Chaos 22
     (2012), 1250022; and S. Das et al., *Measuring quasiperiodicity*,
     Europhys. Lett. 114 (2016), 40005.
  3. **Permutation entropy (H_PE):** C. Bandt & B. Pompe, *Permutation entropy:
     A natural complexity measure for time series*, Phys. Rev. Lett. 88 (2002),
     174102.
  4. **Hurst exponent (H_Hurst):** H. E. Hurst, *Long-term storage capacity of
     reservoirs*, Trans. Am. Soc. Civil Eng. 116 (1951), 770-799; and J. Feder,
     *Fractals*, Plenum 1988, ch. 8.

- **Effort:** S. The worker pattern is established and can be templated directly
  from `_LyapunovWorker` (CSC-032). The four function calls are one-liners with
  default kwargs. The sampling-rate guard is a single conditional on
  `self._last_trajectory.dt` against the Lorenz natural-period heuristic — bounded
  in scope by the existing docstrings. Calibration: heavier than CSC-008 (XS,
  Kaplan-Yorke one-liner) and CSC-032 (XS, Quick λ₁ toggle) because of the new
  worker class + four chips + guard; lighter than CSC-029 (M, Poincaré panel with
  new module) because no new module is created.

- **Rationale:** All four indicators are pure-numpy, comprehensively tested (64
  tests across CSC-011/012/013/014), and carry documented reference observables —
  but they are currently invokable only from Python. GUI users cannot access them
  at all. This wire-up closes that gap with a single button click, following the
  same D1-class pattern (built-in-core, un-surfaced-in-GUI) as D1 (Lyapunov
  spectrum), CSC-008 (Kaplan-Yorke), and CSC-032 (Quick λ₁). The observable proving
  it works: with HenonHeiles at its canonical IC, after a Run and clicking "Compute
  indicators", all four chips populate within ~10 s with K (≈ 0 for regular orbits /
  ≈ 1 for chaotic), digit-loss (≈ 16 for regular / ≈ 1-3 for chaotic), H_PE
  (> 0.99 for chaotic), and H_Hurst (≈ 0.56 for memoryless signals) — all within
  the documented reference ranges from `diagnostics.py`.

- **Risks / open questions:**
  - ID `CIS-1` adopted from the sequencer to avoid collision with shipped `D2`
    (bifurcation diagram, commit `73ce5e3`, CONTEXT.md). The `CIS-` namespace is
    reserved for this and any follow-on Chaos Indicator Suite items; it does not
    consume a slot in the `D`-series (which has so far been reserved for diagnostics
    tools with significant new infrastructure: D1 = Lyapunov GUI surface, D2 =
    bifurcation diagram).
  - The 0-1 test and Hurst exponent are sampling-rate-sensitive; the proposed banner
    (`self.chaos_indicators_banner`) handles this for the most common oversampling
    case (Lorenz at `dt = 0.04`). A future item could extend the guard to
    system-specific Nyquist checks if sampling-rate awareness becomes a recurring
    user confusion vector.

## Rejected at drafting

- **`post_sim_diagnostics` hook surface** — the user brief explicitly contrasts this
  against the click-to-compute pattern. Running all four indicators on every Run
  would violate the 16 ms tick budget (CSC-033's hook runs synchronously on the
  simulation completion path). Not a CLAUDE.md lock violation but rejected on
  explicit brief instruction.
- **Dedicated panel (new module)** — a `chaotic_systems.gui.chaos_indicators_panel`
  module would follow the CSC-029 Poincaré-panel precedent but adds a new file for
  what the brief explicitly scopes as a Diagnostics-card sub-section at v1. Deferred
  if a future proposal wants to promote the suite to a standalone panel.
- **Command-palette secondary affordance** — the brief mentions a "Compute chaos
  indicators" command-palette entry as a secondary affordance. This is additive and
  can be bundled into the same item if `/milestone-pipeline` determines the
  `collect_actions` helper in `command_palette.py` picks up the QAction automatically
  (which it will, given the `findChildren(QAction)` pattern in FU-014). No separate
  item needed; the action is auto-discovered.

## Rejected at refinement

*(none — REDESIGN applied; no items dropped)*

## Reading order

A new contributor should:

1. Read the **Sequencing** table — one row, no dependencies.
2. Read the **CIS-1** entry end-to-end, then open
   `src/chaotic_systems/gui/main_window.py` at line 1655 (the Diagnostics card
   block) and `src/chaotic_systems/core/diagnostics.py` (the four functions to
   call).
3. Run `/milestone-pipeline CIS-1` to ship it.

`/milestone-pipeline` reads the same file: it parses the **Items** section to find
`CIS-1`, reads the W/W/S/E/R block, and proceeds.
