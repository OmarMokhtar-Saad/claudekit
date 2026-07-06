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

| Type | Required fields | Optional fields |
|---|---|---|
| `file_create` | `path`, `content` | `id`, `description` |
| `file_delete` | `path`, `reason` (min 10 chars) | `id`, `description` |
| `code_edit` | `path`, `edits` (array) | `id`, `description` |

**No other types are valid.** Do NOT use `edit`, `create`, `delete`, `move`, `append`, `git_commit`, or any other type — the executor will reject them.

**No other fields are valid.** Do NOT add fields like `label`, `name`, `comment`, `meta`, or any key not listed above — `additionalProperties: false` in the schema will reject the entire config.

#### code_edit — edits array actions

Each entry in `edits` requires `find` plus exactly one of:

| Action key | Effect |
|---|---|
| `add_after` | Insert content immediately after the found pattern |
| `add_before` | Insert content immediately before the found pattern |
| `replace` | Replace the found pattern with new content |
| `delete: true` | Remove the found pattern |

#### Hard limits enforced by the executor

- `path` must be relative and inside the project directory

There is no cap on operation count or file size. Split into sequenced files (ops-1.json, ops-2.json, …) only when it aids review clarity.

### Step 3: Self-Check

After creating ops.json, verify:
- [ ] Top-level key is `plan` (string, kebab-case) — NOT `version` or `description`
- [ ] All operation types are exactly `file_create`, `file_delete`, or `code_edit`
- [ ] All paths use `path` key — NOT `target`
- [ ] Every `file_create` has a non-empty `content` field with full file text
- [ ] Every `file_delete` has a `reason` field of at least 10 characters
- [ ] Every `code_edit` has an `edits` array where each item has `find` + one action key
- [ ] `find` strings are copied verbatim from the Read tool output (exact whitespace)
- [ ] Each operation only has allowed fields: required (`type`, `path`, + type-specific) and optional (`id`, `description`). No other fields.

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
