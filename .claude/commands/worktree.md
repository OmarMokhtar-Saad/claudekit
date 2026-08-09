---
description: "Manage agent worktrees — create, list, remove, prune isolated parallel workspaces"
argument-hint: "<create <slug> | list | remove <slug> | prune>"
model: haiku
---

# Worktree Command

Thin front-end to the worktree lifecycle manager. This command is the
*primitive* (one worktree's lifecycle); `/batch` is the *orchestrator* that
uses it for large-scale parallel changes.

## Task

Worktree operation: $ARGUMENTS

## Mandatory Skills

You MUST load and apply the following skills before proceeding:

- **using-superpowers** - Core agent capabilities and tool usage
- **using-git-worktrees** - Worktree patterns, safety rules, and the worktree-per-agent model

## Execution

All lifecycle operations go through the manager script — never improvise raw
`git worktree` commands:

```bash
python3 .claude/operations/scripts/worktree-manager.py create <slug> [--base <ref>] [--copy <path>] [--json]
python3 .claude/operations/scripts/worktree-manager.py list [--json]
python3 .claude/operations/scripts/worktree-manager.py remove <slug> [--force]
python3 .claude/operations/scripts/worktree-manager.py prune
```

What the manager guarantees:

- Worktrees at `.worktrees/<slug>` on branch `agent/<slug>`; slug validated (`^[a-z0-9][a-z0-9-]{0,40}$`).
- Registry at `.claude/state/worktrees.json` (git-ignored, repo-relative paths, atomic writes under a lock).
- Max 5 concurrent worktrees — returns collapse past 4-5 parallel agents.
- `.claude/settings.local.json` copied into new worktrees (mode preserved). **`.env` and other secrets are never copied by default** — only with an explicit `--copy .env`.
- `.worktree-env` written per worktree with `WORKTREE_SLUG`, `WORKTREE_INDEX`, `WORKTREE_PORT_OFFSET` (index x 10) for port/device assignment.
- `remove` refuses dirty trees, commits not contained in the base, and the primary worktree; `--force` overrides the first two only.

## Safety Rules

- NEVER delete a worktree directory with `rm -rf` — use `remove`, then `prune` for stragglers.
- NEVER merge or push from inside an agent worktree — agents commit on their `agent/*` branch only; the gitOps merge protocol integrates (see the gitOps agent's Multi-Agent Merge Protocol).
- NEVER check out the same branch in two worktrees (git prevents it — do not work around it).
- Exit code 2 from the manager means a validation refusal — report it, do not retry with `--force` unless the user explicitly approves.

## Cleanup After a Failed Run

```bash
python3 .claude/operations/scripts/worktree-manager.py prune
git worktree list                       # verify
git branch -D agent/<slug>              # only after merge or explicit abandon
```

## Usage Examples

- `/worktree create feature-auth` — new isolated workspace on branch agent/feature-auth
- `/worktree create ocr-fix --base main` — branch from main instead of HEAD
- `/worktree list` — registered worktrees + live status
- `/worktree remove feature-auth` — safe removal (branch kept for merge)
- `/worktree prune` — reconcile registry after crashes or manual deletions
