---
description: "Generate quality validation checklists from a specification for pre-deployment verification"
argument-hint: "<feature-name>"
---

# Checklist Command

Generate a comprehensive quality validation checklist from a feature specification. The checklist covers functional verification, non-functional verification, code quality, security, testing, documentation, and deployment.

## Task

Generate validation checklist for: $ARGUMENTS

## Mandatory Skills

You MUST load and apply the following skills before proceeding:

- **spec-driven-development** - Spec format and requirements tracing
- **security-checklist** - Security validation criteria
- **verification-before-completion** - Verification methodology

## Workflow

### Phase 1: Locate the Specification

1. If the argument is a file path, read that file directly
2. If the argument is a feature name, look for `.specify/features/{name}/spec.md`
3. If neither exists, report the error and recommend running `/specify` first

### Phase 2: Extract Requirements

From the specification, extract:
- All functional requirements (FR-N) and their acceptance criteria
- All non-functional requirements (NFR-N) and their measurable targets
- All constraints
- All success criteria

### Phase 3: Generate Checklist

Build a checklist covering seven categories. Every item must be:
- Derived from a specific requirement in the spec (reference it)
- Binary: either it passes or it does not
- Verifiable: someone can test it concretely

### Phase 4: Save the Checklist

Write the checklist to `.specify/features/{feature-name}/checklist.md`.

## Checklist Template

```markdown
# Validation Checklist: {Feature Name}

**Spec:** `.specify/features/{name}/spec.md`
**Generated:** {date}
**Status:** NOT STARTED | IN PROGRESS | COMPLETE

---

## 1. Functional Verification

Verify that every functional requirement works as specified.

- [ ] **FR-1: {title}** -- {acceptance criterion 1}
- [ ] **FR-1: {title}** -- {acceptance criterion 2}
- [ ] **FR-2: {title}** -- {acceptance criterion 1}
- [ ] ...

## 2. Non-Functional Verification

Verify that quality attributes meet their measurable targets.

- [ ] **NFR-1: {title}** -- {measurable target, e.g., "Response time < 200ms at p95"}
- [ ] **NFR-2: {title}** -- {measurable target}
- [ ] ...

## 3. Code Quality

- [ ] No compiler/linter warnings introduced
- [ ] All new functions have clear parameter names and return types
- [ ] No duplicated logic -- shared code is extracted
- [ ] Error messages are descriptive and actionable
- [ ] No hardcoded values that should be configurable
- [ ] Code follows existing project conventions and patterns

## 4. Security

- [ ] Input validation on all user-supplied data
- [ ] No secrets, credentials, or API keys in source code
- [ ] Authentication required for protected endpoints/operations
- [ ] Authorization checks enforce correct access levels
- [ ] Sensitive data is not logged or exposed in error messages
- [ ] SQL/command injection prevented (parameterized queries, safe APIs)
- [ ] {Any spec-specific security requirements from NFRs}

## 5. Testing

- [ ] Unit tests cover every functional requirement
- [ ] Unit tests cover every error case defined in the spec
- [ ] Edge cases from the spec are covered (empty input, boundaries, concurrent access)
- [ ] Integration tests verify cross-component behavior
- [ ] All tests pass in CI
- [ ] Test coverage meets project threshold (if defined)
- [ ] {Any spec-specific testing requirements}

## 6. Documentation

- [ ] Public API changes are documented (endpoints, parameters, return values)
- [ ] Breaking changes are noted in changelog or migration guide
- [ ] Configuration changes are documented
- [ ] README or relevant docs updated if user-facing behavior changed
- [ ] Code comments explain non-obvious decisions (why, not what)

## 7. Deployment

- [ ] Database migrations are reversible (if applicable)
- [ ] Feature flags or gradual rollout configured (if applicable)
- [ ] Monitoring and alerting in place for new functionality
- [ ] Rollback procedure documented and tested
- [ ] Dependencies are pinned to specific versions
- [ ] Environment-specific configuration is correct (staging, production)

---

## Sign-Off

| Category | Items | Passed | Status |
|---|---|---|---|
| Functional Verification | {n} | {n} | -- |
| Non-Functional Verification | {n} | {n} | -- |
| Code Quality | {n} | {n} | -- |
| Security | {n} | {n} | -- |
| Testing | {n} | {n} | -- |
| Documentation | {n} | {n} | -- |
| Deployment | {n} | {n} | -- |
| **Total** | **{n}** | **{n}** | -- |
```

## Output Location

```
.specify/features/{feature-name}/checklist.md
```

Create the directory structure if it does not exist.

## Forbidden Actions

- Do NOT generate checklist items that cannot be verified concretely
- Do NOT include items unrelated to the feature specification
- Do NOT skip any of the seven checklist categories
- Do NOT create a checklist from an empty or placeholder spec -- flag the issue instead
- Do NOT fill in the "Passed" column -- that is done during verification

## Usage Examples

- `/checklist user-authentication` -- Generate checklist from user-auth spec
- `/checklist search-api` -- Generate checklist for search API
- `/checklist billing-notifications` -- Generate checklist for billing alerts
