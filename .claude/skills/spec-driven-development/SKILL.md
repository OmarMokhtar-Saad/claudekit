---
name: spec-driven-development
description: Spec-driven development workflow where specifications are the single source of truth. Write specs first, then generate code that conforms exactly. Treat development as compilation from spec to code.
disable-model-invocation: true
argument-hint: "<spec-file-or-feature>"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# Spec-Driven Development

## Core Principle

**The specification is the single source of truth. Code is a compiled artifact of the spec.** When spec and code disagree, the spec is correct and the code must be updated. Never change code without updating the spec first.

---

## The SDD Workflow

```
[SPECIFY] Write the specification first
    |
    v
[VALIDATE] Review spec for completeness and consistency
    |
    v
[GENERATE] Write code that conforms to the specification
    |
    v
[VERIFY] Confirm code matches spec exactly
    |
    v
[EVOLVE] Change spec first, then update code to match
```

---

## Spec Format

### Feature Specification Template

```markdown
# SPEC: <Feature Name>

## Status: DRAFT | REVIEW | APPROVED | IMPLEMENTED

## Overview
<1-3 sentences describing what this feature does and why>

## Actors
- <Actor 1>: <role description>
- <Actor 2>: <role description>

## Inputs
| Field | Type | Required | Constraints | Default |
|---|---|---|---|---|
| <name> | <type> | Yes/No | <validation rules> | <default> |

## Outputs
| Field | Type | Description |
|---|---|---|
| <name> | <type> | <what this represents> |

## Behavior
### Happy Path
1. <step 1>
2. <step 2>
3. <step 3>

### Error Cases
| Condition | Response | HTTP Status (if API) |
|---|---|---|
| <condition> | <what happens> | <code> |

## Invariants
- <rule that must ALWAYS hold>
- <rule that must ALWAYS hold>

## Dependencies
- <external system or feature this depends on>

## Non-Functional Requirements
- Performance: <latency, throughput targets>
- Security: <auth, encryption, audit requirements>
- Availability: <uptime, degradation behavior>
```

---

## Spec-to-Code Workflow

### Step 1: Write the Spec

Before writing ANY code:

1. Create the spec file at `.claude/specs/<feature-name>.md`
2. Fill in ALL sections of the template
3. Mark status as DRAFT
4. Review for completeness: every input validated, every error handled, every invariant stated

### Step 2: Validate the Spec

Check the spec against these criteria:

| Criterion | Question |
|---|---|
| **Complete** | Are all inputs, outputs, and error cases defined? |
| **Consistent** | Do invariants contradict any behavior rules? |
| **Testable** | Can every behavior statement be verified with a test? |
| **Unambiguous** | Would two developers implement the same thing from this spec? |
| **Bounded** | Are all constraints and limits explicitly stated? |

Mark status as REVIEW, then APPROVED when all criteria pass.

### Step 3: Generate Code from Spec

For each spec section, generate corresponding code:

| Spec Section | Code Artifact |
|---|---|
| Inputs | Input validation / DTO / request schema |
| Outputs | Response DTO / return type |
| Happy Path | Main implementation logic |
| Error Cases | Error handling / exception mapping |
| Invariants | Assertions / domain rules / tests |
| Non-Functional | Performance tests / security config |

### Step 4: Verify Compliance

After implementation, verify every spec statement maps to code:

```
COMPLIANCE MATRIX:
  Spec Statement              | Code Location       | Test Location        | Status
  "Input X is required"       | validator.ts:15     | validator.test.ts:8  | PASS
  "Returns 404 if not found"  | handler.ts:32       | handler.test.ts:45   | PASS
  "Max 100 items per page"    | query.ts:10         | query.test.ts:22     | PASS
  ...
```

Every row must have a code location AND a test location. Missing entries mean the implementation is incomplete.

---

## Spec Evolution Patterns

### The Change Protocol

```
1. NEVER change code directly
2. Update the spec FIRST
3. Mark spec status as REVIEW
4. Get approval on spec change
5. Update code to match new spec
6. Update compliance matrix
7. Mark spec status as IMPLEMENTED
```

### Breaking vs Non-Breaking Changes

| Change Type | Spec Action | Code Action |
|---|---|---|
| Add optional input | Add to inputs table | Add with default |
| Add required input | New spec version, migration plan | Expand-contract |
| Change behavior | Update behavior section, note breaking | Update + migration |
| Remove feature | Mark as DEPRECATED in spec | Remove after deprecation period |

### Spec Versioning

```
specs/
  user-registration-v1.md    (DEPRECATED)
  user-registration-v2.md    (IMPLEMENTED)
  user-registration-v3.md    (DRAFT)
```

Keep old spec versions for reference. Mark deprecated specs clearly.

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

## Anti-Patterns

| Anti-Pattern | Why It Is Bad | Alternative |
|---|---|---|
| Code without spec | No source of truth, behavior is implicit | Write spec first, always |
| Spec that is vague | "Handle errors gracefully" is not testable | Enumerate every error case explicitly |
| Spec updated after code | Spec becomes documentation, not source of truth | Change spec first, then code |
| Spec without invariants | No way to verify correctness | State what must ALWAYS hold |
| Monolithic spec | Too large to review or maintain | One spec per feature or bounded context |
| Spec without compliance matrix | No way to verify completeness | Build matrix during implementation |

---

## Spec Quality Checklist

- [ ] Every input has type, constraints, and required/optional status
- [ ] Every output has type and description
- [ ] Every error case has condition, response, and status code
- [ ] Every invariant is testable with a concrete assertion
- [ ] Happy path is a numbered step-by-step sequence
- [ ] Non-functional requirements have measurable targets
- [ ] Dependencies are explicitly listed
- [ ] Status field reflects the current state of the spec
