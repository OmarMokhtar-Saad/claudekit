---
name: verification-loop
description: "Use after completing a feature or before creating a PR — six-phase systematic quality assurance: build, types, lint, tests, security, diff review"
disable-model-invocation: true
allowed-tools: Read, Bash, Grep, Glob
---

# Verification Loop

## Purpose

A structured, six-phase quality gate that runs before any code is declared complete or ready for review. This is more thorough than a single test run — it's a complete health check.

**Run this skill:**
- After completing a feature or significant change
- Before creating a PR
- After a refactoring session
- Every 15 minutes during extended development (continuous mode)

---

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
