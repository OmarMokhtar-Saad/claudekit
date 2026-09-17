# Planner Reference

On-demand companion to `.claude/agents/planner.md`. Nothing here is optional: these are the
same rules the planner has always followed, moved out of the always-injected prompt so they
cost one Read instead of every token of every turn. Read this ONCE per run, before you
compose plan.md and ops.json.

---

## Plan Document Structure

**Plan structure:**
```markdown
# Implementation Plan: <Title>

## Overview
<1-3 sentence summary of what will be done and why>

## Scope
- **In Scope:** <what this plan covers>
- **Out of Scope:** <what this plan explicitly does NOT cover>

## Prerequisites
- <any setup, dependencies, or prior work needed>

## Implementation Steps

### Step 1: <Title>
- **File:** `path/to/file`
- **Action:** Create | Modify | Delete
- **Description:** <what to do>
- **Details:** <specific changes>
- **Done when:** <observable check> (~<N> min)

### Step 2: <Title>
...

## Testing Strategy
- <what tests to add or modify>
- <how to verify the changes work>

## Rollback Plan
- <how to undo these changes if needed>

## Risk Assessment
- **Low Risk:** <items>
- **Medium Risk:** <items>
- **High Risk:** <items>
```

---

## ops.json Hard Rules

**Hard rules the validator enforces (violating any one rejects the whole config):**
- Top-level key is `plan` (kebab-case string) — NOT `version`, `plan_ref`, or `description`.
- Operation `type` is exactly one of `file_create`, `file_delete`, `code_edit`,
  `run_command` — NOT `create`, `modify`, `delete`, `move`, or `rename`.
- `run_command` uses a `command` argv array (allowlisted executable basename, no shell)
  plus `reason`; max 5 per plan, and they must come AFTER all file operations.
- Paths use the `path` key — NOT `file` or `target`.
- `code_edit` uses an `edits` array; each entry has `find` + exactly one of
  `replace` / `add_after` / `add_before` / `delete: true` — NOT a `changes`/`action` block.
- `additionalProperties: false` — only `type`, `path`, the type-specific field, the optional
  payload-ref pair, and `id`/`description`. Rollback and validation notes go in **plan.md**.
- Max 3 `file_delete` operations per config (GUARD 26); split larger deletions across files.

---

## Tiered Briefing Format

### Simple Tasks (1-3 files, straightforward changes)
```
PLAN BRIEF (Simple)
====================
Task: <description>
Files: <list>
Steps: <numbered list, 1-2 lines each>
Ops Config: <path to ops.json>
Estimated Effort: Low
```

### Medium Tasks (4-10 files, some architectural decisions)
```
PLAN BRIEF (Medium)
====================
Task: <description>

Architecture Decision:
  <brief explanation of the approach chosen and why>

Files Affected:
  - <file> - <what changes>
  ...

Steps: <numbered list with brief descriptions>
Dependencies: <any new dependencies>
Ops Config: <path to ops.json>
Estimated Effort: Medium
```

### Complex Tasks (10+ files, significant architectural impact)
```
PLAN BRIEF (Complex)
====================
Task: <description>

Architecture Overview:
  <detailed explanation of the approach>
  <diagram if helpful>

Component Breakdown:
  Component 1: <name>
    Files: <list>
    Changes: <summary>

  Component 2: <name>
    Files: <list>
    Changes: <summary>

Integration Points:
  - <where components connect>

Migration Strategy:
  - <how to migrate existing code/data if applicable>

Steps: <detailed numbered list>
Risk Assessment: <high/medium/low items>
Dependencies: <new dependencies>
Ops Config: <path to ops.json>
Estimated Effort: High
```

---

## Automatic Reviewer Trigger

When the plan and ops.json are complete:

1. Save both files
2. Output the plan brief in the appropriate tier format
3. Include this handoff block at the end:

```
HANDOFF TO: reviewer
---
Plan File: <path to plan.md>
Ops Config: <path to ops.json>
Complexity: <Simple|Medium|Complex>
Files Affected: <count>
Steps: <count>
Risk Level: <Low|Medium|High>
```

---

## Operations Config Rules

When generating ops.json (schema owned by `generate-operations-config`):

1. **Every plan step MUST map to at least one operation**
2. **Operations MUST be ordered by dependency** (independent ops first) — encode order by
   position in the `operations` array; the schema has no `dependencies` field.
3. **Rollback, dependency, and validation notes live in plan.md**, not ops.json (the schema
   forbids extra fields).
4. **File paths MUST be relative to project root** (`path` key)
5. **`content` and `find` strings MUST be exact** — full file text for `file_create`; `find`
   copied verbatim from grep/Read output (exact whitespace), no pseudocode or placeholders.
6. **`find` patterns MUST be unique** within the target file (`grep -cF` returns 1)
7. **Every ops.json MUST pass `validate-config-json.py`** before handoff to the Reviewer.

---

## Handling Revision Feedback

If the Reviewer sends back feedback:

1. Address CRITICAL and MAJOR items; MINORs never block convergence
2. Revision mode (Discovery budget): no re-exploration; touch only what a finding names —
   an unrequested rewrite moves the reviewer's target and stalls the loop
3. Update BOTH files in place, re-run `validate-config-json.py`, report a ≤10-line summary
   keyed by finding ("F1: fixed by op X", "F3: disputed because ...")
4. Do NOT ask the user for permission to revise

---

## Quality Checklist (Self-Review Before Handoff)

Before handing off to the Reviewer, verify:

- [ ] Plan has a clear overview and scope
- [ ] Every step specifies the target file and action
- [ ] ops.json exists and PASSES `validate-config-json.py`
- [ ] Every plan step has a corresponding ops.json operation
- [ ] All file paths are correct and relative to project root
- [ ] Validation commands and rollback notes are in plan.md (not ops.json)
- [ ] Risk assessment is included
- [ ] Testing strategy is defined
- [ ] No placeholder or TODO content remains

---

## Output to Coordinator

When complete, provide:

```
Next action: <the single thing the caller should do now>
PLANNER COMPLETE
================
Plan: <path to plan.md>
Ops Config: <path to ops.json>
Complexity: <tier>
Steps: <count>
Files Affected: <count>
Risk: <level>
Status: Ready for Review
```
