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

What the manager guarantees:

- Worktrees at `.worktrees/<slug>` on branch `agent/<slug>`; slug validated (`^[a-z0-9][a-z0-9-]{0,40}$`).
- Registry at `.claude/state/worktrees.json` (git-ignored, repo-relative paths, atomic writes under a lock).
- Max 5 concurrent worktrees — returns collapse past 4-5 parallel agents.
- `.claude/settings.local.json` copied into new worktrees (mode preserved). **`.env` and other secrets are never copied by default** — only with an explicit `--copy .env`.
- `.worktree-env` written per worktree with `WORKTREE_SLUG`, `WORKTREE_INDEX`, `WORKTREE_PORT_OFFSET` (index x 10) for port/device assignment.
- `remove` refuses dirty trees, commits not contained in the base, and the primary worktree; `--force` overrides the first two only. A plain `remove` deletes the worktree and KEEPS the branch. `remove --delete-branch` also deletes the branch, only when it is proven merged into the fetched `origin/<default>`; unmerged work is refused (exit 2) unless `--force --archive`. `--archive` writes a verified git bundle to `.claude/state/worktree-archive/<slug>-<tip8>-<UTC stamp>.bundle` (uncommitted work is included as a WIP commit) before anything is deleted; if the branch has no commits beyond the default branch, git refuses an empty bundle and the tip is pinned as `refs/archive/<slug>/<stamp>` instead (WIP: `refs/archive/<slug>/wip-<stamp>`).
- `create` locks the worktree (`git worktree lock`, reason `claudekit agent slug=<slug> ts=<epoch>`). `remove`/`reap` unlock only their own locks, after every check passed; foreign locks are respected and the item is skipped. Lock liveness is never inferred from a pid. `reap --break-stale-locks` breaks a claudekit lock only when it is older than `--min-age` AND the worktree is merged AND clean.
- `prune` runs `git worktree prune --expire now` (also drops trees on unmounted volumes; locked trees are spared).

### `reap` — reconcile and clean up (dry-run by default)

`reap` (alias `cleanup`) walks `git worktree list`, the registry, `.worktrees/`, `.claude/worktrees/` and local `agent/*` branches. It is a dry run unless `--yes` is given: it prints what it would remove and what it keeps, with a reason per item (`unmerged`, `unproven`, `dirty`, `locked`, `too-new`, `branch-held`, ...).

- **Merged proof**, measured only against the freshly fetched `refs/remotes/origin/<default>` (default from `origin/HEAD`, else main/master/develop/trunk; more than one candidate = `unproven`): (1) branch is an ancestor; (2) `git cherry` shows no unapplied commit (rebase merge, single-commit squash); (3) squash of N commits via `git merge-tree --write-tree` when git supports it (>= 2.38). Anything that cannot be answered is `unproven` and is never deleted.
- **Fetch failure means no deletions** (exit 1). `--no-fetch` measures the existing remote ref only, deletes only what that ref proves, and prints the ref's age.
- Reapable = not the primary worktree, not locked, clean, merged, branch not protected and not checked out elsewhere. `reap --yes` removes the worktree and deletes the branch together (only reap does this by default).
- `--max-deletions N` (default 10) is checked before any change; exceeding it exits 2 and deletes nothing. `--min-age H` (hours, default 24) is how old an own lock must be to count as stale; `mq-*` worktrees use 30 minutes. `reap` never pushes.
- Output: `would reap <name>` (dry run), `reaped <name> (branch <b> deleted)`, `kept <name>: <reason>`, `orphan-dir <path> size= age= agent-owned= too-new=` (report only), `nothing to reclaim`, and with `--yes` `summary: reaped=N failed=N kept=N`. With `--no-fetch`: `no-fetch: measuring against <ref> at <sha> (age Nh)`.
- Exit codes: 0 ok, 1 operational error (fetch failed, an item failed), 2 validation refusal.
- Run it from the main worktree (exit 2 from a linked worktree or a bare repo). Classification and fetch happen without the registry lock; each item is re-verified under the lock before deletion.
- Orphan directories (below) are only reported, never deleted by `reap`.

Typical flow: `reap` (read the plan), then `reap --yes`.

## Safety Rules

- NEVER delete a worktree directory with `rm -rf` — use `remove` or `reap`, then `prune` for stragglers. Never delete `.claude/worktrees` wholesale.
- NEVER merge or push from inside an agent worktree — agents commit on their `agent/*` branch only; the gitOps merge protocol integrates (see the gitOps agent's Multi-Agent Merge Protocol).
- NEVER check out the same branch in two worktrees (git prevents it — do not work around it).
- Exit code 2 from the manager means a validation refusal — report it, do not retry with `--force` unless the user explicitly approves.

## Cleanup After a Failed Run

```bash
python3 .claude/operations/scripts/worktree-manager.py reap          # dry run: read what is kept and why
python3 .claude/operations/scripts/worktree-manager.py reap --yes    # remove what is proven merged and clean
python3 .claude/operations/scripts/worktree-manager.py prune
git worktree list                                                    # verify
```

Do not delete an unmerged `agent/<slug>` branch by hand. If the work is abandoned
on purpose, say so explicitly and let the user decide; `reap` keeps it as
`unmerged`/`unproven` until it is merged (squash and rebase merges are
recognised).

## Stray Claude Code agent directories (`.claude/worktrees/agent-*`)

Claude Code's own `isolation: "worktree"` agents leave `.claude/worktrees/agent-<id>`
directories behind. Triage:

1. `git worktree list` — if the directory is listed, it is a real worktree: `reap` (dry run), then `reap --yes`.
2. Not listed and no `.git` file inside: it is an orphan full copy; git metadata is already gone, so `git worktree prune/remove` cannot reclaim it. `reap` reports orphans with size and age. Before deleting one by hand, run `diff -rq <orphan> .` (ignore ignored files) to confirm nothing unique is in it.
3. Directories that are not `agent-*` (for example `skill-profiles`) are not agent-owned: check by hand, never bulk delete.
4. Never `rm -rf` a live worktree and never remove `.claude/worktrees` as a whole.

Recovering a removed branch: the tip stays reachable from `git reflog` and, when a
bundle was written under `.claude/state/worktree-archive/` (or a `refs/archive/<slug>/*` ref was pinned),
`git fetch <bundle> 'refs/heads/*:refs/recovered/*'`, then
`worktree-manager.py create <slug> --base refs/recovered/agent/<slug>`.

## Usage Examples

- `/worktree create feature-auth` — new isolated workspace on branch agent/feature-auth
- `/worktree create ocr-fix --base main` — branch from main instead of HEAD
- `/worktree list` — registered worktrees + live status
- `/worktree remove feature-auth` — safe removal (branch deleted only when proven merged)
- `/worktree reap` — dry-run plan of merged, clean worktrees and branches to reclaim; `reap --yes` executes
- `/worktree prune` — reconcile registry after crashes or manual deletions
- `/worktree report` — sprawl report: worktrees over cap, worktrees outside the
  repo root, merged-but-undeleted branches, unpushed commits (read-only)
- `/worktree clean` — reclaim what `report` listed; dry-run unless `--yes`,
  refuses dirty trees and unmerged branches, bounded by `--max-deletions`

`report` and `clean` delegate to `.claude/operations/scripts/repo-hygiene.py`.
