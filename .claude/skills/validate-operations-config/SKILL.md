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
[STEP 1] Run the Python structural validator (REQUIRED)
    |
    v
[STEP 2] Run dry-run simulation via Python executor (REQUIRED)
    |
    v
[STEP 3] Report verdict: PASS / FAIL / WARN
```

**Both steps MUST use the actual Python scripts** — do NOT substitute in-context reasoning for these checks. The scripts enforce 29 safety guards that cannot be reliably replicated in a language model response.

---

## Step 1: Run the Structural Validator

Use the Bash tool to run the Python validator:

```bash
python3 .claude/operations/scripts/validate-config-json.py <path-to-ops.json>
```

If the script is not at that path, search for it:
```bash
find . -name "validate-config-json.py" -not -path "*/node_modules/*"
```

**Interpret the output:**
- Script exits 0 AND prints `PASS` or `WARN` → continue to Step 2
- Script exits non-zero OR prints `FAIL` → **STOP. Report all errors. Do NOT proceed to Step 2 or execution.**

The validator checks (among 29 guards):
- `plan` key exists and is non-empty
- `operations` or `files` array is present and non-empty
- All operation types are exactly `file_create`, `file_delete`, or `code_edit`
- `file_create` has `path` and non-empty `content`
- `file_delete` has `path` and `reason` (min 10 chars), and the file exists
- `code_edit` has `path`, `edits` array, each edit has `find` key, and all `find` patterns exist in the target file
- No path traversal, null bytes, or paths outside the project
- Max 5 operations, max 3 deletions, max 2 MB file size

---

## Step 2: Run the Dry-Run Executor

Use the Bash tool to run the dry-run:

```bash
python3 .claude/operations/scripts/execute-json-ops.py <path-to-ops.json> --dry-run
```

**Interpret the output:**
- All operations print `[DRY RUN] Would ...` and the script exits 0 → PASS
- Any operation fails or script exits non-zero → **STOP. Report which operation failed. Do NOT proceed to execution.**

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

For manual quick-checks when the Python scripts are unavailable (e.g., missing venv):

- [ ] Top-level key is `plan` (not `version`, `description`, or `id`)
- [ ] All operation types are exactly `file_create`, `file_delete`, or `code_edit` — no other values
- [ ] All paths use `path` key — NOT `target`
- [ ] Every `file_create` has a non-empty `content` field
- [ ] Every `file_delete` has a `reason` field with at least 10 characters
- [ ] Every `code_edit` has an `edits` array; each item has a `find` key
- [ ] All `find` strings exist verbatim in their target files
- [ ] Total operations ≤ 5; total `file_delete` operations ≤ 3
