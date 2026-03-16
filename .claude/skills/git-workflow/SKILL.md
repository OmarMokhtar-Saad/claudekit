---
name: git-workflow
description: "Use when performing git operations - branching, committing, PRs, releases"
disable-model-invocation: true
---

# Git Workflow

## Core Principle

**Every commit should be a clean, atomic unit of change that could be safely reverted.** Messy history is technical debt that compounds over time.

---

## Branch Naming

### Convention

```
<type>/<short-description>
```

### Types

| Type | Use For | Example |
|---|---|---|
| `feature/` | New functionality | `feature/user-authentication` |
| `fix/` | Bug fixes | `fix/login-timeout` |
| `refactor/` | Code restructuring | `refactor/extract-payment-service` |
| `docs/` | Documentation only | `docs/api-reference` |
| `test/` | Test additions or fixes | `test/payment-edge-cases` |
| `chore/` | Maintenance tasks | `chore/update-dependencies` |
| `hotfix/` | Urgent production fix | `hotfix/crash-on-startup` |

### Rules

- Use lowercase with hyphens (not underscores or camelCase)
- Keep descriptions short (2-4 words)
- Include ticket/issue number if applicable: `fix/PROJ-123-login-timeout`
- Never use spaces or special characters

---

## Commit Message Format

### Conventional Commits

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Type Prefixes

| Type | Description |
|---|---|
| `feat` | New feature |
| `fix` | Bug fix |
| `refactor` | Code restructuring (no behavior change) |
| `test` | Adding or updating tests |
| `docs` | Documentation changes |
| `style` | Formatting, whitespace (no logic change) |
| `perf` | Performance improvement |
| `chore` | Build, CI, tooling changes |
| `revert` | Reverting a previous commit |

### Subject Rules

- Use imperative mood ("add", not "added" or "adds")
- Do not capitalize the first letter
- No period at the end
- Maximum 72 characters
- Complete the sentence: "If applied, this commit will ___"

### Body Rules

- Separated from subject by a blank line
- Explain WHAT and WHY, not HOW (the diff shows how)
- Wrap at 72 characters
- Use bullet points for multiple items

### Examples

```
feat(auth): add password reset via email

Users can now request a password reset link sent to their registered
email address. The link expires after 24 hours.

- Add reset token generation
- Add email sending service integration
- Add token validation endpoint

Closes #234
```

```
fix(orders): prevent duplicate charge on retry

When a payment API call times out and the user retries, the system was
creating a second charge. Now we check for existing pending charges
before initiating a new one.

Fixes #567
```

---

## Operation Workflows

### Starting New Work

```bash
# Update main branch
git checkout main
git pull origin main

# Create feature branch
git checkout -b feature/description

# Work...
git add <specific-files>
git commit -m "feat(scope): description"
```

### Saving Progress

```bash
# Stage specific files (not git add -A)
git add src/module/file.py
git add tests/test_file.py

# Commit with descriptive message
git commit -m "feat(module): add validation logic"
```

### Staying Current with Main

```bash
# Preferred: rebase for clean history
git fetch origin
git rebase origin/main

# Alternative: merge if rebase would be complex
git merge origin/main
```

### Preparing for Review

```bash
# Verify all tests pass
# Review your own diff
git diff main...HEAD

# Check commit history
git log --oneline main..HEAD

# Push to remote
git push -u origin feature/description
```

### Creating a Pull Request

```bash
# Using GitHub CLI
gh pr create --title "feat(scope): description" --body "## Summary
- Change 1
- Change 2

## Test Plan
- [ ] Unit tests pass
- [ ] Manual testing completed"
```

---

## Commit Hygiene

### Do

- Commit early and often during development
- Each commit should compile/build successfully
- Each commit should pass tests
- Group related changes in one commit
- Write meaningful commit messages

### Do Not

- Commit generated files (build output, compiled assets)
- Commit environment-specific files (.env, local config)
- Mix formatting changes with logic changes
- Create "WIP" commits on shared branches
- Force push to shared branches

---

## Error Handling in Git Operations

### Merge Conflicts

```bash
# 1. See which files conflict
git status

# 2. Open conflicted files and resolve
# Look for <<<<<<< ======= >>>>>>> markers

# 3. After resolving, stage the files
git add <resolved-files>

# 4. Continue the operation
git rebase --continue   # if rebasing
git merge --continue    # if merging
git commit              # if was a merge conflict during commit
```

### Undoing Mistakes

| Situation | Command | Safety |
|---|---|---|
| Undo last commit (keep changes) | `git reset --soft HEAD~1` | Safe |
| Discard unstaged changes in a file | `git checkout -- <file>` | Destructive |
| Discard all uncommitted changes | `git stash` (recoverable) | Semi-safe |
| Revert a pushed commit | `git revert <sha>` | Safe |
| Fix commit message | `git commit --amend` | Safe if not pushed |

### Recovering Lost Work

```bash
# Find recently lost commits
git reflog

# Recover a specific commit
git checkout <sha>

# Create a branch from recovered commit
git checkout -b recovery-branch <sha>
```

---

## Tag and Release

### Semantic Versioning

```
MAJOR.MINOR.PATCH
```

| Component | Increment When |
|---|---|
| MAJOR | Breaking changes (incompatible API changes) |
| MINOR | New features (backward compatible) |
| PATCH | Bug fixes (backward compatible) |

### Creating a Release

```bash
# Tag the release
git tag -a v1.2.3 -m "Release v1.2.3: brief description"

# Push the tag
git push origin v1.2.3
```

---

## Protected Branch Rules

| Rule | Purpose |
|---|---|
| No direct pushes to main | All changes go through PR review |
| Require passing CI | Catch issues before merge |
| Require code review | Second pair of eyes on every change |
| No force push on main | Protect shared history |
| Linear history (optional) | Clean, readable history |
