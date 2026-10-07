# Hermes Agent: Research Summary

**Query Date**: 2026-09-17  
**Project**: Hermes Agent (NousResearch/hermes-agent)  
**Status**: Authoritative repo found; core mechanics documented

> **Provenance — read before citing.** This is a `web-researcher` cache, not a source
> artifact (CLAUDE.md evidence precedence): verify against the repo/docs before any plan
> rests on a claim here. Two citations below are **suspect and were not confirmed**: the
> arXiv ids in the `2606.*` range and `issue #25833` on a repo whose issue numbering is
> nowhere near five digits. The docs-level mechanics (memory file budgets, session-start
> frozen injection, FTS5 `session_search`, `write_approval`, autonomous `skill_manage`
> writes) are consistent across the report and the linked docs paths, and are what the
> 2026-09-17 ideas session relied on.

---

## 1. What It Is & Component Inventory

**Core Identity**: An open-source AI agent framework by Nous Research emphasizing persistent memory, self-learning, and modular skill architecture.

**Component Inventory**:
- `agent/` — core AIAgent orchestrator (synchronous loop, provider selection, prompt construction)
- `gateway/` — multi-platform messaging (Telegram, Discord, Slack, WhatsApp, Signal)
- `skills/` + `optional-skills/` — procedural memory (on-demand knowledge documents)
- `tools/` — 70+ registered tools across ~28 toolsets (terminal, browser, web, MCP)
- `providers/` — LLM adapters (OpenAI, Anthropic, OpenRouter, etc.)
- `hermes_state_*.py` — persistent storage (SQLite sessions, FTS5 search, WAL)
- `hermes_cli/` — terminal interface
- `ui-tui/` + `tui_gateway/` — text UI with multiline editing
- `optional-mcps/` — Model Context Protocol integrations
- `plugins/` + `plugin-catalog/` — extensibility system
- `cron/` — scheduled task automation
- `evals/` — evaluation and testing

**Storage Layout**: 
- `~/.hermes/memories/` — MEMORY.md + USER.md files
- `~/.hermes/skills/` — skill library (with project-local override support)
- SQLite session database (per-platform isolation)

---

## 2. Memory Model

**File Format & Schema**:
- **MEMORY.md** (~2,200 char budget): agent's learned facts, environment context, lessons
- **USER.md** (~1,375 char budget): user profile, preferences, communication style
- Plain text (Markdown) with character-based capacity constraints

**Scoping**: 
- Per-profile (separate agents get separate profiles)
- External providers enable cross-profile/fleet sharing (Honcho, Mem0, Hindsight)
- Project-local skills (activate within specific repositories)

**Retrieval & Injection**:
- Frozen snapshot injected into system prompt at session start
- No mid-session updates visible until next session (design choice for cost predictability)
- Session search via `session_search` tool queries SQLite FTS5 across past conversations
- No LLM summarization required for retrieval

**Consolidation & Curation**:
- Capacity errors force explicit consolidation (no silent drops)
- Agent manages entries via `memory` tool (add, replace, remove)
- Tight character budget enforces curation discipline

**Human Gating**:
- Optional `write_approval: true` setting stages all memory/skill writes for review before persistence

**Decay/Expiry**: Not explicitly documented; appears indefinite unless manually removed.

---

## 3. Learning & Self-Improvement Loop

**Triggers**: 
- Repeated corrections (workflow refinement)
- Complex or error-prone task completion
- User-initiated skill extraction

**Artifacts Written**:
- Skills (procedural memory, reusable multi-step workflows)
- Memory entries (factual updates, lessons learned)
- User profile refinements (preferences, communication patterns)

**Autonomous vs. Human-Gated**:
- Default: autonomous skill creation via `skill_manage` tool
- Optional: `write_approval: true` requires human approval before writes commit
- Consent-aware design: learning loop respects user review preferences

**Skill Auto-Creation**:
- Agent persists "multi-step workflows worth repeating" as reusable skills
- Skills follow agentskills.io open standard
- Metadata includes version, OS platforms, tags, category, configuration
- Skills stored in `~/.hermes/skills/` (subject to progressive disclosure: Level 0 list, Level 1 full content, Level 2 specific refs)

