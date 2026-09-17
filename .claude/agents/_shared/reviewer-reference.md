# Reviewer Reference

On-demand companion to `.claude/agents/reviewer.md`. These rules are binding; they were moved
out of the always-injected prompt so they cost one Read per review instead of a full copy on
every turn. Read this ONCE, before you score. The machine-readable `=== REVIEW ===` verdict
block is NOT here — it stays in reviewer.md, because emitting a verdict must never depend on
having read another file.

---

## Scoring Criteria Tables

### Plan Quality (40% weight) - Score 0-100

| Criteria                        | Points | Description                                          |
|---------------------------------|--------|------------------------------------------------------|
| Clarity of overview             | 15     | Is the purpose and scope clearly stated?             |
| Step completeness               | 20     | Are all steps detailed with file paths and actions?  |
| ops.json accuracy               | 25     | Do operations match steps? Are contents exact?       |
| Testing strategy                | 15     | Are tests defined? Do they cover the changes?        |
| Rollback plan                   | 10     | Is there a clear undo strategy?                      |
| Risk assessment                 | 10     | Are risks identified and mitigated?                  |
| Documentation                   | 5      | Is the plan well-organized and readable?             |

### Architecture (30% weight) - Score 0-100

| Criteria                        | Points | Description                                          |
|---------------------------------|--------|------------------------------------------------------|
| Separation of concerns          | 20     | Does the plan maintain clean boundaries?             |
| Dependency management           | 15     | Are new dependencies justified and minimal?          |
| Interface design                | 15     | Are public APIs clean and well-defined?              |
| Consistency with existing code  | 20     | Does the plan follow established patterns?           |
| Scalability considerations      | 15     | Will the changes scale with the project?             |
| Testability                     | 15     | Are changes designed to be testable?                 |

### Security (30% weight) - Score 0-100

| Criteria                        | Points | Description                                          |
|---------------------------------|--------|------------------------------------------------------|
| Input validation                | 20     | Are all inputs validated and sanitized?              |
| Authentication/Authorization    | 20     | Are auth boundaries respected?                       |
| Data handling                   | 20     | Is sensitive data properly handled?                  |
| Dependency security             | 15     | Are new dependencies vetted?                         |
| Error handling                  | 15     | Do errors leak information? Are they handled safely? |
| Configuration security          | 10     | Are configs secure by default?                       |

---

## Validation Steps

### Step 1: Structural Validation
```
1. Verify plan.md structure has all required sections
2. Parse ops.json and validate schema
3. Cross-reference plan steps with ops.json operations
4. Check for orphaned operations or phantom steps
5. Validate file paths exist (or are new files being created)
```

### Step 2: Plan Quality Review
```
1. Read the plan overview - is it clear and complete?
2. For each step:
   a. Is the file path specified?
   b. Is the action clear (create/modify/delete)?
   c. Are the details specific enough to implement?
3. Check ops.json operations:
   a. Are content strings exact (not pseudocode)?
   b. Are search patterns unique within target files?
   c. Are dependencies correctly specified?
4. Evaluate testing strategy
5. Evaluate rollback plan
6. Assess risk identification
```

### Step 3: Architecture Review
```
1. Identify architectural patterns in the existing codebase
2. Check if the plan follows or violates these patterns
3. Evaluate new abstractions and interfaces
4. Check dependency impact (new imports, new packages)
5. Assess coupling between modified components
6. Check for unnecessary complexity
```

### Step 4: Security Review
```
1. Scan for hardcoded credentials or secrets
2. Check input validation on all new endpoints or interfaces
3. Verify error messages don't leak sensitive information
4. Check for SQL injection, XSS, or other injection vectors
5. Verify auth boundaries are maintained
6. Check file system operations for path traversal
7. Validate configuration defaults are secure
```

---

## Human-Facing Report Template

The template below is the human-facing report that accompanies the anchored verdict block.

```
REVIEW REPORT
=============

Plan: <path to plan.md>
Ops Config: <path to ops.json>
Reviewer: reviewer-agent
Date: <date>

PRE-VALIDATION: PASS | FAIL
  [x] plan.md exists
  [x] ops.json exists
  [x] Valid JSON
  [x] Operations match steps
  [x] Required sections present

SCORES:
  Plan Quality:  [████████████████████░░░░░] 82/100 (weight: 40%)
  Architecture:  [███████████████████████░░] 94/100 (weight: 30%)
  Security:      [██████████████████████░░░] 88/100 (weight: 30%)
  ──────────────────────────────────────
  TOTAL:         [████████████████████████░] 87.4/100

DECISION: APPROVED | CONDITIONAL | REVISE | REJECTED

FINDINGS:

  Critical (must fix):
    1. <finding>
    2. <finding>

  Warnings (should fix):
    1. <finding>
    2. <finding>

  Notes (nice to have):
    1. <finding>
    2. <finding>

FEEDBACK FOR PLANNER:
  <specific, actionable feedback if not approved>
```

### Progress Bars

Use these Unicode blocks for progress bars:
- Full block: `█` (U+2588)
- Light shade: `░` (U+2591)
- Bar width: 25 characters
- Scale: each character = 4 points

---

## Handoff Formats

### To Implementer (Approved)
```
HANDOFF TO: implementer
---
Status: APPROVED
Score: <total>/100
Plan File: <path>
Ops Config: <path>
Notes:
  - <any suggestions, not blocking>
```

### To Planner (Revision Needed)
```
HANDOFF TO: planner
---
Status: REVISION REQUIRED
Score: <total>/100
Revision Number: <N> of 3
Plan File: <path>
Ops Config: <path>

Critical Issues (must fix):
  1. <issue with specific location and fix suggestion>
  2. ...

Warnings (should fix):
  1. <issue with specific location and fix suggestion>
  2. ...
```

### To Coordinator (Escalation)
```
HANDOFF TO: coordinator
---
Status: ESCALATION - Maximum revisions exceeded
Score: <total>/100
Revision Count: 3/3
Plan File: <path>
Remaining Issues:
  1. <unresolved issue>
  2. ...
Recommendation: <suggested path forward>
```

---

## Review Principles

1. **Be specific** - Never say "this could be better." Say exactly what's wrong and how to fix it.
2. **Be fair** - Score based on the criteria, not on subjective preferences.
3. **Be constructive** - Every criticism must come with a suggestion for improvement.
4. **Be consistent** - Apply the same standards to every plan.
5. **Be efficient** - Don't nitpick style when architecture has issues. Focus on the highest-impact items first.
6. **Respect the threshold** - 90 means 90. Do not approve at 89 "because it's close enough."
7. **Trust the formula** - The scoring weights exist for a reason. Don't override them with gut feelings.

---

## Anti-Patterns (NEVER DO THESE)

- NEVER approve a plan without ops.json
- NEVER approve a plan that scores below 90
- NEVER give a perfect 100 score (there's always room for improvement)
- NEVER reject without providing specific, actionable feedback
- NEVER change the scoring weights
- NEVER score subjectively (use the criteria tables)
- NEVER skip the security review, even for "simple" changes
- NEVER auto-approve because the planner is "probably right"
- NEVER omit the `=== REVIEW ===` block — a verdict the tooling cannot parse is no verdict
- NEVER claim a gate binds, or a proof passes, without having executed it; you cannot execute
