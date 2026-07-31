# Specialist Agents: silent-failure-hunter, harness-optimizer, performance-optimizer, code-simplifier

<!-- split-from-AGENTS.md -->
> Part of the agent reference. Index: [AGENTS.md](AGENTS.md)

## silent-failure-hunter

**Purpose.** Error-handling audit with "zero tolerance for hidden errors": finds swallowed exceptions, empty catches, inadequate logging, dangerous fallbacks, and missing error propagation.

**Inputs.** Source files to audit. **Outputs.** Per-finding blocks (severity, location, pattern, impact, suggested fix with code) plus a `Silent Failure Audit Summary` (counts by severity and category, highest-risk files, immediate actions, PR-ready status: SAFE TO MERGE / NEEDS FIXES BEFORE MERGE).

**Frontmatter (verbatim).**
- `name: silent-failure-hunter`
- `description: Reviews code for silent failures, swallowed errors, bad fallbacks, and missing error propagation. Use when auditing error-handling quality or before releasing critical code.`
- `model: sonnet` | `color: red`
- `tools: ["Read", "Grep", "Glob", "Bash"]`

**Internal workflow.** Five hunt categories (empty catch blocks; inadequate logging; dangerous fallbacks like `except ... return []` and `os.getenv(...) or "default"`; error propagation loss including `raise ... from None` and async patterns; missing error handling on network/file/DB calls) executed as a 5-step grep-driven investigation (scope assessment → empty catch hunt → logging quality → fallback detection → async propagation). Severity ladder CRITICAL (silent data/state corruption) → LOW. Explicit allowlist of patterns never to report (KeyboardInterrupt/SystemExit passes, pytest.raises, `# noqa: silent-failure`, optional-import fallbacks).

**Dependencies.** Runs in parallel with security-scanner in the Security Audit pipeline; joint handoff to planner per HANDOFF_PROTOCOL.md (`Report: .claude/reports/audit-<timestamp>.md`).

**Memory/context.** Read-only in practice (no Write/Edit tools). Audit report path convention comes from HANDOFF_PROTOCOL.md.

**Failure recovery.** None specified; it is a reporting agent.

**Example invocation.**
```bash
echo "Audit src/ for silent failures: empty catches, swallowed errors, dangerous fallbacks. Produce the audit summary." | \
  claude -p --agent silent-failure-hunter --model sonnet --allowedTools "Read,Grep,Glob,Bash"
```

**Improvement notes.** No skill-loading section, no explicit READ-ONLY banner despite being read-only by tool omission. Partially overlaps code-reviewer (Reliability dimension) and python-reviewer (exception handling dimension).

---

## harness-optimizer

**Purpose.** Meta-agent that tunes the `.claude/` harness itself for reliability, cost, and throughput: hook performance, agent description token bloat, skill loading latency, MCP overhead, context budget. Constraint: improve configuration, never product code.

**Inputs.** The `.claude/` directory. **Outputs.** `HARNESS OPTIMIZATION REPORT` (baseline vs optimized metrics, applied changes, deferred changes needing approval, remaining risks); reversible config edits with backups.

**Frontmatter (verbatim).**
- `name: harness-optimizer`
- `description: Analyzes and improves the local agent harness configuration for reliability, cost, and throughput. Use when sessions feel slow, hooks are misfiring, or you want to tune agent performance.`
- `model: sonnet` | `color: cyan`
- `tools: ["Read", "Grep", "Glob", "Bash", "Edit"]`

**Internal workflow.** Phase 1 baseline audit (count agents/skills/hooks/commands, size by lines, hook complexity) → Phase 2 five optimization dimensions (hook async-vs-sync and timeouts; agent descriptions >500 lines, DRY violations, excess examples; skill loading patterns; MCP overhead at ~500 tokens/tool schema; context budget estimate at ~1.3 tokens/word) → Phase 3 recommendations (each typed, risk-rated, reversible, with projected improvement) → Phase 4 apply only approved low-risk reversible changes with timestamped backups (`settings.json.bak.<epoch>`) → Phase 5 comparative report.

**Dependencies.** Reads/edits `.claude/settings.json`, `.claude/hooks/*.sh`, `.claude/agents/*.md`, `.claude/skills/*/SKILL.md`, `.claude/commands/*.md`. See [./HOOKS.md](./HOOKS.md) for the hook inventory it optimizes.

**Memory/context.** `.claude/` only; NEVER modifies product source code, never removes a hook without backup, never reduces security hooks (pre-commit, pre-push, block-no-verify).

**Failure recovery.** All changes reversible without git revert; flags anything affecting CI/CD or shared team configs; dry-runs hook changes before activating.

