# Context Budget -- the audit and optimization strategies

Moved verbatim from SKILL.md.

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

### Strategy 5: Account for Read and Output Waste

Component overhead is the *floor*. In-session reads and pasted tool output are the
*variable* cost, and usually the larger one. Audit both -- for the session under
review, count:

- unbounded reads that an `offset`/`limit` or `head_limit` read would have covered;
- large tool results pasted into the transcript instead of left on disk with a path;
- repeated broad searches that one deterministic probe would have answered.

Report these as line items alongside component costs. The behavioral rules that fix
them -- bounded reads, spill, script-first -- live in the `token-optimization` skill:
audit here, change behavior there.

---

