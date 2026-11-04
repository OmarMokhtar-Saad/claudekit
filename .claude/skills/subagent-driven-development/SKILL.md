---
name: subagent-driven-development
description: "Use when executing a plan task by task — the main session edits, fresh review-only subagents check each task"
---

# Subagent-Driven Development

## Core Principle

**The main session writes the code; fresh subagents only look at it.** Each finished task is
checked by a read-only subagent with a focused context (specification review, then code
quality review if the user asked). Subagents never get Edit/Write on source: edits stay in the
main session, where `plan-gate` and `checkpoint-gate` apply.

---

## When to Use

### Good Fit

| Scenario | Why |
|---|---|
| Executing a multi-task plan | Each task ends at a checkable boundary |
| Tasks that follow established patterns | A reviewer can judge them from the spec alone |
| Work where the main context is large | A fresh reviewer has no authoring bias |

### Poor Fit

| Scenario | Why |
|---|---|
| Single quick fix | Dispatch overhead is not worth it |
| Exploratory work with unclear direction | A reviewer needs a spec to review against |
| Tightly coupled tasks | The review needs the whole diff, not one task |

---

## The Process

For each task in the plan:

```
[IMPLEMENT] Main session edits the files the task names (plan Files: list)
    |
    v
[SPEC REVIEW] Fresh read-only subagent: does the diff match the specification?
    |
    v
[CODE QUALITY REVIEW] Only if the user asked: is the code clean, tested, secure?
    |
    v
[ACCEPT or REWORK] Main session fixes findings, or accepts the task
    |
    v
[NEXT TASK]
```

Independent read-only checks (spec review, tests, security scan) run in ONE batched message.

---

## Stage 1: Implement (main session)

Edit directly, one task at a time, in the plan's order. Stay inside the plan's `Files:` list;
a path outside it is a plan change, not a quiet extra. Read each file before editing it.

---

## Stage 2: Spec Review

Dispatch a fresh `code-reviewer` (or `explore`) subagent. It has no Write grant for source;
give it the task spec and the diff scope, and ask for findings with file:line.

### The Review Prompt

```markdown
## Review: [Task Name from Plan]

### Specification
[Exact specification from the plan, with acceptance criteria]

### Scope
Changed files: [list]. Review `git diff` for these files only.

### Check
- Completeness: every acceptance criterion covered?
- Correctness: matches what was specified, not just something that works?
- Scope: nothing changed outside the listed files?
- Contracts: interfaces/APIs match the plan's design?

### Report
At most 300 words: PASS / MINOR ISSUES / REWORK NEEDED, then findings as
[severity] file:line - issue - suggested fix. Do not edit anything.
```

### Spec Review Outcomes

- **PASS**: Matches the specification. Proceed to code review if the user asked; else accept.
- **MINOR ISSUES**: Small deviations that can be noted and accepted. Proceed.
- **REWORK NEEDED**: Significant deviation. The main session fixes it and re-requests review.

---

## Stage 3: Code Quality Review

Runs only when the user asked for code review — never on its own. After spec review passes:

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

Outcomes: **PASS** (task complete), **MINOR ISSUES** (fix and accept), **REWORK NEEDED**
(main session fixes with the specific feedback, then re-review).

---

## Rework Protocol

1. Apply the reviewer's specific findings yourself ("change X to Y because Z").
2. Re-run the checks that failed; request a fresh review of the new diff.

### Maximum Rework Cycles

- **Limit: 2 rework cycles** per task (3 review rounds is the hook-enforced ceiling).
- If still not passing, escalate to the coordinator/user. Likely causes: unclear spec, wrong
  pattern, or a task too large for one pass.

---

## Progress Tracking

```markdown
## Plan Execution Progress

| # | Task | Edited | Spec Review | Code Review | Status |
|---|---|---|---|---|---|
| 1 | Create User entity | DONE | PASS | PASS | COMPLETE |
| 2 | Add validation | DONE | PASS | REWORK | IN REVIEW |
| 3 | Implement repository | IN PROGRESS | - | - | IN PROGRESS |
| 4 | Add API endpoint | NOT STARTED | - | - | PENDING |
```

---

## Integration with Other Skills

- **writing-plans**: Plans provide the task list and the `Files:` scope
- **multi-agent-coordination**: Read-only subagents may run in parallel; edits never do
- **verification-before-completion**: Verify before reporting each task done
- **golden-rule**: Edits need an approved plan (Tier 3) or the user's go-ahead