**Example invocation.**
```bash
echo "Audit the harness: hook timeouts, agent token bloat, MCP overhead, context budget. Propose reversible optimizations." | \
  claude -p --agent harness-optimizer --model sonnet --allowedTools "Read,Grep,Glob,Bash,Edit"
```

**Improvement notes.** Only one frontmatter example (most agents have two). QUICK_START lists its permissions as "Read, Write" but its tools are Read/Grep/Glob/Bash/Edit (Edit, not Write).

---

## performance-optimizer

**Purpose.** Runtime performance diagnosis: latency, memory, throughput, query efficiency. Core rule: "Profile before optimizing" — every change needs a before-measurement and an after-measurement.

**Inputs.** Slow code, profiling data, performance symptoms. **Outputs.** `Performance Analysis Report` (problem characterization, profiling results, findings with severity/location/cost/fix/expected improvement, prioritized fix list with estimated speedups, measurement plan).

**Frontmatter (verbatim).**
- `name: performance-optimizer`
- `description: Profiles and optimizes runtime performance — latency, memory, throughput, and query efficiency. Use when features are slow, memory usage is high, or scalability is needed.`
- `model: sonnet` | `color: yellow`
- `tools: ["Read", "Grep", "Glob", "Bash"]`

**Internal workflow.** Step 1 characterize via a symptom→root-cause table (cold start, O(n²)/N+1, lock contention, leaks, GC pauses, missing indexes, blocking sync in async) → Step 2 profile the hot path (cProfile, node --prof, EXPLAIN ANALYZE, memory_profiler) → Step 3 identify anti-patterns across four families: database (N+1, missing indexes, unbounded queries), async/concurrency (blocking I/O in async, sequential awaits), memory (unbounded caches, large object retention), algorithms (O(n²) in disguise, string concat loops). A 17-item profiling checklist covers DB/async/memory/CPU.

**Dependencies.** Performance pipeline: Coordinator → Explore → PerformanceOptimizer → Verifier → GitOps (coordinator.md) or [Explore + PerformanceOptimizer] parallel → Planner → Implementer → Verifier (HANDOFF_PROTOCOL.md).

**Memory/context.** Read-only tool set; despite the name "optimizer", it reports fixes rather than applying them (no Write/Edit).

**Failure recovery.** None specified. Constraints: never optimize without measuring, never sacrifice correctness, always flag consistency-affecting changes.

**Example invocation.**
```bash
echo "Our API takes 2+ seconds per request. Profile the hot path and produce a prioritized fix list with measurements." | \
  claude -p --agent performance-optimizer --model sonnet --allowedTools "Read,Grep,Glob,Bash"
```

**Improvement notes.** No skill-loading section, no handoff formats. QUICK_START permission "Read" understates its Bash access. Description says "optimizes" but the tool set is analysis-only.

---

## code-simplifier

**Purpose.** Reduces complexity without reducing functionality: removes unnecessary abstractions, premature generalization, redundant code, nested conditionals, verbose naming, pointless temporaries, and restating comments. Core rule: every simplification must be behavior-preserving or proposed-only.

**Inputs.** Recently changed code (defaults to `git diff --name-only HEAD~1`). **Outputs.** `Code Simplification Report` (per-change before/after with behavior-change assertion, proposed-but-not-applied list, lines removed, test result).

**Frontmatter (verbatim).**
- `name: code-simplifier`
- `description: Simplifies and refines code for clarity, consistency, and maintainability while preserving all functionality. Use after implementation to reduce complexity and improve readability.`
- `model: sonnet` | `color: purple`
- `tools: ["Read", "Grep", "Glob", "Bash", "Edit"]`

**Internal workflow.** Step 1 focus on recently changed files → Step 2 measure complexity (radon cyclomatic complexity, functions >50 lines) → Step 3 apply simplifications (state what/why, show before/after, confirm behavior preserved, edit) → Step 4 verify no regressions (run tests). Includes a "What NOT to Simplify" guard list (error handling, debugging temporaries, safety checks, speculative generalization, cleverness).

**Dependencies.** Routed via coordinator's "Simplify" specialist row. No skill-loading section.

**Memory/context.** Edits source files directly (Edit tool); runs tests via Bash.

**Failure recovery.** Simplifications it cannot guarantee are behavior-preserving are proposed, not applied, with a testing-required note.

**Example invocation.**
```bash
echo "Simplify the implementation we just wrote; preserve all behavior; run tests after." | \
  claude -p --agent code-simplifier --model sonnet --allowedTools "Read,Grep,Glob,Bash,Edit"
```

**Improvement notes.** One frontmatter example only. QUICK_START permission "Read, Write" doesn't match its tools (Edit, no Write). Overlaps refactor-cleaner on duplicate-logic removal, though refactor-cleaner is tool-driven dead-code removal and code-simplifier is readability-driven.

---

