---
name: spec-driven-development
description: "Use when developing features with specifications first — covers the full workflow: specify, clarify, checklist, plan, analyze, implement, verify. Specs are the single source of truth."
disable-model-invocation: true
argument-hint: "<spec-file-or-feature>"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# Spec-Driven Development

## Core Principle

**The specification is the single source of truth. Code is a compiled artifact of the spec.** When spec and code disagree, the spec is correct and the code must be updated. Never change code without updating the spec first.

---

## The Full Workflow

```
[1. SPECIFY]  Define requirements -- WHAT and WHY, not HOW
       |
       v
[2. CLARIFY]  Identify and resolve ambiguities
       |
       v
[3. CHECKLIST] Generate validation criteria from the spec
       |
       v
[4. PLAN]     Create implementation plan from the spec
       |
       v
[5. ANALYZE]  Verify plan covers all spec requirements
       |
       v
[6. IMPLEMENT] Write code that conforms to the spec
       |
       v
[7. VERIFY]   Run the checklist against the implementation
       |
       v
[8. ANALYZE]  Final cross-artifact consistency check
```

### Command Mapping

| Step | Command | Input | Output |
|---|---|---|---|
| 1. Specify | `/specify {name}` | User's feature idea | `.specify/features/{name}/spec.md` |
| 2. Clarify | `/clarify {name}` | spec.md | Ambiguity Report, updated spec.md |
| 3. Checklist | `/checklist {name}` | spec.md | `.specify/features/{name}/checklist.md` |
| 4. Plan | `/plan {name}` | spec.md | Implementation plan + ops.json |
| 5. Analyze | `/analyze {name}` | spec.md + plan | Completeness Matrix + Gap Report |
| 6. Implement | `/implement {name}` | plan + ops.json | Source code + tests |
| 7. Verify | Manual or `/verify` | checklist.md + code | Filled checklist with pass/fail |
| 8. Analyze | `/analyze {name}` | All artifacts | Final consistency report |

---

## Directory Structure

```
.specify/
  features/
    {feature-name}/
      spec.md          # The specification (source of truth)
      checklist.md     # Generated validation checklist
      ambiguity-report.md  # Output of /clarify (optional, kept for audit)
      analysis/
        gap-report.md  # Output of /analyze
```

All spec-driven artifacts live under `.specify/`. This keeps them separate from source code and configuration.

---

## Spec Format

### Feature Specification Template

```markdown
# SPEC: {Feature Name}

## Status: DRAFT | REVIEW | APPROVED | IMPLEMENTED

## Problem Statement
{What problem does this solve? Who is affected? What is the impact?}

## Users & Stakeholders
| Role | Relationship to Feature | Key Concern |
|---|---|---|

## Functional Requirements
### FR-1: {Title}
**Description:** {What the system must do}
**Acceptance Criteria:**
- Given {context}, when {action}, then {expected result}

## Non-Functional Requirements
### NFR-1: {Title}
**Category:** Performance | Security | Reliability | Usability | Accessibility
**Description:** {What quality attribute must be met}
**Measurable Target:** {Specific, testable threshold}

## Success Criteria
- [ ] {Observable outcome 1}
- [ ] {Observable outcome 2}

## Constraints
- {Constraint 1}

## Out of Scope
- {Explicitly excluded item 1}

## Open Questions
- [ ] {Unresolved question 1}
```

---

## Spec-to-Code Traceability

Every requirement in the spec must be traceable to:

1. **A plan step** that addresses it
2. **Source code** that implements it
3. **A test** that verifies it

The traceability is validated by `/analyze`, which produces a Completeness Matrix:

```
| Requirement | Spec | Plan | Code | Test | Status |
|---|---|---|---|---|---|
| FR-1 | Defined | Step 3 | auth.ts:45 | auth.test.ts:12 | COMPLETE |
| FR-2 | Defined | -- | -- | -- | NOT PLANNED |
```

A feature is not done until every row shows COMPLETE.

---

## Spec Evolution Rules

### The Change Protocol

```
1. NEVER change code directly to alter behavior
2. Update the spec FIRST with the new requirement
3. Mark spec status as REVIEW
4. Run /clarify on the updated spec
5. Update the checklist with /checklist
6. Update the plan
7. Update code to match the new spec
8. Run /analyze to verify consistency
9. Mark spec status as IMPLEMENTED
```

### Breaking vs Non-Breaking Changes

| Change Type | Spec Action | Code Action |
|---|---|---|
| Add optional input | Add to inputs, mark optional | Add with default value |
| Add required input | New spec version, migration plan | Expand-contract migration |
| Change behavior | Update behavior section, note breaking | Update + migration path |
| Remove feature | Mark as DEPRECATED in spec | Remove after deprecation period |

---

## Rules

1. **Spec before code.** No implementation begins without an approved spec.
2. **One spec per feature.** Each feature gets its own spec file.
3. **Acceptance criteria are mandatory.** Every functional requirement must have at least one Given/When/Then criterion.
4. **Measurable targets are mandatory.** Every non-functional requirement must have a numeric or boolean threshold.
5. **Open questions block implementation.** Resolve all open questions before starting to code.
6. **The checklist is the exit gate.** A feature is not complete until the checklist is fully passed.
7. **Analysis runs twice.** Once after planning (to catch gaps early) and once after implementation (to verify completeness).
8. **Specs are versioned.** When a spec changes significantly, keep the old version for reference.

---

## Anti-Patterns

| Anti-Pattern | Why It Is Bad | Alternative |
|---|---|---|
| Code without spec | No source of truth, behavior is implicit | Write spec first, always |
| Vague spec | "Handle errors gracefully" is not testable | Enumerate every error case explicitly |
| Spec updated after code | Spec becomes documentation, not source of truth | Change spec first, then code |
| Spec without acceptance criteria | No way to verify correctness | Every FR needs Given/When/Then |
| Skipping /clarify | Ambiguities become bugs | Always clarify before planning |
| Skipping /analyze | Gaps are discovered late | Analyze after planning AND after implementation |
| Monolithic spec | Too large to review or maintain | One spec per feature or bounded context |
| Implementation in the spec | Spec should say WHAT, not HOW | Remove technology choices from requirements |

---

## Integration with Other Skills

| Situation | Skill to Load |
|---|---|
| Spec describes API endpoints | **api-design-patterns** |
| Spec involves database changes | **database-migration-patterns** |
| Spec has security requirements | **security-checklist** |
| Spec needs implementation plan | **writing-plans** |
| Spec requires architecture decisions | **clean-architecture** |

---

## Quality Checklist for Specs

Before marking a spec as APPROVED, verify:

- [ ] Every input has type, constraints, and required/optional status
- [ ] Every functional requirement has at least one acceptance criterion
- [ ] Every non-functional requirement has a measurable target
- [ ] Every error case has a defined response
- [ ] Success criteria are concrete and observable
- [ ] Constraints are realistic and complete
- [ ] Out of Scope section is populated
- [ ] All Open Questions are resolved
- [ ] No implementation details in the spec (WHAT, not HOW)
- [ ] Status field reflects the current state
