---
description: "Audit context window token consumption across agents, skills, hooks, and MCP servers — find bloat, optimize usage"
argument-hint: "[--audit|--optimize|--mcp|--agents|--skills]"
model: haiku
---

# Context Budget Command

Audit and optimize how the Claude Code harness uses the context window. Every component loaded consumes tokens — this command shows you where they're going and how to reduce overhead.

## Mandatory Skills

- **using-superpowers** - Core capabilities
- **context-budget** - Token estimation and optimization methodology

## Task

Audit context budget: $ARGUMENTS

---

## Execution Steps

### Step 1: Full Inventory

```bash
echo "=== CLAUDEKIT CONTEXT AUDIT ==="
echo ""
echo "--- Agents ---"
for f in .claude/agents/*.md; do
    lines=$(wc -l < "$f" 2>/dev/null || echo 0)
    tokens=$((lines * 15))
    printf "  %5d tokens  %s\n" "$tokens" "$(basename $f)"
done | sort -rn

echo ""
echo "--- Skills ---"
for f in .claude/skills/*/SKILL.md; do
    lines=$(wc -l < "$f" 2>/dev/null || echo 0)
    tokens=$((lines * 15))
    skill=$(basename "$(dirname "$f")")
    printf "  %5d tokens  %s\n" "$tokens" "$skill"
done | sort -rn | head -20

echo ""
echo "--- Commands ---"
total_cmd_lines=$(cat .claude/commands/*.md 2>/dev/null | wc -l)
printf "  %5d tokens  (all commands combined)\n" "$((total_cmd_lines * 15))"

echo ""
echo "--- MCP Servers ---"
python3 -c "
import json, os
try:
    cfg = json.load(open('.claude/settings.json'))
    mcp = cfg.get('mcpServers', {})
    if mcp:
        for name in mcp:
            print(f'  ~500+ tokens per tool  {name}')
    else:
        print('  No MCP servers configured')
except:
    print('  Cannot read settings.json')
" 2>/dev/null
```

### Step 2: Total Estimate

```
Component              Estimated Tokens
----------------------+----------------
System prompt          ~2,000
Agents (active)        ~X,XXX
Skills (loaded)        ~X,XXX
Commands               ~X,XXX
MCP tool schemas       ~X,XXX
─────────────────────────────────────
Total overhead         ~XX,XXX
Model context limit    ~200,000 (Sonnet)
Budget used            ~XX%
```

### Step 3: Identify Savings

Flag items for optimization:
- Any agent > 200 lines: candidate for compression
- Any skill > 300 lines: candidate for splitting
- MCP servers with many tools: restrict with `allowedTools`
- Duplicate content across agents: extract to shared skill

### Step 4: Apply Optimizations (if --optimize flag)

For each flagged item, propose and (with confirmation) apply:
- Compress verbose agent descriptions
- Split large skills into focused sub-skills
- Configure MCP `allowedTools`
- Extract shared instructions to a common skill

---

## Output Format

```
## Context Budget Report

### Overview
Total estimated overhead: ~XX,XXX tokens (XX% of Sonnet 200K context)

### Largest Consumers
1. MCP server 'X' — ~X,XXX tokens (N tools)
2. Agent 'coordinator' — ~X,XXX tokens (N lines)
3. Skill 'Y' — ~X,XXX tokens (N lines)

### Savings Opportunities
[QUICK] Restrict MCP tools: X → Y tools saves ~X,XXX tokens
[MEDIUM] Compress 2 verbose agents: saves ~X,XXX tokens  
[LONG] On-demand skill loading: saves ~X,XXX tokens/session

### Status
[OPTIMAL | MODERATE BLOAT (>20%) | HIGH BLOAT (>40%)]

### Recommendation
[Specific next actions]
```

---

## Usage Examples

- `/context-budget` — Full audit with recommendations
- `/context-budget --mcp` — Focus only on MCP server overhead
- `/context-budget --agents` — Analyze only agent descriptions
- `/context-budget --skills` — Analyze only skills
- `/context-budget --optimize` — Run audit and apply safe optimizations

## Notes

- Run after adding any new MCP server or 5+ new skills
- Token estimates are approximations (±20%)
- MCP tool schemas are the single biggest optimization lever
- Each MCP tool costs ~500 tokens regardless of its complexity
