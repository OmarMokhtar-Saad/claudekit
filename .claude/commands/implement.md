---
description: "Execute an approved plan in the main session (direct edits)"
model: sonnet
---

# Implement Command

Execute an approved `plan.md` **in the main session** with Edit/Write. No ops.json, no
executor script, no implementer agent. Subagents explore, review, test and verify; they
never edit.

## Task

Implement the approved plan.

## Mandatory Skills

You MUST load and apply the following skills before proceeding:

- **using-superpowers** - Core agent capabilities and tool usage
- **verification-before-completion** - Post-implementation verification gates

**On demand:** load **clean-architecture** when edits cross module boundaries.

## STEP 0: Pre-Flight Check

Before editing anything, verify ALL of the following:

1. **Tier 3 plan (security, schema, >15 files or ops):** the plan is approved. Prove it:
   ```bash
   python3 .claude/operations/scripts/review-record.py plan-check "$PLAN_FILE"
   ```
   Exit 0 = APPROVED and the plan bytes still match. Exit 2 = the plan changed after
   approval (re-run `/review`; it scores the delta). Exit 3 = never reviewed. Exit 4 =
   the verdict does not authorise this plan. On any non-zero exit STOP and report; never
   retry hoping for a different result and never write an approval record yourself.
   **Tier 2 plans** need no reviewer; **Tier 1** needs no plan.
2. The plan names every file you will touch under `Files:`. `plan-gate` blocks Tier 3 edits
   to a path the approved plan does not list; add the path to the plan and re-review
   rather than working around the block.
3. No conflicting uncommitted changes in the working tree.
4. All dependencies the plan references are available.

If ANY check fails, STOP and report it.

## Checkpoint

`checkpoint-gate` takes a git checkpoint (tag `ck-checkpoint/<epoch>`) before the first
edit of a work period. To take one by hand: `/checkpoint`. `/rollback` restores it.

## Workflow

### Phase 1: Preparation
- Read the plan and each file you will edit, in windows, before the first edit.
- Note the validation commands recorded in the plan for Phase 3.
- STAGE HANDOFF: start from a compacted or fresh context whose only input is the plan
  path; never continue in the planning/review conversation. If `suggest-compact` has
  fired, run `/compact` (or tell the user to) before Phase 2.

### Phase 2: Execution
1. Edit directly with Edit/Write, one plan step at a time, in the plan's order. Create
   files before referencing them.
2. Keep the diff to what the plan says. Anything outside the plan is a plan change, not
   a quiet extra edit.
3. Do not delegate edits to a subagent. Delegate searches and test runs only.

### Phase 3: Verification
- Run all verification steps defined in the plan.
- Build, tests and lint are independent: launch them in ONE batched message.
- Every PASS/FAIL you report must quote the executed command's actual output (exit code,
  counts). Never estimate, and never report before the command has exited: a still-running
  suite is not a PASS, and a red gate is reported, never repaired with
  `ck lint --update-baseline`, `--no-verify`, or any other baseline-mutating command.

### Phase 4: Report
- Summarize the files changed and any deviation from the plan.
- Report verification results.
- Suggest `/verify` for comprehensive validation.

## Safety Rules

- NEVER force-push to any branch
- NEVER delete files the plan does not name
- NEVER modify files outside the project directory
- NEVER skip verification steps
- NEVER commit without running at least basic validation
- If a step modifies more than 5 files, pause and confirm with the user
- If a step would delete more than 3 files, pause and confirm with the user
- Preserve existing file permissions and line endings

## Error Handling

- On an edit that fails or does not apply: re-read the file, retry ONCE with a materially
  different approach inside the plan's scope; if that fails, STOP with the pasted error.
- On a broken tree: `/rollback` to the checkpoint, then report the state. Do not hand-patch
  a half-applied change.
- On test failure: report which tests failed and why, suggest `/debug`.
- On build failure: report the error, check whether an earlier step caused it.

## Output

```
## Implementation Report

### Status: COMPLETE / PARTIAL / FAILED

### Changes Made
- Files created: [list]
- Files modified: [list]
- Files deleted: [list]

### Deviations from the plan
- [none, or list]

### Verification Results
- Build: PASS/FAIL
- Tests: PASS/FAIL (X passed, Y failed)
- Lint: PASS/FAIL

### Next Steps
- Run `/verify` for comprehensive validation
- Run `/git` to commit changes
```
