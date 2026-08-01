# AI Agent Memory & Self-Improvement Loops: Framework Survey
**Date:** 2026-08-01 | **Queries:** 5 | **Sources:** 10

## Reflexion
**Problem:** LLM agents lack mechanism to learn from failure without weight updates. **Memory structure:** Dual-tier with short-term trajectory history and long-term episodic reflexion store (capped at 1-3 reflections to fit context). **Persistence mechanism:** Binary/scalar environment feedback is converted to natural-language summaries by a self-reflection LLM model immediately after evaluation; summaries persist in memory buffer; memory is capped by context limits, oldest reflections may be discarded.  
**Concrete detail:** After trial t, the agent appends the LLM-generated textual reflection to memory: "Given a sparse reward signal (success/fail), current trajectory, and persistent memory, the self-reflection model generates nuanced and specific feedback" which is then provided as context in the next episode.

## MemGPT / Letta
**Problem:** Context windows are finite; long-running agents need unbounded effective memory. **Memory structure:** Hierarchical OS-inspired paging with hot memory (in-context, fast), warm memory (summaries/indices), and cold memory (external archival storage). Agent manages paging through function calls. **Persistence mechanism:** Agent explicitly decides what to move between layers via virtual context management; slow/archival tier is write-once; warm tier (indexes) is LLM-created abstractions of cold data.  
**Concrete detail:** Agent treats context as operating system treats RAM—it interrupts execution, calls memory-management functions to load/evict data between main context and external storage (filesystem/database), and resumes; the LLM controls what summaries/indices are retained in warm memory for future retrieval.

## Generative Agents (Stanford, "Smallville")
**Problem:** Agents need to maintain consistent behavior, self-knowledge, and react contextually over long interactions. **Memory structure:** Unified memory stream storing raw observations, explicit reflection layer synthesizing observations into high-level insights, and retrieval scoring ranking by recency (exponential decay), importance (LLM-assigned binary labels), and relevance (embedding cosine similarity). **Persistence mechanism:** All raw observations stored indefinitely; reflections (higher-order abstractions) also stored; importance scoring determines which memories influence next decision—low-importance memories contribute less via retrieval score, effectively deprioritizing routine events.  
**Concrete detail:** Retrieval score = α·recency(t) + β·importance(mem) + γ·cosine_similarity(query_emb, mem_emb); memories surface contextually at decision points; reflection process distills multiple observations into abstract summaries (e.g., "Isabella seems to like John"), which are appended back to stream.

## Voyager (Minecraft)
**Problem:** Open-ended embodied tasks require compositional skill reuse without manual library curation. **Memory structure:** Vector-indexed skill library storing <description_embedding : executable_code> pairs; environment produces observations and success feedback. **Persistence mechanism:** New skills are only added after a dedicated GPT-4 critic verifies successful task completion using environment feedback + execution errors + self-verification; failure after 4 refinement attempts triggers discard; once verified, code is vectorized and indexed for future semantic-similarity retrieval.  
**Concrete detail:** Voyager stores verified-working code as skills in a vector-indexed library and retrieves by embedding-similarity of task description against skill descriptions; when facing a new task, the agent queries the top-5 most similar skills, composes or adapts them, and only persists the result if the verifier confirms execution success.

## CoALA (Cognitive Architectures for Language Agents)
**Problem:** Agent memory design lacks principled taxonomy; systems ad-hoc mix episodic, semantic, and procedural knowledge. **Memory structure:** Cognitive framework organizing four memory types: working memory (short-term context), episodic (past event records), semantic (factual world knowledge), procedural (skill/procedure definitions). **Persistence mechanism:** Framework is taxonomic, not prescriptive—each memory type serves distinct query patterns; agents decide persistence per-type (e.g., episodic may decay with time, semantic is durable, procedural requires verification before storage).  
**Concrete detail:** CoALA decomposes agent cognition using Tulving's cognitive psychology basis: working memory holds immediate context (chat history, partial solutions), episodic memory keeps timestamped events, semantic memory caches facts, procedural memory stores algorithms/policies; the architecture permits agents to design retention differently per tier (e.g., episodic → sliding window, semantic → LLM-refreshed, procedural → success-gated).

---

## Cross-Framework Pattern
All frameworks solve the core problem differently:
- **Reflexion**: Converts feedback → natural language → episodic buffer (bounded, text-centric)
- **MemGPT/Letta**: Agent-controlled paging between layers (hierarchical, active management)
- **Generative Agents**: Unified stream with scored retrieval + reflection synthesis (unified, scored access)
- **Voyager**: Episodic skill library with semantic indexing (modular, verified-only persistence)
- **CoALA**: Taxonomy permitting per-tier policies (framework, not implementation)
