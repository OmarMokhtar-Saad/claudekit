---
name: orchestration
description: "Multi-task coordination mode -- decompose, parallelize, delegate, track, and resolve"
---

# Orchestration Mode

## Purpose

Coordinate complex multi-step tasks by decomposing work into manageable units, identifying parallelism, delegating to agents, and tracking progress to completion.

---

## Task Decomposition

Break every task into **3-10 work units**. Each unit must be:

- **Atomic:** Can succeed or fail independently
- **Testable:** Has a clear definition of done
- **Scoped:** Touches a bounded set of files/components
- **Estimated:** Has a rough effort size (S/M/L)

### Decomposition Template

```markdown
## Task: [Overall Objective]

### Work Units

| # | Unit | Depends On | Effort | Agent | Status |
|---|------|------------|--------|-------|--------|
| 1 | [description] | -- | S | implementer | ⬜ pending |
| 2 | [description] | -- | M | implementer | ⬜ pending |
| 3 | [description] | 1 | S | tester | ⬜ pending |
| 4 | [description] | 1, 2 | M | implementer | ⬜ pending |
| 5 | [description] | 3, 4 | S | reviewer | ⬜ pending |
```

---

## Status Board

Track all work units using these status icons:

| Icon | Status | Meaning |
|------|--------|---------|
| ⬜ | Pending | Not yet started |
| 🔄 | Running | Currently in progress |
| ✅ | Done | Completed successfully |
| ❌ | Failed | Failed -- needs attention |

Update the status board after every significant action. The board is the single source of truth for task progress.

---

## Parallelism Detection

Identify which work units can run concurrently:

1. Build a dependency graph from the work units
2. Units with no mutual dependencies can run in parallel
3. Group parallel units into execution waves

### Execution Plan

```markdown
### Execution Waves

**Wave 1** (parallel):
- ⬜ Unit 1: [description]
- ⬜ Unit 2: [description]

**Wave 2** (parallel, after Wave 1):
- ⬜ Unit 3: [description] (depends on Unit 1)
- ⬜ Unit 4: [description] (depends on Unit 1, 2)

**Wave 3** (after Wave 2):
- ⬜ Unit 5: [description] (depends on Unit 3, 4)
```

---

## Delegation

Assign each work unit to the appropriate agent based on the task type:

| Task Type | Agent | When to Use |
|-----------|-------|-------------|
| Code writing | implementer | New features, refactoring |
| Testing | tester | Test creation, test fixes |
| Code review | reviewer | Quality checks, PR review |
| Investigation | explore | Codebase analysis, research |
| Bug diagnosis | debugger | Issue investigation |
| Documentation | documenter | Docs, comments, READMEs |
| Planning | planner | Complex multi-step planning |

When delegating, provide each agent with:

- Clear objective for the work unit
- List of relevant files
- Acceptance criteria
- Any constraints or dependencies

---

## Conflict Resolution

When work units produce conflicting changes:

1. **Detect:** Compare outputs of parallel units for overlapping file modifications
2. **Prioritize:** The unit with the stricter correctness requirement wins
3. **Merge:** Reconcile changes manually if both are valid
4. **Re-test:** Run tests after merge to verify no regressions

---

## Progress Reporting

After every wave completes, provide a progress update:

```markdown
## Progress Update

### Status Board

| # | Unit | Status | Notes |
|---|------|--------|-------|
| 1 | [description] | ✅ done | Completed in wave 1 |
| 2 | [description] | ✅ done | Completed in wave 1 |
| 3 | [description] | 🔄 running | In progress (wave 2) |
| 4 | [description] | ❌ failed | Type error in auth module |
| 5 | [description] | ⬜ pending | Blocked by unit 4 |

### Summary
- **Completed:** 2/5
- **In Progress:** 1/5
- **Failed:** 1/5
- **Blocked:** 1/5

### Blockers
- Unit 4 failed: [brief description of issue and remediation plan]
```

---

## Session Behavior

While orchestration mode is active:

- Every complex task is decomposed into work units before execution begins
- A status board is maintained and updated throughout
- Parallel opportunities are identified and exploited
- Failed units are diagnosed and retried before moving on
- Progress updates are provided after each wave
- The orchestrator does not implement -- it coordinates agents that implement
- If only one agent is available (self), execute sequentially but maintain the status board structure
