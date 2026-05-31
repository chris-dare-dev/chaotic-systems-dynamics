# Python-Only Pipeline Tooling — 2026-05-31

## TL;DR

This proposal eliminates the Bash dependency from all three agentic pipelines
(`capability-scout`, `draft-proposal`, `frontend-uplift`) so that `python` +
`git` are the only runtime requirements on any OS — including a vanilla Windows
box with no Git Bash or WSL. It contains 4 items (all mitigated, 0 dropped):
PT1 (foundational) adds a shared Python helper module and `init`/`status`
subcommands to each pipeline's `checkpoint.py`; PT2 ports
`ensure-gui-bootable.sh` to cross-platform Python; PT3 rewires in-repo
reference docs, error strings, AND the `.claude/commands/` slash-command
definitions from `bash …sh` to the new Python entrypoints; PT4 removes the
now-dead `.sh` files and closes out `PORTABILITY.md`'s "remaining cross-platform
ceiling" section. PT1 is foundational — every other item depends on it landing
first. Critique outcome: 0 BLOCKERs / 4 MAJORs (all addressed and mitigated
in the Items below).

## Provenance

Freeform brief originated from `.claude/scripts/PORTABILITY.md`'s "remaining
cross-platform ceiling" section (2026-05-31), which explicitly recommends porting
`init-*.sh` and `status.sh` to Python as the final step to make `python` + `git`
the sole runtime requirements on any OS. This proposal executes that
recommendation. No CSC source. Critique outcome: 0 BLOCKER / 4 MAJOR all
mitigated (0 dropped, 0 redesigned).

## Sequencing

| Order | Item | Effort | Why first / why not |
|---|---|---|---|
| 1 | PT1 — Shared Python helper + `init`/`status` subcommands | M–L (recommend splitting into PT1a/PT1b at ship time) | foundational; ≥3 items depend on these entrypoints existing; unblocks PT2, PT3, PT4 |
| 2 | PT2 — Port `ensure-gui-bootable.sh` to Python | S | foundational (PT3 + PT4 depend on it); only depends on PT1 shared helper; independent of PT3 scope |
| 3 | PT3 — Rewire in-repo references, error strings, and command definitions | S | depends on PT1 (entrypoints exist) and PT2 (ensure-gui reference is now a Python path); unblocks PT4 |
| 4 | PT4 — Remove dead `.sh` scripts + update PORTABILITY.md | S | LAST; depends on PT1 + PT2 + PT3 all landed; removing a script still referenced is broken |

## Items

### PT1 — Shared Python helper module + `init`/`status` subcommands

- **What:** Add `.claude/scripts/_pipeline_common.py` (shared repo-root, git-head,
  UTC, mkdir, and arg-parse helpers) and extend each pipeline's `checkpoint.py`
  with `init` and `status` subcommands, replacing the three `init-*.sh` and three
  `status.sh` files with pure-Python equivalents that reproduce their exact
  behavior on all platforms.

- **Where:**
  - New: `.claude/scripts/_pipeline_common.py`
  - Extended: `.claude/scripts/capability-scout/checkpoint.py`
  - Extended: `.claude/scripts/draft-proposal/checkpoint.py`
  - Extended: `.claude/scripts/frontend-uplift/checkpoint.py`
  - (The six `.sh` files listed in PT4 become dead code after this item lands;
    removal is deferred to PT4 to allow parallel testing.)

