---
description: "Cross-artifact consistency analysis -- check coverage and completeness across spec, plan, tasks, and implementation"
argument-hint: "<feature-name>"
---

# Analyze Command

Perform cross-artifact consistency analysis for a feature. Verify that the spec, plan, tasks, and implementation are aligned and complete.

## Task

Cross-artifact analysis for: $ARGUMENTS

## Mandatory Skills

You MUST load and apply the following skills before proceeding:

- **spec-driven-development** - Spec format and compliance verification
- **verification-before-completion** - Verification methodology

## Workflow

### Phase 1: Locate Artifacts

Find all artifacts for the feature:

| Artifact | Expected Location | Required |
|---|---|---|
| Specification | `.specify/features/{name}/spec.md` | Yes |
| Checklist | `.specify/features/{name}/checklist.md` | No |
| Plan | Current conversation or `.claude/plans/` | No |
| Implementation | Source files referenced in plan | No |
| Tests | Test files corresponding to implementation | No |

If the specification does not exist, stop and recommend running `/specify` first.

### Phase 2: Build the Completeness Matrix

For every functional requirement (FR-N) and non-functional requirement (NFR-N) in the spec, trace it through the artifacts:

```markdown
## Completeness Matrix

| Requirement | Spec | Plan | Implemented | Tested | Status |
|---|---|---|---|---|---|
| FR-1: {title} | Defined | Step 3 | src/auth.ts:45 | auth.test.ts:12 | COMPLETE |
| FR-2: {title} | Defined | Step 5 | src/api.ts:22 | -- | MISSING TEST |
| FR-3: {title} | Defined | -- | -- | -- | NOT PLANNED |
| NFR-1: {title} | Defined | Step 7 | config.ts:8 | perf.test.ts:5 | COMPLETE |
| NFR-2: {title} | Defined | Step 7 | -- | -- | NOT IMPLEMENTED |
```

Status values:
- **COMPLETE**: Traced through all applicable artifacts
- **MISSING TEST**: Implemented but no corresponding test
- **NOT IMPLEMENTED**: Planned but no code yet
- **NOT PLANNED**: In spec but missing from plan
- **INCONSISTENT**: Artifacts contradict each other

### Phase 3: Consistency Checks

Verify consistency across artifacts:

#### Spec-to-Plan Consistency
- Every functional requirement in the spec has a corresponding plan step
- Plan steps do not introduce requirements not in the spec
- Plan approach does not violate spec constraints

#### Plan-to-Implementation Consistency
- Every plan step has corresponding code changes
- Implementation does not deviate from the plan approach
- File paths in the plan match actual file locations

#### Implementation-to-Test Consistency
- Every implemented requirement has at least one test
- Test assertions match the acceptance criteria in the spec
- Edge cases from the spec are covered in tests

#### Cross-Artifact Term Consistency
- The same terms are used consistently across all artifacts
- No requirement has been silently renamed or reinterpreted

### Phase 4: Generate Gap Report

```markdown
## Gap Report: {Feature Name}

**Date:** {current date}
**Artifacts analyzed:** {list}

### Scores

| Dimension | Score | Details |
|---|---|---|
| **Coverage** | {0-100}% | {X of Y requirements traced to implementation} |
| **Consistency** | {0-100}% | {X of Y artifacts aligned, Z contradictions found} |
| **Completeness** | {0-100}% | {X of Y requirements fully complete through testing} |
| **Overall** | {0-100}% | Weighted: Coverage 40%, Consistency 30%, Completeness 30% |

### Gaps Found

#### Gap 1: {Title}
- **Type:** Missing Coverage | Inconsistency | Incomplete
- **Artifacts involved:** {which artifacts}
- **Details:** {what is missing or wrong}
- **Recommendation:** {how to fix}

#### Gap 2: ...

### Orphaned Artifacts
{List any plan steps, code, or tests that do not trace back to a spec requirement.
These may indicate scope creep or undocumented requirements.}

### Recommendation

{Overall assessment: Is the feature ready to ship?
What gaps must be closed first? Suggested order of resolution.}
```

### Phase 5: Present Results

Display both the Completeness Matrix and the Gap Report. Recommend next steps based on the overall score:

| Score Range | Recommendation |
|---|---|
| 90-100% | Ready for final review and deployment |
| 70-89% | Close gaps before proceeding -- list specific actions |
| 50-69% | Significant gaps -- revisit plan or spec |
| Below 50% | Major alignment issues -- re-run `/specify` or `/plan` |

## Forbidden Actions

- Do NOT modify any artifacts -- this is a read-only analysis
- Do NOT skip requirements when building the matrix
- Do NOT inflate scores -- be honest about gaps
- Do NOT suggest implementation fixes -- only identify the gap

## Usage Examples

- `/analyze user-authentication` -- Full analysis of the user-auth feature
- `/analyze search-api` -- Analyze search API spec-to-code alignment
- `/analyze billing-notifications` -- Check billing feature completeness
