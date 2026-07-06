---
name: deep-research
description: "Use when asked to research a topic in depth — multi-source research with parallel subagents, synthesis, and confidence-rated report"
disable-model-invocation: true
allowed-tools: Read, Bash, WebFetch, WebSearch
---

# Deep Research

## Purpose

Systematic multi-source research that produces a structured, cited report. Goes beyond a single web search to cross-reference sources, identify gaps, and explicitly rate confidence.

**Trigger when:** "research", "deep dive", "investigate", "what's the current state of", "competitive analysis", "due diligence", "compare X and Y"

**Do NOT trigger for:**
- Single factual questions with a known answer
- Code implementation questions (use search-first skill instead)
- Internal project questions (read the codebase, not the web)

---

## 6-Phase Research Workflow

### Phase 1: Understand the Goal

Ask 1-2 clarifying questions — or skip if the user says "just research it":

```
What I need to clarify:
1. What decision will this research inform?
2. How recent must the information be? (last 6 months / last 2 years / any)
```

If the question is clear, proceed without asking.

### Phase 2: Plan the Research

Break the topic into 3-5 sub-questions:

```
Topic: [main topic]

Sub-questions:
1. [specific aspect 1]
2. [specific aspect 2]
3. [specific aspect 3]
4. [what are the main competing options?]
5. [what are experts saying recently?]
```

### Phase 3: Parallel Multi-Source Search

For each sub-question, search with 2-3 keyword variations. Target 15-30 unique sources total.

**Source priority:**
1. Official documentation / specs
2. Peer-reviewed papers / technical reports
3. Engineering blogs from practitioners
4. News articles from reputable tech outlets
5. Community discussions (GitHub issues, forums)

```bash
# Example search approach (adapt to available tools)
# Use WebSearch or WebFetch on curated URLs

# For each sub-question, search:
# - Primary keyword
# - Alternative phrasing
# - "site:github.com" for implementation evidence
# - "after:2024" for recency
```

**Optional MCP tools (if configured):**
- `firecrawl_search` — deep web crawl with result ranking
- `web_search_exa` — semantic search with date filtering
- `crawling_exa` — full-page content extraction

### Phase 4: Deep-Read Key Sources

From the search results, select 3-5 highest-value sources and read them in full. Selection criteria:
- Direct author authority on the topic
- Published within the required date range
- Contains data/benchmarks (not just opinions)
- Contradicts or challenges the initial hypothesis (prioritize these)

### Phase 5: Synthesis

Organize findings into themes, then write the report.

**Quality rules during synthesis:**
- Every factual claim needs a source citation
- Cross-reference claims that appear in only 1 source (treat as unverified)
- Explicitly acknowledge when sources contradict each other
- Label estimates and projections as such
- State confidence level: HIGH (3+ sources agree) / MEDIUM (2 sources) / LOW (1 source / inference)
- Never fill gaps with hallucination — say "insufficient data found"

### Phase 6: Deliver

```
Short topics (<1,000 words): deliver inline in chat
Long reports: summary in chat + save full report to file

File location: .claude/research/<topic-slug>-<date>.md
```

---

## Parallel Research Pattern

For complex topics, spawn 3 subagents to cover different sub-questions simultaneously:

```
Subagent 1: [Sub-questions 1-2]
Subagent 2: [Sub-questions 3-4]
Subagent 3: [Sub-question 5 + recent developments]
```

Each subagent returns: findings, sources list, confidence ratings. Main agent synthesizes.

---

## Report Format

```markdown
# Research Report: [Topic]

**Date:** [ISO date]
**Research depth:** [N sources consulted, N fully read]
**Confidence:** [OVERALL LEVEL]

## Executive Summary
[3-5 sentences covering the key finding and recommendation]

## [Theme 1]
[Findings with inline citations]
Confidence: HIGH/MEDIUM/LOW

## [Theme 2]
[Findings with inline citations]
Confidence: HIGH/MEDIUM/LOW

## [Theme 3]
[Findings with inline citations]
Confidence: HIGH/MEDIUM/LOW

## Key Takeaways
1. [most important finding]
2. [second most important]
3. [third]

## Gaps & Limitations
[What we couldn't find, what would increase confidence]

## Sources
1. [Title](URL) — [relevance note]
2. ...

## Methodology
Searched [N] sources, fully read [N]. Date range: [range].
Keywords used: [list].
```

---

## Anti-Patterns

| Anti-Pattern | Why Wrong |
|-------------|----------|
| Single-source conclusions | One source can be wrong, biased, or outdated |
| Not acknowledging gaps | Silence about unknowns = implied certainty |
| Skipping contradictory sources | Best insights come from challenge |
| Research without a decision in mind | Unfocused research produces unfocused reports |
| Searching without reading fully | Headlines mislead — read the actual content |
