# Workflow File Templates

Standard templates for workflow files used across ClaudeKit agents. These templates define the structure for plans, reviews, reports, and handoffs.

---

## Plan File Template

**Location:** `.claude/plans/plan-<descriptor>.md`

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

### Step 2: <Title>
- **File:** `path/to/file`
- **Action:** Create | Modify | Delete
- **Description:** <what to do>
- **Details:** <specific changes>

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

## Operations Config Template

**Location:** `.claude/plans/ops-<descriptor>.json`

**Schema owners:** `.claude/skills/generate-operations-config/SKILL.md` (CANONICAL SCHEMA) and
`.claude/operations/scripts/operations-schema.json`. This template is a convenience copy — if it
ever disagrees with them, they win. The example below is executed against the real
`validate-config-json.py` by `tests/test_agent_doc_ops_examples.py`, so it cannot drift.

```json
{
  "plan": "add-user-repository",
  "operations": [
    {
      "type": "file_create",
      "path": "src/repositories/user_repository.py",
      "content": "class UserRepository:\n    def find_by_id(self, user_id):\n        raise NotImplementedError\n"
    },
    {
      "type": "code_edit",
      "path": "src/services/user_service.py",
      "edits": [
        {
          "find": "from src.repositories.legacy_repo import LegacyRepo",
          "replace": "from src.repositories.user_repository import UserRepository"
        },
        {
          "find": "        self.repo = LegacyRepo()",
          "replace": "        self.repo = UserRepository()"
        }
      ]
    },
    {
      "type": "file_delete",
      "path": "src/repositories/legacy_repo.py",
      "reason": "Superseded by user_repository.py created earlier in this plan"
    }
  ]
}
```

Rules the validator enforces — violating any one rejects the whole config:

| Rule | Detail |
|------|--------|
| Top-level keys | `plan` (kebab-case) plus exactly one of `operations` (modern) or `files` (legacy, code edits only). No `version`, `plan_ref`, `description`, `validation`. |
| Operation types | exactly `file_create`, `file_delete`, `code_edit`. Never `create`/`modify`/`delete`/`move`/`rename`. |
| Path key | `path`, relative to the project root. Never `file` or `target`. |
| Per-type fields | `file_create` needs `content` (non-empty); `file_delete` needs `reason` (>= 10 chars); `code_edit` needs `edits` (non-empty array). Optional on any operation: `id`, `description`. |
| Edit actions | each `edits` entry is `find` plus exactly one of `replace`, `add_after`, `add_before`, `delete: true`. Never a `changes`/`action`/`target` block. |
| Unknown fields | `additionalProperties: false` — any other key rejects the whole config. Rollback notes, dependency ordering and validation commands belong in **plan.md**, not here. |
| Deletions | at most 3 `file_delete` operations per config (GUARD 26); split larger removals across configs. |
| `find` patterns | copied verbatim from the file (exact whitespace) and unique within it — ambiguous or missing matches are rejected. |

Execution order is array order; the schema has no `dependencies` field. Validate before handoff:

```bash
python3 .claude/operations/scripts/validate-config-json.py .claude/plans/ops-<descriptor>.json
```

---

## Review Report Template

**Location:** `.claude/reports/review-<descriptor>.md`

```markdown
# Review Report: <Plan Title>

Date: <YYYY-MM-DD>
Plan: <path to plan.md>
Ops Config: <path to ops.json>

## Pre-Validation
- [x] plan.md exists
- [x] ops.json exists
- [x] Valid JSON
- [x] Operations match steps
- [x] Required sections present

## Scores
| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Plan Quality | /100 | 40% | |
| Architecture | /100 | 30% | |
| Security | /100 | 30% | |
| **Total** | | | **/100** |

## Decision
**APPROVED** | **CONDITIONAL** | **REJECTED**

## Findings

### Critical (must fix)
1. <finding>

### Warnings (should fix)
1. <finding>

### Notes (nice to have)
1. <finding>

## Feedback for Planner
<specific, actionable feedback if not approved>
```

---

## Verification Report Template

**Location:** `.claude/reports/verification-<descriptor>.md`

```markdown
# Verification Report: <Title>

Date: <YYYY-MM-DD>
Files Verified: <count>

## Static Analysis
- Tool: <name>
- Errors: <count>
- Warnings: <count> (<new> new)
- Score: /100

## Tests
- Framework: <name>
- Passed: <N>
- Failed: <N>
- Skipped: <N>
- New Tests: <N>
- Score: /100

## Coverage
- Tool: <name>
- Overall: <N>%
- Modified Files: <N>%
- Delta: <+/- N>%
- Score: /100

## Anti-Pattern Penalties
- <pattern>: -<N>
- Total: -<N>

## Final Score
| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Static Analysis | /100 | 30% | |
| Tests | /100 | 40% | |
| Coverage | /100 | 30% | |
| Penalties | | | -<N> |
| **Total** | | | **/100** |

## Decision
**PASS** | **RETRY** | **FAIL**

## Issues
<list of issues with file paths and line numbers>
```

---

## Exploration Report Template

**Location:** `.claude/reports/explore-<descriptor>.md`

```markdown
# Exploration Report: <Question/Topic>

Date: <YYYY-MM-DD>
Thoroughness: Quick | Medium | Very Thorough

## Purpose
<what was being explored and why>

## Scope
<what parts of the codebase were examined>

## Target Files
| File | Relevance | Description |
|------|-----------|-------------|
| path/to/file | High | <description> |

## Findings
<structured findings organized by topic>

## Patterns Observed
- <pattern 1>
- <pattern 2>

## Constraints
- <constraint 1>
- <constraint 2>

## Planner Handoff
<structured summary for the Planner agent, if applicable>
```

---

## Debug Report Template

**Location:** `.claude/reports/debug-<descriptor>.md`

```markdown
# Debug Report: <Bug Title>

Date: <YYYY-MM-DD>
Confidence: <Low|Medium|High> (<N>%)

## Error Description
<what the error is>

## Reproduction
<steps to reproduce, or "not reproducible">

## Root Cause Analysis
<identified root cause with file paths and line numbers>

## Evidence
1. <evidence item>
2. <evidence item>

## Suggested Fix
<high-level description of the fix>

## Affected Files
| File | Issue | Severity |
|------|-------|----------|
| path/to/file | <description> | High |

## Handoff to Planner
<structured context for creating a fix plan>
```

---

## Workflow State Template

**Location:** `.claude/state/workflow-<id>.json`

```json
{
  "workflow_id": "<uuid-short>",
  "classification": "<Feature|Bug|Quality|Git|Docs|Explore|Refactor>",
  "task_description": "<what was requested>",
  "pipeline": ["planner", "reviewer", "implementer", "verifier", "gitOps"],
  "current_step": 0,
  "status": "pending",
  "revision_count": 0,
  "max_revisions": 3,
  "started_at": "<ISO timestamp>",
  "history": [],
  "context": {}
}
```

---

## Handoff File Template

**Location:** `.claude/state/handoff-<id>.md`

```markdown
# Handoff: <Source Agent> to <Target Agent>

## Context
Task: <description>
Classification: <type>
Pipeline Position: Step <N> of <M>

## Prior Agent Output
<summary of what the previous agent produced>

## Files
- <file path> (<status: modified/created/reviewed>)

## Constraints
- <constraint 1>
- <constraint 2>

## Expected Output
<what the target agent should produce>

## Return To
<agent to hand off to after completion>
```
