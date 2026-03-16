---
description: "Execute approved plan via implementer agent"
model: sonnet
---

# Implementer Command

Invoke the implementer agent to execute an approved implementation plan.

## Agent Reference

See @agents/implementer.md for the full agent specification.

## Task

Implement the approved plan.

## Mandatory Skills

You MUST load and apply the following skills before proceeding:

- **using-superpowers** - Core agent capabilities and tool usage
- **execute-operations-config** - ops.json execution engine
- **clean-architecture** - Architectural compliance during implementation
- **verification-before-completion** - Post-implementation verification gates

## STEP 0: Pre-Flight Check

Before writing any code, verify ALL of the following:

1. An approved plan exists (review score >= 90 or explicit user override)
2. ops.json is present, valid, and parseable
3. All target directories exist or can be created
4. No conflicting uncommitted changes in the working tree
5. All dependencies referenced in the plan are available

If ANY check fails, STOP and report the failure. Do NOT proceed without a valid ops.json.

## IRON LAW

Execute operations EXACTLY as specified in ops.json. Do not improvise, skip steps, or reorder operations unless a blocking error requires it. If you must deviate, document the deviation and the reason.

## Script Execution Workflow

### Phase 1: Preparation
- Parse ops.json and validate all operations
- Create a checklist of all operations with status tracking
- Identify any operations that can be parallelized
- Set up verification checkpoints

### Phase 2: Execution
For each operation in ops.json order:
1. Announce: "Executing step N of M: [operation description]"
2. Execute the operation
3. Verify the operation succeeded (compile check, lint, basic test)
4. Mark the operation as complete
5. If the operation fails, attempt the rollback procedure from the plan
6. If rollback fails, STOP and report

### Phase 3: Verification
- Run all verification steps defined in the plan
- Execute project build (if applicable)
- Run affected test suites
- Validate no regressions introduced

### Phase 4: Report
- Summarize all operations executed
- List any deviations from the plan
- Report verification results
- Suggest running `/verify` for comprehensive validation

## Safety Rules

- NEVER force-push to any branch
- NEVER delete files not specified in ops.json
- NEVER modify files outside the project directory
- NEVER skip verification steps
- NEVER commit without running at least basic validation
- If a step modifies more than 5 files, pause and confirm with the user
- If a step would delete more than 3 files, pause and confirm with the user
- Always create files before referencing them in other files
- Preserve existing file permissions and line endings

## Error Handling

- On first failure: attempt the specific rollback for that step
- On rollback failure: STOP immediately, report state, suggest manual intervention
- On test failure: report which tests failed and why, suggest `/debug` for investigation
- On build failure: report the error, check if a previous step caused it

## Output

After all operations complete, provide:

```
## Implementation Report

### Status: COMPLETE / PARTIAL / FAILED

### Operations Summary
- Total: N
- Succeeded: N
- Failed: N
- Skipped: N

### Changes Made
- Files created: [list]
- Files modified: [list]
- Files deleted: [list]

### Verification Results
- Build: PASS/FAIL
- Tests: PASS/FAIL (X passed, Y failed)
- Lint: PASS/FAIL

### Next Steps
- Run `/verify` for comprehensive validation
- Run `/git` to commit changes
```
