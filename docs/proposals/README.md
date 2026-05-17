# Proposals

Time-stamped output of the project-local scout agents
(`.claude/agents/`). Each file represents one outside-in evaluation
round.

## Conventions

- File name: `<agent-domain>-<YYYY-MM-DD>.md` — e.g.
  `ui-upgrade-2026-05-17.md`, `capability-roadmap-2026-05-17.md`.
- Newer proposals build on older ones; don't delete the old files.
  They document the historical reasoning for what got shipped vs.
  rejected.
- A proposal becoming reality is tracked in `CONTEXT.md` (under
  "Recently shipped") and in commit messages, not by deleting the
  proposal.

## Reading order for a new contributor

1. The most recent UI proposal.
2. The most recent capability roadmap.
3. `CONTEXT.md` to see which proposed items have already shipped.
