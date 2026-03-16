---
name: test-driven-development
description: "Use when implementing features or fixing bugs - RED/GREEN/REFACTOR workflow ensures test coverage"
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# Test-Driven Development

## Core Principle

**Write the test first, watch it fail, then write the minimum code to make it pass.** This is not about testing - it is about design. Tests written first produce better interfaces.

---

## The RED/GREEN/REFACTOR Cycle

```
[RED] Write a test that fails
  |
  v
[GREEN] Write minimum code to pass the test
  |
  v
[REFACTOR] Improve the code while keeping tests green
  |
  v
(repeat)
```

### RED Phase

1. Write a test for the next piece of desired behavior
2. Run the test
3. **Confirm it fails** (and fails for the RIGHT reason)
4. If it passes, either the behavior already exists or the test is wrong

**Key questions:**
- Does the test clearly express the desired behavior?
- Is it testing ONE thing?
- Does the failure message explain what went wrong?

### GREEN Phase

1. Write the SIMPLEST code that makes the test pass
2. It is okay if the code is ugly or naive
3. Do not over-engineer during this phase
4. Do not write code for future tests
5. Run the test and confirm it passes

**Key questions:**
- Is this the minimum code to pass?
- Am I writing code for this test or for a future one?
- Do ALL tests still pass (not just the new one)?

### REFACTOR Phase

1. Look for duplication in the code
2. Look for duplication in the tests
3. Improve naming and structure
4. Extract methods or classes if needed
5. Run tests after EVERY refactoring step

**Key questions:**
- Is the code cleaner than before?
- Do all tests still pass?
- Did I change behavior? (I should not have)

---

## TDD in Practice

### For a New Feature

```
1. RED:    Write test for the simplest case of the feature
2. GREEN:  Implement the simplest case
3. REFACTOR: Clean up
4. RED:    Write test for the next case
5. GREEN:  Handle the next case
6. REFACTOR: Clean up
... repeat until feature is complete
```

### For a Bug Fix

```
1. RED:    Write test that reproduces the bug (fails now)
2. GREEN:  Fix the bug (test passes)
3. REFACTOR: Clean up the fix if needed
4. VERIFY: Run full test suite to check for regressions
```

### For a Refactoring

```
1. VERIFY: Ensure comprehensive tests exist (write them if not)
2. REFACTOR: Make small, incremental changes
3. VERIFY: Run tests after every change
4. REPEAT: Continue until refactoring is complete
```

---

## Common Rationalizations for Skipping TDD

| Rationalization | Why It Is Wrong |
|---|---|
| "I'll write the tests after" | You will write weaker tests that confirm your implementation rather than specify behavior |
| "This is too simple to test" | Simple code has simple tests - there is no excuse not to write them |
| "TDD is too slow" | Debugging without tests is slower. TDD front-loads the time cost |
| "I know the design already" | TDD often reveals design issues you would not have found otherwise |
| "The existing code has no tests" | Start now. Every journey begins with one step |
| "I am just prototyping" | Prototypes have a way of becoming production code |
| "The test would be harder than the code" | That is a sign the code needs a better interface |

---

## When to Use TDD

**Always use TDD when:**
- Implementing a new feature
- Fixing a bug (write the reproducing test first)
- The codebase has an existing test framework
- Working on business logic or domain code

**TDD may be skipped when:**
- Exploring/prototyping with explicit intention to discard the code
- Writing configuration files (no logic to test)
- Writing one-off scripts intended for immediate disposal
- The change is purely cosmetic (comments, formatting)

Even when TDD is skipped, tests should still be written afterward.

---

## Test Quality Guidelines

### Good Tests Are:

| Property | Description |
|---|---|
| **Fast** | Each test runs in milliseconds |
| **Isolated** | No test depends on another test's state |
| **Repeatable** | Same result every time, no flakiness |
| **Self-validating** | Pass or fail, no manual inspection needed |
| **Timely** | Written at the right time (before or with the code) |

### Good Tests Have:

```
[ARRANGE] Set up the test conditions
[ACT]     Perform the action being tested
[ASSERT]  Verify the expected outcome
```

### Good Test Names:

- Describe the behavior, not the implementation
- Include the scenario and expected result
- Read like a specification

```
# Good
test_empty_cart_has_zero_total()
test_discount_applied_when_coupon_is_valid()
test_returns_error_when_user_not_found()

# Bad
test_calculate()
test_discount()
test_error()
```

---

## Integration with Other Skills

- **writing-plans**: Plans should include TDD tasks ("Write test for X", "Implement X")
- **golden-rule**: Tests are code changes too - present the test plan for approval
- **verification-before-completion**: TDD naturally satisfies verification requirements
- **clean-architecture**: TDD drives toward testable, decoupled designs
