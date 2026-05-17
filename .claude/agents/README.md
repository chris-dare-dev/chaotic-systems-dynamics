# Project-local Claude Code agents

Reusable agent definitions for `chaotic-systems-dynamics`. These let any
Claude Code session invoke a long, repo-aware brief by short name
instead of re-typing a 600-line prompt every time.

## Inventory

| Agent | Purpose | Output |
|---|---|---|
| `ui-upgrade-scout` | Evaluate the current PySide6 GUI, research 2025-2026 desktop scientific tool patterns online, propose concrete improvements. | `docs/proposals/ui-upgrade-<date>.md` |
| `capability-research-scout` | Catalog current systems/integrators/diagnostics, research SOTA in chaotic dynamics + numerics, propose new directions (new systems, GPU paths, novel analyses). | `docs/proposals/capability-roadmap-<date>.md` |

Both agents are **read-only**: they propose, they do not ship. Once a
proposal lands, dispatch a separate implementation agent (or just do
the work yourself) against it.

## How to invoke

**In a fresh Claude Code session** (CLI or IDE integration), these
agents are auto-discovered from `.claude/agents/` at session start and
appear in the agent list. Invoke via the `Agent` tool with
`subagent_type: "ui-upgrade-scout"` (or the other name) and a brief
task description; the agent's full brief lives in the file.

**Mid-session limitation.** If you add or modify an agent definition
during a running session, the harness's `Agent` tool will NOT see the
new definition — the agent list is locked at session start. Workaround:
dispatch via `subagent_type: "general-purpose"` and put `"You are
acting as the <name> agent defined at .claude/agents/<name>.md — read
that file first and follow it exactly"` at the top of the prompt.
Restart the session to get the auto-discovered path back.

## Why this pattern

Every prior round of UI critique / capability research in this repo
was a one-shot inline prompt that was lost after the agent finished.
By persisting the agent definitions here:

- Future sessions reuse the same vocabulary and evaluation axes.
- Proposals accumulate as a time-stamped record in `docs/proposals/`.
- The "what does this project look like to an outside expert" lens is
  one slash command away rather than a fresh hour of prompt-writing.

## When to add a new agent

Add a new agent here when you find yourself writing the same long
brief twice. Single-shot work stays inline. The bar for adding a
persistent agent is "I expect to invoke this 3+ times over the
project's life."