**Skill Bundling**: Multiple related skills grouped under single `/` commands for efficiency

**Skill Improvement**: Skills iteratively improve during use; not one-shot creation

**Bloat/Drift Prevention**:
- Curator mechanism and test gates (documented but mechanism details sparse)
- Security scanning for data exfiltration, prompt injection, destructive commands
- Syntactic/formatting compliance checks (but not semantic safety analysis)

---

## 4. Unique Features (vs. Typical Claude Code Setup)

**Cross-Session Semantic Memory**:
- Session search with FTS5 without requiring LLM summarization (differentiator from naive context retrieval)
- Honcho "dialectic modeling" for progressive user profile refinement

**External Memory Provider Ecosystem**:
- Pluggable providers (Honcho, Mem0, Hindsight, others) for knowledge graphs and semantic search

**Skill Bundles & Progressive Disclosure**:
- Token-efficient loading of skill metadata (Level 0 lists ~3k tokens vs. full content)
- Project-local skill activation (context-specific capability loading)

**Multi-Modal Gateway**:
- Native messaging platform support (not typical Claude Code)
- Platform isolation in session storage

**Observable Tool Execution**:
- All tool calls remain visible to users (transparency design principle)

**Loose-Coupled Plugin Architecture**:
- Optional subsystems use registry patterns (no hard dependencies)

---

## 5. Known Limitations & Failure Modes

**Critical Structural Issue**: 
- Agent is simultaneously author, executor, and quality inspector of self-created skills
- No external validation point or consistency guarantee
- Self-created skills lack mechanism-level correctness guarantees

**Learning Pathologies**:
- Skill auto-creation can encode transient failures as persistent behaviors (learned helplessness)
- Skills can capture session-specific lucky paths or suboptimal approaches as reusable procedures
- Prompt-level mitigations exist but don't prevent encoding incorrect workflows

**Session Boundary Issue**:
- Learning loop dormant within single continuous session (common on messaging platforms)
- Memory activation only at session boundaries (Hermes-specific, may surprise users migrating from continuous memory systems)

**Security Gap**:
- Skill review is syntactic/formatting only; no semantic safety analysis
- Hub-installed skills scanned, but self-created ones rely on prompt-level guardrails

**Scalability Unknown**:
- No documented limits on skill library size or memory consolidation scaling
- Token cost of very large MEMORY/USER files in system prompt not quantified

**No Explicit Verification Mechanism**:
- Documentation mentions "Verification" sections in skills (how to confirm it worked) but enforcement/automation not detailed
- No automatic QA/test-generation tie-in documented

---

## Source URLs

- [NousResearch/hermes-agent (GitHub)](https://github.com/NousResearch/hermes-agent)
- [Hermes Agent Official Docs](https://hermes-agent.nousresearch.com/docs/)
- [Memory Documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory)
- [Architecture Documentation](https://hermes-agent.nousresearch.com/docs/developer-guide/architecture)
- [Skills System Documentation](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/skills.md)
- [hermes-CCC (Claude Code Port)](https://github.com/AlexAI-MCP/hermes-CCC)
- [Safety in Self-Evolving LLM Agent Systems (Academic)](https://arxiv.org/pdf/2606.23075)
- [Self-Created Skills Issue #25833](https://github.com/NousResearch/hermes-agent/issues/25833)
- [Are Online Skill and Memory Modules Always Worth Their Tokens?](https://arxiv.org/pdf/2606.15017)
- [Channel Fracture: Multi-Agent Reliability Failures](https://arxiv.org/pdf/2606.04896)

---

## Key Uncertainties (UNVERIFIED)

- Exact mechanism of Curator bloat-prevention system (referenced but not documented in public docs)
- Scalability limits on skill library and memory consolidation
- Metrics/telemetry on memory usefulness or skill adoption
- Semantic safety analysis details for skill review
- Citation/provenance tracking for learned claims
