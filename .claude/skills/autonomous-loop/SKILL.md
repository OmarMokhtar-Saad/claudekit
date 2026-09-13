---
name: autonomous-loop
description: "Use when implementing features end-to-end autonomously, or when designing any agent loop that runs until a goal is met -- the analyze-plan-implement-test-review-iterate pipeline plus convergence criteria, loop patterns and mandatory safety guards."
---

# Autonomous Development Loop

## Purpose

Implement the autonomous development loop (Ralph pattern) that allows Claude Code to take a task from description to completion with minimal human intervention. Each iteration moves the implementation closer to the goal, with built-in safety limits to prevent runaway execution.

---

## Loop Phases

ANALYZE -> PLAN -> IMPLEMENT -> TEST -> REVIEW -> (score < 80: ITERATE back to the
relevant phase) -> COMPLETE. Review scores 0-100: Correctness 40%, Code quality 25%,
Test coverage 20%, Safety 15%. Each iteration must improve the score or change approach.

Read [references/pipeline-phases.md](references/pipeline-phases.md) when you run the six-phase pipeline -- per-phase steps, the diagram, and the iteration and completion report formats.

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
## Integration

- Uses **planner** agent for Phase 2
- Uses **implementer** agent for Phase 3
- Uses **tester** agent for Phase 4
- Uses **reviewer** scoring logic for Phase 5
- Respects all **operations system** safety guards
- Saves progress to **context-keeper** state between iterations
---


# Loop Design (merged from `autonomous-loops`)

The general contract every loop in the kit must satisfy, whatever its phases.

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

## Convergence and guards (mandatory)

Every loop MUST have at least one of: **Hard Convergence** (a deterministic check,
e.g. `npm test` exits 0), **Soft Convergence** (a quality threshold), or an
**Iteration Budget** (`max_iterations: 5`, then report progress and escalate).

Every autonomous loop MUST implement: a maximum iteration limit; progress validation
(escalate after 2 consecutive no-progress iterations); an idempotency check (never
re-apply a fix); and a destructive operation block (`git reset --hard`, `rm -rf`,
`DROP TABLE`, `git push --force` require explicit approval). Verify ALL criteria,
not just one, before reporting success.

Read [references/loop-design.md](references/loop-design.md) when you design a loop -- the loop architecture, convergence criteria in full, and the Test-Fix / Quality-Improve / Search-Refine patterns.
Read [references/safety-guards.md](references/safety-guards.md) when you implement the guards, track loop state, write the loop report, or check the anti-patterns table.
