---
description: Ship a single proposal item from docs/proposals/ end-to-end — implement, test, lint, commit, push, update CONTEXT.md. Argument is the proposal ID (e.g. N2, D1, V3) or proposal ID plus a roadmap filename.
argument-hint: <proposal-id> [roadmap-file]
allowed-tools: Bash, Read, Edit, Write, Glob, Grep
---

You are executing the end-to-end milestone-shipping pipeline for the
`chaotic-systems-dynamics` project. The argument is a proposal ID
($1, e.g. `N2`, `D1`, `V3`); optional second argument is a specific
roadmap file ($2). If $2 is omitted, use the most recent
`docs/proposals/capability-roadmap-*.md` or `docs/proposals/ui-upgrade-*.md`
that contains the proposal ID.

## Pipeline phases

### Phase 1 — Locate and read the proposal

1. `git log --oneline -15` so you know what's already shipped.
2. `ls docs/proposals/` — find the candidate roadmap files.
3. Read the proposal section for $1. Capture:
   - **What** to add
   - **Where** to put it (target file paths)
   - **SOTA reference** (cite this in code + commit)
   - **Effort estimate** (S / M / L) — calibrates how much you build
   - **Rationale** — informs the commit message

If $1 is ambiguous (matches multiple proposals) or absent from the
listed roadmap, STOP and ask the user to disambiguate before writing
any code.

### Phase 2 — Implement

Follow the existing project patterns *exactly*:

- New systems live under `src/chaotic_systems/systems/<name>.py`,
  inherit `DynamicalSystem`, are registered in
  `src/chaotic_systems/systems/registry.py` (or via the
  registry's auto-discovery if used).
- New integrators live under
  `src/chaotic_systems/integrators/<name>.py` and are registered
  in `integrators/__init__.py:_REGISTRY`.
- New diagnostics live under `src/chaotic_systems/core/<name>.py`.
- New GUI panels live under `src/chaotic_systems/gui/`.
- All public symbols typed (PEP 612 / 3.12 syntax: `list[int]`,
  `X | None`).
- Module docstrings cite the SOTA reference verbatim.
- Cite canonical parameter values as named constants, not magic
  numbers (see `CLAUDE.md` Mathematical correctness section).

### Phase 3 — Test

Mirror the source layout under `tests/`. Cover:

- Sanity: object constructs, RHS at the canonical IC returns finite values.
- Numerical correctness: at least one observable that's known from
  the cited reference (e.g. a conserved quantity, a Lyapunov
  spectrum signature, a fixed-point location).
- Edge cases that match the new code's branches.

Run `CHAOTIC_GUI_TESTS_USE_DISPLAY=1 pytest tests/ --tb=line` and
`ruff check src/ tests/`. Both must be clean. If a test fails, fix it
before moving on — don't ship red.

### Phase 4 — Update CONTEXT.md

The `Recently shipped` section gets a one-line entry mentioning the
proposal ID, what landed, and the commit SHA (which you'll know
after Phase 5; come back and patch the SHA in). If the proposal was
listed under `What's next`, remove it there.

### Phase 5 — Commit + push

One commit. Conventional Commits subject. Body explains: what
shipped, which proposal ID it closes, what was measured (numerical
results, test count delta, performance numbers if applicable),
where the SOTA reference lives in the code.

```
git add <touched files>
git commit -F /tmp/commit_msg.txt
git push origin main
```

Per `CLAUDE.md`: direct-to-main only, no feature branches. If the
harness's auto-mode classifier blocks the push, leave the commit
local and surface the block in your report. Do NOT silently fall
back to a feature branch.

### Phase 6 — Final report

Return to the user (under 250 words):
- Commit SHA + push status.
- What numerical observable proves it works.
- Test count before / after.
- Files added / modified.
- Pointer to the next milestone in the roadmap's sequencing table.

## Constraints

- Native PySide6 only. No web frameworks. (See `CLAUDE.md`.)
- Python 3.12, ruff-clean, no emojis.
- Don't add Julia / Rust / C++ dependencies that require user-side
  compilation.
- One milestone per invocation. If the proposal is L-sized and you
  can't ship it cleanly in one pass, STOP after Phase 1 and ask
  the user to either split it or invoke a longer-running agent.
- Don't edit any file the proposal doesn't authorize touching.

## What you must NOT do

- Don't ship multiple proposals at once unless they're explicitly
  bundled in the roadmap's sequencing.
- Don't create a feature branch. Direct commit to `main`.
- Don't skip the CONTEXT.md update — the next session needs it.
- Don't ship without measuring at least one observable.
