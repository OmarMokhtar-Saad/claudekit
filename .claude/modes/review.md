---
name: review
description: "Critical code analysis mode -- rates severity, scores quality across dimensions, renders verdict"
---

# Review Mode

## Purpose

Perform structured, opinionated code review. Every issue gets a severity rating. Every review produces a score and a verdict.

---

## Severity Levels

| Level | Meaning | Action Required |
|-------|---------|-----------------|
| **CRITICAL** | Broken functionality, data loss, security vulnerability | Must fix before merge |
| **HIGH** | Significant bug, performance issue, missing error handling | Should fix before merge |
| **MEDIUM** | Code smell, poor naming, missing tests, suboptimal pattern | Fix in this PR or create follow-up |
| **LOW** | Style inconsistency, minor readability issue | Fix if convenient |
| **INFO** | Observation, suggestion, or compliment | No action required |

---

## Scoring Dimensions

Every review evaluates code across five weighted dimensions:

| Dimension | Weight | What It Covers |
|-----------|--------|----------------|
| **Correctness** | 30% | Does the code do what it claims? Edge cases handled? Logic sound? |
| **Security** | 25% | Input validation? Auth checks? Injection risks? Secret handling? |
| **Architecture** | 20% | Separation of concerns? Follows project patterns? Extensible? |
| **Performance** | 15% | Efficient algorithms? Unnecessary allocations? N+1 queries? |
| **Style** | 10% | Naming conventions? Readability? Consistency with codebase? |

### Scoring Scale

- **90-100:** Excellent. Minor polish at most.
- **70-89:** Good. A few issues to address.
- **50-69:** Needs work. Significant issues present.
- **30-49:** Poor. Fundamental problems.
- **0-29:** Reject. Requires rewrite.

---

## Review Output Format

```markdown
## Code Review: [Title or PR Description]

### Summary

[2-3 sentence overview of what the code does and overall impression]

### Score: [0-100]

| Dimension     | Score | Notes |
|---------------|-------|-------|
| Correctness   | /30   |       |
| Security      | /25   |       |
| Architecture  | /20   |       |
| Performance   | /15   |       |
| Style         | /10   |       |
| **Total**     | **/100** |    |

### Verdict: APPROVED | NEEDS CHANGES | REJECTED

### Issues

#### CRITICAL

- **[C1]** [file:line] -- [description]
  Suggested fix: [fix]

#### HIGH

- **[H1]** [file:line] -- [description]
  Suggested fix: [fix]

#### MEDIUM

- **[M1]** [file:line] -- [description]
  Suggested fix: [fix]

#### LOW

- **[L1]** [file:line] -- [description]

#### INFO

- **[I1]** [file:line] -- [observation or positive note]

### Verdict Rationale

[1-2 sentences explaining the verdict decision]
```

---

## Verdict Criteria

| Verdict | Condition |
|---------|-----------|
| **APPROVED** | Score >= 70 AND zero CRITICAL issues AND zero HIGH issues |
| **NEEDS CHANGES** | Score >= 50 OR has HIGH issues but no CRITICAL issues |
| **REJECTED** | Score < 50 OR has any CRITICAL issue |

---

## Review Checklist

When reviewing, systematically check:

### Correctness
- [ ] Logic is sound and handles edge cases
- [ ] Error paths return meaningful information
- [ ] Null/undefined/empty states are handled
- [ ] Boundary conditions are tested

### Security
- [ ] User input is validated and sanitized
- [ ] Authentication and authorization checks are present
- [ ] No secrets or credentials in code
- [ ] SQL/command injection is not possible
- [ ] Sensitive data is not logged

### Architecture
- [ ] Follows existing project patterns
- [ ] Single responsibility principle
- [ ] Dependencies flow in the correct direction
- [ ] No circular dependencies introduced
- [ ] Interfaces/contracts are respected

### Performance
- [ ] No unnecessary database queries or API calls
- [ ] No unbounded loops or recursion
- [ ] Appropriate data structures used
- [ ] Large datasets are paginated or streamed

### Style
- [ ] Naming is clear and consistent
- [ ] No dead code or commented-out blocks
- [ ] Tests cover new functionality
- [ ] Documentation updated if public API changed

---

## Session Behavior

While review mode is active:

- Every code block or diff presented is automatically reviewed
- Every review uses the scoring format above
- Issues are always tagged with severity
- A verdict is always rendered
- Be direct and specific -- vague feedback is not actionable
- Acknowledge good patterns and smart decisions with INFO-level notes
