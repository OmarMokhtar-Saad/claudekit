---
name: using-git-worktrees
description: "Use when needing isolated workspace for parallel development - git worktree patterns"
disable-model-invocation: true
---

# Using Git Worktrees

## Core Principle

**Worktrees provide isolated workspaces without the overhead of cloning.** Use them when you need to work on multiple branches simultaneously without stashing or switching context.

---

## What Are Git Worktrees?

A git worktree creates a separate working directory linked to the same repository. Each worktree has its own checked-out branch, but shares the same git history.

```
main-repo/              (main branch - primary worktree)
├── .git/
├── src/
└── ...

../worktrees/
├── feature-auth/       (feature/auth branch - linked worktree)
│   ├── src/
│   └── ...
└── fix-login/          (fix/login branch - linked worktree)
    ├── src/
    └── ...
```

---

## Directory Selection

### Where to Place Worktrees

**Recommended structure:**
```
project-root/           # Main repository
../project-worktrees/   # Worktrees directory (sibling to main repo)
    ├── feature-x/
    ├── fix-y/
    └── refactor-z/
```

**Why sibling directory?**
- Keeps worktrees outside the main repo
- Avoids nesting repos within repos
- Easy to find and manage
- Does not pollute the main repo's directory listing

### Naming Conventions

- Use the branch name with slashes replaced by hyphens
- Example: `feature/user-auth` -> worktree dir `feature-user-auth`

---

## Safety Verification

### Before Creating a Worktree

1. **Check .gitignore** - Ensure the worktree location will not be tracked:

```bash
# If placing worktrees inside the repo parent, check .gitignore
# The worktree directory should be ignored if it's under the repo

# Verify worktree location is not inside the git repo
git -C /path/to/main-repo rev-parse --show-toplevel
# Compare with your intended worktree path
```

2. **Check for existing worktrees:**

```bash
git worktree list
```

3. **Verify the branch exists or create it:**

```bash
# Check if branch exists
git branch --list feature/my-feature

# If not, create it
git branch feature/my-feature
```

---

## Creation Steps

### Step 1: Create the Worktree

```bash
# From the main repository
cd /path/to/main-repo

# Create worktree with existing branch
git worktree add ../project-worktrees/feature-auth feature/auth

# Create worktree with new branch based on main
git worktree add -b feature/new-thing ../project-worktrees/feature-new-thing main
```

### Step 2: Verify the Worktree

```bash
# List all worktrees
git worktree list

# Verify the new worktree
ls ../project-worktrees/feature-auth
cd ../project-worktrees/feature-auth
git status
git branch
```

### Step 3: Set Up the Worktree

The worktree is a fresh checkout. It may need setup:

```bash
cd ../project-worktrees/feature-auth

# Install dependencies (project-specific)
# npm install / pip install -r requirements.txt / etc.

# Copy local configuration if needed (NOT secrets)
# cp ../main-repo/.env.example .env.local

# Verify the project builds
# npm run build / make / etc.
```

---

## Setup Commands

### Common Setup After Creating Worktree

| Task | Command | Why |
|---|---|---|
| Install dependencies | (language-specific install command) | Worktree has no node_modules/venv/etc |
| Copy local config | Copy from main or template | Environment-specific settings |
| Build the project | (language-specific build command) | Verify everything compiles |
| Run tests | (language-specific test command) | Verify clean state |

---

## Working with Worktrees

### Sharing Git State

All worktrees share:
- Same git history and objects
- Same remotes
- Same stash

All worktrees have separate:
- Working directory
- Index (staging area)
- Checked-out branch
- Untracked files

### Important Rules

| Rule | Reason |
|---|---|
| Never check out the same branch in two worktrees | Git prevents this - each branch can only be checked out once |
| Commit or stash before removing a worktree | Uncommitted changes will be lost |
| Fetch from the main worktree | All worktrees see the fetched refs |
| Do not delete worktree directories manually | Use `git worktree remove` instead |

---

## Removing Worktrees

### When Work Is Complete

```bash
# From any worktree or the main repo

# 1. Verify all changes are committed/pushed
cd ../project-worktrees/feature-auth
git status
git log origin/feature/auth..HEAD  # Check unpushed commits

# 2. Return to main repo
cd /path/to/main-repo

# 3. Remove the worktree properly
git worktree remove ../project-worktrees/feature-auth

# 4. Optionally delete the branch if merged
git branch -d feature/auth
```

### Cleaning Up

```bash
# Remove stale worktree references (if directory was deleted manually)
git worktree prune

# List remaining worktrees to verify cleanup
git worktree list
```

---

## Common Use Cases

### Parallel Feature Development

```
Main worktree: Reviewing PR on feature-A
Worktree 2: Actively developing feature-B
Worktree 3: Investigating a bug on fix/issue-123
```

### Code Review

```
Main worktree: Your current development work (don't disrupt)
Worktree 2: Check out the PR branch, run tests, review code
```

### Hotfix While Developing

```
Main worktree: Mid-feature development (messy state)
Worktree 2: Clean checkout of main for emergency hotfix
```

---

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| "Branch is already checked out" | Branch active in another worktree | Use a different branch or remove the other worktree |
| Missing dependencies after creating | Worktree is fresh checkout | Run install/setup commands |
| Tests fail in worktree but pass in main | Different dependency versions | Reinstall dependencies |
| "Not a git repository" | Inside worktree that was manually deleted | Run `git worktree prune` |
