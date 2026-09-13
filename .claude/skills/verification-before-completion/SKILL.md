---
name: verification-before-completion
description: "Use when about to claim work is complete or passing, or when running a pre-PR quality gate - requires executed evidence before any success claim, and carries the six-phase build/types/lint/tests/security/diff runbook."
allowed-tools: Read, Bash, Grep, Glob
---

# Verification Before Completion

## The Iron Law

**NEVER claim work is complete, passing, or successful without running verification commands and reading their output.**

This is non-negotiable. No exceptions. No shortcuts.

---

## The Gate Function

Every completion claim must pass through this gate, in order:
IDENTIFY -> RUN -> READ -> VERIFY -> REFUTE -> CLAIM.
Read [references/gate-and-traps.md](references/gate-and-traps.md) when you want the gate diagram, the rationalization traps in full, or the single-claim report template.

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


**Rationalization traps** ("Obviously Works", "Same as Before", "Tests Are Slow",
"I Checked the Diff"): confidence is not evidence, and diffs show what changed, not
whether it works. If the full suite is too slow, run at minimum the targeted tests and
note in your report that you ran a subset.

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

---

# The Runbook (merged from `verification-loop`)

The executable form of the discipline above: a six-phase gate. Run it in full after
a feature or significant change, before creating a PR, and after a refactoring
session. Each phase must pass before the next begins; a failure halts and reports
rather than continuing.

| Phase | Pass criteria |
|---|---|
| 1. Build | Exit code 0, no compilation errors; on failure stop |
| 2. Types | Zero type errors (warnings flagged, not failing) |
| 3. Lint | Zero errors (warnings flagged, non-blocking) |
| 4. Tests + coverage | 0 failures; coverage >= 70% (warn below 80%); no tests removed or skipped |
| 5. Security | No hardcoded secrets, no debug statements in non-test code, no high/critical audit findings |
| 6. Diff review | Every changed file intentional; no `.env`/credentials, stray binaries, commented-out code, or new TODO/FIXME |

Read [references/runbook.md](references/runbook.md) when you execute the runbook -- it carries the per-ecosystem commands for every phase, the Verification Loop Report template, Continuous Mode, and the PostToolUse quick-verify hook.
