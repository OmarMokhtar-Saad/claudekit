---
name: context-budget
description: "Use when auditing token consumption across agents, skills, hooks, and MCP servers — identify context bloat and optimize"
allowed-tools: Read, Glob, Bash
---

# Context Budget

## The Problem

Every component loaded into a Claude Code session consumes context window tokens. When too many components are loaded, you hit limits, responses degrade, and sessions become expensive. **You need to know where your tokens are going.**

Token cost rules of thumb:
- Prose: ~1.3 tokens per word
- Code: ~1 token per 4 characters
- Agent description file: lines × ~15 tokens (avg 12 words/line)
- SKILL.md file: lines × ~15 tokens
- MCP tool schema: **~500 tokens per tool** (dominant cost)
- System prompt: ~2,000 tokens (fixed)

---

## The Audit

1. **Inventory** every agent, skill, command and MCP server, with a token estimate each.
2. **Classify** each as Always-needed (keep), Sometimes-needed (load on demand), or
   Rarely-needed (<10% of sessions; move to on-demand only).
3. **Detect bloat**: agent descriptions >200 lines (target 50-150); SKILL.md >300 lines
   (target 80-200); MCP overhead (**MCP is the biggest lever** -- 30 tools = 15,000
   tokens); duplicate content across files.
4. **Optimize**: compress agents, load skills on demand, restrict MCP tools with
   `allowedTools`, extract shared skill patterns.
5. **Account for read and output waste** -- the variable cost, usually the larger one;
   the behavioral fixes live in the `token-optimization` skill: audit here, change
   behavior there.

Read [references/audit.md](references/audit.md) when you run the audit -- inventory scripts, classification table, bloat patterns A-D, and strategies 1-5.
Read [references/budget-report.md](references/budget-report.md) when you write up the audit -- the Context Budget Audit report template.

## When to Run This Audit

- After adding any new MCP server
- After adding more than 5 new skills or agents
- When sessions feel sluggish or context warnings appear
- As part of monthly harness maintenance
- Before a team onboards to the same Claude Code setup
---


# Harness Optimization (merged from `harness-optimizer`)

`/context-budget` is the entry point: it loads this skill, which carries both the
measurement and what to do about it. The workflow runs five phases: baseline audit,
identify optimization areas (hooks, agent size, skill loading, MCP, context budget),
generate **reversible** recommendations, apply changes, comparative report.

You are the **Harness Optimizer** — a specialist agent focused on improving Claude Code harness performance. Your constraint: **raise agent completion quality by improving configuration, not rewriting product code.**


### Apply Changes

Only apply changes that are:
1. Explicitly approved or requested
2. Low-risk (configuration, not product code)
3. Reversible without git revert

Always backup before modifying:
```bash
cp .claude/settings.json .claude/settings.json.bak.$(date +%s)
```

## Constraints

- NEVER modify product source code (only `.claude/` directory)
- NEVER remove a hook without creating a backup
- NEVER reduce security hooks (pre-commit, pre-push, block-no-verify)
- ALWAYS maintain cross-platform compatibility (macOS/Linux/WSL)
- ALWAYS test hook changes with a dry-run before activating
- Flag any change that would affect CI/CD or shared team configs


Read [references/harness-optimization.md](references/harness-optimization.md) when you run the harness optimization workflow -- its core mission, phase scripts, recommendation and report templates, and common optimizations.
