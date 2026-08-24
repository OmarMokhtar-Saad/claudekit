---
name: autonomous-loop
description: "Use when implementing features end-to-end autonomously, or when designing any agent loop that runs until a goal is met -- the analyze-plan-implement-test-review-iterate pipeline plus convergence criteria, loop patterns and mandatory safety guards."
---

# Autonomous Development Loop

## Purpose

Implement the autonomous development loop (Ralph pattern) that allows Claude Code to take a task from description to completion with minimal human intervention. Each iteration moves the implementation closer to the goal, with built-in safety limits to prevent runaway execution.

---

## Loop Phases

```
    ┌──────────────────────────────────┐
    │         1. ANALYZE               │
    │   Understand task & codebase     │
    └──────────────┬───────────────────┘
                   │
    ┌──────────────▼───────────────────┐
    │         2. PLAN                  │
    │   Break into concrete steps      │
    └──────────────┬───────────────────┘
                   │
    ┌──────────────▼───────────────────┐
    │         3. IMPLEMENT             │
    │   Write code changes             │
    └──────────────┬───────────────────┘
                   │
    ┌──────────────▼───────────────────┐
    │         4. TEST                  │
    │   Run tests, check for errors    │
    └──────────────┬───────────────────┘
                   │
    ┌──────────────▼───────────────────┐
    │         5. REVIEW                │
    │   Self-evaluate quality          │
    └──────────────┬───────────────────┘
                   │
              Pass? ──No──► 6. ITERATE (back to relevant phase)
                │
               Yes
                │
    ┌──────────────▼───────────────────┐
    │         COMPLETE                 │
    │   Report results to user         │
    └──────────────────────────────────┘
```

### Phase 1: Analyze

- Read the task description and acceptance criteria
- Explore relevant areas of the codebase
- Identify existing patterns, conventions, and dependencies
- Determine scope and potential risks
- Output: analysis summary with risk assessment

### Phase 2: Plan

- Break the task into ordered, atomic steps
- Each step must be independently testable
- Estimate complexity (low/medium/high) per step
- Identify which files will be created/modified/deleted
- Generate ops.json config if using the operations system
- Output: numbered step list with file manifest

### Phase 3: Implement

- Execute each planned step in order
- Follow existing code conventions detected in analysis
- Create backups before modifying existing files
- Write implementation incrementally -- verify each step compiles before moving on
- Output: list of changes made

### Phase 4: Test

- Run the project's test suite
- Run any newly written tests
- Check for compilation/lint errors
- Verify no regressions (existing tests still pass)
- Output: test results summary with pass/fail counts

### Phase 5: Review

- Self-evaluate against the original acceptance criteria
- Check code quality: naming, structure, error handling, edge cases
- Verify no security issues introduced
- Calculate a quality score (0-100):
  - Correctness: 40% (does it do what was asked?)
  - Code quality: 25% (clean, readable, follows conventions?)
  - Test coverage: 20% (are the changes tested?)
  - Safety: 15% (no regressions, no security issues?)
- Output: review scorecard

### Phase 6: Iterate

- If quality score < 80, identify the weakest dimension
- Create a targeted fix plan for that dimension only
- Return to the appropriate phase (usually Phase 3 or Phase 4)
- Each iteration must improve the score or change approach
- Log what was attempted and why it was insufficient

---

## Exit Conditions

The loop exits successfully when ALL of these are true:

1. All tests pass (zero failures)
2. Quality score >= 80
3. No regressions detected
4. All acceptance criteria are met

The loop exits with escalation when ANY of these are true:

1. Maximum iterations reached (default: 5)
2. Quality score is not improving between iterations
3. A blocker is encountered that requires human decision
4. The task scope is larger than originally estimated

---

## Safety Controls

### Iteration Limits

| Control | Default | Configurable |
|---------|---------|-------------|
| Max iterations | 5 | Yes, via `max_iterations` param |
| Max files modified per iteration | 10 | Yes |
| Max total files modified | 30 | Yes |
| Max time per iteration | 5 minutes | No |

### Rate Limiting

- Minimum 2-second pause between file writes
- Maximum 3 file operations per second
- No more than 1 destructive operation (delete) per iteration

### Circuit Breaker

The loop halts immediately if:

- A test that previously passed now fails (regression)
- A file outside the planned scope is modified
- The total number of modified files exceeds the limit
- An iteration produces zero changes (stuck loop)
- The same error appears in 3 consecutive iterations

### Rollback

- Each iteration creates a rollback checkpoint
- If the circuit breaker triggers, automatically rollback to the last good checkpoint
- User can manually trigger rollback at any point

---

## Reporting

At the end of each iteration, output:

```
--- Iteration 2/5 ---
Phase: Test -> Issues found
Quality Score: 65/100 (+12 from last iteration)
  Correctness:  30/40
  Code Quality: 18/25
  Test Coverage: 10/20
  Safety:       7/15
Changes: 4 files modified, 1 created
Tests: 23 pass, 2 fail
Next: Fix failing tests (auth.test.ts:L45, user.test.ts:L112)
---
```

At completion:

```
--- Autonomous Loop Complete ---
Iterations: 3/5
Final Score: 87/100
Files: 6 modified, 2 created
Tests: 25 pass, 0 fail
Duration: ~4 minutes
Result: SUCCESS -- all acceptance criteria met
---
```

---

## Integration

- Uses **planner** agent for Phase 2
- Uses **implementer** agent for Phase 3
- Uses **tester** agent for Phase 4
- Uses **reviewer** scoring logic for Phase 5
- Respects all **operations system** safety guards
- Saves progress to **context-keeper** state between iterations
---

# Loop Design (merged from `autonomous-loops`)

The six phases above are one *instance* of an autonomous loop. This half is the
general contract every loop in the kit must satisfy, whatever its phases: when it
is allowed to run at all, how convergence is defined, which guards are mandatory,
and what it must report. Merged from the `autonomous-loops` skill, which is gone;
the name resolves here through the registry `renamed` alias map.

**Use when:** a task needs multiple attempts to get right (e.g. fixing all lint
errors), quality must be verified after each step, the goal is clear but the path
requires iteration, or you want the agent to run until tests pass rather than until
it has tried once.

**Do NOT use when:** the task has a clear single-step solution, user input is
required between steps, or the loop could run indefinitely with no meaningful
stopping condition.

**Iteration budget, reconciled:** the six-phase loop above caps at **5** iterations.
The Quality-Improve pattern below was written against a cap of 10. The cap that
binds is the one in Safety Controls above -- **5** -- unless the invoker raises it
explicitly via `max_iterations`. Two budgets in one skill is how a runaway loop gets
argued into being legitimate.

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

