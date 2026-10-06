---
description: "Manage agent worktrees — create, list, remove, reap, prune isolated parallel workspaces"
argument-hint: "<create <slug> | list | remove <slug> | reap [--yes] | prune>"
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

```text
python3 .claude/operations/scripts/worktree-manager.py create <slug> [--base <ref>] [--copy <path>] [--json]
python3 .claude/operations/scripts/worktree-manager.py list [--json]
python3 .claude/operations/scripts/worktree-manager.py remove <slug> [--force] [--delete-branch] [--archive]
python3 .claude/operations/scripts/worktree-manager.py reap [--yes] [--max-deletions N] [--min-age H] [--no-fetch] [--break-stale-locks]
python3 .claude/operations/scripts/worktree-manager.py prune
```

What the manager guarantees (full reference: `worktree-manager.py --help`):

- Worktrees at `.worktrees/<slug>` on branch `agent/<slug>` (slug `^[a-z0-9][a-z0-9-]{0,40}$`); registry `.claude/state/worktrees.json` (git-ignored); max 5 concurrent. `.claude/settings.local.json` is copied in; **`.env` and secrets only with an explicit `--copy .env`**; `.worktree-env` sets `WORKTREE_SLUG`, `WORKTREE_INDEX`, `WORKTREE_PORT_OFFSET`.
- `remove` refuses dirty trees, commits not contained in the base, and the primary worktree (`--force` overrides the first two). A plain `remove` KEEPS the branch; `--delete-branch` deletes it only when proven merged into the fetched `origin/<default>`; unmerged work is refused (exit 2) unless `--force --archive`.
- `--archive` writes a verified bundle to `.claude/state/worktree-archive/<slug>-<tip8>-<UTC stamp>.bundle` (uncommitted work as a WIP commit) before deleting; with no commits beyond the default branch the tip is pinned as `refs/archive/<slug>/<stamp>` instead.
- `create` locks the worktree; `remove`/`reap` unlock only their own locks and skip foreign ones. `prune` runs `git worktree prune --expire now`.

### `reap` — dry-run by default

Walks `git worktree list`, the registry, `.worktrees/`, `.claude/worktrees/` and `agent/*` branches, printing `would reap`/`kept <name>: <reason>`; `--yes` executes and ends with `summary: reaped=N failed=N kept=N`.

- Merged = ancestor of, or squash/rebase-equivalent to, the freshly fetched `origin/<default>`; anything unanswerable is `unproven` and never deleted. A fetch failure means no deletions (`--no-fetch` measures the existing ref only).
- `--max-deletions N` (default 10) is checked first; exceeding it deletes nothing. Exit codes: 0 ok, 1 operational error, 2 validation refusal. Run from the main worktree.

## Safety Rules

- NEVER `rm -rf` a worktree or `.claude/worktrees` — use `remove`/`reap`, then `prune`. NEVER merge or push from inside an agent worktree; never check out one branch in two worktrees.
- Exit code 2 is a validation refusal: report it, do not retry with `--force` unless the user approves.

## Cleanup After a Failed Run

Run `reap` (dry run, read what is kept and why), then `reap --yes`, then `prune`; never delete an unmerged `agent/<slug>` branch by hand. Stray `.claude/worktrees/agent-*` dirs and branch recovery: see `--help`.

## Usage Examples

- `/worktree create feature-auth` — new workspace on branch agent/feature-auth (`--base main` to branch from main)
- `/worktree list` — registered worktrees + live status
- `/worktree remove feature-auth` — safe removal (branch kept unless `--delete-branch`)
- `/worktree reap` — dry-run plan of merged, clean worktrees to reclaim; `reap --yes` executes
- `/worktree prune` — reconcile registry after crashes or manual deletions
- `/worktree report` — read-only sprawl report (via `.claude/operations/scripts/repo-hygiene.py`)
- `/worktree clean` — reclaim what `report` listed; dry-run unless `--yes`, bounded by `--max-deletions`
