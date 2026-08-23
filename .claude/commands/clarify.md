---
description: "Identify and resolve ambiguities in specifications. Generates an Ambiguity Report."
argument-hint: "<spec-file-or-feature-name>"
---

# Clarify Command

Analyze a specification for ambiguities, gaps, and inconsistencies. Produce an Ambiguity Report that identifies every issue and proposes resolutions.

## Task

Analyze specification for ambiguities: $ARGUMENTS

## Mandatory Skills

You MUST load and apply the following skills before proceeding:

- **spec-driven-development** - Spec format and quality criteria
- **clarify** - Ambiguity detection techniques

## Workflow

### Phase 1: Locate the Specification

1. If the argument is a file path, read that file directly
2. If the argument is a feature name, look for `.specify/features/{name}/spec.md`
3. If neither exists, report the error and stop

### Phase 2: Ambiguity Analysis

Read the specification and analyze it against these six categories:

#### Category 1: Vague Language
Scan for words and phrases that lack precision:
- "appropriate", "reasonable", "sufficient", "adequate"
- "fast", "slow", "large", "small", "many", "few"
- "should handle gracefully", "user-friendly", "intuitive"
- "etc.", "and so on", "similar", "as needed"
- Subjective terms without measurable thresholds

#### Category 2: Missing Edge Cases
Identify scenarios not addressed in the spec:
- What happens with empty input?
- What happens with maximum/boundary values?
- What happens during concurrent access?
- What happens when external dependencies fail?
- What happens on first use vs. repeated use?
- What happens with invalid or malicious input?

#### Category 3: Implicit Assumptions
Find statements that assume context not stated in the spec:
- Assumed authentication state
- Assumed data format or encoding
- Assumed availability of services or resources
- Assumed ordering or sequencing
- Assumed user knowledge or behavior

#### Category 4: Conflicting Requirements
Detect requirements that contradict each other:
- Performance targets that conflict with data completeness
- Security requirements that conflict with usability
- Functional requirements that overlap or contradict
- Non-functional requirements with incompatible targets

#### Category 5: Undefined Terms
Flag domain-specific or technical terms used without definition:
- Acronyms without expansion
- Terms that could mean different things to different readers
- References to external systems or processes not described

#### Category 6: Missing Boundaries
Identify limits and ranges that are not specified:
- Input field length limits
- Numeric range limits
- Rate limits or throttling rules
- Timeout durations
- Retry counts and backoff strategies
- Data retention periods

### Phase 3: Generate Ambiguity Report

Produce the report organized by severity.

## Ambiguity Report Format

```markdown
# Ambiguity Report: {Feature Name}

**Spec analyzed:** {path to spec file}
**Date:** {current date}
**Total issues found:** {count}

## Critical (Must Resolve Before Implementation)

### C-1: {Issue Title}
- **Category:** {Vague Language | Missing Edge Case | Implicit Assumption | Conflicting Requirement | Undefined Term | Missing Boundary}
- **Location:** {Section and line reference in the spec}
- **Problem:** {What is ambiguous and why it matters}
- **Impact:** {What could go wrong if left unresolved}
- **Suggested resolution:** {Concrete proposal to fix the ambiguity}

### C-2: ...

## Important (Should Resolve Before Implementation)

### I-1: {Issue Title}
- **Category:** ...
- **Location:** ...
- **Problem:** ...
- **Impact:** ...
- **Suggested resolution:** ...

## Minor (Can Resolve During Implementation)

### M-1: {Issue Title}
- **Category:** ...
- **Location:** ...
- **Problem:** ...
- **Suggested resolution:** ...

## Summary

| Severity | Count |
|---|---|
| Critical | {n} |
| Important | {n} |
| Minor | {n} |

## Recommendation

{Overall assessment: Is this spec ready for implementation?
If not, what are the top 3 things that must be resolved first?}
```

### Phase 4: Present and Resolve

1. Present the Ambiguity Report to the user
2. Walk through Critical issues first, asking for resolution decisions
3. Update the spec with agreed resolutions
4. Move resolved Open Questions to answered status
5. Re-run the analysis to confirm no new ambiguities were introduced

## Forbidden Actions

- Do NOT propose implementation solutions -- only clarify requirements
- Do NOT modify the spec without user approval
- Do NOT skip any of the six analysis categories
- Do NOT mark an issue as Minor if it could lead to a wrong implementation
- Do NOT generate a report with zero issues -- every spec has at least one area to sharpen

## Usage Examples

- `/clarify user-authentication` -- Analyze the user-auth spec for ambiguities
- `/clarify .specify/features/search-api/spec.md` -- Analyze a specific spec file
- `/clarify billing-notifications` -- Analyze the billing notifications spec
