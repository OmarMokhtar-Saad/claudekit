---
name: validate-operations-config
description: "Use after /generate-ops - validates ops.json by running validator and dry-run"
disable-model-invocation: true
allowed-tools: Read, Bash, Grep, Glob
---

# Validate Operations Config

## Core Principle

**Never execute an unvalidated ops.json.** Validation catches errors before they reach your codebase.

---

## The Validation Process

```
[STEP 1] Run structural validator
    |
    v
[STEP 2] Run dry-run simulation
    |
    v
[STEP 3] Report verdict: PASS / FAIL / WARN
```

---

## Step 1: Structural Validation

Check the ops.json for structural correctness:

### Required Fields Check

| Field | Required | Validation |
|---|---|---|
| `version` | Yes | Must be "1.0" |
| `description` | Yes | Must be non-empty string |
| `operations` | Yes | Must be non-empty array |
| `operations[].id` | Yes | Must be unique across all operations |
| `operations[].type` | Yes | Must be one of: edit, create, delete, move, append, prepend, insert_after, insert_before |
| `operations[].target` | Yes | Must be a valid relative file path |
| `operations[].description` | Yes | Must be non-empty string |
| `execution_order` | Yes | Must contain all operation IDs |
| `rollback_order` | Yes | Must contain all operation IDs |

### Type-Specific Validation

**For `edit` operations:**
- `action` field must exist and be valid (replace, replace_all, delete_lines, wrap)
- `search` field must exist and be non-empty
- `replace` field must exist for replace/replace_all actions

**For `create` operations:**
- `content_source` must be one of: inline, template, copy
- If inline: `content` field must exist
- If copy: `source` field must exist and reference an existing file

**For `delete` operations:**
- Target file must currently exist

**For `move` operations:**
- `destination` field must exist
- Target file must currently exist
- Destination must not already exist

### Cross-Reference Validation

- No two operations target the same file with conflicting changes
- `execution_order` forms a valid dependency chain
- `rollback_order` is a valid reverse sequence
- All IDs referenced in execution/rollback orders exist in operations

---

## Step 2: Dry-Run Simulation

For each operation in execution order, simulate without modifying files:

### For Edit Operations

1. Read the target file
2. Search for the `search` string
3. Verify it exists exactly once (unless `replace_all`)
4. Verify the replacement would produce valid content
5. Report: "WOULD replace [N chars] at line [L] in [file]"

### For Create Operations

1. Verify the target path's parent directory exists
2. Verify the target file does NOT exist (or is expected to be overwritten)
3. Verify content is available (inline content exists, source file exists, etc.)
4. Report: "WOULD create [file] ([N bytes])"

### For Delete Operations

1. Verify the target file exists
2. Verify no other operation depends on this file AFTER this point in execution order
3. Report: "WOULD delete [file]"

### For Move Operations

1. Verify source exists
2. Verify destination does not exist
3. Verify destination directory exists
4. Check if any other operations reference the old path
5. Report: "WOULD move [source] -> [destination]"

---

## Step 3: Report Verdict

### PASS

All structural checks passed AND all dry-run simulations succeeded.

```
VALIDATION: PASS
- [N] operations validated
- [N] files will be modified
- [N] files will be created
- [N] files will be deleted
- Ready for execution
```

### WARN

Structural checks passed but dry-run found non-blocking issues.

```
VALIDATION: WARN
- [N] operations validated
- Warnings:
  - [warning 1]
  - [warning 2]
- Operations can proceed with caution
```

Common warnings:
- Search string matches multiple times (for non-replace_all)
- Target file has been modified since plan creation
- Large file modification (>100 lines changed)

### FAIL

Structural errors or dry-run failures found.

```
VALIDATION: FAIL
- Errors:
  - [error 1]
  - [error 2]
- Operations MUST NOT proceed
- Fix the errors and re-validate
```

Common failures:
- Search string not found in target file
- Target file does not exist
- Duplicate operation IDs
- Missing required fields
- Circular dependencies in execution order

---

## Handling Failures

When validation fails:

1. **Report all errors** (not just the first one)
2. **Suggest fixes** for each error
3. **Do NOT proceed** to execution
4. **Regenerate** ops.json if errors are extensive
5. **Re-validate** after fixes

---

## Quick Validation Checklist

For manual quick-checks when full validation is not available:

- [ ] All target files exist (for edit/delete)
- [ ] All search strings are findable in their target files
- [ ] No duplicate operation IDs
- [ ] Execution order makes logical sense
- [ ] Rollback order is reversed execution order
- [ ] Verification command is valid and runnable
