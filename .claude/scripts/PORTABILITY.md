# Cross-platform portability of the pipeline scripts

Root-cause analysis and fixes for the instability observed running the
`/capability-scout` and `/draft-proposal` pipelines on Windows
(2026-05-30). Read this before adding or editing anything under
`.claude/scripts/`.

## TL;DR

The pipeline's own scripts had **one** genuine Windows-only defect: Python
scripts printed non-ASCII characters (`→` U+2192, `—` U+2014) to a console
whose default code page on Windows is **cp1252**, which cannot encode them.
That raised `UnicodeEncodeError` and the script exited non-zero **after** (or
partway through) mutating `state.json`, desyncing the pipeline state machine.
Two *other* instability sources seen during the same run were **not** caused by
these scripts and are documented below so they aren't misattributed.

## Symptom (reproduced)

```
$ python .claude/scripts/capability-scout/checkpoint.py <ID> survey-running
UnicodeEncodeError: 'charmap' codec can't encode character '→'
in position 31: character maps to <undefined>
```

The `--set` that ran in the same invocation *had already written* its field,
but the `advance` print crashed — so a field was set while the phase wasn't,
and the caller saw a non-zero exit and assumed total failure. Every
`checkpoint.py` advance, every `status.sh`, and the `verify.py` PASS/FAIL lines
were affected because they all print `→`/`—`.

## Root cause

CPython on Windows initializes `sys.stdout`/`sys.stderr` with the console's
**active code page** (cp1252 / "charmap"), not UTF-8, unless `PYTHONUTF8=1` or
`PYTHONIOENCODING=utf-8` is set in the environment. Linux/macOS default to
UTF-8, so the same code "works on my machine" there. The scripts also opened
`state.json` with the platform-default text encoding for read/write, which is
cp1252 on Windows — latent corruption risk for any non-ASCII state content.

This is the single most common Python cross-platform bug. It is **not** a
filesystem, path, or shell bug.

## Fix applied (all 10 scripts)

1. **Force UTF-8 on the std streams** at import time, before any printing:

   ```python
   for _stream in (sys.stdout, sys.stderr):
       try:
           _stream.reconfigure(encoding="utf-8")   # Python 3.7+
       except (AttributeError, ValueError):
           pass
   ```

   Applied to every `*.py` (`checkpoint.py` x3, `verify.py`) and to every
   embedded `python3 - <<'PY'` heredoc inside the `status.sh` scripts.

2. **Pin `encoding="utf-8"` on every file open** — `read_text`, `write_text`,
   and bare `open()` (including the heredocs in the `init-*.sh` and `status.sh`
   scripts):

   ```python
   json.loads(path.read_text(encoding="utf-8"))
   tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
   with open(tmp, "w", encoding="utf-8") as f: ...
   json.load(open(state_path, encoding="utf-8"))
   ```

### Verification (run on Windows with `PYTHONUTF8` and `PYTHONIOENCODING` unset)

- `python -m py_compile` of all 4 `.py` scripts -> OK.
- `status.sh` for a real state dir -> prints the `→` history cleanly, exit 0
  (previously crashed).
- `checkpoint.py <ID> <phase>` -> prints the `cur → new` line cleanly.
- `checkpoint.py --get` and `verify.py phase-4` run at exit 0 (PASS).
- All `.sh` scripts confirmed LF line endings (no CRLF hazard).

## Rule for future scripts (capability-scout, draft-proposal, frontend-uplift, and any new pipeline)

**Any Python that may print non-ASCII or touch a text file MUST:**
1. `reconfigure(encoding="utf-8")` on stdout/stderr at the top, AND
2. pass `encoding="utf-8"` to every `open`/`read_text`/`write_text`.

Cheaper alternative if you prefer no code change: keep all script *output*
strictly ASCII (`->` instead of `→`, `--` instead of `—`). The repo chose the
reconfigure approach so the human-readable arrows survive. Do not rely on
callers exporting `PYTHONUTF8=1`; the scripts must be correct unconditionally.

A pre-commit guard worth adding: grep new `.claude/scripts/**/*.py` for
`open(` / `read_text(` / `write_text(` without `encoding=` and fail.

## Two instability sources that were NOT these scripts (do not misattribute)

1. **Worktree sub-agent artifact loss.** Phase-1 scouts dispatched with
   `isolation: worktree` wrote their briefs to gitignored `.claude/notes/...`
   paths *inside the worktree*, which were removed when the worktree was
   cleaned up — so the briefs never appeared in the main tree. This is the
   documented D4 finding
   (`.claude/notes/draft-proposals/_adversary-review-2026-05-19.md`): worktree
   agents only reliably persist to **absolute parent-repo paths**.
   **Mitigation:** dispatch the brief-writing scouts WITHOUT worktree
   isolation, or instruct them to write to the absolute
   `{REPO_ROOT}/.claude/notes/...` path and have the orchestrator verify the
   file exists in the main tree before advancing state. This is platform-
   independent (affects Linux too) but compounded the confusion on this run.

2. **Harness tool-result replay / non-persisted writes.** Several large
   parallel tool batches returned stale or fabricated results, and some
   `Write`/`Edit` calls reported success without persisting. That is a
   transport/harness instability, not a repo bug, and is not fixable from
   inside the scripts. **Mitigation for operators:** keep tool batches small on
   Windows, and always re-read an artifact from disk (a fresh command) before
   trusting a write — `verify.py`'s "artefacts on disk, not state.json claims"
   philosophy is exactly the right instinct and should be applied at every
   phase boundary.

