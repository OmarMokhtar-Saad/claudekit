---
description: "Write plan.md inline; --deep spawns the planner agent"
argument-hint: "[--deep] [task description]"
model: sonnet
---

# Planner Command

**Default: no spawn.** You — the parent session — write `.claude/plans/plan-<slug>.md`
yourself, from the context you already hold. A planner spawn pays a second full corpus load:
measured 2026-09-19, 98 turns average (worst 572 / 895 K) and 19 % of two days' token spend,
mostly re-reading files the parent had already read.

| Mode | What runs | When |
|---|---|---|
| default | you write the plan inline | you can name the files the change touches (Tier 1/2) |
| `--deep` | spawns the `planner` agent | the change spans unfamiliar subsystems, or you cannot name those files |

After approval the **main session implements the plan directly** (`/implement`). There is
no ops.json: the plan is the contract, and `plan-gate` binds Tier 3 edits to its `Files:`.

## Task

Create implementation plan for: $ARGUMENTS

If `$ARGUMENTS` begins with `--deep`, strip that flag from the task description and follow
the `--deep` section below. Otherwise write the file yourself, as follows.

**Headless (`claude -p`): mechanism B, always.** Without the Task tool this body cannot
be followed inline: measured on 2026-09-23, a headless `/plan` skipped the plan file and
implemented the task directly (7 turns, 36k avg context). If `Task` is not in your tool
list, skip the inline steps and run the bash block under "Mechanism B" regardless of
`--deep`. If Bash is unavailable as well, stop and print exactly this, then end the turn:
`/plan is interactive-only in this mode. Run: echo "<task>" | claude -p --agent planner --model opus --allowedTools "Read,Grep,Glob,Write" > .claude/plans/plan-<slug>.md`

## Default (no `--deep`) — you write the plan

1. Name every file the change touches. If you cannot, stop and re-run with `--deep`.
2. Write `.claude/plans/plan-<slug>.md` with:
   - a `Tier:` line (1, 2 or 3) and a `Files:` list naming **every path the change writes**
     (`plan-gate` enforces it for Tier 3; `scripts/check-plan-artifacts.py` checks the paths);
     no bare globs such as `*` or `**`
   - overview, implementation steps in execution order, a `## Validation commands` fenced
     block, a rollback plan, a risk assessment
3. Report the path, the tier and the file count — never the plan body; you just wrote it.

Tier 1 needs no plan file at all (edit directly). Tier 2 stops here (no reviewer). Tier 3
continues to `/review`, then user approval, then `/implement`.

## `--deep` — spawn the planner agent

Two mechanisms, both verified (see `.claude/agents/_shared/INVOCATION.md`, single source of
truth). Either way the delivery contract is PATHS + A SHORT SUMMARY, never file bodies.

### `--deep` mechanism A — interactive Task tool (preferred)

No cold boot; shares the session's MCP servers and permission gating.

1. Spawn with `subagent_type: "planner"` (model: opus) and the task/exploration instructions
   of `PLANNER_MSG` below, plus: "Write the plan to `.claude/plans/plan-<slug>.md` yourself
   using the Write tool. Return ONLY: the path, the tier, the file count and a ≤10-line
   summary — never the plan body."
2. Report the path and summary. Do NOT Read the file back into context unless the user asks
   to see it.

### `--deep` mechanism B — scripted (claude -p)

Pays ~13s cold boot per spawn. The headless planner cannot write into `.claude/**` (platform
sensitive-path gate, verified 2026-07-08), so its stdout is the delivery contract: the block
below stays SILENT except for the final summary — no `tee`, no echo of `plan_output`.

```bash
PLAN_FILE=".claude/plans/plan-$(date +%Y%m%d-%H%M%S).md"
mkdir -p .claude/plans

PLANNER_MSG="Create a complete implementation plan for the following task.

Task: $ARGUMENTS

Explore with BATCHED parallel Read/Grep/Glob calls — fire all independent searches in ONE
message. Open the plan with a 3-line summary: goal, approach, riskiest step.

The plan MUST carry a Tier: line and a Files: list naming every path the change writes."

plan_output=$(echo "$PLANNER_MSG" | claude -p --agent planner --model opus --allowedTools "Read,Grep,Glob,Write")
EXIT_CODE=$?
[ $EXIT_CODE -ne 0 ] && { echo "ERROR: planner failed (exit $EXIT_CODE) — check .claude/agents/planner.md"; exit 1; }

printf '%s\n' "$plan_output" > "$PLAN_FILE"
grep -qE '^\*{0,2}Files:' "$PLAN_FILE" \
  || { echo "ERROR: planner output has no Files: list — re-run /plan"; exit 1; }

printf '\nPlan saved to: %s\n\nSummary:\n' "$PLAN_FILE"
grep -v '^$' "$PLAN_FILE" | head -3
```

Final stdout ≤15 lines: path and the plan's first 3 non-blank lines.

After output, suggest:
- Tier 3: `/review` — single-pass review (auto-detects the saved plan file); once APPROVED and the user approves, run `/implement` from a compacted or fresh context whose only input is the plan path
- Tier 2: `/implement` directly
