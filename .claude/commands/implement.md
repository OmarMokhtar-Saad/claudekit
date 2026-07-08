---
description: "Execute approved plan via implementer agent"
model: sonnet
---

# Implementer Command

Invoke the implementer agent to execute an approved implementation plan.

## Agent Reference

See @.claude/agents/implementer.md for the full agent specification.

## Task

Implement the approved plan.

## Mandatory Skills

You MUST load and apply the following skills before proceeding:

- **using-superpowers** - Core agent capabilities and tool usage
- **execute-operations-config** - ops.json execution engine
- **verification-before-completion** - Post-implementation verification gates

**On demand:** load **clean-architecture** when edits cross module boundaries.

## STEP 0: Pre-Flight Check

Before writing any code, verify ALL of the following:

1. An approved plan exists (review score >= 90 or explicit user override)
2. ops.json is present, valid, and parseable
3. **Run the Python validator** (MANDATORY — do not skip):
   ```bash
   python3 .claude/operations/scripts/validate-config-json.py <path-to-ops.json>
   ```
   If it exits non-zero or prints FAIL, STOP. Fix ops.json and re-run `/review` before proceeding.
4. **Run the dry-run executor** (MANDATORY — do not skip):
   ```bash
   python3 .claude/operations/scripts/execute-json-ops.py <path-to-ops.json> --dry-run
   ```
   If it exits non-zero, STOP. The ops.json has a runtime issue that must be resolved first.
5. No conflicting uncommitted changes in the working tree
6. All dependencies referenced in the plan are available

If ANY check fails, STOP and report the failure. Do NOT proceed without a validator PASS and a dry-run exit 0.

## IRON LAW

Execute operations EXACTLY as specified in ops.json using execute-json-ops.py.
Direct Edit or Write tool use is PERMANENTLY FORBIDDEN — even for minor post-script fixes.
If ops.json is missing, STOP immediately. Do not proceed. Return to the Planner.
If you must deviate from the ops.json spec, you need explicit user authorization.

## Script Execution Workflow

### Phase 1: Preparation
- Parse ops.json and validate all operations
- Create a checklist of all operations with status tracking
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
- Build, tests, and lint are independent — launch them in ONE batched message
- Validate no regressions introduced
- Every PASS/FAIL you report must quote the executed command's actual output (exit code,
  counts) — never estimate or fill in template numbers

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

- On operation failure: retry ONCE with a materially different approach within the ops.json
  scope (a verbatim retry reproduces the same failure); if the retry fails, attempt the
  specific rollback for that step and STOP with the pasted error output
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
