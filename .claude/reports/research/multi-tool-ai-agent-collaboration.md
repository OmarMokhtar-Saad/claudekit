# Multi-Tool AI Agent Collaboration Patterns (2025-2026)

**Date**: 2026-08-09  
**Question**: Proven patterns for Claude Code + Cursor + Codex CLI + Gemini CLI collaboration on same project without conflicts

## Findings

### 1. Shared Instruction Files: AGENTS.md Standard
- **AGENTS.md** is the cross-tool standard (originated OpenAI, stewarded Linux Foundation's Agentic AI Foundation as of Dec 2025)
- Supported by 30+ agents: Claude Code, Cursor, Codex, GitHub Copilot, Gemini CLI, Google Jules, Factory, Aider, Zed, Windsurf, Devin
- No required fields; common sections: project overview, build/test commands, code style
- Claude Code added AGENTS.md support spring 2026, but prefers CLAUDE.md for richer memory
- **Pattern**: single `AGENTS.md` + tool-specific files (.cursor/rules, CLAUDE.md) for one source of truth

### 2. Coordination Mechanisms
**MCP Servers as Coordination Buses**:
- **claude-peers-mcp**: Local message bus for Claude Code instances to message each other ad-hoc (no central orchestrator)
- **Agent Bus MCP**: Topic-based durable inbox; agents join named topics, exchange messages, resume from cursors; supports Claude Code, Cursor, other MCP clients
- Both enable async handoffs, reviews, sidecar work

**Claude Code Agent Teams** (Feb 2026):
- Native parallel coordination for Claude Code subagents
- Use cases: PR review, debugging (competing hypotheses), architecture research, cross-layer features, independent implementation + verification

### 3. Real Multi-Tool Workflows Reported
- **Parallel mode**: Claude Code + Cursor extensions run together ($40/month test week available)
- **Specialization**: Claude Code for architecture/coordination; Cursor for feature implementation; one reviews the other's PRs
- **Agent Teams + external tools**: Claude agents coordinate internally, external agents (Cursor CLI, Codex) integrated via MCP

### 4. Multi-Tool Orchestrators (2025-2026)
- **Agent Room** (MCP-native): Real-time collaboration, persistent rooms, structured artifacts ([DECISION] [TODO] [STATUS] [RESULT] markers)
  - Free, self-hostable, joins with 9-char code
  - Supports Claude Code, Cursor, Codex, Gemini, Antigravity
- **Agents Council**: Gathers opinions from multiple CLIs (Codex, Gemini); configurable Chairman synthesizes
- **Claude Codex Bridge**: TUI for cross-provider coordination (Codex, Claude, Gemini, others)
- **AgentsRoom**: Visual cockpit for parallel multi-project work (Claude Code, Codex CLI, Gemini CLI, Aider)

### 5. Cursor CLI Headless Mode for Scripting
- Released August 2025; fully headless via `-p` flag (prompt in, result out)
- Installation: `npm install -g @cursor/cli cursor`
- Usage: `cursor --headless "prompt" --branch fix/auth`
- Use cases: CI jobs, git hooks, shell scripts, cron jobs, bulk edits
- Shares MCP servers, rules, authentication with desktop app
- Security: Can read/modify/delete files, execute approved commands

## Key Pattern: File Ownership + MCP
1. **AGENTS.md** (shared) → project overview, build, style
2. **File ownership map** → track which agent is responsible per module/task
3. **MCP servers** (Agent Bus or claude-peers-mcp) → durable message queue for handoffs
4. **Headless CLI agents** (cursor-agent, codex CLI) in CI → validate reviewed changes

## Sources
- [AGENTS.md vs CLAUDE.md: The AI Developer's Guide to Context Standards](https://hivetrail.com/blog/agents-md-vs-claude-md-cross-tool-standard)
- [Claude Code multiple agent systems: Complete 2026 guide](https://www.eesel.ai/blog/claude-code-multiple-agent-systems-complete-2026-guide)
- [Cursor Agent CLI · Cursor](https://cursor.com/blog/cli)
- [Using Headless CLI | Cursor Docs](https://cursor.com/docs/cli/headless)
- [How to Coordinate Multiple Claude Code Agents Without Losing Your Mind - DEV Community](https://dev.to/alanwest/how-to-coordinate-multiple-claude-code-agents-without-losing-your-mind-1i9f)
- [Agent Room — Multi-agent collaboration for Claude Code, Codex, Cursor & Gemini](https://www.agent-room.com/)
- [Agent Room GitHub](https://github.com/ebin198351-akl/agent-room)
- [Agent Bus MCP Docs](https://www.agentbusmcp.com/)
- [12 Claude Code MCP Servers Every AI Team Needs in 2026](https://coworker.ai/blog/claude-code-mcp-servers)
