---
name: search-first
description: "Use before writing custom code — systematically search npm/PyPI, MCP servers, GitHub, and existing skills for existing solutions"
disable-model-invocation: true
allowed-tools: Read, Bash, WebFetch, WebSearch
---

# Search First

## Core Principle

**Before writing a single line of custom code, search for existing solutions.** The best code is code you don't have to write, maintain, or debug.

> "The most expensive code is code that already exists but you reimplemented anyway."

---

## When to Apply This Skill

Trigger search-first whenever:
- Starting a new feature that involves external integrations
- Implementing data processing, parsing, or validation logic
- Building CLI tools or developer utilities
- Setting up authentication, caching, queuing, or observability
- Creating Claude Code integrations (MCP, skills, agents)

Skip search-first for:
- Business logic unique to your domain
- Glue code that ties known components together
- Features where you've already evaluated and decided to build custom

---

## The Five-Stage Search Workflow

### Stage 1: Need Analysis

Before searching, clarify:

```
What exactly do I need?
- Core functionality: <one sentence>
- Input/output format: <describe>
- Performance requirements: <latency, throughput>
- Constraints: <language, license, size, dependencies>
- Non-negotiables: <what must be true>
```

### Stage 2: Parallel Search

Search all channels simultaneously:

#### Package Registries
```bash
# npm (Node.js/TypeScript)
npm search <keyword> --json | python3 -c "import json,sys; pkgs=json.load(sys.stdin); [print(f'{p[\"name\"]:40} {p[\"description\"][:60]}') for p in pkgs[:10]]"

# PyPI (Python)
pip index versions <package-name> 2>/dev/null | head -5
# or search: https://pypi.org/search/?q=<keyword>

# Go modules
# search: https://pkg.go.dev/search?q=<keyword>
```

#### MCP Servers
```bash
# Check if an MCP server exists for this capability
# Search: https://github.com/modelcontextprotocol/servers
# Check Claude Code's built-in MCP capabilities

ls ~/.claude/skills/ | grep -i <keyword>
cat ~/.claude/settings.json | python3 -c "import json,sys; cfg=json.load(sys.stdin); print('\n'.join(cfg.get('mcpServers',{}).keys()))"
```

#### Existing Skills
```bash
# Check claudekit skills
ls .claude/skills/ | grep -i <keyword>
grep -rl "<keyword>" .claude/skills/ --include="SKILL.md" | head -5
```

#### GitHub Search
```bash
# Use gh CLI for GitHub search
gh search repos "<keyword> Claude Code" --limit 5 --json name,description,stargazerCount
gh search repos "<keyword> MCP server" --limit 5 --json name,description,stargazerCount
```

### Stage 3: Evaluate Candidates

Score each candidate on 6 dimensions:

| Dimension | Questions | Weight |
|-----------|----------|--------|
| **Functionality** | Does it do what I need? Gaps? | 30% |
| **Maintenance** | Last commit <6 months? Active issues? | 20% |
| **Community** | Stars, downloads, forks? | 15% |
| **Documentation** | Is it usable without reading source? | 15% |
| **License** | MIT/Apache/BSD compatible? | 10% |
| **Dependencies** | Minimal transitive deps? | 10% |

**Score 0-10 per dimension, apply weights. >= 7.0 total = adopt.**

### Stage 4: Decision

| Score | Decision | Action |
|-------|---------|--------|
| >= 8.0, MIT/Apache | **Adopt** | Install and use directly |
| 6.0-7.9, mostly fits | **Extend** | Wrap with thin adapter |
| Multiple 5.0-6.0 | **Compose** | Combine 2-3 weak solutions |
| < 5.0 across all | **Build** | Custom implementation justified |

### Stage 5: Implement

Based on decision:

**Adopt:**
```bash
npm install <package>
# or
pip install <package>
```

**Extend:**
```python
# Thin wrapper that adapts the interface
class MyAdapter:
    def __init__(self):
        self._lib = ThirdPartyLib()
    
    def my_interface(self, ...):
        return self._lib.their_interface(...)
```

**Build:**
```
Document WHY you're building custom:
- Searched: [list of packages evaluated]
- Why each was rejected: [reason per package]
- Custom approach: [brief description]
```

---

## Anti-Patterns

| Anti-Pattern | Why It's Wrong |
|-------------|---------------|
| Starting to code before searching | You might spend days building what exists |
| Searching only npm/PyPI | MCP servers and skills can save even more work |
| Rejecting imperfect packages | 80% fit + thin adapter beats 100% custom |
| Taking unstable packages (0.x, 1+ year stale) | Maintenance cost shifts to you |
| GPL/AGPL in commercial product | License compliance is expensive |
| Skipping dep analysis | Heavy transitive deps can bloat your bundle |

---

## Search Quick Reference

```bash
# Find npm packages with >1k weekly downloads
npm search <term> --json | python3 -c "
import json, sys
pkgs = json.load(sys.stdin)
for p in sorted(pkgs, key=lambda x: x.get('downloads',{}).get('weekly',0), reverse=True)[:5]:
    weekly = p.get('downloads',{}).get('weekly',0)
    print(f'{weekly:>8} downloads/wk  {p[\"name\"]:40} {p[\"description\"][:50]}')
"

# Check package health
npm view <package> --json | python3 -c "
import json, sys
p = json.load(sys.stdin)
print('Version:', p.get('version'))
print('License:', p.get('license'))
print('Last publish:', p.get('time',{}).get('modified','?')[:10])
print('Weekly downloads: check npmtrends.com')
"

# Find Claude Code / MCP repos on GitHub
gh search repos "topic:mcp-server <keyword>" --limit 5 --json name,description,stargazerCount,updatedAt
```

---

## Decision Record Template

When you decide to build custom, document it:

```markdown
## Search Record: <feature>

**Date:** YYYY-MM-DD
**Need:** <what functionality was needed>

### Packages Evaluated
| Package | Score | Reason Rejected |
|---------|-------|----------------|
| pkg-a   | 6.2   | No TypeScript types, last updated 2022 |
| pkg-b   | 4.1   | GPL license, incompatible |
| pkg-c   | 7.8   | Adopted — wrapping with thin adapter |

### Decision
[Adopt pkg-c with adapter | Build custom because ...]

### Custom Approach
[Brief description if building custom]
```
