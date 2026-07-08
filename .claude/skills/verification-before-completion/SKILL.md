---
name: verification-before-completion
description: "Use when about to claim work is complete or passing - requires running verification commands before making success claims"
disable-model-invocation: true
---

# Verification Before Completion

## The Iron Law

**NEVER claim work is complete, passing, or successful without running verification commands and reading their output.**

This is non-negotiable. No exceptions. No shortcuts.

---

## The Gate Function

Every completion claim must pass through this gate:

```
[IDENTIFY] What needs to be verified?
    |
    v
[RUN] Execute verification commands
    |
    v
[READ] Read the FULL output (not just exit code)
    |
    v
[VERIFY] Confirm the output matches expectations
    |
    v
[CLAIM] Only now may you claim success
```

### Step 1: IDENTIFY

Determine what verification is needed based on what was done:

| Change Type | Verification Required |
|---|---|
| Code change | Run tests for the modified module |
| New feature | Run new tests + existing tests |
| Bug fix | Run the specific failing test + regression suite |
| Refactoring | Run full test suite for affected area |
| Configuration | Verify config loads correctly |
| Build change | Run full build |
| Dependency update | Run full test suite |

### Step 2: RUN

Execute the verification commands:
- Run them in the actual project environment
- Do not simulate or predict outcomes
- Capture full output

### Step 3: READ

Read the COMPLETE output:
- Check exit codes
- Read error messages
- Count pass/fail numbers
- Look for warnings
- Check for skipped tests

### Step 4: VERIFY

Confirm the output matches expectations:
- All tests pass (not just "most")
- No new warnings introduced
- No skipped tests that were previously running
- Build completes without errors
- No deprecation warnings in new code

### Step 5: REFUTE

Before claiming, attempt to refute your own conclusion:

- **What input or state would break this?** (edge case, empty input, other platform)
- **What did I NOT run?** A skipped check is a hole in the claim, not a footnote.
- **Which claim rests on reading prose rather than executing something?**

If any answer weakens the conclusion, run the missing check or downgrade the claim
explicitly ("done but unverified for X"). A conclusion that was never challenged is an
opinion, not a verification.

### Step 6: CLAIM

Only after steps 1-5 succeed may you state:
- "Tests pass"
- "Implementation is complete"
- "The fix works"
- "The build succeeds"

---

## Common Failures

| Failure | What Actually Happened |
|---|---|
| "Tests pass" without running them | You have no evidence for this claim |
| Running tests but not reading output | You missed the 3 failures at the bottom |
| Reading only the last line | You missed compile errors in the middle |
| Seeing "BUILD SUCCESSFUL" | But there were 0 tests executed (empty suite) |
| Trusting exit code 0 | Some frameworks return 0 even with failures |
| Running wrong test suite | You tested module A but changed module B |
| Running tests in wrong directory | Tests passed against old code |

---

## Red Flags

If you catch yourself thinking any of these, STOP:

| Red Flag Thought | What to Do Instead |
|---|---|
| "The tests should pass because..." | Run them and find out |
| "This is a trivial change, no need to verify" | Trivial changes cause non-trivial bugs |
| "I verified a similar change earlier" | Each change needs its own verification |
| "The logic is obviously correct" | Logic that seems obvious is often wrong |
| "I'll run the tests after I finish everything" | Run them now, after each meaningful change |
| "The user can run the tests" | Verification is YOUR responsibility |

---

## Rationalization Prevention

### The "Obviously Works" Trap

You see simple code and think: "This clearly works, no need to test."

**Reality:** The most confident claims of correctness are the most likely to be wrong. Confidence is not evidence.

### The "Same as Before" Trap

You think: "I made the same kind of change earlier and it worked."

**Reality:** Context matters. The same pattern in a different file may have different dependencies, edge cases, or interactions.

### The "Tests Are Slow" Trap

You think: "Running the full suite takes too long, I'll skip it."

**Reality:** Run at minimum the targeted tests. A partial verification is better than none. But note in your report that you ran a subset.

### The "I Checked the Diff" Trap

You think: "The diff looks correct, so it works."

**Reality:** Diffs show what changed, not whether the change is correct. Only execution reveals runtime behavior.

---

## Verification Report Format

When reporting verification results:

```
## Verification Results

### Command Run
[exact command]

### Output Summary
- Tests: [X passed, Y failed, Z skipped]
- Build: [SUCCESS / FAILED]
- Warnings: [count]

### Full Output
[include relevant output, not just summary]

### Verdict
[PASS / FAIL with explanation]
```

---

## When Verification Is Not Possible

Rare cases where you genuinely cannot verify:

- No test suite exists for the changed code
- The verification requires external services that are unavailable
- The change only affects runtime behavior that cannot be tested locally

In these cases:
1. State clearly that you CANNOT verify
2. Explain WHY verification is not possible
3. Suggest how the user can verify manually
4. Do NOT claim the work is complete - say "implementation is done but unverified"
