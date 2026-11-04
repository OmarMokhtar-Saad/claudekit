# Planner Reference

On-demand companion to `.claude/agents/planner.md`. Nothing here is optional: these are the
same rules the planner has always followed, moved out of the always-injected prompt so they
cost one Read instead of every token of every turn. Read this ONCE per run, before you
compose plan.md.

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

## Code Quality
- <unit> — single responsibility: <one sentence>
- New cases are added by: <registry entry / strategy / table row, not an if/elif edit>
- Limits: no new code exceeds ≤50-line functions, complexity ≤10, ≤5 params, nesting ≤4
- Over-limit functions touched: <none | split step N | justification>
```

**Code Quality section is mandatory** in every plan that changes code. Rules, limits and
severity: `.claude/agents/_shared/CODE_QUALITY_STANDARD.md` (new code only; pre-existing
violations are grandfathered). Adding logic to a function already over a limit needs a
split step or a written justification.

---

## Plan Metadata Hard Rules

The main session edits directly after approval; the plan is the only artifact. `plan-gate`
reads these fields, so they are not optional:
- A `Tier:` line near the top: `Tier: 1`, `Tier: 2` or `Tier: 3` (blast radius, see CLAUDE.md).
- A `Files:` list of every path the plan will touch, one backticked repo-relative path per
  bullet. Tier 3 plans are gated on it, and it is frozen once the plan is approved: a new
  path means a revised plan and a new review.
- Every Implementation Step's `File:` appears in `Files:`, and every `Files:` entry is used
  by a step.
- Rollback and validation notes live in plan.md (rollback = `/rollback` to the
  `ck-checkpoint/<epoch>` tag taken before the first edit).

---

## Tiered Briefing Format

### Simple Tasks (1-3 files, straightforward changes)
```
PLAN BRIEF (Simple)
====================
Task: <description>
Files: <list>
Steps: <numbered list, 1-2 lines each>
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
Estimated Effort: High
```

---

## Automatic Reviewer Trigger

When the plan is complete:

1. Save plan.md
2. Output the plan brief in the appropriate tier format
3. Include this handoff block at the end:

```
HANDOFF TO: reviewer
---
Plan File: <path to plan.md>
Complexity: <Simple|Medium|Complex>
Files Affected: <count>
Steps: <count>
Risk Level: <Low|Medium|High>
```

---

## Plan Content Rules

1. **Every plan step names its file and action**, and the file is in the `Files:` list.
2. **Order steps by dependency** (independent steps first).
3. **File paths are relative to the project root.**
4. **Details are exact**: name the function, string or block to change, copied from
   grep/Read output; no pseudocode or placeholders.
5. **Anchors are unique**: a step that quotes text to change quotes text that occurs once.

---

## Handling Revision Feedback

If the Reviewer sends back feedback:

1. Address CRITICAL and MAJOR items; MINORs never block convergence
2. Revision mode (Discovery budget): no re-exploration; touch only what a finding names —
   an unrequested rewrite moves the reviewer's target and stalls the loop
3. Update plan.md in place (keep `Files:` in step with the steps), report a ≤10-line summary
   keyed by finding ("F1: fixed by op X", "F3: disputed because ...")
4. Do NOT ask the user for permission to revise

---

## Quality Checklist (Self-Review Before Handoff)

Before handing off to the Reviewer, verify:

- [ ] Plan has a clear overview and scope
- [ ] Every step specifies the target file and action
- [ ] `Tier:` line present and `Files:` list matches the steps exactly
- [ ] All file paths are correct and relative to project root
- [ ] Validation commands and rollback notes are in plan.md
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
Complexity: <tier>
Steps: <count>
Files Affected: <count>
Risk: <level>
Status: Ready for Review
```
