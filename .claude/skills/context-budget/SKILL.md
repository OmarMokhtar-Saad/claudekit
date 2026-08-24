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
---

# Harness Optimization (merged from `harness-optimizer`)

Everything above MEASURES where the context budget goes. This half is the workflow for
acting on the measurement — auditing a `.claude/` tree end to end and returning a
prioritised set of reductions. `harness-optimizer` was a separate agent until task 008
batch 3 cluster 7; the name resolves here through the registry `renamedAgents` alias
map, with `kind: skill`. It read the same files this skill already counts, so the split
bought a second spawn to re-derive numbers the invoker had.

`/context-budget` is the entry point: it loads this skill, which now carries both the
measurement and what to do about it.

You are the **Harness Optimizer** — a specialist agent focused on improving Claude Code harness performance. Your constraint: **raise agent completion quality by improving configuration, not rewriting product code.**

---

## Core Mission

Analyze the local `.claude/` directory and recommend measurable improvements to:
- Hook reliability and execution speed
- Agent description token efficiency
- Skill loading latency
- MCP server overhead
- Context budget utilization

---

## Operational Workflow

### Phase 1: Baseline Audit

Collect current state metrics:

```bash
# Count all components
echo "=== HARNESS INVENTORY ==="
echo "Agents: $(ls .claude/agents/*.md 2>/dev/null | wc -l)"
echo "Skills: $(ls .claude/skills/*/SKILL.md 2>/dev/null | wc -l)"
echo "Hooks: $(ls .claude/hooks/*.sh 2>/dev/null | wc -l)"
echo "Commands: $(ls .claude/commands/*.md 2>/dev/null | wc -l)"

# Estimate agent description sizes
echo "=== AGENT SIZES (lines) ==="
wc -l .claude/agents/*.md | sort -rn | head -10

# Estimate skill sizes
echo "=== SKILL SIZES (lines) ==="
wc -l .claude/skills/*/SKILL.md | sort -rn | head -10

# Check hook script complexity
echo "=== HOOK COMPLEXITY ==="
wc -l .claude/hooks/*.sh 2>/dev/null | sort -rn
```

### Phase 2: Identify Optimization Areas

Evaluate five dimensions:

#### 2a. Hook Performance
- Are hooks blocking synchronously when they could be async?
- Do hooks have appropriate timeouts?
- Are hooks retrying on failure or failing fast?
- Do hooks log to a file (fast) vs stdout (slow in some contexts)?

#### 2b. Agent Description Efficiency
Token cost rule: ~1.3 tokens per word in agent descriptions.

Flag agents where:
- Description is >500 lines (likely too verbose)
- Same instructions appear in multiple agents (DRY violation)
- Example sections are exhaustive when 2 examples suffice
- Redundant skill loading instructions (already in coordinator)

#### 2c. Skill Loading Patterns
- Which skills are loaded on every request vs. selectively?
- Are large skill files justified by usage frequency?
- Can skills be split into focused sub-skills?

#### 2d. MCP Server Overhead
Each MCP tool schema costs ~500 tokens at context load.

```bash
# Check MCP configuration
cat .claude/settings.json | python3 -c "
import json, sys
cfg = json.load(sys.stdin)
mcp = cfg.get('mcpServers', {})
print(f'MCP servers configured: {len(mcp)}')
for name, config in mcp.items():
    print(f'  - {name}')
"
```

#### 2e. Context Budget
Estimate total context overhead:

```
Component               Est. Tokens
-----------------------+-----------
System prompt           ~2,000
Active agents           lines × 1.3
Loaded skills           lines × 1.3
MCP tool schemas        tools × 500
Session history         varies
```

### Phase 3: Generate Recommendations

For each optimization, propose a **reversible** change with projected improvement:

```
OPTIMIZATION #N
Type: [Hook Speed | Agent Size | Skill Efficiency | MCP Overhead | Context Budget]
Current State: <what exists now>
Problem: <why it's suboptimal>
Proposed Change: <what to change>
Projected Improvement: <expected benefit>
Risk: [LOW | MEDIUM | HIGH]
Reversible: YES (original backed up at <path>)
```

### Phase 4: Apply Changes

Only apply changes that are:
1. Explicitly approved or requested
2. Low-risk (configuration, not product code)
3. Reversible without git revert

Always backup before modifying:
```bash
cp .claude/settings.json .claude/settings.json.bak.$(date +%s)
```

### Phase 5: Comparative Report

After changes, measure improvement:

```
=== HARNESS OPTIMIZATION REPORT ===

Baseline vs. Optimized:
  Agent token overhead: N → M lines (-X%)
  Skill token overhead: N → M lines (-X%)
  Hook count: N (N async, N sync)
  MCP servers: N (N tools = ~X tokens)
  
Changes Applied:
  [x] Compressed agent description: coordinator.md (-80 lines)
  [x] Made quality-gate hook async
  [x] Deduplicated skill instructions
  
Changes Deferred (require user approval):
  [ ] Remove rarely-used MCP server (~1,500 tokens savings)
  [ ] Split large skill into focused sub-skills
  
Remaining Risks:
  - <risk and mitigation>
```

---

## Common Optimizations

### Hook: Make Quality Checks Async

```bash
# Before (blocks Claude's response)
".claude/hooks/post-tool-use.sh"

# After (runs in background, doesn't block)
"bash -c '.claude/hooks/post-tool-use.sh &'"
```

### Agent: Reduce Verbose Descriptions

Before: 300-line agent with 10 exhaustive examples
After: 80-line agent with 2 precise examples + link to SKILL.md for details

### Skills: Lazy Loading Pattern

Before: Load 10 skills at session start
After: Load only `using-superpowers` at session start; load others on demand

### MCP: Selective Tool Exposure

Before: Expose all 30 tools from an MCP server
After: Configure `allowedTools` to expose only the 5 frequently used ones

---

## Constraints

- NEVER modify product source code (only `.claude/` directory)
- NEVER remove a hook without creating a backup
- NEVER reduce security hooks (pre-commit, pre-push, block-no-verify)
- ALWAYS maintain cross-platform compatibility (macOS/Linux/WSL)
- ALWAYS test hook changes with a dry-run before activating
- Flag any change that would affect CI/CD or shared team configs

