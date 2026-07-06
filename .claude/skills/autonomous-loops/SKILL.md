---
name: autonomous-loops
description: "Use when setting up agents to run iteratively until a goal is met — continuous improvement loops with convergence criteria and safety guards"
disable-model-invocation: true
---

# Autonomous Loops

## Core Concept

An autonomous loop is an agent that runs repeatedly until a convergence condition is met. Unlike a single-pass agent, it can self-correct, retry on failure, and improve its output across iterations.

**Use when:**
- A task requires multiple attempts to get right (e.g., fixing all lint errors)
- Quality must be verified after each step
- The goal is clear but the path requires iteration
- You want an agent to run until tests pass, not just until it tries

**Do NOT use when:**
- The task has a clear, single-step solution
- User input is required between steps
- The loop could run indefinitely without a meaningful stopping condition

---

## Loop Architecture

```
[Start]
  |
  v
[Execute Iteration N]
  |
  v
[Evaluate: Convergence Criteria Met?]
  |
  +--YES--> [Report Success] --> [Stop]
  |
  +--NO, max_iterations not reached--> [Log Progress] --> [Execute Iteration N+1]
  |
  +--NO, max_iterations reached--> [Report Partial Results + Escalate]
```

---

## Convergence Criteria

Every loop MUST have at least one of:

### Hard Convergence
A deterministic check that is either true or false:
- All tests pass: `npm test` exits 0
- No lint errors: `flake8 src/` exits 0
- File exists and matches pattern
- API returns expected response

### Soft Convergence
A quality threshold:
- Coverage >= 80%
- Security score <= 2 high severity issues
- Performance benchmark within 10% of target

### Iteration Budget
A maximum number of attempts:
- `max_iterations: 5` (hard limit)
- After which: report progress and escalate

---

## Loop Design Patterns

### Pattern 1: Test-Fix Loop

Run tests → fix failures → repeat until all pass:

```
Loop:
  Run: npm test
  If all pass → DONE
  If failures:
    Analyze: Which tests failed?
    Fix: Apply targeted fix for first failure
    Continue loop

Max iterations: 5
On budget exceeded: Report remaining failures, ask for human input
```

### Pattern 2: Quality-Improve Loop

Measure quality → improve → repeat until threshold met:

```
Loop:
  Measure: Current quality score (lint, coverage, complexity)
  If score >= target → DONE
  If score < target:
    Identify: Lowest-scoring dimension
    Improve: Apply one targeted improvement
    Verify: Re-measure that dimension
    Continue loop

Max iterations: 10
On budget exceeded: Report current score vs. target, list remaining issues
```

### Pattern 3: Search-Refine Loop

Search for information → refine query based on results → repeat until answer found:

```
Loop:
  Search: Current query
  Evaluate: Did results answer the question?
  If yes → Synthesize and DONE
  If no:
    Analyze: What's missing from results?
    Refine: Narrow or pivot query
    Continue loop

Max iterations: 5
On budget exceeded: Provide best answer from collected data
```

---

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
