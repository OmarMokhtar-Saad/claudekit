---
description: "Create implementation plan via planner agent and save to .claude/plans/"
argument-hint: "[task description]"
model: sonnet
---

# Planner Command

Runs the local `planner` agent via `claude -p --agent planner`.
Verified mechanism: `--agent <name>` loads `.claude/agents/<name>.md` as system prompt.
Canonical spawn contract: see `.claude/agents/_shared/INVOCATION.md` (single source of truth).

## Task

Create implementation plan for: $ARGUMENTS

## Invocation

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
echo ""
echo "Plan saved to: $PLAN_FILE"
```

After output, suggest:
- `/refine "$ARGUMENTS"` — automatic iterative plan-review loop until score ≥ 90
- `/review` — single-pass review (auto-detects the saved plan file)
