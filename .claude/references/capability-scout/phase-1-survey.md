# Phase 1 — Survey

## Purpose

Fan out N specialized sub-agents in parallel to surface candidates from
independent lenses. Each agent writes a structured brief into
`.claude/notes/capability-scouts/<ID>/survey-briefs/`.

## Inputs

- `state.json` field `capability_scout_brief` — the user-supplied scope.
- `state.json` field `survey_mode` — `standard` (4 agents) /
  `lean` (3 agents) / `deep` (4 agents, opus-bumped adversary).
- Curated sources at `.claude/references/capability-scout/source-registry.md`.
- Canonical prompts at `.claude/references/capability-scout/agent-prompts.md`.

## Output

One brief per agent under
`.claude/notes/capability-scouts/<ID>/survey-briefs/<agent-name>-brief.md`.

## Dispatch matrix

| Mode | Agents dispatched | Notes |
|---|---|---|
| `standard` | competitive + academic + oss + internal-adversary | Default. 4 agents, sonnet, worktree-isolated. |
| `lean` | competitive + oss + internal-adversary | Drop academic for fast-turnaround scans. |
| `deep` | competitive + academic + oss + internal-adversary (opus) | Same 4 agents; bump the adversary to opus when scope is wide. |

## Dispatch protocol — ONE assistant turn

**Critical**: all N agents must be dispatched in a SINGLE assistant
turn containing N parallel `Agent` tool blocks. Sequential dispatch
defeats the parallelism and roughly doubles wall-clock.

Each `Agent` call uses:
- `subagent_type: general-purpose` (the harness's agent list locks at
  session start; project-local agents `.claude/agents/capability-scout-*`
  may not be visible mid-session)
- `model: sonnet` (default; `--deep` bumps the adversary to opus)
- `isolation: worktree` (each agent gets an isolated git worktree)
- Prompt verbatim from `.claude/references/capability-scout/agent-prompts.md`,
  with `{ID}` / `{BRIEF}` / `{BRIEF_PATH}` substituted.

After dispatching, append each agent name to `agents_dispatched` via
`checkpoint.py --append` and advance to `survey-running`.

## As briefs return

For each agent that returns:
1. Read the agent's reply (it should include the brief path + a
   3-line summary).
2. Verify the brief file exists at the expected path.
3. `checkpoint.py <ID> --append agents_returned='"<agent-name>"'`
4. `checkpoint.py <ID> --append survey_briefs='"<path>"'`

When `agents_returned == agents_dispatched` (set equality), advance
to `survey-complete`.

## Hard rules

- **One assistant turn for the entire dispatch.** Do not fire one
  agent, wait, fire another — that's sequential.
- **Each agent's prompt is the canonical version from
  `agent-prompts.md`**. Do not paraphrase. Substitute placeholders only.
- **No code from any agent.** They write briefs.
- **Sub-agents cannot spawn sub-agents.** If a brief proposes
  "investigate further with another agent", that's a synthesis-time
  concern, not a Phase 1 concern.

## Failure modes + recovery

| Failure | Recovery |
|---|---|
| Agent returns without a brief file | Re-dispatch that single agent with the same prompt. Mark it `dispatched` again. |
| Agent's brief is empty or malformed | Same — re-dispatch. |
| Agent's brief proposes web/Electron/etc. | Surface in synthesis as "rejected by Phase 1 hard rule". Do not block. |
| All agents return but you suspect bias toward one lens | OK to dispatch a fifth ad-hoc agent in `--deep` mode. |
| Session compacts mid-Phase-1 | `checkpoint.py status <ID>` shows what's dispatched-but-not-returned. Resume by checking each pending agent's worktree for an emitted brief; if none, re-dispatch. |

## Anti-patterns

- **Synthesizing while Phase 1 is still running.** The synthesizer
  needs all briefs in working memory simultaneously. Wait for all
  agents.
- **Letting one agent dominate the agenda.** If one brief has 30
  candidates and another has 3, the synthesizer should weight by
  evidence quality, not by candidate count. Surface this calibration
  concern in synthesis if you see it.
- **Skipping the internal-adversary.** It's the single most
  load-bearing agent because it surfaces "already built but
  un-exposed" candidates — the D1-class wins.
