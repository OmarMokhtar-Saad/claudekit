---
description: "Create implementation plan via planner agent and save to .claude/plans/"
argument-hint: "[task description]"
model: sonnet
---

# Planner Command

Spawns the local `planner` agent. Two verified mechanisms (see
`.claude/agents/_shared/INVOCATION.md`, single source of truth):

- **Interactive session (default): Task tool**, `subagent_type: "planner"` — no cold boot,
  shares the session's MCP servers and permission gating.
- **Scripted/CI: `claude -p --agent planner`** — pays ~13s cold boot per spawn.

Either way the DELIVERY CONTRACT is the same: the planner returns the plan document and the
complete ops.json in its response (headless spawns cannot write into `.claude/**` — platform
sensitive-path gate); this command saves and validates them.

## Task

Create implementation plan for: $ARGUMENTS

## Invocation — interactive (default)

1. Spawn via the Task tool with `subagent_type: "planner"` (model: opus) and the same
   message as `PLANNER_MSG` below, plus: "Return the complete plan document and ops.json
   in your final response."
2. Save the returned plan to `.claude/plans/plan-<slug>.md` and extract + validate the ops
   config exactly as the post-processing block below does.

## Invocation — scripted (claude -p)

Use the Bash tool to run:

```bash
PLAN_FILE=".claude/plans/plan-$(date +%Y%m%d-%H%M%S).md"
mkdir -p .claude/plans

PLANNER_MSG="Create a complete implementation plan for the following task.

Task: $ARGUMENTS

Before writing anything, explore the codebase with BATCHED parallel Read/Grep/Glob calls —
fire all independent searches in ONE message; do not serialize independent lookups.
Open the plan with a 3-line summary: goal, approach, riskiest step.

IRON LAW: The plan MUST include a valid ops.json."

plan_output=$(echo "$PLANNER_MSG" | claude -p --agent planner --model opus --allowedTools "Read,Grep,Glob,Write,Bash(python3 .claude/operations/scripts/validate-config-json.py *)")
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
  echo "ERROR: Planner agent failed (exit code $EXIT_CODE). Check that .claude/agents/planner.md exists."
  exit 1
fi

echo "$plan_output" | tee "$PLAN_FILE"

# The planner cannot write into .claude/ itself when spawned headless (sensitive-path
# gate, verified 2026-07-08) — its stdout is the delivery contract. Extract the ops.json
# it emitted and validate it.
OPS_FILE="${PLAN_FILE%.md}.ops.json"
python3 .claude/operations/scripts/extract-json-from-plan.py "$PLAN_FILE" --output "$OPS_FILE" \
  && python3 .claude/operations/scripts/validate-config-json.py "$OPS_FILE" \
  || { echo "ERROR: no valid ops.json in planner output — IRON LAW violated, re-run /plan"; exit 1; }

echo ""
echo "Plan saved to: $PLAN_FILE"
echo "Ops config:    $OPS_FILE (validated)"
```

After output, suggest:
- `/refine "$ARGUMENTS"` — automatic iterative plan-review loop until score ≥ 90
- `/review` — single-pass review (auto-detects the saved plan file)
