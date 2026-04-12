---
name: ship
description: Full ship pipeline from pre-flight checks to PR creation
usage: /ship [--dry-run] [--skip-tests] [--target=branch] [--checkpoint]
args:
  dry-run:
    description: Run all checks without making any changes
    required: false
  skip-tests:
    description: Skip the test execution stage (not recommended)
    required: false
  target:
    description: Target branch for the PR (default auto-detected from repo)
    required: false
  checkpoint:
    description: Create a checkpoint before starting the pipeline
    required: false
---

# /ship - Full Ship Pipeline

Execute a complete shipping pipeline: pre-flight checks, code review, testing, security scan, git operations, and PR creation. Reports pass/fail for each stage and stops on critical failures.

## Pipeline Stages

### Stage 1: Pre-Flight Checks

Verify the project is in a shippable state before proceeding.

**Checks:**
1. **Git status clean**: No untracked files that should be committed.
2. **Branch check**: Not on main/master (should be on a feature branch).
3. **Branch up to date**: No upstream changes that need to be pulled.
4. **No merge conflicts**: No unresolved conflict markers in tracked files.
5. **Build succeeds**: Run the project build command if configured.
6. **Dependencies resolved**: `node_modules/`, `venv/`, etc. are present and up to date.

**Output:**
```
STAGE 1: PRE-FLIGHT CHECKS
===========================
  [PASS] Git working tree clean
  [PASS] On feature branch: feature/auth-improvements
  [PASS] Branch up to date with origin
  [PASS] No merge conflicts detected
  [PASS] Build successful
  [WARN] Lock file out of date (package-lock.json)

Result: PASS (5/6 checks passed, 1 warning)
```

**Stop condition:** FAIL on any critical check (merge conflicts, wrong branch). Warnings do not stop the pipeline.

### Stage 2: Code Review

Automated code quality review of all changes.

**Checks:**
1. **Lint**: Run project linter on changed files.
2. **Type check**: Run type checker if applicable (tsc, mypy, etc.).
3. **Format check**: Verify code formatting matches project standards.
4. **Placeholder detection**: Run `check-comment-replacement` hook on staged diffs.
5. **Code complexity**: Flag functions with high cyclomatic complexity.
6. **Import analysis**: Check for unused imports, circular dependencies.

**Output:**
```
STAGE 2: CODE REVIEW
=====================
  [PASS] Lint: 0 errors, 0 warnings
  [PASS] Types: No type errors
  [PASS] Formatting: All files formatted correctly
  [PASS] No placeholder comments detected
  [WARN] High complexity: src/auth/validator.ts:handleAuth (complexity: 15)
  [PASS] No circular dependencies

Result: PASS (5/6 checks passed, 1 warning)
```

**Stop condition:** FAIL on lint errors or type errors. Warnings are included in the PR description.

### Stage 3: Testing

Run the project test suite and evaluate coverage.

**Checks:**
1. **Unit tests**: Run unit test suite.
2. **Integration tests**: Run integration tests if available.
3. **Coverage threshold**: Check if coverage meets the project minimum (default 80%).
4. **New code coverage**: Verify changed files have adequate test coverage.
5. **Test regression**: Compare test count with previous run (flag if tests were removed).

**Output:**
```
STAGE 3: TESTING
================
  [PASS] Unit tests: 142 passed, 0 failed, 0 skipped (12.3s)
  [PASS] Integration tests: 23 passed, 0 failed (45.1s)
  [PASS] Coverage: 84% (threshold: 80%)
  [WARN] New code coverage: src/auth/refresh.ts at 65% (below 80%)
  [PASS] Test count: 165 (was 160, +5 new tests)

Result: PASS (4/5 checks passed, 1 warning)
```

**Stop condition:** FAIL if any tests fail. WARN if coverage is below threshold (does not stop pipeline).

### Stage 4: Security Scan

Check for security issues in the changes.

**Checks:**
1. **Secrets scan**: Run `file-guard` hook on all changed files.
2. **Dependency audit**: Check for known vulnerabilities (`npm audit`, `pip-audit`, etc.).
3. **Prompt injection**: Run `prompt-injection-scanner` on any AI-generated content.
4. **Sensitive file check**: Verify no sensitive files are staged (`.env`, keys, etc.).
5. **Permission check**: Flag any changed file permissions or new executables.

**Output:**
```
STAGE 4: SECURITY SCAN
=======================
  [PASS] No secrets in changed files
  [PASS] No known vulnerabilities in dependencies
  [PASS] No prompt injection patterns detected
  [PASS] No sensitive files staged
  [PASS] No suspicious permission changes

Result: PASS (5/5 checks passed)
```

**Stop condition:** FAIL on any secrets detected or sensitive files staged. This is always a critical failure.

### Stage 5: Git Operations

Prepare the branch for PR creation.

**Actions:**
1. Stage all relevant changes (`git add` modified and new files).
2. Generate a descriptive commit message from the changes.
3. Create the commit.
4. Push the branch to the remote.
5. Verify the push succeeded.

**Output:**
```
STAGE 5: GIT OPERATIONS
========================
  [DONE] Staged 8 files (6 modified, 2 new)
  [DONE] Committed: "Add input validation to auth endpoints"
  [DONE] Pushed to origin/feature/auth-improvements

Result: PASS
```

**Stop condition:** FAIL if push is rejected (usually means branch needs rebase).

### Stage 6: PR Creation

Create a pull request with a comprehensive description.

**Actions:**
1. Determine the target branch (auto-detect or use `--target`).
2. Generate PR title from the commit(s).
3. Generate PR body with:
   - Summary of changes.
   - Files modified with brief descriptions.
   - Test results summary.
   - Code review findings (warnings).
   - Security scan results.
4. Create the PR via `gh pr create`.
5. Report the PR URL.

**Output:**
```
STAGE 6: PR CREATION
=====================
  [DONE] Target branch: main
  [DONE] PR title: "Add input validation to auth endpoints"
  [DONE] PR created: https://github.com/org/repo/pull/47

Result: PASS
```

## Pipeline Summary

After all stages complete, display a summary:

```
SHIP PIPELINE COMPLETE
======================

Stage 1: Pre-Flight    PASS  (5/6, 1 warn)
Stage 2: Code Review   PASS  (5/6, 1 warn)
Stage 3: Testing       PASS  (4/5, 1 warn)
Stage 4: Security      PASS  (5/5)
Stage 5: Git Ops       PASS
Stage 6: PR Created    PASS

PR: https://github.com/org/repo/pull/47
Branch: feature/auth-improvements → main

Warnings (3):
  - Lock file out of date (package-lock.json)
  - High complexity: src/auth/validator.ts:handleAuth
  - New code coverage below threshold: src/auth/refresh.ts

Overall: SUCCESS with 3 warnings
```

## Dry Run Mode

When `--dry-run` is specified:
- Run Stages 1-4 (all checks) normally.
- Skip Stage 5 (git operations) and Stage 6 (PR creation).
- Report what would have been committed and pushed.
- Useful for validating before actually shipping.

## Behavior

1. If `--checkpoint` is set, create a checkpoint before starting.
2. Execute stages 1 through 6 sequentially.
3. Stop immediately on any critical failure (exit code 1).
4. Accumulate warnings and include them in the final report.
5. If `--dry-run`, stop after Stage 4 with a summary of what would happen.
6. If `--skip-tests`, skip Stage 3 (add a warning to the PR description).
7. On failure, report which stage failed, what went wrong, and how to fix it.
8. The universal flags (`--depth`, `--format`, `--persona`, `--save`) apply as usual.
