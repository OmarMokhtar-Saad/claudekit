---
description: "Validate plan via reviewer agent (90% threshold)"
model: opus
---

# Reviewer Command

Invoke the reviewer agent to validate the most recent implementation plan.

## Agent Reference

See @agents/reviewer.md for the full agent specification.

## Task

Validate the most recent plan.

## Mandatory Skills

You MUST load and apply the following skills before proceeding:

- **using-superpowers** - Core agent capabilities and tool usage
- **validate-operations-config** - ops.json schema and semantic validation
- **clean-architecture** - Architectural quality gates
- **security-checklist** - Security and safety validation

## Pre-Validation Check

Before scoring, verify these prerequisites:

1. A plan document exists in the current conversation or working directory
2. An ops.json file is present and parseable
3. The plan has a clear goal statement
4. The plan includes at least one verification step
5. **Run the Python validator** — this is MANDATORY, not optional:
   ```bash
   python3 .claude/operations/scripts/validate-config-json.py <path-to-ops.json>
   ```
   If the script exits non-zero OR prints `FAIL`, treat this as "ops.json is invalid" → automatic score 0 and REJECT. Do NOT proceed to scoring.
6. **Run the dry-run executor** — also MANDATORY:
   ```bash
   python3 .claude/operations/scripts/execute-json-ops.py <path-to-ops.json> --dry-run
   ```
   If the script exits non-zero, treat this as a blocking validation failure → REJECT.

If ANY prerequisite is missing, REJECT immediately with a clear explanation of what is missing.

## Mandatory Rejection Rules

Automatically score 0 and REJECT if any of the following are true:

- ops.json is missing or invalid JSON
- Plan modifies files outside the project directory
- Plan includes destructive git operations (force push, reset --hard) without explicit user request
- Plan has no rollback strategy for any step
- Plan creates files that duplicate existing functionality without justification
- Security-sensitive operations lack validation steps
- Plan violates clean architecture boundaries

## Scoring Formula

See the Reviewer agent specification for the scoring formula and evaluation criteria.

## Output Format

```
## Plan Review Report

### Summary
- **Plan**: [plan title or goal]
- **Score**: [final score]/100
- **Decision**: APPROVED / REVISE / REJECTED

### Dimension Scores
| Dimension    | Score | Weight | Weighted | Notes                |
|--------------|-------|--------|----------|----------------------|
| Completeness | XX    | 25%    | XX.X     | [brief note]         |
| Correctness  | XX    | 25%    | XX.X     | [brief note]         |
| Safety       | XX    | 20%    | XX.X     | [brief note]         |
| Architecture | XX    | 15%    | XX.X     | [brief note]         |
| Efficiency   | XX    | 10%    | XX.X     | [brief note]         |
| Clarity      | XX    | 5%     | XX.X     | [brief note]         |

### Issues Found
1. [CRITICAL/MAJOR/MINOR] Description of issue
   - Location: where in the plan
   - Suggestion: how to fix

### ops.json Validation
- Schema valid: YES/NO
- Operations count: N
- Semantic issues: [list or "None"]
```

## Decision Logic

- **Score >= 90**: APPROVED -- proceed to implementation with `/implement`
- **Score 70-89**: REVISE -- send back to planner with specific feedback, suggest `/plan` with refined arguments
- **Score < 70**: REJECTED -- fundamental issues must be resolved, explain why

## Post-Review

- If APPROVED: suggest running `/implement`
- If REVISE: list the specific changes needed and suggest re-running `/plan`
- If REJECTED: provide a clear explanation and suggest a different approach
