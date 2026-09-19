# Agent-Skills Repository Deep Dive

**Retrieved:** 2026-09-16  
**Source:** https://github.com/moonlight-lupin/agent-skills

---

## Repository Overview

**What it is:** A curated library of 40+ reusable AI agent skills organized by domain (creative, research, productivity, devops, web-scraping, mlops). Built specifically for Hermes Agent but designed to port to other multi-agent frameworks (Claude Code, LangGraph).

**License:** MIT  
**Stars:** 70  
**Last commit:** 2026-09-12 (4 days old, active development)  
**Maturity:** Early-to-mid stage, pre-production; intended for early adopters and contributors, not mission-critical deployments. Architecture still evolving; emphasis on portability and capability expansion.

---

## Complete Skills Inventory

### Agent Operations (agent-ops/)
- `claude-plugin-converter` — Convert Claude plugins to skill format
- `hermes-onboarding` — Onboarding workflows for Hermes
- `input-token-analysis` — Analyze and measure token usage patterns
- `input-token-overheads` — Measure overhead costs per operation
- `log-analyzer` — Parse and extract patterns from agent logs
- `operator-brain` — Central operational management coordination
- `skill-maintainer` — Maintenance utilities for skills

### Creative (creative/)
- `clips-studio` — Video clip generation and editing
- `image-studio` — Image generation and manipulation
- `pexels-stock-photos` — Retrieval and filtering of stock photography

### DevOps (devops/)
- `disk-cleanup` — Storage space recovery and cleanup

### MLOps (mlops/)
- `model-compare` — Side-by-side model evaluation and comparison

### Plugins (plugins/)
- `skill-retrieval` — **BM25-based dynamic skill discovery** (see deep dive below)

### Productivity (productivity/)
- `decision-log` — Track and review decision history
- `file-organizer` — Automatic file categorization and organization
- `fill-template` — Template expansion with variable substitution
- `receipt-compiler` — Extract and consolidate expense data
- `scheduled-summary` — Generate time-based summaries of activity
- `task-brief` — Task decomposition and briefing generation
- `travel-itinerary` — Travel planning and itinerary management

### Research (research/)
- `deep-research` — Multi-source investigation with fact synthesis
- `endpoint-probe` — API endpoint discovery and testing
- `entity-research` — Biographical and contextual entity enrichment
- `fact-checker` — Claim verification against reference sources
- `library-rag` — Document retrieval and augmented generation
- `media-analyzer` — Media content analysis and classification
- `news-monitoring` — News aggregation and trend tracking
- `notebooklm-mode` — Notebook-style research interface
- `people-enrichment` — Person data enrichment and profiling
- `source-tracker` — Track and cite information provenance
- `youtube-topic-research` — Video metadata analysis and topic extraction

### Web Scraping (web-scraping/)
- `website-scraping` — General-purpose web content extraction

---

## DEEP DIVE: Skill-Retrieval Plugin

### The Problem

Hermes Agent deployments with hundreds of skills face a crippling **token overhead**: including full skill descriptions in the system prompt consumes ~11.5K tokens *per session*. This starves the actual work context window. With skills numbered in the hundreds, it becomes impractical to list all of them upfront.

### Solution: Two-Phase Token Optimization

**Phase 1 (Session Initialization):**
- Monkey-patches `build_skills_system_prompt` to strip descriptions
- Replaces full skill list with **names only, organized by category**
- Reduces system prompt from ~11.5K tokens to ~2K tokens
- All skills remain discoverable by name

**Phase 2 (Per Turn, Pre-LLM Hook):**
- `pre_llm_call` hook intercepts each user message
- Ranks available skills against the message using **BM25 Okapi ranking**
- Injects top-K (default 6) most relevant skill descriptions (~300 tokens)
- Skills formatted as: `- **{name}** ({skill_id}): {description}` (truncated to 200 chars)

### Impact
- **System prompt savings:** ~9.5K tokens
- **Per-turn injection:** ~300 tokens
- **Net per-turn gain:** ~9K tokens for deployments with 300+ skills
- **Retrieval performance:** Sub-millisecond for 128 skills

### Mechanical Implementation

#### Index Construction (Runtime, No Pre-built File)

The `BM25Index.build()` method in `scripts/bm25_retriever.py`:

