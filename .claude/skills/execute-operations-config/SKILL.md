---
name: execute-operations-config
description: "Use after /validate-ops - executes approved ops.json via execute-json-ops.py with backup and rollback"
disable-model-invocation: true
allowed-tools: Read, Bash, Grep, Glob
---

# Execute Operations Config

## Core Principle

**Never apply ops.json changes by hand.** All changes are applied by the execution engine,
`execute-json-ops.py`, which provides atomic ordering, automatic pre-change backup, and
automatic rollback on failure.

> ## IRON LAW (matches the Implementer agent)
> Direct use of the **Edit** or **Write** tools to apply an operation is FORBIDDEN — with or
> without ops.json. The `ops-enforcement.sh` hook blocks manual edits to files under an ops
> plan. The only permitted way to apply changes is the execution script below. If the executor
> can't apply an operation, STOP and report — do not hand-edit around it.

---

## Prerequisites

Before execution, confirm:
- [ ] ops.json has been generated (`generate-operations-config`) in the canonical MODERN schema
      (`plan` + `operations[]` of `file_create` / `file_delete` / `code_edit`)
- [ ] ops.json has PASSED `validate-config-json.py`
- [ ] User has approved the operations (golden-rule)

If ANY prerequisite is missing, **STOP** and complete it first.

---

## The Execution Process

```
[STEP 1] Dry run   -> execute-json-ops.py <ops.json> --dry-run
    |
    v
[STEP 2] Execute   -> execute-json-ops.py <ops.json>   (auto-backup + auto-rollback)
    |
    v
[STEP 3] Verify    -> run the plan.md build/test/lint commands
    |
    v
[REPORT] Summary of changes + backup location for rollback
```

## Step 1: Dry Run

```bash
python3 .claude/operations/scripts/execute-json-ops.py <ops.json> --dry-run
```

Review the preview:
- Every operation targets the expected file, with the expected change
- No unexpected file is touched
- If anything looks wrong → STOP, fix ops.json, re-validate, re-dry-run

## Step 2: Execute

```bash
python3 .claude/operations/scripts/execute-json-ops.py <ops.json>
```

The engine, not you, applies each operation:
- It backs up every file it will modify or delete **before** touching anything
  (manifest compatible with `restore-backup.py`).
- It applies operations in array order.
- On ANY failure it **automatically rolls back** the whole batch from the backup.

Do not use Edit/Write to "finish" a partial run. If the run fails, read the engine's output,
fix the ops.json, and re-run the script from the dry-run step.

## Step 3: Verify

Run the build / test / lint commands recorded in **plan.md** (they are not stored in ops.json):

```bash
# examples — use the project's real commands from plan.md
python3 -m pytest -q
ruff check src/ tests/
```

Record the output and determine PASS or FAIL. If verification FAILS, offer rollback (below).

---

## Execution Report

```
## Execution Report

### Summary
- Operations executed: [N] of [M]   (engine reports this; SUCCESS means all M applied)
- Status: SUCCESS / ROLLED BACK

### Operations
| Type        | Path                        | Status  |
|-------------|-----------------------------|---------|
| code_edit   | src/module/file.py          | SUCCESS |
| file_create | src/module/new_file.py      | SUCCESS |
| file_delete | src/module/deprecated.py    | SUCCESS |

### Verification
- Build/test/lint (from plan.md): PASS / FAIL

### Rollback
- Backup created at: <path printed by the engine>
- To roll back:  /rollback latest   (or restore-backup.py --list then restore)
```

---

## Rollback

The engine rolls back automatically on a failed run. To undo a **completed** run afterward,
use the backup it created — never hand-revert:

```bash
python3 .claude/operations/scripts/restore-backup.py --list      # find the backup
python3 .claude/operations/scripts/restore-backup.py <backup-name>
```

Or run the `/rollback` command, which wraps `restore-backup.py`.

---

## Error Handling

### The engine reports a failed operation
The batch has already been rolled back. Read the reason (pattern not found, path outside
project, protected file, etc.), fix ops.json, re-validate, and re-run from Step 1.
**Do not** attempt a manual Edit to patch the single failing operation.

### Verification fails after a clean run
All operations applied but the build/tests fail. Investigate; if the change is bad, roll back
with `restore-backup.py` / `/rollback`, then revise the plan and ops.json.
