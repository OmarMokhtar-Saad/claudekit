---
name: subagent-driven-development
description: "Use when executing a plan by dispatching fresh subagent per task with two-stage review"
disable-model-invocation: true
---

# Subagent-Driven Development

## Core Principle

**Each task gets a fresh agent with a focused context window.** This prevents context pollution, ensures consistent quality, and enables two-stage review (specification review + code quality review).

---

## When to Use

### Good Fit

| Scenario | Why |
|---|---|
| Executing a multi-task plan | Each task is independent enough for a fresh agent |
| Tasks that follow established patterns | Subagent can follow patterns without full history |
| Repetitive but non-trivial tasks | Fresh context prevents fatigue and drift |
| Work that benefits from review | Two-stage review catches more issues |

### Poor Fit

| Scenario | Why |
|---|---|
| Tightly coupled tasks requiring shared context | Handoff cost exceeds benefit |
| Exploratory work with unclear direction | Subagent needs clear instructions |
| Single quick fix | Dispatch overhead not worth it |
| Tasks requiring real-time user interaction | Subagent cannot ask the user questions |

---

## The Process

For each task in the plan:

```
[DISPATCH IMPLEMENTER] Fresh agent implements the task
    |
    v
[SPEC REVIEW] Review: Does implementation match the specification?
    |
    v
[CODE QUALITY REVIEW] Review: Is the code clean, tested, secure?
    |
    v
[ACCEPT or REWORK] Decide if task is complete
    |
    v
[NEXT TASK] Move to the next task in the plan
```

---

## Stage 1: Dispatch Implementer

### The Implementer Prompt

```markdown
## Task: [Task Name from Plan]

### Context
You are implementing task [N] of [M] in a development plan.

### What to Implement
[Exact specification from the plan]

### Files to Modify
- [file 1]: [what to change]
- [file 2]: [what to change]

### Files to Create
- [file 1]: [purpose]

### Patterns to Follow
[Reference existing code that demonstrates the pattern]
- See: [file path] for the pattern to follow
- Naming convention: [convention]
- Test pattern: [how tests should be structured]

### Acceptance Criteria
- [ ] [criterion 1]
- [ ] [criterion 2]
- [ ] [criterion 3]

### Constraints
- Do not modify files outside your scope
- Follow existing patterns in the codebase
- Write tests for all new functionality
- Do not introduce new dependencies without noting them

### When Done
Report:
- Files created/modified
- Tests written
- Any concerns or deviations from spec
```

---

## Stage 2: Spec Review

After the implementer completes, review against the specification:

### Spec Review Checklist

| Check | Question |
|---|---|
| **Completeness** | Does the implementation cover all acceptance criteria? |
| **Correctness** | Does it match what was specified, not just something that works? |
| **Scope** | Did the implementer stay within the specified scope? |
| **Contracts** | Do interfaces/APIs match the plan's design? |
| **Integration** | Will this integrate with the rest of the system as planned? |

### Spec Review Outcomes

- **PASS**: Implementation matches specification. Proceed to code review.
- **MINOR ISSUES**: Small deviations that can be noted and accepted. Proceed.
- **REWORK NEEDED**: Significant deviation from spec. Send back to implementer.

---

## Stage 3: Code Quality Review

After spec review passes, review code quality:

### Code Quality Checklist

| Area | What to Check |
|---|---|
| **Tests** | Adequate coverage? Edge cases? Readable? |
| **Naming** | Clear and consistent with codebase? |
| **Architecture** | Follows layer boundaries? Dependency direction correct? |
| **Error handling** | Errors handled appropriately? User-friendly messages? |
| **Security** | Input validated? No injection risks? |
| **Performance** | No obvious performance issues? N+1 queries? |
| **Readability** | Can another developer understand this easily? |
| **Duplication** | No copy-paste code that should be abstracted? |

### Code Quality Outcomes

- **PASS**: Code is clean and well-structured. Task complete.
- **MINOR ISSUES**: Small improvements needed. Fix and accept.
- **REWORK NEEDED**: Significant quality issues. Send back to implementer with specific feedback.

---

## Rework Protocol

When rework is needed:

1. **Provide specific feedback** - not "make it better" but "change X to Y because Z"
2. **Dispatch a fresh agent** (or the same one if context is still valid)
3. **Include the feedback** in the new dispatch prompt
4. **Re-review** after rework

### Maximum Rework Cycles

- **Limit: 2 rework cycles** per task
- If still not passing after 2 reworks, escalate to the coordinator/user
- Possible issues: unclear spec, wrong pattern, or task too complex for subagent

---

## Prompt Templates

### Rework Prompt

```markdown
## Rework: [Task Name]

### Previous Implementation
[Summary of what was implemented]

### Feedback
The following issues need to be addressed:

1. [Specific issue 1]
   - Current: [what was done]
   - Expected: [what should be done]
   - Why: [explanation]

2. [Specific issue 2]
   - Current: [what was done]
   - Expected: [what should be done]
   - Why: [explanation]

### Files to Modify
[Same file list, updated with rework targets]

### Updated Acceptance Criteria
[Original criteria plus rework-specific criteria]
```

---

## Advantages of Subagent-Driven Development

| Advantage | Explanation |
|---|---|
| **Fresh context** | No context pollution from previous tasks |
| **Consistent quality** | Each task gets full attention, no fatigue |
| **Two-stage review** | Catches both spec and quality issues |
| **Parallelizable** | Independent tasks can use parallel subagents |
| **Auditable** | Clear record of what each agent did |
| **Replaceable** | Failed agents can be easily re-dispatched |

---

## Progress Tracking

Maintain a task tracker during execution:

```markdown
## Plan Execution Progress

| # | Task | Implementer | Spec Review | Code Review | Status |
|---|---|---|---|---|---|
| 1 | Create User entity | DONE | PASS | PASS | COMPLETE |
| 2 | Add validation | DONE | PASS | REWORK | IN REVIEW |
| 3 | Implement repository | IN PROGRESS | - | - | IN PROGRESS |
| 4 | Add API endpoint | NOT STARTED | - | - | PENDING |
| 5 | Write integration tests | NOT STARTED | - | - | PENDING |
```

---

## Integration with Other Skills

- **writing-plans**: Plans provide the task list for subagent execution
- **multi-agent-coordination**: File scope rules apply to parallel subagents
- **verification-before-completion**: Each subagent must verify before reporting
- **golden-rule**: Coordinator must have user approval for the overall plan
