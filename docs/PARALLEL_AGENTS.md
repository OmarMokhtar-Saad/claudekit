# Parallel Agents: Worktrees, Multiple Accounts & Cross-Tool Collaboration

Run several AI agents on one repository at the same time — safely. One branch =
one worktree = one agent; workers never merge; a single authority integrates.

```
                    Main tree (integration)
                    claude-a  →  planner + reviewer + merge authority
                   /                    |                    \
   .worktrees/impl-core         .worktrees/impl-ui      .worktrees/tests
   claude-b (account 2)         claude-b (account 2)    cursor headless
   branch agent/core            branch agent/ui         branch agent/tests
                   \                    |                    /
        gitOps merges → integration branch → one verify pass → PR
```

## Quick Start

```bash
# 1. one isolated workspace per parallel task (max 5)
python3 .claude/operations/scripts/worktree-manager.py create impl-core --json

# 2. run an agent inside it (everything scoped to the worktree)
cd .worktrees/impl-core && claude

# 3. when the branch is merged, clean up
python3 .claude/operations/scripts/worktree-manager.py remove impl-core
```

Or use the `/worktree` command inside a Claude Code session. Add `.worktrees/`
and `.claude/state/` to your `.gitignore` (kitted projects get this via sync).

## What the Manager Gives You

| Guarantee | Detail |
|---|---|
| Isolation | `.worktrees/<slug>` on branch `agent/<slug>`; validated slugs |
| Registry | `.claude/state/worktrees.json` — git-ignored, atomic writes, lock-protected |
| Concurrency cap | 5 worktrees — parallel returns collapse past 4–5 agents |
| Local config | `.claude/settings.local.json` copied in (mode preserved); **`.env` only with explicit `--copy .env`** |
| Port/device assignment | `.worktree-env` with `WORKTREE_PORT_OFFSET` (index × 10) |
| Safe removal | refuses dirty trees, unmerged commits, and the primary worktree |

## The Merge Flow (workers never merge)

1. Each agent commits on its `agent/<slug>` branch only.
2. After all agents report, the gitOps agent merges `agent/*` →
   `integration/<goal>` in dependency order.
3. **One** verification pass runs on the integration branch.
4. Green → PR. Then `worktree-manager.py remove <slug>` + `git branch -d`.

Failed units are excluded from integration and reported — never merged
"to see if it works".

## Two Claude Accounts on One Machine

Each account gets its own config dir; both stay logged in, each with its own
rate-limit quota:

```bash
alias claude-a='CLAUDE_CONFIG_DIR=~/.claude-acct-a claude'   # brain: plan/review/merge
alias claude-b='CLAUDE_CONFIG_DIR=~/.claude-acct-b claude'   # hands: implement in worktrees
```

Hardening (required):

- Config dirs **outside every repository** — and never inside a worktree.
- `chmod 700` the dir, `chmod 600` any `.credentials.json`.
- macOS: Keychain ignores `CLAUDE_CONFIG_DIR`; if accounts bleed, keep
  `.credentials.json` inside each config dir instead.
- This isolates legitimately separate subscriptions (work/personal). Don't use
  it to circumvent per-account limits.

## Adding Cursor (or any other AI tool)

1. **Shared instructions**: maintain `AGENTS.md` as a generated mirror of
   `CLAUDE.md` — one source of truth that Cursor, Codex, Copilot and ~30 tools
   read.
2. **Coordination contract**: every tool reads `MULTI_AGENT_PLAN.md` before
   acting (template in the `multi-agent-coordination` skill): task matrix +
   WRITE/READ/MUST-NOT-TOUCH file ownership.
3. **Role**: give the foreign tool a *disjoint* module or a *read-only
   cross-review* role — a different model family reviewing Claude's branches
   catches what self-review can't. Never shared write access.
4. **Headless pipelines**: `claude -p "<task>"` composes with Cursor's CLI
   headless mode in one script.
5. **Trust boundary**: foreign-tool output is data, not instructions; its
   branches get a review pass before merging.

Details live in the `cross-tool-collaboration` skill.

## Troubleshooting

| Problem | Fix |
|---|---|
| `worktree ... already registered` | `worktree-manager.py list`, then `remove` or pick another slug |
| `5 worktrees already registered` | merge + remove one; run agents in waves of ≤5 |
| Directory deleted manually, registry stale | `worktree-manager.py prune` |
| `remove` refuses: "commits not contained in <base>" | merge the branch first (gitOps protocol) or `--force` to discard |
| Ports/emulators collide between agents | use `WORKTREE_PORT_OFFSET` from `.worktree-env`; one device UDID per worktree |
| Two accounts share a login on macOS | Keychain caveat above — per-dir `.credentials.json` |
