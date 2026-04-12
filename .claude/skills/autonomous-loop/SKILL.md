---
name: autonomous-loop
description: "Use when implementing features end-to-end autonomously -- follows the analyze-plan-implement-test-review-iterate loop with safety limits and exit conditions."
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
- Saves progress to **session-continuity** state between iterations
