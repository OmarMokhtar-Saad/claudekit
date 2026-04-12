---
description: "Start an autonomous agent loop monitored by loop-operator. The operator watches for stagnation, escalates on destructive behavior, and reports when the loop terminates."
argument-hint: "<task> [--agent <name>] [--max-iter N] [--stall-after N]"
model: sonnet
---

# Loop Start Command

Starts an autonomous agent loop with the `loop-operator` agent watching in the background. The operator detects stagnation (same output repeated, no file changes, growing errors) and escalates to human review before the loop goes off the rails.

## Mandatory Skills

- **using-superpowers** - Core capabilities
- **autonomous-loop** - Autonomous execution with checkpoints
- **verification-loop** - 6-phase quality gate
- **verification-before-completion** - Never claim done without evidence

## Task

Start autonomous loop: $ARGUMENTS

---

## Execution Steps

### Step 1: Parse Options

```bash
ARGS="$ARGUMENTS"
MAX_ITER=10
STALL_AFTER=3
AGENT="implementer"

if echo "$ARGS" | grep -q '\-\-max-iter'; then
    MAX_ITER=$(echo "$ARGS" | grep -oE '\-\-max-iter\s+[0-9]+' | grep -oE '[0-9]+')
fi

if echo "$ARGS" | grep -q '\-\-stall-after'; then
    STALL_AFTER=$(echo "$ARGS" | grep -oE '\-\-stall-after\s+[0-9]+' | grep -oE '[0-9]+')
fi

if echo "$ARGS" | grep -q '\-\-agent'; then
    AGENT=$(echo "$ARGS" | grep -oE '\-\-agent\s+\S+' | awk '{print $2}')
fi

TASK=$(echo "$ARGS" | sed 's/--max-iter\s\+[0-9]\+//; s/--stall-after\s\+[0-9]\+//; s/--agent\s\+\S\+//' | xargs)

echo "Task: $TASK"
echo "Agent: $AGENT | Max iterations: $MAX_ITER | Stall detection: $STALL_AFTER"
```

### Step 2: Pre-Loop Baseline

```bash
# Capture baseline state for stagnation detection
git stash list | head -3
git status --short | wc -l
git rev-parse HEAD
```

### Step 3: Brief the Loop Operator

The `loop-operator` agent monitors the loop. Brief it with:

```
Task: <TASK>
Worker agent: <AGENT>
Max iterations: <MAX_ITER>
Stall detection: flag stagnation after <STALL_AFTER> iterations with no progress

Monitoring responsibilities:
1. After each iteration: check that files changed OR errors decreased
2. Detect stagnation: same output 2+ times, growing errors, zero file changes after N≥3 iterations
3. Level 1 (Warn): log warning, continue
4. Level 2 (Pause): stop loop, report state to human, ask whether to continue
5. Level 3 (Emergency Stop): immediately halt on destructive ops or security violations

Stagnation signals to watch:
  - Git diff shows no changes after iteration N
  - Error count same or growing iteration over iteration
  - Same tool called 3+ times with same arguments
  - Max iterations reached

Report format after each iteration:
  Iteration <N>/<MAX>: <status> | Files changed: <Y/N> | Errors: <delta>
```

### Step 4: Execute Worker Loop

The worker agent (`<AGENT>`) runs autonomously. Each iteration:

1. **Read** — understand current state (git status, error output, test results)
2. **Act** — implement the next logical step toward the task goal
3. **Verify** — run appropriate checks (build, tests, linter) after each file change
4. **Report** — brief summary of what changed and what remains

**Worker constraints (enforced by loop-operator):**
- Must make file changes or reduce error count each iteration
- Must not re-attempt a failed approach without modification
- Must not run destructive commands (rm -rf, git reset --hard, DROP TABLE) without explicit human approval
- Must not bypass safety hooks (--no-verify, --force)

### Step 5: Iteration Checkpoint Protocol

After each iteration, the loop-operator checks:

```
Stagnation check (after iteration N):
  IF files_changed == 0 AND errors_unchanged AND N >= STALL_AFTER:
    → Level 2: Pause loop, report to human

Progress check:
  IF error_count INCREASED from prior iteration:
    → Level 1: Log warning, continue (one chance)
    IF error_count STILL INCREASING next iteration:
    → Level 2: Pause loop

Safety check (every iteration):
  IF worker issued: rm -rf | git reset --hard | DROP TABLE | --no-verify | --force-push:
    → Level 3: Emergency Stop
```

### Step 6: Loop Termination

The loop terminates when:

- **Task complete:** Worker signals completion AND verification-loop passes all 6 gates
- **Max iterations:** Loop-operator escalates with final state report
- **Stagnation:** Loop-operator pauses for human input
- **Emergency stop:** Immediate halt with destructive-action report

### Step 7: Completion Report

**Success:**
```
AUTONOMOUS LOOP COMPLETE
=========================
Task: <task>
Agent: <agent>
Iterations used: <N> / <max>

Progress per iteration:
  [1] Created src/auth/middleware.ts (+47 lines) — build PASS
  [2] Fixed type error in auth.ts:88 — types PASS
  [3] Added tests in tests/auth.test.ts — tests PASS (12/12)

Validation gate:
  Build:    PASS ✓
  Types:    PASS ✓
  Lint:     PASS ✓
  Tests:    PASS ✓ (N passed)
  Security: PASS ✓

Files modified: N
Next: /prp-commit "<task summary>"
```

**Paused (human input needed):**
```
LOOP PAUSED — LOOP OPERATOR INTERVENTION
==========================================
Reason: <stagnation|error-growth|human-requested>
Iteration: <N> / <max>

Last 3 iterations showed no progress:
  [N-2] No files changed. Error count: 5
  [N-1] No files changed. Error count: 5
  [N]   No files changed. Error count: 6 (growing)

Current state:
  <git status output>

Remaining errors:
  <error output>

Options:
  1. Reply "continue" to resume with fresh context
  2. Reply "stop" to end the loop and review manually
  3. Describe a specific fix to unblock the loop
```

**Emergency stop:**
```
EMERGENCY STOP — DESTRUCTIVE ACTION DETECTED
==============================================
Iteration: <N>
Reason: Worker attempted <destructive command>
Command blocked: <command>

Current state is SAFE — no destructive action was executed.

Review what the worker was trying to do:
  <context of the attempted action>

Human approval required to continue. Reply with:
  "approve: <command>" — to allow this specific command once
  "stop" — to end the loop
```

---

## Usage Examples

- `/loop-start "implement the rate limiter from the prp plan"` — default implementer agent, 10 iterations
- `/loop-start "fix all TypeScript errors" --agent build-error-resolver --max-iter 7` — dedicated resolver
- `/loop-start "refactor the auth module" --stall-after 2` — aggressive stagnation detection
- `/loop-start "add tests for the payment module" --max-iter 5` — bounded test-writing loop

## Notes

- The loop-operator is a safety layer — it CANNOT guarantee completion, only safe termination
- For deterministic tasks (fix N known errors), use `/build-fix` directly
- For GAN-style generative tasks, use `/gan-build` instead
- Loop-operator escalation is a feature, not a failure — it means the task needs human judgment
- Always review the loop report before committing — autonomous loops can produce unexpected diffs
