# Git Worktrees + Parallel AI Agents (2025–2026)

**Question**: Best practices for running multiple AI coding agents in parallel on one repo using git worktrees?

**Date Cached**: 2026-08-09

---

## 1. Claude Code Native Worktree Support

**Built-in Feature**: Claude Code has native EnterWorktree support (Desktop since early 2025, CLI since v2.1.206, July 2026).

**Flags & Invocation**:
- `claude --worktree <n>` — spawns isolated Claude Code session
- `/EnterWorktree` tool — creates + enters worktree with confirmation prompt (v2.1.206+)
- Desktop app has had worktree support "for a while"; CLI parity achieved July 2026
- When `/team-build` dispatches multiple agents, each auto-receives worktree isolation

**Official Guidance**: Each agent gets own worktree + branch, works independently without interfering with others. Anthropic ships updates "every few weeks" (Feb–July 2026).

---

## 2. Directory Layout & Naming

**Standard Structure**:
- Default: `.claude/worktrees/` inside repo (v2.1.206+ asks confirmation for paths outside)
- Alternative: `../worktrees/<project>/<feature-name>` as sibling directory

**Exact Commands**:
```bash
git worktree add .claude/worktrees/feature-auth -b feature/auth-implementation
git worktree list
git worktree remove <path>
```

**Cleanup**: Remove merged branches + stale worktrees (`git worktree prune`).

---

## 3. Gotchas & Isolation Rules

- **Shared .git**: All worktrees point to one `.git/` history; no duplication
- **Per-worktree dependencies**: Each worktree needs own `node_modules/`, `venv/`, build artifacts
- **Shared files at risk**: `.env`, `.cursorrules`, MCP configs — copy to each worktree before agent launch
- **Port conflicts**: Only one dev server per port; use per-worktree ports or reverse proxy
- **Hooks & settings**: `.git/hooks/` shared; `.claude/settings.json` shared — document in `MULTI_AGENT_PLAN.md`
- **Configuration Propagation**: Copy critical config files to new worktree (`.cursorrules`, `.env`)

---

## 4. Automation Tools (2026)

| Tool | Pattern | Status |
|------|---------|--------|
| **Claude Squad** | tmux + worktrees, background tasks, branch ops | Active, integrated |
| **Vibe Kanban** | Web dashboard, multiple agents in parallel, Rust/TS | OSS (Bloop shutdown 2026) |
| **Conductor** | Multi-Claude sessions, isolated workspaces, progress UI | Active |
| **Crystal** | Desktop app, parallel sessions, diffs/tests in one window | Open source |
| **Composio, Emdash, Baton** | Agent orchestrators with worktree support | Various maturity |

All tested orchestrators solve parallel execution via git worktrees.

---

## 5. Merging & Coordination

**Pattern**:
1. Write `MULTI_AGENT_PLAN.md` — task assignments, file ownership matrix, progress tracking
2. Limit each agent's worktree-specific `CLAUDE.md` to status/commit/diff (no merge)
3. Orchestrator merges results into main branch
4. Central validation pass in single worktree post-merge

**Resource Scale**: Teams run 4–5 agents concurrently; documented systems reaching 371 worktrees. Use shared package cache (pnpm) to manage disk/RAM past 2–3 agents.

---

## Sources

- [Using Worktrees For Parallel Claude Code Sessions — HeyClaude](https://heyclau.de/entry/guides/using-worktrees-for-parallel-claude-code-sessions)
- [Claude Code Git Worktrees: Run 5 AI Agents in Parallel (2026 Guide) | DevToolLab](https://devtoollab.com/blog/claude-code-git-worktrees-parallel-agents-guide-2026)
- [Git Worktrees for Parallel AI Agent Execution | Augment Code](https://www.augmentcode.com/guides/git-worktrees-parallel-ai-agent-execution)
- [Parallel Agentic Development With Git Worktrees | MindStudio](https://www.mindstudio.ai/blog/parallel-agentic-development-git-worktrees)
- [Best Practices: Hybrid AI Agent Multi-Git Worktree Development | enuno/claude-command-and-control](https://github.com/enuno/claude-command-and-control/blob/main/docs/best-practices/12-hybrid-ai-agent-multi-git-worktree-development.md)
- [Open-Source Agent Orchestrators for AI Coding (2026) | Augment Code](https://www.augmentcode.com/tools/open-source-agent-orchestrators)
- [Best Tools for Managing Parallel AI Coding Agents in 2026 | Nimbalyst](https://nimbalyst.com/blog/best-agent-management-tools-2026/)
