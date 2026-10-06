---
name: using-git-worktrees
description: "Use when needing isolated workspace for parallel development - git worktree patterns"
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
| Do not delete worktree directories manually | Use `git worktree remove` (or the manager's `remove`/`reap`); NEVER `rm -rf` a worktree |

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

# 3. Remove the worktree properly, and its branch together once the merge is confirmed
git worktree remove ../project-worktrees/feature-auth
git branch -d feature/auth   # -d refuses unmerged work; never -D without the user's say-so
```

Delete the worktree and its branch together, and only after the merge is confirmed against the fetched remote default branch. Never `rm -rf` a worktree directory.

### Cleaning Up

```bash
# Remove stale worktree references (if directory was deleted manually)
git worktree prune

# List remaining worktrees to verify cleanup
git worktree list
```

---

## Worktree-Per-Agent (Parallel AI Agents)

**One branch = one worktree = one agent.** When multiple agents work the same
repo in parallel, each gets its own worktree so edits never collide. Use the
lifecycle manager — never improvise raw `git worktree` commands for agent work:

```bash
python3 .claude/operations/scripts/worktree-manager.py create <slug> [--base <ref>] [--json]
python3 .claude/operations/scripts/worktree-manager.py list [--json]
python3 .claude/operations/scripts/worktree-manager.py remove <slug> [--force]
python3 .claude/operations/scripts/worktree-manager.py reap [--yes] [--max-deletions N] [--no-fetch]
python3 .claude/operations/scripts/worktree-manager.py prune
```

The manager creates `.worktrees/<slug>` on branch `agent/<slug>`, tracks it in
a git-ignored registry (`.claude/state/worktrees.json`), copies
`.claude/settings.local.json` into the worktree (mode preserved), and caps
concurrency at 5 (returns collapse past 4-5 parallel agents). It locks each
worktree (`git worktree lock`, reason `claudekit agent slug=<slug> ts=<epoch>`);
foreign locks are respected and a lock is never judged stale from a pid.

### Cleaning up agent worktrees: `reap`

`remove <slug>` deletes the worktree and its branch together when the branch is
proven merged; otherwise the branch is kept and the message says why. There are
no `remove` flags that delete a branch or archive; use `reap` for bulk cleanup.

`reap` (alias `cleanup`) is a reconciler and a **dry run unless `--yes`**:

- Merged proof only against the freshly fetched `origin/<default>`: ancestor, then `git cherry` (rebase, single-commit squash), then `git merge-tree --write-tree` (squash of N commits, git >= 2.38). A question git cannot answer is `unproven` and is never deleted.
- Fetch failure: no deletions (exit 1). `--no-fetch` trusts the existing ref, deletes only what it proves, and prints its age.
- Keeps locked, dirty, unmerged, unproven, too-new, primary and branch-held items, each with a reason. `--break-stale-locks` only for claudekit locks older than `--min-age` (24h) that are merged and clean.
- `--max-deletions` defaults to 25 and is checked before any change (exit 2 if exceeded, nothing deleted). Run from the main worktree.

Recovery after a mistaken removal: `git fetch <bundle> 'refs/heads/*:refs/recovered/*'`
(bundles live under `.claude/state/worktree-archive/`), then
`worktree-manager.py create <slug> --base refs/recovered/agent/<slug>`; otherwise
`git reflog`.

### Stray Claude Code `.claude/worktrees/agent-*` directories

Claude Code's own `isolation: "worktree"` leaves `.claude/worktrees/agent-<id>`
behind. If `git worktree list` shows it, `reap` then `reap --yes`. If it is not
listed and has no `.git`, it is an orphan copy that git cannot reclaim: `reap`
reports it (size, age); run `diff -rq <orphan> .` to confirm nothing unique,
then delete by hand. Non-`agent-*` dirs there (e.g. `skill-profiles`) are not
agent-owned: check manually. Never `rm -rf` a live worktree or the whole
`.claude/worktrees` directory.

### Rules for agent worktrees

| Rule | Reason |
|---|---|
| Agents commit on their `agent/*` branch only — NEVER merge or push | Single merge authority (gitOps protocol) prevents integration chaos |
| Copy local configuration, NOT secrets — `.env` requires explicit `--copy .env` | Secrets must not silently multiply across worktrees |
| Run every command from the worktree root (`cd <worktree_root> && ...`) | The ops-executor path guard and enforcement hooks scope to the process cwd / git toplevel |
| Required `.gitignore` entries: `.worktrees/` and `.claude/state/` | Worktrees and the registry are machine-local runtime state |

### Known limitation (session-rooted hooks)

The `cd`-contract above covers the Bash-invoked executor path (the Iron Law
path). PreToolUse hooks resolve their root from the *session* cwd — a `cd`
inside one Bash command does not move it. A session rooted in the MAIN tree
that uses Edit/Write directly on `.worktrees/<slug>/.claude/...` paths is
outside the hook's `.claude/*` exemption. For fully hook-scoped sessions,
root the agent session in the worktree (or use the harness's native worktree
isolation, e.g. Claude Code's `--worktree` / `EnterWorktree` / Agent
`isolation: "worktree"`).

### Per-worktree environment (ports & devices)

The manager writes `.worktree-env` into each worktree:

```
WORKTREE_SLUG=<slug>
WORKTREE_INDEX=<n>
WORKTREE_PORT_OFFSET=<n*10>
```

Use the offset to keep parallel dev servers, Appium servers, emulators, or
device assignments from colliding: e.g. `PORT=$((3000 + WORKTREE_PORT_OFFSET))`,
`APPIUM_PORT=$((4723 + WORKTREE_PORT_OFFSET))`, and assign each device UDID to
exactly one worktree.

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