- **SOTA reference:** Python stdlib documentation:
  `argparse` (docs.python.org/3.12/library/argparse.html) for subcommand
  dispatch; `sys.executable` (docs.python.org/3.12/library/sys.html#sys.executable)
  as the cross-platform Python-interpreter self-reference replacing the
  `command -v python3 || command -v python` bash probe; `pathlib.Path.mkdir(parents=True,
  exist_ok=True)` replacing `mkdir -p`; `subprocess.run(["git", "rev-parse", "HEAD"])`
  replacing `git -C ... rev-parse` in shell; `datetime.now(timezone.utc)` for UTC
  stamping. In-repo authority: `.claude/scripts/PORTABILITY.md` §"The remaining
  cross-platform ceiling" (2026-05-31) explicitly recommends this exact port:
  "port `init-*.sh` and `status.sh` to Python … then the only runtime requirement
  on any OS is `python` + `git`."

- **Effort:** M–L (recommend splitting into PT1a/PT1b at ship time)

- **Rationale:** The six `.sh` files are thin wrappers whose real logic is already
  Python heredocs that shell out to Python for all state work — but the bash
  wrapper itself (`command -v`, `set -euo pipefail`, `source`, `heredoc`) is
  un-runnable on a native Windows box without Git Bash or WSL. Porting the thin
  wrapper to Python stdlib (`argparse`/`subprocess`/`pathlib`/`datetime`) eliminates
  the last POSIX-shell dependency from the pipeline tooling layer. The measurable
  observable: `python .claude/scripts/capability-scout/checkpoint.py init <ID>
  --brief "…"` followed by `… status <ID>` produces the same `state.json` schema
  keys (verified against `.claude/references/capability-scout/state-schema.md`) and
  the same human-readable status output — including phase-history elapsed deltas and
  the `→` arrow via the already-present `reconfigure(encoding="utf-8")` — as the
  old `.sh` did; and re-running `init` on an existing `state.json` prints the resume
  line and exits 0 (idempotent). The `draft-proposal` variant must additionally
  preserve: `init_head_sha` capture for the phase-5 rogue-commit guard; the
  `--from`/`--brief`/both-rejected mutual-exclusion; slug/date decomposition
  (currently done via `sed -E`). The `capability-scout` and `frontend-uplift`
  variants must preserve the `--brief`/`--lean`/`--deep` mode flags. No new
  third-party dependencies; no regression of the `encoding='utf-8'` or idempotent
  same-phase no-op semantics already in all three `checkpoint.py` files.

- **Risks / open questions:**

  1. **Effort recalibration — M hiding as L.** The combined deliverable is:
     (a) one new shared module (`_pipeline_common.py`), (b) three separate
     `checkpoint.py` extensions each requiring correct subcommand dispatch, plus
     (c) the `draft-proposal` variant must additionally handle `init_head_sha`
     capture via git, `--from`/`--brief` mutual-exclusion, and `sed -E` slug/date
     logic not present in the other two. An honest read puts PT1 on the heavy side
     of M — possibly L given the behavior-parity test requirement across three
     distinct state machines. **Recommendation for `/milestone-pipeline`: split
     PT1 into two increments at ship time — PT1a (shared `_pipeline_common.py`
     helper + `init` subcommand wired into all three `checkpoint.py` files, no
     parity tests yet) and PT1b (`status` subcommand for all three + full
     behavior-parity test suite). The proposal keeps PT1 as a single item for
     sequencing purposes, but the implementer should gate these increments
     separately to reduce regression surface per commit.**

  2. **Invasiveness regression-guard.** The three `checkpoint.py` files carry
     just-landed semantics that are easy to regress: (i) forward-only phase
     transitions (capability-scout lines 94-97; draft-proposal lines 126-128;
     frontend-uplift lines 89-92); (ii) idempotent same-phase no-op (capability-scout
     lines 86-93; draft-proposal lines 119-125; frontend-uplift lines 82-88);
     (iii) draft-proposal's recritique loop-back `LOOP_BACK_TRANSITIONS` +
     `MAX_CRITIQUE_CYCLES` guard (draft-proposal lines 55-58, 96-115);
     (iv) the `reconfigure(encoding="utf-8")` block present in all three files
     (lines 31-35 in each). Folding `init`/`status` subcommands into these files
     must NOT regress any of these. **Required behavior-parity check before merging
     PT1:** capture the current `.sh` `init`/`status` output as a golden fixture
     (run `init-*.sh <test-id> --brief "test"` and `status.sh <test-id>` for all
     three pipelines, save stdout + `state.json`), then assert byte/schema parity
     after the rewrite. The existing forward-only, backward-prevention, and
     same-phase no-op transition tests must stay green. The draft-proposal
     `MAX_CRITIQUE_CYCLES` guard and `LOOP_BACK_TRANSITIONS` dict must remain
     structurally intact after adding the new subcommand dispatch layer.

---

### PT2 — Port `ensure-gui-bootable.sh` to Python

- **What:** Replace `.claude/scripts/frontend-uplift/ensure-gui-bootable.sh` with
  a cross-platform Python script (`.claude/scripts/frontend-uplift/ensure_gui_bootable.py`)
  that locates the venv interpreter cross-platform, subprocess-runs the existing
  import and headless-construct probe, exits 0 on green and 1 on red, and preserves
  the human-facing recovery instructions on a missing venv.

- **Where:**
  - New: `.claude/scripts/frontend-uplift/ensure_gui_bootable.py`
  - (The old `.sh` becomes dead code; removal deferred to PT4.)

- **SOTA reference:** Python stdlib: `pathlib.Path` for cross-platform venv
  interpreter discovery (`.venv/bin/python` on POSIX vs `.venv/Scripts/python.exe`
  on Windows — documented at docs.python.org/3.12/library/venv.html §"Creating
  virtual environments"); `subprocess.run` for spawning the probe process in a
  clean interpreter context. The `source .venv/bin/activate` pattern in the
  current `.sh` is POSIX-only and the direct cause of the Windows breakage;
  the stdlib-only replacement avoids the activation step entirely by calling
  the venv interpreter binary directly, which is the recommended cross-platform
  pattern per PEP 405 (python.org/dev/peps/pep-0405/).

- **Effort:** S

- **Rationale:** `ensure-gui-bootable.sh` uses `source "$VENV/bin/activate"` — a
  bash-only construct that cannot run on native Windows — then delegates the actual
  probe to a Python snippet. Converting the wrapper to Python means: (a) detect the
  venv at `.venv/bin/python` (POSIX) or `.venv/Scripts/python.exe` (Windows) using
  `pathlib`; (b) if absent, print the recovery instructions (`python3.12 -m venv
  .venv && pip install -e ".[dev]"`) and exit 1; (c) otherwise `subprocess.run` the
  existing probe snippet against the venv interpreter and relay its exit code.
  The measurable observable: on a Windows machine with a valid venv the script exits
  0; with `.venv` absent it exits 1 with the recovery text; the probe logic is
  byte-identical to the shell script's embedded Python — no behavioral regression.
  No new dependencies.

- **Risks / open questions:**

  The Python probe must be tested on BOTH venv layouts: `.venv/bin/python` (POSIX)
  and `.venv/Scripts/python.exe` (Windows), returning exit 0 on green and exit 1 +
  recovery text when `.venv` is absent. The implementation must use `pathlib.Path`
  to detect which layout is present at runtime (not a platform conditional that
  could lie in cross-compiled or unusual environments). GUI-import probes are
  environment-flaky when no display is available (headless CI), so the probe must
  use the same offscreen/headless construction that the existing `.sh` version used
  (check the embedded Python snippet for the `QApplication` or offscreen attribute
  setup before porting) — do not introduce a display requirement that wasn't already
  there.

---

### PT3 — Rewire in-repo references, error strings, and command definitions

- **What:** Update the in-repo reference documents, `checkpoint.py`/`verify.py`
  error strings, AND the `.claude/commands/` slash-command definition files that
  currently cite `bash …sh` invocations to cite the new Python entrypoints; ship
  the exact `bash …sh` → `python …` command-mapping table in `PORTABILITY.md` so
  any remaining external caller (harness/plugin layer outside the repo) can apply
  the substitution.

- **Where:**
  - `.claude/references/frontend-uplift/phase-1-discover.md` line 23
    (`ensure-gui-bootable.sh` preflight code block) and line 86
    (`status.sh <ID>` recovery hint)
  - `.claude/references/capability-scout/phase-1-survey.md` line 79
    (`status.sh <ID>` recovery hint)
  - `.claude/references/capability-scout/state-schema.md` line 23
    (`init-capability-scout.sh` mention) and line 96 (`status.sh <ID>` mention)
  - `.claude/references/draft-proposal/state-schema.md` line 114
    (`status.sh <ID>` mention)
  - `.claude/scripts/capability-scout/checkpoint.py` line 61
    (`"init-capability-scout.sh first"` error string)
  - `.claude/scripts/frontend-uplift/checkpoint.py` line 59
    (`"init-frontend-uplift.sh first"` error string)
  - `.claude/scripts/draft-proposal/checkpoint.py` line 72
    (`"init-draft-proposal.sh first"` error string)
  - `.claude/scripts/draft-proposal/verify.py` line 58
    (`"Run init-draft-proposal.sh first"` error string)
  - `.claude/commands/capability-scout.md` (lines invoking `init-capability-scout.sh`
    and `status.sh`)
  - `.claude/commands/draft-proposal.md` (lines invoking `init-draft-proposal.sh`
    and `status.sh`)
  - `.claude/commands/frontend-uplift.md` (lines invoking `init-frontend-uplift.sh`,
    `status.sh`, and `ensure-gui-bootable.sh`)
  - `.claude/scripts/PORTABILITY.md` — append command-mapping table (old → new)

- **SOTA reference:** The in-repo authority for the exact old → new mapping is
  `.claude/scripts/PORTABILITY.md` §"The remaining cross-platform ceiling", which
  names the `bash .claude/scripts/.../foo.sh` invocation pattern as the sole
  remaining portability risk and specifies the replacement direction. No external
  citation required for a ref-doc rewire of internal tooling.

- **Effort:** S

- **Rationale:** After PT1 and PT2 land, the reference docs, error strings, and
  slash-command definitions that say "run `bash .claude/scripts/.../init-*.sh`" or
  "`status.sh <ID>`" will be stale. A contributor who reads `phase-1-discover.md`
  line 23 (the preflight code block), a checkpoint.py error message, or the
  `.claude/commands/draft-proposal.md` run instructions will encounter a command
  that won't work on Windows — or won't work at all after PT4 deletes the `.sh`
  files. The `.claude/commands/` directory is in-repo and versioned; its three
  files (`capability-scout.md`, `draft-proposal.md`, `frontend-uplift.md`)
  explicitly invoke the `.sh` scripts and must be updated in this item alongside
  the reference docs and error strings. The measurable observable:
  `grep -r "init-.*\.sh\|status\.sh\|ensure-gui-bootable\.sh" .claude/scripts
  .claude/references .claude/commands` finds no live invocations after this item
  (only the `PORTABILITY.md` historical record and the new command-mapping table
  added by this item).

- **Risks / open questions:**

  **External slash-command-body gap (residual risk after this item).** Although the
  `.claude/commands/` definition files are in-repo and will be updated by this item,
  the harness/plugin layer may inject additional slash-command bodies from outside
  the repo (e.g. a skill runner that wraps or overrides the in-repo command files).
  PT3 cannot update what it cannot see. To address this residual risk, PT3 must:
  (i) ship the exact command-mapping table in `PORTABILITY.md` — one row per
  replaced invocation, old `bash … .sh` form → new `python … checkpoint.py`/
  `ensure_gui_bootable.py` form — so whoever owns any external layer can apply the
  substitution mechanically; and (ii) include a note in `PORTABILITY.md` explicitly
  recommending that the external action be taken (update any harness or plugin body
  that wraps or re-emits the old `.sh` invocations) before PT4 ships. After PT4
  deletes the `.sh` files, any external caller still invoking them will break. This
  is a real residual risk, not a documentation formality — PT3's PORTABILITY.md
  table is the handoff artifact.

---

### PT4 — Remove dead `.sh` scripts and close PORTABILITY.md ceiling

- **What:** Delete the seven now-dead `.sh` scripts from `.claude/scripts/` and
  update `.claude/scripts/PORTABILITY.md` to mark the "remaining cross-platform
  ceiling" as removed, closing out the recommendation made in the 2026-05-31
  round-2 analysis.

- **Where:**
  - Delete: `.claude/scripts/capability-scout/init-capability-scout.sh`
  - Delete: `.claude/scripts/capability-scout/status.sh`
  - Delete: `.claude/scripts/draft-proposal/init-draft-proposal.sh`
  - Delete: `.claude/scripts/draft-proposal/status.sh`
  - Delete: `.claude/scripts/frontend-uplift/init-frontend-uplift.sh`
  - Delete: `.claude/scripts/frontend-uplift/status.sh`
  - Delete: `.claude/scripts/frontend-uplift/ensure-gui-bootable.sh`
  - Update: `.claude/scripts/PORTABILITY.md` — add a "Round 3" section marking
    the ceiling removed and noting the `*.sh eol=lf` rule in `.gitattributes`
    as now applicable only to any remaining `.sh` files (currently none under
    `.claude/scripts/`).

- **SOTA reference:** `.claude/scripts/PORTABILITY.md` §"The remaining
  cross-platform ceiling" (2026-05-31): "This is a larger change … left as a
  deliberate follow-up." This item is that follow-up. The in-repo `.gitattributes`
  (top-level, 2026-05-30 round 2) pinned `*.sh text eol=lf` — that rule becomes
  vacuously true under `.claude/scripts/` after deletion; the update notes this.

- **Effort:** S

- **Rationale:** Leaving the `.sh` files alongside the Python replacements creates
  a "which one is authoritative?" ambiguity for future contributors and preserves
  the bash dependency as an accidental import path. Deletion establishes a single
  source of truth. The measurable observable: `git ls-files .claude/scripts/` shows
  no `.sh` extension under that path; `grep -r "\.sh" .claude/scripts .claude/references`
  finds references only in the `PORTABILITY.md` historical record (the "Round 1 / 2
  / 3" narrative), not as live invocation commands. No new dependency; no behavioral
  change — all behaviors were replaced in PT1/PT2/PT3.

- **Risks / open questions:**

  **Pre-flight gate required before any deletion.** Before deleting any `.sh` file,
  run a grep gate confirming no live in-repo invocation remains:
  `grep -r "init-.*\.sh\|status\.sh\|ensure-gui-bootable\.sh" .claude/scripts
  .claude/references .claude/commands` must return zero matches outside the
  `PORTABILITY.md` historical record and command-mapping table. Only historical
  mentions in `PORTABILITY.md` are acceptable — any other live reference is a
  blocker that must be resolved before deletion proceeds. Deletion is contingent on
  PT1, PT2, and PT3 having all landed; the sequencing table encodes this as a hard
  prerequisite. Do not delete the `.sh` files in the same commit that adds their
  Python replacements — the intentional gap between PT1/PT2/PT3 landing and PT4
  shipping allows parallel smoke-testing of the Python entrypoints against the still-
  present `.sh` files before the old scripts are removed.

---

## Rejected at drafting

None — no item violates a hard rule at draft time.

## Rejected at refinement

None — all four items are disposition MITIGATE or PROCEED (0 BLOCKER, 0 REDESIGN,
4 MAJOR all addressed in the Risks sections above).

## Reading order

A new contributor should:

1. Read the **Sequencing** table — top to bottom.
2. Start with PT1 (foundational); every other item requires the Python entrypoints
   it creates. At ship time, consider splitting PT1 into PT1a (shared helper +
   `init` subcommand) and PT1b (`status` subcommand + parity tests) as noted in
   PT1's Risks section.
3. For each item, read its **Items** entry end-to-end before opening the target
   files.
4. Run `/milestone-pipeline PT1` to ship the foundational item first.

`/milestone-pipeline` reads this file: it parses the `## Items` section to find
the requested item ID, reads the What/Where/SOTA/Effort/Rationale block, and
proceeds.
