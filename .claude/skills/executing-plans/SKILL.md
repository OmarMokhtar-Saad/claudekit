---
name: executing-plans
description: "Use when you have a written implementation plan to execute in a separate session with review checkpoints"
disable-model-invocation: true
---

# Executing Plans

## Core Principle

**Execute methodically, verify continuously, and stop when uncertain.** A plan is only valuable if executed faithfully with regular checkpoints.

---

## The Execution Loop

```
[LOAD] Read the plan file
    |
    v
[REVIEW] Understand current state and next batch
    |
    v
[EXECUTE] Implement the next batch of tasks (default: 3)
    |
    v
[REPORT] Checkpoint progress to the plan file: what was done, what changed, what's next
    |
    +---> More tasks + no STOP condition ---> Back to REVIEW (continue autonomously)
    +---> STOP condition hit --------------> Stop and report (see STOP table)
    +---> Plan complete -------------------> Final verification and report
```

The plan was already approved — approval covers ALL of its tasks. Do NOT pause between
batches to ask "continue?"; the STOP table below defines every legitimate reason to halt.
Checkpointing to the plan file (silent) replaces mid-task check-ins (console).

---

## Step 1: LOAD

When starting plan execution:

1. Read the plan file completely
2. Read any referenced ops.json
3. Identify which tasks have already been completed (if resuming)
4. Note the current task number

**Output:** "Loaded plan: [goal]. [N] of [M] tasks completed. Starting at task [X]."

---

## Step 2: REVIEW

Before each batch:

1. Read the next 3 tasks carefully
2. Verify prerequisites are met (previous tasks completed)
3. Check that referenced files exist and are in expected state
4. Identify any blockers

**If blockers found:** Stop and report to user before proceeding.

---

## Step 3: EXECUTE

### Batch Size

- **Default batch:** 3 tasks
- **Smaller batch (1-2):** When tasks are high-risk or complex
- **Larger batch (4-5):** When tasks are simple and low-risk

### Per-Task Execution

For each task in the batch:

1. **Read** all files the task will modify
2. **Implement** the change as specified in the plan
3. **Verify** the task's completion criteria are met
4. **Record** what was done

### Staying on Plan

- Implement EXACTLY what the plan specifies
- Do not add improvements you notice along the way
- Do not skip tasks you think are unnecessary
- Do not reorder tasks without user approval

If the plan seems wrong:
- Complete the current task
- Stop the batch
- Report the concern to the user
- Wait for guidance

---

## Step 4: REPORT

After each batch, provide:

```
## Batch Report: Tasks [X]-[Y]

### Completed
- Task X: [brief description] - DONE
- Task Y: [brief description] - DONE
- Task Z: [brief description] - DONE

### Changes Made
- Modified: [file list]
- Created: [file list]
- Deleted: [file list]

### Verification Results
- [test/check 1]: PASS/FAIL
- [test/check 2]: PASS/FAIL

### Next Up
- Task [N]: [brief description]
- Task [N+1]: [brief description]
- Task [N+2]: [brief description]

### Concerns
- [Any issues, deviations, or uncertainties]
```

---

## Step 5: CONTINUE

Continue autonomously to the next batch — the approved plan IS the permission. Checkpoint
progress to the plan file after each batch, then proceed. Speak up only when a STOP
condition below is hit or the plan is complete ("Plan complete. Ready for final
verification?").

---

## When to STOP

These are the ONLY legitimate reasons to halt mid-plan:

| Situation | Action |
|---|---|
| A task fails its verification twice (different approaches) | Stop and report with the failure output |
| You discover the plan has a mistake | Stop and explain the issue |
| A file is not in the expected state | Stop and investigate |
| You need to make changes not in the plan | Stop and ask for approval |
| Tests fail unexpectedly and diagnosis points outside the plan | Stop and report the diagnosis |
| A task's intent is genuinely ambiguous (two valid readings diverge) | Stop and clarify |

Everything else: proceed. Stopping to ask "continue?" on an approved plan trains
turn-ending, not diligence.

---

## Resuming Execution

When resuming a previously paused plan:

1. Read the plan file
2. Check `git log` or file state to determine what was already done
3. Identify the first uncompleted task
4. Report: "Resuming at task [N]. Tasks 1-[N-1] appear complete."
5. Verify the state is consistent before proceeding

---

## Handling Task Failure

If a task cannot be completed as specified:

1. **Attempt the task** as specified
2. **If it fails**, diagnose the ROOT CAUSE before any retry — if your fix wouldn't explain
   the original failure, the diagnosis is wrong. Never add null-checks/try-catches just to
   make a symptom disappear.
3. **Retry once with a materially different approach** within the plan's scope
4. **Report the failure** (if the retry also fails) with:
   - What you tried
   - Why it failed
   - Your assessment of whether the plan can continue
   - Suggested fix (but do NOT implement without approval)
5. **Wait for user decision**

---

## Progress Tracking

Maintain awareness of:
- Total tasks in the plan
- Tasks completed
- Tasks remaining
- Any tasks that were modified from the original plan
- Any blockers or risks for upcoming tasks

This information goes in every batch report.

---

## Final Verification

When all tasks are complete:

1. Run the plan's verification strategy
2. Check all completion criteria
3. Present a final summary:
   - All tasks completed
   - All verification results
   - Any deviations from the original plan
   - Suggestions for follow-up (if any)