## Date-stamp note (minor, platform-independent)

`init-*.sh` stamps the run ID with **UTC** date. A late-evening local-time run
can land on the next UTC day (e.g. a 2026-05-30 evening run produced a
`-2026-05-31` ID). Not a bug, but expect the ID's date to be UTC, not local.

---

# Round 2 — re-running, the interpreter probe, and the "Cancelled" cascade

A second pass (2026-05-30) hardened the scripts further and analyzed the
`Cancelled: parallel tool call ... errored` failures.

## Additional script fixes applied (all verified on Windows, default env)

1. **Idempotent same-phase `advance`.** `checkpoint.py` previously exited
   non-zero on `refusing backward/same transition` when asked to advance to the
   phase it was already in. That meant a call whose **write landed but whose
   response was lost** (cancelled batch / flaky transport) could not be safely
   re-run — the re-run errored, which then cancelled the *next* batch. Now
   advancing to the current phase is an **exit-0 no-op** (`already at <phase>
   (no-op)`, no history entry appended). Genuine **backward** (`new < cur`) and
   **skipped** (`new > cur+1`) transitions still error. Applied to all three
   `checkpoint.py`.

2. **ASCII arrows in output.** `->` instead of `→` in the `checkpoint.py`
   transition messages, so the scripts are correct even if the
   `reconfigure(encoding="utf-8")` insurance (round 1) somehow fails on an
   exotic stream wrapper. (`draft-proposal/checkpoint.py` already did this; the
   other two now match.)

3. **Portable Python interpreter probe in every `.sh`.** Native Windows ships
   `python` (and the `py` launcher) but **not** `python3`; the shell scripts
   hardcoded `python3` in their heredocs and `-c` calls. Each script now begins
   with `PY="$(command -v python3 || command -v python || true)"` + an explicit
   "no interpreter found" error, and uses `"$PY"` everywhere. (It happened to
   work here because Git Bash provided a `python3` shim, but that is not
   guaranteed.)

4. **`.gitattributes` pinning `*.sh text eol=lf`.** A Windows clone with
   `core.autocrlf=true` would rewrite the shell scripts to CRLF, and a `\r` in
   the shebang makes bash fail with `bad interpreter`. The new top-level
   `.gitattributes` forces LF for `*.sh`/`*.py`/`*.md` and marks binary assets,
   so every checkout is byte-identical regardless of the contributor's git
   config.

## The `Cancelled: parallel tool call ... errored` cascade — root cause

**This is an orchestration artifact, not a script bug, and not OS-specific in
itself.** When several tool calls are issued in ONE assistant message (a
parallel batch) and **any one** of them errors, the harness **cancels the
sibling calls that have not yet completed** — they come back as
`Cancelled: parallel tool call ...`. A single failure therefore poisons the
whole batch.

Windows merely *triggered* it far more often, via two now-fixed sources:
- the `UnicodeEncodeError` crashes (round 1), and
- the `checkpoint.py` same-phase exit-1 on replay (fix #1 above).

With those fixed, a batch only cancels if a call *genuinely* fails. But the
cascade is structural, so the durable mitigation is **behavioral discipline in
the orchestrator (the agent driving the pipeline)**, not more script code:

### Orchestration rules (for any OS — apply when driving these pipelines)

- **Never batch dependent, state-mutating calls.** Do not put
  `checkpoint.py advance` and the follow-up `status.sh`/`--get` that reads the
  result in the same message. Mutate state in its own message, let it return,
  then read. A batch should contain only **independent** operations.
- **Keep parallel batches to read-only / independent work** (e.g. several
  `Read`s of different files, or dispatching N independent sub-agents). One
  failure there costs only that one call's result.
- **Re-read from disk before trusting any write.** This is exactly
  `verify.py`'s stated philosophy ("artefacts on disk, not state.json claims").
  After any write or advance, confirm with a fresh, single command before the
  next step — especially on a flaky transport where a success response may be
  dropped or a stale one replayed.
- **One state transition per message during `*-running` phases.** The state
  machine is forward-only and now idempotent, so a re-run is safe; a batch that
  bundles two transitions is not.

## The remaining cross-platform ceiling (recommended, not yet done)

The biggest portability dependency left is **bash itself**: `init-*.sh` and
`status.sh` are Bash scripts invoked as `bash .claude/scripts/.../foo.sh`. On a
vanilla Windows box **without Git Bash / WSL**, they will not run at all (the
pure-Python `checkpoint.py` / `verify.py` are unaffected — they run under
`python` directly). Bash was present in the environment where this was debugged,
so it was not the failure here, but it is the last "works only because a POSIX
shell happens to be installed" assumption.

**Recommended next step for true OS-independence:** port `init-*.sh` and
`status.sh` to Python (e.g. fold them into the existing `checkpoint.py` as
`init` / `status` subcommands, or add a sibling `pipeline.py`). Then the only
runtime requirement on any OS is `python` + `git`, with no shell dependency and
no heredoc/`command -v` portability surface. This is a larger change (it also
touches the three slash-command bodies that currently call `bash ...sh`) and is
left as a deliberate follow-up rather than bundled here.

