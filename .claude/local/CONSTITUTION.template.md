# {{PROJECT_NAME}} Constitution

**Version**: 1.0
**Effective Date**: {{DATE}}
**Status**: ACTIVE

> This Constitution establishes immutable principles that guide all development work.
> All agents, developers, and automated systems are bound by these articles.

---

## Article I: Architecture Principles

### Section 1: Layer Boundaries
{{PROJECT_NAME}} follows a layered architecture with strict dependency rules:

```
# TODO: Define your architecture layers here, e.g.:
# Presentation → Application → Domain → Infrastructure
# Each layer may only depend on layers below it.
```

### Section 2: Forbidden Dependencies
- **Violation Penalty**: AUTO-REJECT (plan score = 0)
- TODO: Define forbidden dependency rules (e.g., "Domain layer must not import from Infrastructure")

### Section 3: Package Organization
```
# TODO: Define your package structure here, e.g.:
# src/domain/    - Business logic and entities
# src/api/       - API endpoints and controllers
# src/data/      - Data access and external integrations
# tests/         - Test files mirroring src/ structure
```

---

## Article II: Code Quality Standards

### Section 1: Style Guide
- Follow {{LANGUAGE}} community conventions
- Use project linter: `{{LINT_CMD}}`

### Section 2: Naming Conventions
- TODO: Define naming conventions for your project (e.g., snake_case for Python, camelCase for TypeScript)

### Section 3: Error Handling
- Use structured error types
- Log errors appropriately
- Provide clear error messages to users
- Implement graceful recovery where possible

---

## Article III: Testing Requirements

### Section 1: Coverage Minimums
| Scope | Minimum Coverage |
|-------|-----------------|
| New code | 80% |
| Critical paths | 90% |
| Overall project | 70% |

### Section 2: Test Practices
- Write tests before or alongside code (TDD encouraged)
- Test command: `{{TEST_CMD}}`
- Coverage command: `{{COVERAGE_CMD}}`

### Section 3: Test Types Required
- Unit tests for business logic
- Integration tests for external boundaries
- TODO: Add project-specific test types (e.g., E2E tests, contract tests, snapshot tests)

---

## Article IV: Security Requirements

### Section 1: OWASP Compliance
All code must be checked against relevant OWASP Top 10 items:
- Input validation at system boundaries
- No hardcoded secrets or credentials
- Parameterized queries for database operations
- Output encoding for user-facing content

### Section 2: Secrets Management
- **NEVER** hardcode API keys, passwords, or tokens
- Use environment variables or secure vaults
- Pre-commit hook detects common secret patterns

---

## Article V: Plan Gate

### Section 1: Mandatory Plan
- All edits MUST follow an approved plan.md with a Tier and a `Files:` list
- **Violation**: AUTO-REJECT a plan without a `Files:` list

### Section 2: Protected Files
Protected files stay protected by hooks, and a plan cannot unlock them:
- plan-gate denies review records, settings files and `plan-gate.globs` (owner-only)
- shell-write-gate closes the same paths against the shell forms
- config-protection blocks edits to lint/type configs (`eslint`, `prettier`, `tsconfig*.json`,
  `biome.json`, `.flake8`, `setup.cfg`, `pyproject.toml`, `.editorconfig`, and similar)

### Section 3: Safety Limits
- Backup = a git checkpoint: `checkpoint-gate` tags `ck-checkpoint/<epoch>` before the first
  Tier 3 edit (restore with `git stash apply <tag>`); a deleted tracked file is also
  recoverable from git
- Deleting a Tier 3 file requires `(delete)` on its path in the plan's `Files:`, max 3 per plan

---

## Article VI: Performance Standards

### Section 1: Response Times
- TODO: Define response time targets (e.g., API responses < 200ms, page load < 3s)

### Section 2: Resource Constraints
- TODO: Define resource constraints (e.g., memory < 512MB, CPU budget, connection pool limits)

### Section 3: Build Performance
- Build time target: {{BUILD_TIME_TARGET}}

---

## Article VII: Documentation Standards

### Section 1: Code Documentation
- Document public APIs
- Include usage examples for complex functions
- Keep documentation up-to-date with code changes

### Section 2: Plan Documentation
All implementation plans must include:
- Problem statement
- Proposed solution
- Affected files
- Tier and `Files:` list
- Verification steps

---

## Article VIII: Review and Approval

### Section 1: Approval Thresholds
| Review Type | Minimum Score |
|-------------|--------------|
| Plan Review (Reviewer) | 90/100 |
| Quality Verification (Verifier) | 80/100 |

### Section 2: Review Dimensions
- Plan Quality: 40%
- Architecture Compliance: 30%
- Security: 30%

### Section 3: Automatic Rejections
- Missing `Files:` list
- Architecture violations

### Section 4: Escalation
- Maximum 3 plan/review iterations before user escalation
- Maximum 3 implementation attempts before user escalation

---

## Constitutional Amendments

### Amendment Process
1. Propose amendment with justification
2. Get explicit user approval
3. Apply amendment to this document
4. Increment version number
5. Notify all agents of changes

### Amendment Triggers
- New technology adoption
- Security incident
- Performance regression
- Process improvement discovery

---

## Enforcement

### Automatic Enforcement
- Reviewer agent checks all articles during plan review
- Verifier agent checks testing and quality articles
- Pre-commit hook checks security articles
- Pre-push hook runs full validation

### Violation Penalties
| Severity | Penalty | Recovery |
|----------|---------|----------|
| AUTO-REJECT | Score = 0 | Must fix and re-submit |
| Major (-20 pts) | Score reduction | Fix in current iteration |
| Minor (-5 pts) | Score reduction | Fix before merge |
| Warning | No score impact | Track for patterns |
