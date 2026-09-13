# Autonomous Loop -- safety guards, state tracking, reporting, anti-patterns

Moved verbatim from SKILL.md.

## Safety Guards

Every autonomous loop MUST implement:

### 1. Maximum Iteration Limit

```python
MAX_ITERATIONS = 5  # Never run more than this
for iteration in range(MAX_ITERATIONS):
    result = execute_iteration()
    if converged(result):
        break
else:
    escalate("Max iterations reached without convergence")
```

### 2. Progress Validation

Each iteration must make measurable progress:

```python
previous_score = get_score()
execute_iteration()
new_score = get_score()

if new_score <= previous_score:
    consecutive_no_progress += 1
    if consecutive_no_progress >= 2:
        escalate("Loop is not making progress — stuck")
```

### 3. Idempotency Check

Before applying a fix, verify it wasn't already applied:

```python
if fix_already_applied(fix):
    skip("Fix already applied in previous iteration")
    continue
```

### 4. Destructive Operation Block

Never perform destructive operations inside a loop without explicit user approval:

```python
BLOCKED_IN_LOOPS = ["git reset --hard", "rm -rf", "DROP TABLE", "git push --force"]
if any(op in planned_action for op in BLOCKED_IN_LOOPS):
    escalate("Destructive operation requires explicit approval")
```

---

## Loop State Tracking

Track state across iterations for debugging:

```json
{
  "loop_id": "test-fix-2026-04-10T09:00:00",
  "goal": "All tests pass",
  "max_iterations": 5,
  "iterations": [
    {
      "n": 1,
      "action": "Fixed null check in UserService.get()",
      "result": "12 tests pass, 3 fail",
      "score": 80
    },
    {
      "n": 2,
      "action": "Fixed type error in AuthController",
      "result": "14 tests pass, 1 fail",
      "score": 93
    }
  ],
  "status": "in_progress"
}
```

---

## Reporting Format

At the end of each loop (success or budget exceeded):

```
## Autonomous Loop Report

### Goal
[What the loop was trying to achieve]

### Outcome: [CONVERGED | BUDGET_EXCEEDED | ESCALATED]

### Progress by Iteration
| Iteration | Action | Result | Score |
|-----------|--------|--------|-------|
| 1         | [fix]  | [result] | XX% |
| 2         | [fix]  | [result] | XX% |
...

### Final State
[Description of where things stand]

### If Budget Exceeded
Remaining issues:
1. [issue 1]
2. [issue 2]

Recommended next action:
[What a human should do to complete the work]
```

---

## Anti-Patterns

| Anti-Pattern | Risk | Fix |
|-------------|------|-----|
| No max_iterations | Infinite loop | Always set a budget |
| No progress check | Infinite loop on stuck state | Detect stagnation after 2 no-progress iterations |
| Applying fixes without checking if already applied | Duplicate changes | Track applied fixes |
| Running destructive ops in loop | Unrecoverable state | Block and escalate |
| No state tracking | Can't debug failures | Log each iteration's action and result |
| Loop that can succeed on partial completion | False positive | Verify ALL criteria, not just one |

