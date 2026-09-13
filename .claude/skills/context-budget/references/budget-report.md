# Context Budget -- budget report format

Moved verbatim from SKILL.md.

## Budget Report Format

```
## Context Budget Audit

### Total Estimated Overhead
System prompt:          ~2,000 tokens
Agents (N loaded):     ~X,XXX tokens
Skills (N loaded):     ~X,XXX tokens  
MCP servers (N tools): ~X,XXX tokens
─────────────────────────────────────
Estimated total:       ~XX,XXX tokens
Available for content: ~XXX,XXX tokens (depends on model)
Budget used:           XX%

### Top Token Consumers
1. MCP: server-name (N tools) — ~X,XXX tokens — RECOMMENDED: restrict to N used tools
2. Agent: large-agent.md (N lines) — ~X,XXX tokens — RECOMMENDED: compress to 100 lines
3. Skill: large-skill (N lines) — ~X,XXX tokens — RECOMMENDED: split into focused sub-skills

### Savings Opportunities
QUICK WIN: Restrict MCP tools from N → N  saves ~X,XXX tokens
MEDIUM:    Compress 3 verbose agents        saves ~X,XXX tokens
LONG-TERM: On-demand skill loading          saves ~X,XXX tokens per session

### Recommendation
[Current state is OPTIMAL / MODERATE BLOAT / HIGH BLOAT]
[Priority actions]
```

