---
name: generate-operations-config
description: "Use when making ANY code change - generates ops.json config for structured execution"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob
---

# Generate Operations Config

## Core Principle

**Every code change must be described as a structured operation before execution.** The ops.json config makes changes reviewable, validatable, and reversible.

---

## CANONICAL SCHEMA

ops.json MUST conform to the schema consumed by `execute-json-ops.py` and `validate-config-json.py`.
There are TWO valid formats — use MODERN for all new plans.

### MODERN FORMAT (required for mixed operations)

```json
{
  "plan": "kebab-case-plan-name",
  "operations": [
    {
      "type": "file_create",
      "path": "src/module/new_file.py",
      "content": "<full file content as a string>"
    },
    {
      "type": "file_delete",
      "path": "src/module/deprecated.py",
      "reason": "Removing deprecated module replaced by new_file.py"
    },
    {
      "type": "code_edit",
      "path": "src/module/file.py",
      "edits": [
        {
          "find": "def old_function(x):",
          "replace": "def new_function(x, y=None):"
        }
      ]
    }
  ]
}
```

### LEGACY FORMAT (code edits only, backward compat)

```json
{
  "plan": "kebab-case-plan-name",
  "files": [
    {
      "path": "src/module/file.py",
      "edits": [
        {
          "find": "def old_function(x):",
          "replace": "def new_function(x, y=None):"
        }
      ]
    }
  ]
}
```

---

## The Process

### Step 0: Find Existing Scripts and Patterns

Before creating ops.json:
- Check for existing build/task scripts in the project
- Look for Makefiles, package.json scripts, task runners
- Identify the project's existing automation patterns

### Step 1: Read All Target Files

For every file the operation will touch:
1. Read the full file content
2. Note the exact current state
3. Identify the specific lines/sections to change
4. Record any dependencies between files

### Step 2: Create ops.json

Write ops.json using ONLY the canonical types below. Any other type will be rejected by the validator.

#### Allowed Operation Types

| Type | Use when | Required fields |
|---|---|---|
| `file_create` | Creating a new file | `path`, `content` |
| `file_delete` | Removing a file | `path`, `reason` (min 10 chars) |
| `code_edit` | Editing an existing file | `path`, `edits` (array) |

**No other types are valid.** Do NOT use `edit`, `create`, `delete`, `move`, `append`, `git_commit`, or any other type — the executor will reject them.

#### code_edit — edits array actions

Each entry in `edits` requires `find` plus exactly one of:

| Action key | Effect |
|---|---|
| `add_after` | Insert content immediately after the found pattern |
| `add_before` | Insert content immediately before the found pattern |
| `replace` | Replace the found pattern with new content |
| `delete: true` | Remove the found pattern |

#### Hard limits enforced by the executor

- Max **5** operations per ops.json
- Max **3** `file_delete` operations per ops.json
- Max **2 MB** per file
- `path` must be relative and inside the project directory

If the plan requires more than 5 operations, split into multiple ops.json files (ops-1.json, ops-2.json, …).

### Step 3: Self-Check

After creating ops.json, verify:
- [ ] Top-level key is `plan` (string, kebab-case) — NOT `version` or `description`
- [ ] All operation types are exactly `file_create`, `file_delete`, or `code_edit`
- [ ] All paths use `path` key — NOT `target`
- [ ] Every `file_create` has a non-empty `content` field with full file text
- [ ] Every `file_delete` has a `reason` field of at least 10 characters
- [ ] Every `code_edit` has an `edits` array where each item has `find` + one action key
- [ ] `find` strings are copied verbatim from the Read tool output (exact whitespace)
- [ ] Total operations ≤ 5; total `file_delete` ≤ 3

---

## Example: Renaming a Function

```json
{
  "plan": "rename-calculate-total",
  "operations": [
    {
      "type": "code_edit",
      "path": "src/orders/calculator.py",
      "edits": [
        {
          "find": "def calculate_total(",
          "replace": "def compute_order_total("
        }
      ]
    },
    {
      "type": "code_edit",
      "path": "src/orders/service.py",
      "edits": [
        {
          "find": "calculate_total(",
          "replace": "compute_order_total("
        }
      ]
    },
    {
      "type": "code_edit",
      "path": "tests/orders/test_calculator.py",
      "edits": [
        {
          "find": "calculate_total(",
          "replace": "compute_order_total("
        }
      ]
    }
  ]
}
```

---

## After Generation

Once ops.json is created:
1. Run the validator immediately: `python3 .claude/operations/scripts/validate-config-json.py ops.json`
2. If the validator prints FAIL, fix the errors and re-validate before proceeding
3. Present the validated ops.json to the user for review (golden-rule)
4. Run dry-run: `python3 .claude/operations/scripts/execute-json-ops.py ops.json --dry-run`
5. Only then execute (execute-operations-config skill)
