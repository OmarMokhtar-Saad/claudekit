---
name: context-budget
description: "Use when auditing token consumption across agents, skills, hooks, and MCP servers — identify context bloat and optimize"
disable-model-invocation: true
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

### Step 1: Inventory All Components

```bash
# Count agents
echo "Agents: $(ls .claude/agents/*.md 2>/dev/null | wc -l)"
echo "Skills: $(ls .claude/skills/*/SKILL.md 2>/dev/null | wc -l)"
echo "Commands: $(ls .claude/commands/*.md 2>/dev/null | wc -l)"

# Estimate token costs by component size
echo "=== AGENT TOKEN ESTIMATES ==="
for f in .claude/agents/*.md; do
    lines=$(wc -l < "$f")
    tokens=$((lines * 15))
    echo "  $tokens tokens — $(basename $f)"
done | sort -rn

echo "=== SKILL TOKEN ESTIMATES ==="
for f in .claude/skills/*/SKILL.md; do
    lines=$(wc -l < "$f")
    tokens=$((lines * 15))
    skill=$(basename $(dirname $f))
    echo "  $tokens tokens — $skill"
done | sort -rn | head -15
```

### Step 2: Classify Components

Bucket everything into three categories:

| Bucket | Definition | Action |
|--------|-----------|--------|
| **Always-needed** | Used in every session | Keep as-is |
| **Sometimes-needed** | Used in specific task types | Load on demand |
| **Rarely-needed** | Used <10% of sessions | Consider moving to on-demand only |

### Step 3: Detect Bloat Patterns

#### Pattern A: Verbose Agent Descriptions

Flag agents where:
- Description is >200 lines (likely padded)
- More than 3 examples (2 is enough for most agents)
- Duplicate instructions that appear in other agents
- Boilerplate that could be in a shared skill instead

Target: Each agent description should be 50-150 lines.

#### Pattern B: Oversized SKILL.md Files

Flag skills where:
- File is >300 lines
- Contains reference tables that don't change decision-making
- Has more than 5 examples (3 is usually enough)

Target: Each SKILL.md should be 80-200 lines.

#### Pattern C: MCP Overhead

**MCP is the biggest lever.** Each tool schema loaded = ~500 tokens.

```bash
# List MCP servers and estimate tool count
cat .claude/settings.json | python3 -c "
import json, sys
cfg = json.load(sys.stdin)
mcp = cfg.get('mcpServers', cfg.get('mcp', {}))
for name, config in mcp.items():
    print(f'  {name}: check tool count')
" 2>/dev/null
```

For each MCP server:
- How many tools does it expose?
- How many are actually used?
- Can `allowedTools` restrict to only needed tools?

30 MCP tools = 15,000 tokens = more than ALL your skills combined.

#### Pattern D: Duplicate Content

Check for instructions that appear in multiple places:

```bash
# Find potentially duplicated sections
grep -h "##" .claude/agents/*.md .claude/skills/*/SKILL.md | sort | uniq -d | head -20
```

---

## Optimization Strategies

### Strategy 1: Agent Description Compression

For verbose agent descriptions:
- Remove exhaustive examples beyond 2-3
- Move detailed procedures to a SKILL.md file, reference it from the agent
- Keep the agent focused on WHO it is and WHAT it decides
- Move HOW instructions to skills

### Strategy 2: On-Demand Skill Loading

Instead of loading all skills at session start:
- Load only `using-superpowers` at start
- Have agents load domain-specific skills when they engage
- This saves tokens for agents never invoked in a session

### Strategy 3: MCP Tool Restriction

```json
// settings.json — restrict MCP tools
{
  "mcpServers": {
    "my-server": {
      "command": "...",
      "allowedTools": ["tool1", "tool2", "tool3"]
    }
  }
}
```

### Strategy 4: Shared Skill Patterns

Extract repeated instructions into a shared skill:

```bash
# Instead of every agent repeating "Load these skills:"
# Create .claude/skills/standard-protocol/SKILL.md
# And have agents reference it once
```

---

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

---

## When to Run This Audit

- After adding any new MCP server
- After adding more than 5 new skills or agents
- When sessions feel sluggish or context warnings appear
- As part of monthly harness maintenance
- Before a team onboards to the same Claude Code setup
