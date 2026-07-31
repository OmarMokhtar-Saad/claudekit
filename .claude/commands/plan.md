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

DELIVERY CONTRACT differs by mechanism — paths and summaries reach the main context, never
full file bodies:
- **Interactive:** the planner writes `.claude/plans/plan-<slug>.md` and
  `.claude/plans/ops-<slug>.json` itself (nothing blocks this — see below) and returns only
  paths + a short summary.
- **Headless (`claude -p`):** the platform's sensitive-path gate blocks writes into
  `.claude/**`, so stdout is the delivery contract; this command captures it SILENTLY
  (no `tee`) and writes it to disk itself, then reports only paths + a short summary.

## Task

Create implementation plan for: $ARGUMENTS

## Invocation — interactive (default)

**Delivery contract: paths, never payloads** — an interactive Task-subagent shares this
session's hooks/permissions, and `.claude/plans/` is not blocked by any of them
(`ops-enforcement.sh` allows all of `.claude/**`; `config-protection.sh` only matches
linter/formatter filenames; `file-guard-gate.sh` is advisory-only and `strict`-profile
gated — verified by reading all three, 2026-07-31). So the planner writes its own files;
the main agent never re-types or Reads back the plan body.

1. Spawn via the Task tool with `subagent_type: "planner"` (model: opus) and the same
   task/exploration instructions as `PLANNER_MSG` below, plus: "Write the plan to
   `.claude/plans/plan-<slug>.md` and the ops config to `.claude/plans/ops-<slug>.json`
   yourself using the Write tool. Run `python3 .claude/operations/scripts/validate-config-json.py
   <ops-file>` and include its verdict. Return ONLY: both file paths, the validation
   verdict, the op count, and a ≤10-line plan summary — do NOT print the plan body or the
   ops.json contents in your response."
2. Main agent re-runs `python3 .claude/operations/scripts/validate-config-json.py <ops-file>`
   once (trust but verify) and reports the paths + verdict. Do NOT Read the plan or ops
   file back into context unless the user explicitly asks to see them.

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

printf '%s\n' "$plan_output" > "$PLAN_FILE"

# The planner cannot write into .claude/ itself when spawned headless (sensitive-path
# gate, verified 2026-07-08) — its stdout is the delivery contract. Extract the ops.json
# it emitted and validate it. Everything in this block stays SILENT except the final
# summary — no `tee`, no echoing plan_output — so the full payload never lands in the
# main session's context as a Bash tool result.
OPS_FILE="${PLAN_FILE%.md}.ops.json"
python3 .claude/operations/scripts/extract-json-from-plan.py "$PLAN_FILE" --output "$OPS_FILE" \
  && python3 .claude/operations/scripts/validate-config-json.py "$OPS_FILE" > /tmp/plan-validate.$$ 2>&1 \
  || { echo "ERROR: no valid ops.json in planner output — IRON LAW violated, re-run /plan"; exit 1; }

OP_COUNT=$(python3 -c "import json; print(len(json.load(open('$OPS_FILE')).get('operations', [])))" 2>/dev/null || echo "?")
VERDICT=$(grep -m1 '^-> ' /tmp/plan-validate.$$ 2>/dev/null | sed 's/^-> //')
[ -z "$VERDICT" ] && VERDICT="validated"
rm -f /tmp/plan-validate.$$

echo ""
echo "Plan saved to: $PLAN_FILE"
echo "Ops config:    $OPS_FILE ($VERDICT, $OP_COUNT ops)"
echo ""
echo "Summary (first 3 lines):"
grep -v '^$' "$PLAN_FILE" | head -3
```

Final stdout of this block must stay ≤15 lines total: paths, op count, validation verdict,
and the plan's first 3 non-blank lines — never the full plan body or ops.json contents.

After output, suggest:
- `/refine "$ARGUMENTS"` — automatic iterative plan-review loop until score ≥ 90
- `/review` — single-pass review (auto-detects the saved plan file)
