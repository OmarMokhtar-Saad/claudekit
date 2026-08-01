# Anthropic's AI Agent Memory & Context Engineering Guidance

**Date**: 2026-08-01  
**Query**: Anthropic published guidance on agent memory, context engineering, long-term vs short-term storage, bloat prevention, bug persistence

## Summary

Anthropic recommends treating context as a finite resource and separating concerns: just-in-time retrieval for large datasets, memory tools for cross-session persistence, and structured note-taking for discovered issues.

## Concrete Recommendations

### (1) Long-term Memory vs Short-term Context

**Memory (persistent, cross-session):**
- Use the Memory Tool to store information outside the context window in a file-based system
- Store lightweight identifiers (file paths, URLs) and load data at runtime
- Enable agents to build knowledge over time without context bloat
- Works client-side: agent requests operations, app executes them

**Context (active, in-window):**
- Pre-load critical data for speed
- Use just-in-time retrieval pattern (mirroring human external organization systems)
- Clear tool results deeper in message history once they've served their purpose
- Reserve for immediate task execution

### (2) Avoiding Bloat & Staleness

**Context engineering principles:**
- "Treat context as a finite resource with diminishing marginal returns"
- Minimize tool sets: if a human can't choose which tool, neither can the agent
- Curate examples carefully—use diverse canonical cases, not exhaustive edge-case lists
- Prune redundant data deeper in history

**Technical defenses:**
- **Context editing**: Client-side automatic clearing of specific tool results
- **Compaction**: Server-side summarization when conversation approaches context limits
- **Memory expiration**: Periodically delete unused memory files
- Combine both: compaction summarizes older context, memory preserves essentials

### (3) Recording Discovered Issues

**Multisession software development pattern:**
- Set up memory files deliberately before work begins (not ad hoc)
- Include: progress log (done/next), feature checklist (scope), startup scripts
- Use **structured note-taking**: agents maintain external notes (NOTES.md, memory files) tracking progress
- Progress log records what was completed and what remains before each session ends
- Example: Pokémon-playing agent maintains precise tallies and strategy notes across thousands of steps

**Key principle:** Mark work complete only after end-to-end verification, not when code is written—keeps memory accurate across sessions.

## Sources

- [Building Effective Agents (Anthropic)](https://www.anthropic.com/engineering/building-effective-agents)
- [Effective Context Engineering for AI Agents (Anthropic)](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Memory Tool Documentation (Claude Platform)](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)
- [Managing Context on Claude Developer Platform (Anthropic)](https://www.anthropic.com/news/context-management)
