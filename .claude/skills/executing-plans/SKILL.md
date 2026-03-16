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
[REPORT] Show what was done, what changed, what's next
    |
    v
[CONTINUE?] Check if user wants to proceed
    |
    +---> Yes -----> Back to REVIEW
    +---> No ------> Save progress and stop
    +---> Issue ---> Stop and discuss
```

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

After each report, ask the user:

- "Continue with the next batch?" (normal case)
- "I have a concern about [X]. How should I proceed?" (issue found)
- "Plan complete. Ready for final verification?" (last batch)

---

## When to STOP and Ask

**Always stop when:**

| Situation | Action |
|---|---|
| A task fails its verification | Stop and report the failure |
| You discover the plan has a mistake | Stop and explain the issue |
| A file is not in the expected state | Stop and investigate |
| You need to make changes not in the plan | Stop and ask for approval |
| Tests fail unexpectedly | Stop and diagnose |
| You are uncertain about a task's intent | Stop and clarify |

**Never assume.** When in doubt, stop and ask.

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
2. **If it fails**, diagnose why
3. **Report the failure** with:
   - What you tried
   - Why it failed
   - Your assessment of whether the plan can continue
   - Suggested fix (but do NOT implement without approval)
4. **Wait for user decision**

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