1. **Tokenization:** Whitespace + punctuation tokenizer, lowercased
2. **Vocabulary:** Records term frequencies and document lengths; computes average document length (avgdl)
3. **IDF Calculation:** Lucene-style clipped IDF: `max(0, log((N - df + 0.5) / (df + 0.5)))`
4. **Precomputed Weights:** Builds inverted index mapping each term to posting list of (doc_index, BM25_weight)
   - BM25 Okapi parameters: **k1=1.5, b=0.75** (standard tuning)

#### Ranking Process

```
Query → Tokenize → Lookup term posting lists → Sum precomputed weights → Sort by score
```

Highly efficient (no corpus scan, only posting-list lookups).

#### Skill Injection Process

From `__init__.py` hook implementation:
```
_on_pre_llm_call(user_message):
    query = user_message  # or tokenized summary
    skills = index.retrieve(query, top_k=TOP_K)
    injection = format_skill_block(skills)
    return injection + "\n" + user_message
```

No embedding model required; purely lexical ranking.

### Configuration

- `SKILL_RETRIEVAL_TOP_K` — Number of skills to retrieve (default: 6)
- `SKILL_RETRIEVAL_COMPACT` — Enable/disable phase 1 (default: enabled)
- BM25 k1, b parameters — Tunable in source (hardcoded at 1.5, 0.75)

### Dependencies

- **pyyaml** (≥6.0) — YAML configuration parsing
- **No external embeddings, no LLM calls**
- Python 3.11+

### Test Coverage

Comprehensive test suite in `tests/`:
- `test_bm25_retriever.py` — Core BM25 ranking logic
- `test_issue8_round2.py` — Regression tests (issue #8)
- `test_regressions.py` — Broad regression coverage
- `test_stdlib_parity.py` — Parity vs. standard library implementations

---

## Critical Assessment

### Strengths
1. **Real token savings:** ~9K tokens per turn is substantial; claim is backed by transparent calculation
2. **Elegant design:** Two-phase approach decouples presentation from ranking
3. **Efficient:** BM25 with precomputed weights ensures sub-millisecond latency; no I/O or LLM overhead
4. **Well-tested:** 4 test modules covering core logic, regressions, and stdlib parity
5. **Zero external dependencies:** Purely lexical ranking, no embedding model or API call

### Skepticism Points
1. **Hermes-specific:** Plugin architecture relies on `pre_llm_call` hook and Hermes' event system. **Will not work with Claude Code** (lacks hooks).
2. **No runtime index persistence:** Index rebuilt on every session start. For 1000+ skills, startup time unknown (untested).
3. **BM25 parameter lock:** k1=1.5, b=0.75 hardcoded; no per-domain tuning or A/B testing evidence provided
4. **Top-K brittleness:** No fallback if top-6 skills are irrelevant. Static k=6 may be suboptimal for different query distributions
5. **Description truncation:** Truncating descriptions to 200 chars may lose critical details for complex skills
6. **No retrieval evaluation:** No published recall/precision metrics, no comparison to naive "all skills in prompt" on same queries
7. **Maturity risk:** Repository is pre-production; skill-retrieval plugin is active (v0.2.0 as of latest), but no production deployment data shared

### Problem It Claims to Solve
✅ **Progressive disclosure of skill inventory** — solves the token budget problem for large skill sets  
✅ **Maintains discoverability** — names remain visible  
⚠️ **Whether ranking is actually effective** — no published evaluation; relies on BM25 quality assumption

---

## Repository Ecosystem Dependencies

- **Language:** Python 3.11+
- **Runtime dependencies:** None (pyyaml is dev-only for config)
- **Integration:** Hermes Agent framework (event hooks, plugin system)
- **Portability claim:** Skills "should adapt" to Claude Code, LangGraph, etc., but this is not implemented; porting requires manual tool-name mapping

---

## Recommendation for ClaudeKit

The skill-retrieval design is **conceptually sound** and addresses a real problem (context budget for skill-heavy agents). However:

1. **Architecture is Hermes-specific.** Porting to Claude Code would require:
   - Implementing system-prompt interception (possible via prompts)
   - Implementing a per-turn pre-processing hook (not natively available)
   - Building a BM25 index loader/builder (can reuse bm25_retriever.py logic)

2. **The token math is real** but untested at scale (1000+ skills)

3. **Lexical ranking (BM25) works well** for skill discovery but may fail on semantic queries ("convert image to WebP" → no direct keyword match to image-format-conversion skill)

**Consider:** Adapt the two-phase design but evaluate whether embedding-based retrieval (e.g., via sentence-transformers or Claude's own embeddings) would improve recall for ClaudeKit's use case.
