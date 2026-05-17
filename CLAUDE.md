# CLAUDE.md

Instructions for future Claude Code sessions working in this repository. Read this first; then read `CONTEXT.md` for current project state.

## Git workflow — the rule

**Commit and push directly to `main`. No feature branches. No pull requests. No MR flow.**

This repository is single-owner (Chris Dare) and is intentionally kept on a linear history on `main`. Branching adds ceremony with no review benefit at this scale.

Concretely:
- `git checkout -b feature/foo` — **do not do this**.
- `gh pr create` — **do not do this**.
- The flow is: edit → `git add` → `git commit` → `git push origin main`. That's it.

If a change feels big enough that you want a branch "for safety," it's probably a sign to discuss the design with Chris first rather than reflexively branching. Direct commits keep the history readable and force decisions to be deliberate.

## Commit messages

Conventional Commits. The subject line must match:

```
^(feat|fix|docs|style|refactor|test|chore|perf|ci|build|revert): .{1,50}
```

Examples:
- `feat: add Lorenz attractor with RK4 integrator`
- `fix: correct sign in double pendulum kinetic energy term`
- `docs: expand CONTEXT.md with Lyapunov estimation plan`
- `refactor: extract Integrator base class from RK4`
- `chore: initial repository scaffolding`

Every commit made by Claude should carry a `Co-Authored-By` trailer:

```
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Project layout

```
src/chaotic_systems/
├── core/            base classes (DynamicalSystem, Integrator) — the only place these live
├── systems/         one file per concrete system (lorenz.py, double_pendulum.py, ...)
├── integrators/     one file per integrator (rk4.py, rk45.py, verlet.py, ...)
├── visualization/   3D plotting, animation, video/GIF export
└── gui/             native desktop window
tests/               mirrors src/ layout
examples/            runnable example scripts
docs/                long-form docs
assets/              static assets; generated media goes under assets/generated/ (gitignored)
```

Tests live in `tests/`, mirroring the source layout. A change in `src/chaotic_systems/systems/lorenz.py` expects a corresponding `tests/systems/test_lorenz.py`.

## Python version and packaging

- **Python 3.12.** Pinned in `.python-version`. Do not introduce syntax or stdlib features that need a newer version without updating that file and `pyproject.toml`.
- **PEP 621 metadata in `pyproject.toml`.** No `setup.py`, no `setup.cfg`.
- **Use a venv.** `python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"` is the expected dev setup once `[dev]` extras land.

## The frontend is native — do not change that

The GUI is a **native desktop window** (PySide6 / Qt is the leading candidate, Dear PyGui and Tkinter are alternatives). It is not a browser tab.

**Do not introduce:**
- Electron
- Tauri (it's lighter, but still web-rendered)
- Flask / FastAPI / Django serving an HTML frontend
- React / Vue / Svelte
- Any "open the browser to localhost:something" UX

If you find yourself reaching for a web framework to render the UI, stop and re-read this section. The reason for the constraint is in `CONTEXT.md`: the project is meant to feel like a native scientific tool, not a webapp.

A future *remote rendering* server (out of scope today) would be a separate component with its own threat model — that is not what the GUI is.

## Keeping CONTEXT.md current

`CONTEXT.md` is a living document. Update it when:
- The project's direction changes (e.g. we pick PySide6, we drop a planned system, we add Floquet analysis).
- A milestone lands (e.g. first end-to-end Lorenz + RK4 + 3D plot working).
- "Open questions" get answered.
- "Non-goals" get reconsidered.

It is fine — expected, even — for a commit to update `CONTEXT.md` alongside the code change that motivated the update. Don't let `CONTEXT.md` drift; it is the file the next session will rely on.

## Style / linting

To be filled in when dev dependencies land. The expected stack is:
- **ruff** for linting and formatting.
- **mypy** in `--strict` mode for typing on `src/`.
- **pytest** for tests.

Until those are configured, follow PEP 8 and use type hints on every public function signature.

## Project-local agents

`.claude/agents/` ships reusable Claude Code agents scoped to this
project. Two today:

- `ui-upgrade-scout` — outside-in evaluation of the GUI plus 2025-2026
  web research; writes a proposal to `docs/proposals/ui-upgrade-<date>.md`.
- `capability-research-scout` — catalog of current systems / integrators
  / diagnostics plus SOTA research; writes
  `docs/proposals/capability-roadmap-<date>.md`.

Both are read-only — they propose, they don't ship. See
`.claude/agents/README.md` for invocation and the convention for adding
new agents.

## Mathematical correctness

This is a math project. Get the math right.

- Cite the source for any non-trivial system or integrator (textbook + section, or paper).
- When a system has a known conserved quantity (energy, angular momentum), tests should verify it is approximately preserved over the integration window for the appropriate integrator.
- Avoid silent floating-point assumptions. If the math says "this is a small perturbation," document the bound.
- Prefer named constants over magic numbers, especially for canonical parameter values (e.g. Lorenz $\sigma=10, \rho=28, \beta=8/3$).
