# Constitution Guide

The Constitution is a governance document that defines your project's non-negotiable rules. The Reviewer agent enforces these rules automatically during plan validation.

## Why a Constitution?

Without explicit rules:
- Architecture drifts over time
- Quality standards vary by contributor
- Security checks get skipped under pressure
- Review criteria are inconsistent

A Constitution makes these rules explicit and enforceable.

## Writing Your Constitution

Start from the template at `.claude/local/CONSTITUTION.template.md` and customize.

### Step 1: Define Architecture Rules

```markdown
## Article I: Architecture

### Section 1: Layer Boundaries
Our application follows [your architecture]:

Presentation → Business Logic → Data Access

### Section 2: Forbidden Dependencies
- Presentation layer CANNOT import from Data layer directly
- Business logic CANNOT depend on framework-specific code
- **Violation**: AUTO-REJECT (score = 0)
```

**Tip**: Be specific about what's forbidden. "Clean architecture" is vague. "UI cannot import from `src/data/`" is enforceable.

### Step 2: Define Testing Requirements

```markdown
## Article III: Testing

### Section 1: Coverage
| Scope | Minimum |
|-------|---------|
| New code | 80% |
| Critical paths | 90% |
| Overall | 70% |

### Section 2: Required Tests
- Unit tests for all business logic
- Integration tests for API endpoints
- No mocking of the database (use test DB)
```

### Step 3: Define Security Rules

```markdown
## Article IV: Security

- No hardcoded secrets (use environment variables)
- Input validation at all API boundaries
- Parameterized queries only (no string concatenation for SQL)
- Output encoding for user-facing content
```

### Step 4: Set Review Thresholds

```markdown
## Article VIII: Review

| Gate | Threshold |
|------|-----------|
| Plan Review | 90/100 |
| Quality Check | 80/100 |
| Max Iterations | 3 |
```

## Enforcement Levels

| Level | Trigger | Effect |
|-------|---------|--------|
| AUTO-REJECT | Architecture violation, missing ops.json | Score = 0, plan rejected |
| Major (-20 pts) | Missing tests, security issue | Score reduction |
| Minor (-5 pts) | Style violation, missing docs | Score reduction |
| Warning | Non-blocking observation | Logged, no score impact |

## Examples by Project Type

### Web API (Python/FastAPI)

```markdown
## Article I: Architecture
- Routers → Services → Repositories
- No SQLAlchemy in routers
- Pydantic models for all request/response schemas

## Article III: Testing
- pytest with httpx.AsyncClient for API tests
- Test database for integration tests
- 80% coverage minimum
```

### Frontend (TypeScript/React)

```markdown
## Article I: Architecture
- Components → Hooks → Services → API Client
- No direct fetch() in components
- Server components by default (Next.js)

## Article III: Testing
- Vitest + Testing Library
- MSW for API mocking
- Accessibility tests with axe-core
```

### Backend (Java/Spring)

```markdown
## Article I: Architecture
- Controllers → Services → Repositories
- No JPA entities in controller layer
- DTOs for all API boundaries

## Article III: Testing
- JUnit 5 + Mockito
- @SpringBootTest for integration
- 80% line coverage
```

## Amending the Constitution

Constitutions evolve. Use the amendment process:

1. **Propose**: Describe the change and why
2. **Approve**: Get explicit user approval
3. **Apply**: Update the document
4. **Version**: Increment version number
5. **Notify**: Agents will load the new version automatically

### When to Amend

- New technology adopted (add rules for it)
- Security incident (strengthen security articles)
- Performance regression (add benchmarks)
- Process improvement (refine workflows)

## Anti-Patterns

| Anti-Pattern | Why It Fails |
|--------------|-------------|
| Too many rules | Agents can't enforce 50 rules. Keep to 5-10 core principles. |
| Too vague | "Write good code" is unenforceable. Be specific. |
| No penalties | Rules without consequences get ignored. Define AUTO-REJECT triggers. |
| Never updated | Stale rules cause false rejections. Review quarterly. |
| Copied wholesale | Your project isn't the template project. Customize. |
