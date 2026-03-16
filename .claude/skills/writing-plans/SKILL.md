---
name: writing-plans
description: "Use when creating implementation plans - ensures bite-sized tasks, operations config, and structured approach"
disable-model-invocation: true
argument-hint: "<task-description>"
---

# Writing Plans

## Core Principle

**A plan is only as good as its smallest task.** Every task in a plan must be small enough to implement in a single, focused session without losing context.

---

## Plan Structure

Every plan MUST contain:

1. **Goal Statement** - One sentence describing what the plan achieves
2. **Context Summary** - What you explored and learned (from context-first-workflow)
3. **Task List** - Numbered, bite-sized tasks with clear completion criteria
4. **Operations Config** - ops.json for structured execution (see generate-operations-config)
5. **Verification Strategy** - How to confirm the plan succeeded
6. **Risk Notes** - What could go wrong and how to mitigate

---

## Bite-Sized Task Requirements

Each task MUST satisfy ALL of these criteria:

| Criterion | Description |
|---|---|
| **Single Responsibility** | One task does one thing |
| **Clear Input** | What files/state does this task start from? |
| **Clear Output** | What files/state does this task produce? |
| **Independently Verifiable** | Can you confirm this task succeeded without running the whole plan? |
| **Time-Bounded** | Completable in under 15 minutes |
| **No Ambiguity** | Another agent could execute this task without asking questions |

### Good Task Examples

```
Task 3: Create UserRepository interface
- File: src/domain/repositories/user_repository.py
- Define: find_by_id(id: str) -> User | None
- Define: save(user: User) -> User
- Define: delete(id: str) -> bool
- Verification: File exists with all three method signatures
```

### Bad Task Examples

```
Task 3: Set up the data layer
(Too vague - what files? what interfaces? what's "done"?)

Task 3: Implement the entire user management system
(Too large - should be 5-10 smaller tasks)
```

---

## The ops.json Requirement

Every plan MUST include or reference an ops.json file. This config:
- Defines every file operation the plan will perform
- Makes the plan machine-executable
- Enables validation before execution
- Provides rollback capability

If the plan is exploratory or purely conceptual, note "No ops.json needed - exploration only."

---

## Plan Templates by Task Type

### Bug Fix Plan

```markdown
## Goal
Fix [bug description] in [component]

## Context
- Root cause: [from systematic-debugging investigation]
- Affected files: [list]
- Related tests: [list]

## Tasks
1. Write failing test that reproduces the bug
2. Implement the fix in [specific file]
3. Verify existing tests still pass
4. Verify new test passes
5. Check for similar bugs in related code

## Verification
- [ ] New test fails without fix, passes with fix
- [ ] All existing tests pass
- [ ] No regressions in related functionality

## Risks
- [Risk 1]: [Mitigation]
```

### New Feature Plan

```markdown
## Goal
Add [feature description] to [component]

## Context
- Integration points: [list]
- Existing patterns to follow: [list]
- Dependencies needed: [list]

## Tasks
1. Define the interface/contract for the new feature
2. Write tests for the expected behavior
3. Implement the core logic
4. Integrate with existing system at [integration point]
5. Update configuration if needed
6. Verify end-to-end behavior

## Verification
- [ ] All new tests pass
- [ ] All existing tests pass
- [ ] Feature works end-to-end
- [ ] No performance regression

## Risks
- [Risk 1]: [Mitigation]
```

### Refactoring Plan

```markdown
## Goal
Refactor [component] to [improvement description]

## Context
- Current problems: [list]
- Desired state: [description]
- All usages of target code: [list]

## Tasks
1. Ensure comprehensive test coverage exists for current behavior
2. [First atomic refactoring step]
3. Verify tests still pass
4. [Second atomic refactoring step]
5. Verify tests still pass
6. ... (repeat pattern)
7. Clean up any temporary scaffolding
8. Final verification of all tests

## Verification
- [ ] Behavior is unchanged (all tests pass)
- [ ] Code quality metrics improved
- [ ] No new dependencies introduced unexpectedly

## Risks
- [Risk 1]: [Mitigation]
```

---

## Task Ordering Rules

1. **Tests before implementation** - Write/update tests before the code they test
2. **Interfaces before implementations** - Define contracts before filling them in
3. **Inner layers before outer** - Domain logic before infrastructure
4. **Independent before dependent** - Tasks with no prerequisites go first
5. **Risky before safe** - Tackle uncertain tasks early to fail fast

---

## Plan Review Checklist

Before presenting a plan to the user:

- [ ] Every task is bite-sized (satisfies all criteria above)
- [ ] Tasks are ordered correctly (dependencies respected)
- [ ] Verification steps exist for each phase
- [ ] Risks are identified with mitigations
- [ ] The plan references or includes ops.json
- [ ] Total plan scope matches the original request (no scope creep)
- [ ] Another agent could execute this plan without additional context

---

## Presenting the Plan

When presenting to the user:
1. Start with the goal (one sentence)
2. Summarize what you learned during exploration
3. Present the task list
4. Highlight any risks or decision points
5. Ask for approval before proceeding

Remember: The golden-rule applies. No implementation without approval.
