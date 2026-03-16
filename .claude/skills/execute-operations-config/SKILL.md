---
name: execute-operations-config
description: "Use after /validate-ops - executes approved ops.json with backup and verification"
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# Execute Operations Config

## Core Principle

**Execute only validated, approved operations.** Every execution includes backup, verification, and rollback capability.

---

## Prerequisites

Before execution, confirm:
- [ ] ops.json has been generated (generate-operations-config)
- [ ] ops.json has been validated (validate-operations-config) with PASS verdict
- [ ] User has approved the operations (golden-rule)

If ANY prerequisite is missing, **STOP** and complete it first.

---

## The Execution Process

```
[STEP 1] Final dry-run confirmation
    |
    v
[STEP 2] Execute operations in order
    |
    v
[STEP 3] Verify each operation succeeded
    |
    v
[STEP 4] Run final verification command
    |
    v
[REPORT] Summary of all changes
```

---

## Step 1: Final Dry-Run

Even though validation passed, run one final check:

1. Verify all target files still exist and have not changed since validation
2. If files have changed, STOP and re-validate
3. Confirm: "Dry-run passed. Proceeding with execution."

---

## Step 2: Execute Operations

Process each operation in `execution_order`:

### Edit Operations

```
1. Read current file content
2. Find the search string
3. Apply the replacement
4. Write the modified content using Edit tool
5. Verify the edit took effect
```

### Create Operations

```
1. Prepare content (from inline, template, or copy source)
2. Write the file using Write tool
3. Verify the file exists
```

### Delete Operations

```
1. Confirm file exists
2. Note the file path for rollback record
3. Delete the file
4. Verify deletion
```

### Move Operations

```
1. Confirm source exists and destination does not
2. Execute the move
3. Verify source is gone and destination exists
```

### Execution Rules

- Execute operations **one at a time** in the specified order
- After each operation, verify it succeeded before proceeding
- If ANY operation fails, **STOP** immediately
- Do not attempt to continue past a failed operation
- Record the result of each operation for the report

---

## Step 3: Per-Operation Verification

After each operation, run its `verification` command if specified:

```
Operation op-001: EXECUTED
  Verification: grep -n 'def new_function' src/module/file.py
  Result: PASS (found at line 42)

Operation op-002: EXECUTED
  Verification: test -f src/module/new_file.py
  Result: PASS (file exists)
```

If verification fails:
1. Record the failure
2. Stop execution
3. Report which operation failed and why
4. Provide rollback instructions

---

## Step 4: Final Verification

After all operations complete successfully:

1. Run the `verification_command` from ops.json (typically test suite)
2. Record the full output
3. Determine PASS or FAIL

```
Final Verification: npm test
Result: PASS (47 tests passed, 0 failed)
```

If final verification fails:
- Report which tests/checks failed
- Provide the test output
- Suggest investigation steps
- Offer rollback

---

## Execution Report

After execution completes, provide:

```
## Execution Report

### Summary
- Operations executed: [N] of [M]
- Status: SUCCESS / PARTIAL / FAILED

### Operations
| ID | Type | Target | Status |
|---|---|---|---|
| op-001 | edit | src/module/file.py | SUCCESS |
| op-002 | create | src/module/new_file.py | SUCCESS |
| op-003 | delete | src/module/deprecated.py | SUCCESS |

### Verification
- Per-operation checks: [N] PASS, [N] FAIL
- Final verification: PASS / FAIL

### Files Changed
- Modified: [list]
- Created: [list]
- Deleted: [list]

### Rollback
If rollback needed, execute in this order:
1. [rollback step 1]
2. [rollback step 2]
3. [rollback step 3]
```

---

## Rollback Instructions

If the user requests rollback:

### Using Git (preferred)

```bash
git checkout -- <modified files>
git clean -f <created files>
```

### Manual Rollback

Follow the `rollback_order` from ops.json, reversing each operation:
- For `edit`: reverse the search/replace
- For `create`: delete the created file
- For `delete`: restore from git or backup
- For `move`: move back to original location

---

## Error Handling

### Operation Fails to Apply

```
ERROR: Operation [id] failed
Reason: [search string not found / file not writable / etc.]
Action: Execution halted at operation [id]
Completed: [N] of [M] operations
Rollback: [provide rollback for completed operations]
```

### Verification Fails

```
WARNING: Operation [id] applied but verification failed
Verification command: [command]
Expected: [expected result]
Actual: [actual result]
Action: Investigate before continuing
```

### Final Verification Fails

```
WARNING: All operations applied but final verification failed
Command: [verification command]
Output: [output]
Action: Review test failures, may need rollback
```
