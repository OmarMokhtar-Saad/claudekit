# Core Pipeline Agents: explore

<!-- split-from-AGENTS.md -->
> Part of the agent reference. Index: [AGENTS.md](AGENTS.md)

## explore

**Purpose.** Fast, strictly read-only codebase exploration: find files, trace dependencies, answer architecture questions, and produce structured reports — including a dedicated Planner Handoff format to feed planning.

**Responsibilities.** Scope narrowing, parallel search execution (file discovery, content search, structure analysis, dependency tracing, git history analysis), structured reporting at three thoroughness levels.

**Inputs.** A search query or architectural question, optionally a thoroughness level. **Outputs.** `EXPLORATION REPORT` (purpose, scope, target files table with relevance, findings, patterns, constraints, optional Planner Handoff), `EXPLORE COMPLETE` summary.

**Frontmatter (verbatim).**
- `name: explore`
- `description: Fast codebase exploration specialist. Searches files by patterns, keywords, answers architecture questions. Read-only. Use when you need to find files, understand architecture, or answer questions about the codebase.`
- `model: sonnet` | `color: yellow`
- `tools: ["Read", "Grep", "Glob", "Bash"]`

**Internal workflow.** Phase 1 scope narrowing (choose strategy: file/content/structure/dependency/history-based) → Phase 2 parallel searches → Phase 3 structured output. Thoroughness levels: Quick (~30s, simple lookups), Medium (~2min, architectural questions), Very Thorough (~5min, comprehensive audit). Includes search strategy recipes (finding definitions, usages, feature maps, project overview, dependency audit, code quality snapshot) and performance tips (Glob before Read, targeted Grep, stop early).

**Dependencies.** Skills: `using-superpowers`, `golden-rule`. Downstream: coordinator (complete / needs more context) and planner (via Planner Handoff section: relevant files, tech stack, conventions observed, constraints, recommendations).

**Memory/context.** Strictly read-only; Edit/Write FORBIDDEN; Bash limited to read-only commands (ls, find, git log/diff, wc, tree).

**Failure recovery.** `HANDOFF TO: coordinator` with `Status: NEEDS MORE CONTEXT`, found-so-far summary, missing info, and suggestions on where to look next.

**Example invocation.**
```bash
echo "How does the payment processing flow work? Thoroughness: medium. Produce an exploration report with a Planner handoff." | \
  claude -p --agent explore --model sonnet --allowedTools "Read,Grep,Glob,Bash"
```

**Improvement notes.** Functionally similar to the built-in Explore subagent type in newer Claude Code releases; kept as a project-local definition. No issues found internally.

---

