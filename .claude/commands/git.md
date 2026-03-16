---
description: "Git operations via gitOps agent"
model: haiku
---

# GitOps Command

Invoke the gitOps agent to perform safe, structured git operations.

## Agent Reference

See @agents/gitOps.md for the full agent specification.

## Task

Git operation: $ARGUMENTS

## Mandatory Skills

You MUST load and apply the following skills before proceeding:

- **using-superpowers** - Core agent capabilities and tool usage
- **using-git-worktrees** - Git worktree management for parallel work
- **finishing-a-development-branch** - Branch completion, merge, and cleanup
- **security-checklist** - Pre-commit and pre-push security validation

## Safety Rules

These rules are NON-NEGOTIABLE:

1. **NEVER force-push** to main, master, develop, or any shared branch
2. **NEVER use `git reset --hard`** without explicit user confirmation
3. **NEVER use `git clean -f`** without explicit user confirmation
4. **NEVER delete remote branches** without explicit user confirmation
5. **NEVER commit files** containing secrets, credentials, API keys, or tokens
6. **NEVER skip pre-commit hooks** (no --no-verify)
7. **ALWAYS check `git status`** before any destructive operation
8. **ALWAYS create a backup branch** before rebasing

## Branch Naming Convention

Follow this pattern unless the project has a documented alternative:

```
<type>/<short-description>

Types:
  feat/     - New feature
  fix/      - Bug fix
  refactor/ - Code refactoring
  docs/     - Documentation only
  test/     - Test additions or fixes
  chore/    - Maintenance tasks
  hotfix/   - Urgent production fix
```

Examples:
- `feat/user-authentication`
- `fix/null-pointer-in-parser`
- `refactor/extract-validation-service`

## Commit Message Format

Follow Conventional Commits unless the project uses a different standard:

```
<type>(<scope>): <short description>

[optional body]

[optional footer]
```

Rules:
- Subject line: max 72 characters, imperative mood, no period
- Body: wrap at 80 characters, explain what and why (not how)
- Footer: reference issues, breaking changes

Examples:
- `feat(auth): add JWT refresh token rotation`
- `fix(parser): handle null input in CSV parser`
- `refactor(api): extract validation middleware`

## Common Operations

### Create Feature Branch
1. Ensure working tree is clean
2. Fetch latest from remote
3. Create branch from up-to-date base branch
4. Push branch with upstream tracking

### Commit Changes
1. Run `git status` to review changes
2. Stage relevant files (never use `git add .` blindly)
3. Run pre-commit checks
4. Create commit with proper message format
5. Verify commit with `git log -1`

### Finish Branch
1. Ensure all changes are committed
2. Run verification suite
3. Rebase on latest base branch (if needed)
4. Push final changes
5. Create pull request (if applicable)
6. Report status

### Sync with Remote
1. Fetch all remotes
2. Check for divergence
3. Pull with rebase (preferred) or merge
4. Report any conflicts

### Stash and Restore
1. Stash current changes with descriptive message
2. Perform the needed operation
3. Restore stashed changes
4. Resolve any conflicts

## Pre-Push Checklist

Before pushing ANY branch, verify:

- [ ] All files staged intentionally (no accidental inclusions)
- [ ] No secrets or credentials in staged files
- [ ] Commit messages follow project conventions
- [ ] Branch name follows naming convention
- [ ] Tests pass locally (if applicable)
- [ ] No merge conflicts with target branch

## Usage Examples

- `/git create branch feat/user-auth from main`
- `/git commit staged changes`
- `/git finish branch and create PR`
- `/git sync with remote`
- `/git stash current work`
- `/git rebase on main`
- `/git log --oneline last 20 commits`
- `/git cherry-pick abc123 to release branch`

## Output

After each operation, report:
- What was done
- Current branch and status
- Any warnings or issues
- Suggested next steps
