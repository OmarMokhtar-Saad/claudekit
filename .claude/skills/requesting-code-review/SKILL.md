---
name: requesting-code-review
description: "Use when code changes are complete and need review - dispatches code reviewer subagent"
disable-model-invocation: true
---

# Requesting Code Review

## Core Principle

**All code changes benefit from a second pair of eyes.** Request review systematically to catch issues before they reach production.

---

## When to Request Review

| Situation | Request Review? |
|---|---|
| New feature implementation | **Yes, always** |
| Bug fix | **Yes** |
| Refactoring | **Yes** |
| Configuration change | Yes, if it affects behavior |
| Documentation-only change | Optional |
| Formatting-only change | No |
| Dependency update | **Yes** |

---

## How to Request Review

### Step 1: Prepare the Review Request

Before requesting review, ensure:

- [ ] All changes are committed
- [ ] Tests pass (verification-before-completion)
- [ ] You can summarize what changed and why
- [ ] You have identified the relevant commit SHAs

### Step 2: Gather Change Information

```bash
# Get the commit range for review
git log --oneline -n 10

# Get the full diff
git diff <base-sha>..<head-sha>

# Get list of changed files
git diff --name-only <base-sha>..<head-sha>
```

### Step 3: Create the Review Request

Structure your review request as:

```markdown
## Review Request

### Summary
[1-2 sentences describing what changed and why]

### Changes
- [File 1]: [Brief description of change]
- [File 2]: [Brief description of change]

### Commit Range
Base: [base SHA]
Head: [head SHA]

### Areas of Concern
- [Any specific area you want extra attention on]
- [Any tradeoffs you made that should be reviewed]

### Testing
- [How you tested these changes]
- [Test results]
```

### Step 4: Dispatch Reviewer

If using a multi-agent setup, dispatch a reviewer subagent with:

1. The review request (from Step 3)
2. Access to the repository
3. The specific commit range to review
4. Any project-specific review criteria

---

## What Reviewers Look For

Understanding what reviewers check helps you prepare better code:

| Area | Questions |
|---|---|
| **Correctness** | Does the code do what it claims? Are edge cases handled? |
| **Architecture** | Does it follow project patterns? Are layers respected? |
| **Security** | Any security implications? Input validation? |
| **Performance** | Any performance concerns? N+1 queries? Blocking calls? |
| **Testability** | Is the code testable? Are tests adequate? |
| **Readability** | Can a new developer understand this code? |
| **Maintainability** | Will this be easy to modify in the future? |

---

## Acting on Feedback

When you receive review feedback:

### Priority Handling

| Feedback Type | Priority | Action |
|---|---|---|
| Security issue | **Critical** | Fix immediately |
| Bug/correctness | **High** | Fix before merge |
| Architecture concern | **High** | Discuss and resolve |
| Performance issue | **Medium** | Fix or document as known limitation |
| Style/naming suggestion | **Low** | Fix if easy, discuss if not |
| Nitpick | **Low** | Fix if you agree, skip if not |

### Response Protocol

1. **Acknowledge** every piece of feedback
2. **Categorize** by priority
3. **Address** high priority items first
4. **Discuss** items you disagree with (see receiving-code-review skill)
5. **Request re-review** after addressing feedback

---

## Self-Review Checklist

Before requesting review from others, do a self-review:

- [ ] I have re-read every line of my diff
- [ ] I have run all relevant tests
- [ ] I have checked for debug/temporary code left in
- [ ] I have verified no secrets or credentials are in the diff
- [ ] I have checked import statements are clean
- [ ] I have verified naming is consistent with project conventions
- [ ] I have checked for commented-out code that should be removed
- [ ] I have verified error handling is appropriate
- [ ] I have checked that new code has appropriate test coverage

---

## Review Request Anti-Patterns

### The Mega-PR
**Problem:** Requesting review on 50+ files at once.
**Fix:** Break into smaller, focused changes that can be reviewed independently.

### The Undescribed Change
**Problem:** "Please review" with no context.
**Fix:** Always provide summary, motivation, and areas of concern.

### The Unready Request
**Problem:** Requesting review with failing tests or known issues.
**Fix:** Fix known issues first. Note any intentionally deferred items.

### The Review Avoidance
**Problem:** Merging without review because "it's urgent."
**Fix:** Even urgent changes benefit from a quick review. At minimum, do self-review.
