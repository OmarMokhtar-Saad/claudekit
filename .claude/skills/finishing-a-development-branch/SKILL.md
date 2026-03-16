---
name: finishing-a-development-branch
description: "Use when development work is complete on a branch - verify, present options, cleanup"
disable-model-invocation: true
---

# Finishing a Development Branch

## Core Principle

**No branch is finished until it is verified, merged (or discarded), and cleaned up.** Leaving branches in limbo creates confusion and technical debt.

---

## The Finish Process

```
[VERIFY] Ensure everything passes
    |
    v
[PRESENT] Show options to the user
    |
    v
[EXECUTE] Carry out the chosen option
    |
    v
[CLEANUP] Remove worktree and branch if appropriate
```

---

## Step 1: VERIFY

Before presenting options, verify the branch is in a good state:

### Verification Checklist

```bash
# 1. Check for uncommitted changes
git status

# 2. Run the test suite
# (project-specific test command)

# 3. Check for unpushed commits
git log origin/<branch>..HEAD

# 4. Review the full diff against main
git diff main...HEAD

# 5. Review commit history
git log --oneline main..HEAD
```

### Verification Report

```
## Branch Verification: <branch-name>

### Status
- Uncommitted changes: None / [list]
- Unpushed commits: None / [count]
- Tests: PASS / FAIL ([N] passed, [N] failed)
- Diff against main: [N] files changed, [N] insertions, [N] deletions

### Commits
[List of commits on this branch]
```

---

## Step 2: PRESENT OPTIONS

After verification, present these options to the user:

### Option A: Merge to Main

**When appropriate:**
- All tests pass
- Code has been reviewed (or self-reviewed)
- Feature is complete
- Ready for production

**What happens:**
1. Merge branch into main (fast-forward or merge commit)
2. Push main to remote
3. Delete the branch

### Option B: Create Pull Request

**When appropriate:**
- All tests pass
- Code needs team review before merging
- CI/CD pipeline should validate
- Standard team workflow requires PRs

**What happens:**
1. Push branch to remote
2. Create PR with description
3. Branch stays open until PR is merged

### Option C: Keep Branch (Not Ready)

**When appropriate:**
- Work is in progress but needs a checkpoint
- Tests pass but feature is incomplete
- Waiting on external dependency
- Need to switch to something else

**What happens:**
1. Push branch to remote (save progress)
2. Note what remains to be done
3. Branch stays open for future work

### Option D: Discard Branch

**When appropriate:**
- Approach was abandoned
- Better solution found on another branch
- Experimental work that did not pan out
- Changes are no longer needed

**What happens:**
1. Confirm with user (destructive action)
2. Delete local branch
3. Delete remote branch if pushed
4. Remove worktree if one exists

---

## Step 3: EXECUTE

### Executing Option A: Merge

```bash
# Ensure main is up to date
git checkout main
git pull origin main

# Merge the feature branch
git merge feature/branch-name

# Push to remote
git push origin main

# Delete the branch
git branch -d feature/branch-name
git push origin --delete feature/branch-name
```

### Executing Option B: Pull Request

```bash
# Push the branch
git push -u origin feature/branch-name

# Create PR
gh pr create \
  --title "feat(scope): description" \
  --body "## Summary
- What this PR does

## Test Plan
- [ ] Tests pass
- [ ] Manual verification done"
```

### Executing Option C: Keep

```bash
# Push to remote to save progress
git push -u origin feature/branch-name

# Note what remains (in PR draft or commit message)
echo "TODO: [remaining work items]"
```

### Executing Option D: Discard

```bash
# Switch to main first
git checkout main

# Delete local branch
git branch -D feature/branch-name

# Delete remote branch if it was pushed
git push origin --delete feature/branch-name
```

---

## Step 4: CLEANUP

### Worktree Cleanup

If the branch was developed in a worktree:

```bash
# Remove the worktree
git worktree remove /path/to/worktree

# Prune stale references
git worktree prune

# Verify cleanup
git worktree list
```

### Branch Cleanup

```bash
# List merged branches that can be safely deleted
git branch --merged main

# Delete merged local branches (except main)
git branch --merged main | grep -v "main" | xargs git branch -d

# Clean up remote tracking references
git fetch --prune
```

### Verify Cleanup

```bash
# Confirm branch is gone
git branch --list feature/branch-name

# Confirm worktree is removed
git worktree list

# Confirm main is clean
git checkout main
git status
```

---

## Decision Matrix

| Factor | Merge | PR | Keep | Discard |
|---|---|---|---|---|
| Tests passing | Required | Required | Preferred | N/A |
| Code reviewed | Yes/Self | Needed | N/A | N/A |
| Feature complete | Yes | Yes | No | N/A |
| Team workflow | Solo/trusted | Standard | Any | Any |
| Work quality | Production-ready | Review-ready | WIP | Abandoned |

---

## Reporting

After finishing, provide a summary:

```
## Branch Finished: <branch-name>

### Action Taken: [Merged / PR Created / Kept / Discarded]
### Changes: [N] commits, [N] files changed
### Tests: [PASS/FAIL]
### Cleanup:
- Branch: [deleted / kept]
- Worktree: [removed / N/A]
- Remote: [pushed / deleted / unchanged]

### Notes
[Any important observations or follow-up items]
```
