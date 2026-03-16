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

## The Process

### Step 0: Find Existing Scripts and Patterns

Before creating ops.json:
- Check for existing build/task scripts in the project
- Look for Makefiles, package.json scripts, task runners
- Identify the project's existing automation patterns
- Adapt your ops.json to work with existing tooling

### Step 1: Read All Target Files

For every file the operation will touch:
1. Read the full file content
2. Note the exact current state
3. Identify the specific lines/sections to change
4. Record any dependencies between files

### Step 2: Create ops.json

Write the ops.json file in the project's working directory.

#### Modern ops.json Format

```json
{
  "version": "1.0",
  "description": "Brief description of what this set of operations achieves",
  "operations": [
    {
      "id": "op-001",
      "type": "edit",
      "target": "src/module/file.py",
      "action": "replace",
      "description": "Replace old function signature with new one",
      "search": "def old_function(x):",
      "replace": "def new_function(x, y=None):",
      "verification": "grep -n 'def new_function' src/module/file.py"
    },
    {
      "id": "op-002",
      "type": "create",
      "target": "src/module/new_file.py",
      "description": "Create new module for extracted logic",
      "content_source": "inline",
      "verification": "test -f src/module/new_file.py"
    },
    {
      "id": "op-003",
      "type": "delete",
      "target": "src/module/deprecated.py",
      "description": "Remove deprecated module",
      "verification": "test ! -f src/module/deprecated.py"
    }
  ],
  "execution_order": ["op-001", "op-002", "op-003"],
  "rollback_order": ["op-003", "op-002", "op-001"],
  "verification_command": "npm test"
}
```

### Step 3: Self-Check

After creating ops.json, verify:
- [ ] Every target file exists (for edit/delete operations)
- [ ] No target file appears in conflicting operations
- [ ] Search strings are exact matches (copy from Read output)
- [ ] Execution order respects dependencies
- [ ] Rollback order is the reverse of execution
- [ ] Verification commands are valid

---

## Operation Types

| Type | Description | Required Fields |
|---|---|---|
| `edit` | Modify existing file content | target, action, search, replace |
| `create` | Create a new file | target, content_source |
| `delete` | Remove a file | target |
| `move` | Rename or move a file | target, destination |
| `append` | Add content to end of file | target, content |
| `prepend` | Add content to start of file | target, content |
| `insert_after` | Insert content after a match | target, search, content |
| `insert_before` | Insert content before a match | target, search, content |

---

## Edit Actions

| Action | Description | Required Fields |
|---|---|---|
| `replace` | Replace matched text with new text | search, replace |
| `replace_all` | Replace all occurrences | search, replace |
| `delete_lines` | Remove matched lines | search |
| `wrap` | Wrap matched text with prefix/suffix | search, prefix, suffix |

---

## Constraints

### Search Strings Must Be Exact

The `search` field must be an EXACT copy of the text in the target file. This means:
- Copy it directly from the Read tool output
- Preserve indentation (tabs vs spaces)
- Preserve line endings
- Include enough context to be unique within the file

### One Responsibility Per Operation

Each operation should make ONE logical change. If you need to:
- Change a function signature AND update its callers: separate operations
- Create a file AND import it somewhere: separate operations
- Delete old code AND add new code: separate operations

### Order Matters

The `execution_order` must ensure:
- Files are created before they are referenced
- Interfaces are defined before implementations
- Imports are updated after the imported module exists
- Tests are updated alongside the code they test

---

## Content Source Options

For `create` operations, `content_source` can be:

- `"inline"` - Content is provided in a `content` field in the operation
- `"template"` - Content is generated from a template with variables
- `"copy"` - Content is copied from another file (specified in `source` field)

---

## Example: Renaming a Function

```json
{
  "version": "1.0",
  "description": "Rename calculate_total to compute_order_total across codebase",
  "operations": [
    {
      "id": "rename-definition",
      "type": "edit",
      "target": "src/orders/calculator.py",
      "action": "replace",
      "search": "def calculate_total(",
      "replace": "def compute_order_total(",
      "description": "Rename function at definition site"
    },
    {
      "id": "rename-caller-1",
      "type": "edit",
      "target": "src/orders/service.py",
      "action": "replace_all",
      "search": "calculate_total(",
      "replace": "compute_order_total(",
      "description": "Update caller in service module"
    },
    {
      "id": "rename-test",
      "type": "edit",
      "target": "tests/orders/test_calculator.py",
      "action": "replace_all",
      "search": "calculate_total(",
      "replace": "compute_order_total(",
      "description": "Update test references"
    }
  ],
  "execution_order": ["rename-definition", "rename-caller-1", "rename-test"],
  "rollback_order": ["rename-test", "rename-caller-1", "rename-definition"],
  "verification_command": "python -m pytest tests/orders/"
}
```

---

## After Generation

Once ops.json is created:
1. Present it to the user for review (golden-rule)
2. Run validation (validate-operations-config skill)
3. Only then execute (execute-operations-config skill)
