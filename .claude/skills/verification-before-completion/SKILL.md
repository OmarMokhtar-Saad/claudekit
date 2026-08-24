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

---

# The Runbook (merged from `verification-loop`)

Everything above is the discipline: no completion claim without executed evidence.
This half is the executable form of it -- a six-phase gate with the actual commands
per ecosystem. Neither half stands alone: the discipline without the commands is
unactionable, and the commands without the discipline are skippable. Merged from the
`verification-loop` skill, which is gone; the name resolves here through the registry
`renamed` alias map.

**Run this skill:** in full, after completing a feature or significant change,
before creating a PR, after a refactoring session, or on the 15-minute cadence in
Continuous Mode below. Each phase must pass before the next begins; a failure halts
and reports rather than continuing.

## The Six Phases

```
[Phase 1] BUILD VERIFICATION
    |
    v
[Phase 2] TYPE CHECKING
    |
    v
[Phase 3] LINTING
    |
    v
[Phase 4] TEST SUITE + COVERAGE
    |
    v
[Phase 5] SECURITY SCAN
    |
    v
[Phase 6] DIFF REVIEW
```

Each phase must pass before the next begins. A failure in any phase halts and reports the issue.

---

## Phase 1: Build Verification

Ensure the project compiles successfully:

```bash
# Detect build system and run
if [ -f "package.json" ]; then
    npm run build 2>&1 | tail -20
elif [ -f "pyproject.toml" ] || [ -f "setup.py" ]; then
    python3 -m py_compile $(find src/ -name "*.py" | head -20) && echo "Syntax OK"
elif [ -f "Cargo.toml" ]; then
    cargo build 2>&1 | tail -20
elif [ -f "go.mod" ]; then
    go build ./... 2>&1 | tail -20
elif [ -f "pom.xml" ]; then
    mvn compile -q 2>&1 | tail -20
fi
```

**Pass criteria:** Exit code 0, no compilation errors.
**On failure:** Report exact error, stop. Do not proceed to Phase 2.

---

## Phase 2: Type Checking

Validate type safety:

```bash
# TypeScript
if [ -f "tsconfig.json" ]; then
    npx tsc --noEmit 2>&1 | head -30
fi

# Python (mypy)
if [ -f "mypy.ini" ] || grep -q "mypy" pyproject.toml 2>/dev/null; then
    python3 -m mypy src/ --ignore-missing-imports 2>&1 | tail -20
fi

# Go (built into compiler)
# Rust (built into cargo)
```

**Pass criteria:** Zero type errors.
**Warnings:** Flag but don't fail the loop.

---

## Phase 3: Linting

Check code style compliance:

```bash
# JavaScript/TypeScript
if [ -f ".eslintrc*" ] || [ -f "eslint.config*" ]; then
    npx eslint src/ --max-warnings 0 2>&1 | tail -30
fi

# Python
if command -v flake8 &>/dev/null; then
    python3 -m flake8 src/ --count --statistics 2>&1 | tail -20
elif command -v ruff &>/dev/null; then
    ruff check src/ 2>&1 | tail -20
fi

# Go
if [ -f "go.mod" ]; then
    gofmt -l . | head -10
fi
```

**Pass criteria:** Zero errors. Warnings flagged but non-blocking.

---

## Phase 4: Test Suite + Coverage

Run tests and measure coverage:

```bash
# Node.js/TypeScript
if grep -q '"test"' package.json 2>/dev/null; then
    npm test -- --coverage 2>&1 | tail -30
fi

# Python
if [ -f "pytest.ini" ] || grep -q "pytest" pyproject.toml 2>/dev/null; then
    python3 -m pytest --tb=short --cov=src --cov-report=term-missing -q 2>&1 | tail -30
fi

# Go
if [ -f "go.mod" ]; then
    go test ./... -cover 2>&1 | tail -20
fi

# Rust
if [ -f "Cargo.toml" ]; then
    cargo test 2>&1 | tail -20
fi
```

**Pass criteria:**
- All tests pass (0 failures)
- Coverage >= 70% (warn if below 80%)
- No new test files removed or skipped

---

## Phase 5: Security Scan

Detect common security issues:

```bash
# Check for hardcoded secrets (fast, no tools needed)
echo "=== Scanning for potential secrets ==="
git diff HEAD --unified=0 | grep "^+" | grep -iE \
    '(api[_-]?key|secret|password|token|credential)["\s]*[:=]["\s]*[A-Za-z0-9+/]{10,}' \
    | grep -v "example\|placeholder\|test\|fake\|dummy\|REDACTED" | head -10

# Check for debug statements left in code
echo "=== Debug statements ==="
git diff HEAD --name-only | xargs grep -ln "console\.log\|debugger\|import pdb\|breakpoint()" 2>/dev/null | head -10

# Python security scan
if command -v bandit &>/dev/null; then
    bandit -r src/ -ll -q 2>&1 | tail -20
fi

# Node.js: check for known vulnerable packages
if [ -f "package-lock.json" ]; then
    npm audit --audit-level=high 2>&1 | tail -15
fi
```

**Pass criteria:**
- No hardcoded secrets detected
- No debug statements in non-test code
- No high/critical npm audit findings
- No high-severity bandit findings

---

## Phase 6: Diff Review

Examine the actual changes for intent vs. reality mismatches:

```bash
# Show a summary of all changed files
echo "=== Changed Files ==="
git diff HEAD --stat

echo "=== Unintended Changes? ==="
git diff HEAD --name-only | while read file; do
    echo "  $file: $(git diff HEAD -- "$file" | grep "^+" | wc -l) additions, $(git diff HEAD -- "$file" | grep "^-" | wc -l) deletions"
done
```

**Manual review checklist:**
- [ ] All changed files were intentionally modified
- [ ] No unrelated files accidentally modified
- [ ] No large binary files added unexpectedly
- [ ] No `.env` or credential files staged
- [ ] No commented-out code blocks left behind
- [ ] No TODO/FIXME introduced that should be resolved before merge

---

## Verification Report

After all phases, produce:

```
## Verification Loop Report

### Status: PASS / WARN / FAIL

Phase 1 — Build:        [PASS | FAIL: <error>]
Phase 2 — Types:        [PASS | N errors]
Phase 3 — Lint:         [PASS | N errors, N warnings]
Phase 4 — Tests:        [PASS | N failed — Coverage: XX%]
Phase 5 — Security:     [PASS | N issues]
Phase 6 — Diff Review:  [PASS | Issues: <list>]

### Issues Requiring Action
[Only listed if status is WARN or FAIL]
1. [CRITICAL/MAJOR/MINOR] Description — File:Line

### PR Readiness
[READY TO MERGE / FIX REQUIRED / NEEDS DISCUSSION]
```

---

## Continuous Mode

For extended development sessions, run the verification loop automatically every 15 minutes:

```bash
# Run in background, output to .claude/hooks/hooks.log
while true; do
    sleep 900
    bash .claude/verify-loop.sh >> .claude/hooks/hooks.log 2>&1
    echo "[$(date '+%H:%M')] Verification checkpoint complete"
done &
```

This catches regressions early while you work, rather than discovering them at PR time.

---

## Integration with PostToolUse Hook

The verification loop can be triggered automatically after significant edits:

```json
{
  "PostToolUse": [{
    "matcher": "Edit|Write",
    "hooks": [{
      "type": "command",
      "command": "bash -c 'bash .claude/hooks/quick-verify.sh &'"
    }]
  }]
}
```

A "quick-verify" runs only Phase 1 (build) and Phase 2 (types) — the fastest signal that something is broken.

