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

1. An approved plan exists (review score >= 90 or explicit user override). Verify
   mechanically — run each command as its OWN Bash invocation (the implementer tool grant
   is a literal prefix match; compound/assignment forms may not match):
   ```bash
   python3 .claude/operations/scripts/review-record.py resolve <plan.md>
   ```
   ```bash
   python3 .claude/operations/scripts/review-record.py check <plan.md> <resolved-ops-path>
   ```
   Exit 0 → the file matches an APPROVED, >= 90 record; proceed. Exit 2 → DRIFT: ops.json
   changed after approval; STOP and re-run `/review` (it scores only the delta). Exit 3 →
   no record; STOP and run `/review` first. Exit 4 → recorded verdict is not APPROVED /
   below 90; STOP and fix the findings. Exit 1 → the check itself could not run; STOP and
   report — never treat a non-zero exit as approval, and never re-run `check` in a retry
   loop hoping for a different result.
2. ops.json is present at the specified path (step 3's validator proves it is valid —
   you do not need to open it)
3. **Run the Python validator** (MANDATORY — do not skip):
   ```bash
   python3 .claude/operations/scripts/validate-config-json.py <path-to-ops.json> --stamp-baseline
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
- Run `validate-config-json.py <ops.json> --stamp-baseline` and read its verdict. Do NOT parse or read
  ops.json yourself — pass the path; the validator proves every anchor exists and is
  unique (GUARDs 10/11, simulated cumulatively) and the executor fails closed on drift.
- Note the validation commands recorded in plan.md for Phase 3

### Phase 2: Execution
The engine applies the whole batch in ONE invocation — there is no per-operation loop to
drive, and the implementer's tool grant (`Bash(python3 .claude/operations/scripts/*)`)
cannot run per-operation build/lint checks anyway.

1. Dry run: `execute-json-ops.py <ops.json> --dry-run` — abort on any failure
2. Execute: `execute-json-ops.py <ops.json>`
3. The engine backs up every target first and rolls the ENTIRE batch back on any
   failure. Never hand-patch a partial run.
4. Capture the unified diff and the final `RESULT-JSON:` line as your evidence of what
   changed, and relay them — do not re-read the target files to find out.

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
  scope (a verbatim retry reproduces the same failure); if the retry fails, STOP with the
  pasted error output — the engine has already rolled the ENTIRE batch back, so there is no
  per-step rollback to run and no partial state to hand-patch
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
