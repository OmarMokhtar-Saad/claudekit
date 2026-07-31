# Specialist Agents: typescript-reviewer, python-reviewer, code-reviewer, build-error-resolver

<!-- split-from-AGENTS.md -->
> Part of the agent reference. Index: [AGENTS.md](AGENTS.md)

## typescript-reviewer

**Purpose.** TypeScript-specific code review: type safety (`any` abuse, missing null handling, unvalidated assertions), async/await patterns (floating promises, sequential awaits, untyped catch), interface/type design, generics constraints, module/export patterns.

**Inputs.** TypeScript files or a PR. **Outputs.** `TypeScript Review Report` — Score XX/100, Type Safety Rating (STRICT/MODERATE/LOOSE) with counts of `any` usage/assertions/unhandled promises/missing null checks, findings with severity, verdict APPROVE / REQUEST_CHANGES / BLOCK.

**Frontmatter (verbatim).**
- `name: typescript-reviewer`
- `description: TypeScript code quality specialist. Reviews TypeScript code for type safety, best practices, common pitfalls, and idiomatic patterns. Use when reviewing TS files or PRs.`
- `model: sonnet` | `color: blue`
- `tools: ["Read", "Grep", "Glob", "Bash"]`

**Internal workflow.** Review the five dimensions with before/after code exemplars, then run automated checks: `npx tsc --noEmit`, grep for `any`, type assertions, floating promises, and untyped catch clauses. Severity ladder CRITICAL (runtime crashes/data loss from type errors) → LOW (style).

**Dependencies.** Code Quality Audit pipeline: Coordinator → [TypeScriptReviewer | PythonReviewer] → Implementer (if fixes needed) → Verifier. Parallel-safe with python-reviewer.

**Memory/context.** Read-only tool usage (no Write/Edit).

**Failure recovery.** None specified.

**Example invocation.**
```bash
echo "Review src/services/*.ts for type safety, any usage, and async issues. Produce the TS review report with a verdict." | \
  claude -p --agent typescript-reviewer --model sonnet --allowedTools "Read,Grep,Glob,Bash"
```

**Improvement notes.** Score XX/100 has no defined threshold (unlike reviewer's 90 and verifier's 80). One frontmatter example. No skill-loading section. Overlaps code-reviewer's Correctness/Quality dimensions on TS code; model-router's override says code review for merge approval should be "minimum Opus" while this reviewer is Sonnet.

---

## python-reviewer

**Purpose.** Python-specific code review: mutable default arguments, type hint coverage, exception handling (bare except, swallowed exceptions), Pythonic idioms (enumerate, context managers), security (SQL/shell injection, unsafe deserialization), performance patterns.

**Inputs.** Python files or a PR. **Outputs.** `Python Code Review` report — Score XX/100, detected Python version, type coverage %, critical security issues, findings with fix snippets, PEP 8/docstring/type-hint compliance stats, verdict APPROVE / REQUEST_CHANGES / BLOCK.

**Frontmatter (verbatim).**
- `name: python-reviewer`
- `description: Python code quality specialist. Reviews Python code for correctness, Pythonic patterns, type hints, security, and performance. Use when reviewing Python files or PRs.`
- `model: sonnet` | `color: green`
- `tools: ["Read", "Grep", "Glob", "Bash"]`

**Internal workflow.** Review six dimensions with code exemplars, then run automated checks: flake8, mypy, bandit, plus greps for mutable defaults, bare excepts, SQL string formatting, and `shell=True`.

**Dependencies.** Code Quality Audit pipeline (parallel-safe with typescript-reviewer). No skill-loading section.

**Memory/context.** Read-only tool usage.

**Failure recovery.** None specified.

**Example invocation.**
```bash
echo "Review this Python module for type hints, exception handling, security, and idioms. Produce the review report." | \
  claude -p --agent python-reviewer --model sonnet --allowedTools "Read,Grep,Glob,Bash"
```

**Improvement notes.** Same structural gaps as typescript-reviewer: undefined score threshold, single example, no skill loading. Its security dimension overlaps security-scanner's SAST phase and its exception-handling dimension overlaps silent-failure-hunter.

---

## code-reviewer

**Purpose.** Expert review of **actual code** — diffs, files, PRs — for correctness, security, performance, reliability, and quality. Explicitly "NOT the plan reviewer (`reviewer.md`). You review implementation, not plans." Read-only.

**Inputs.** Changed files or a PR diff. **Outputs.** `CODE REVIEW REPORT` — counts by severity, verdict (APPROVE / APPROVE WITH SUGGESTIONS / REQUEST CHANGES / BLOCK), findings with Evidence/Impact/Fix and file:line, positive observations, coverage checklist.

**Frontmatter (verbatim).**
- `name: code-reviewer`
- `description: Expert code review specialist that reviews actual code diffs, files, and PRs for bugs, logic errors, security issues, and code quality. Distinct from the plan-reviewer — this agent reviews implementation, not plans. Use when code has been written and needs review before merging.`
- `model: opus` | `color: orange`
- `tools: ["Read", "Grep", "Glob", "Bash"]`

**Internal workflow.** Phase 1 scope assessment (what changed, LOC, domain, domain skill) → Phase 2 read and trace (full files not just diffs, call graph, data flows, trust boundaries) → Phase 3 apply five prioritized dimensions (Correctness P0, Security P0, Performance P1, Reliability P1, Code Quality P2) → Phase 4 confidence filtering (only report with a file:line, real not hypothetical, actionable fix; no style nitpicks, no findings in unchanged code) → Phase 5 report. Severity table: Critical blocks merge; High fix before merge; Medium this sprint; Low when convenient.

**Dependencies.** Skills: `using-superpowers`, `golden-rule`, `security-checklist`, `differential-security-review` (detects removed security controls). Routed via coordinator's generic "Code Review" specialist row ("review this code", "review PR", "check this diff").

**Memory/context.** Read-only ("You do NOT modify any code"). NEVER approves with a Critical finding.

**Failure recovery.** None specified; it is a gate that emits verdicts.

**Example invocation.**
```bash
echo "Review the changes in src/auth/ for correctness and security. Rank findings by severity with file:line evidence." | \
  claude -p --agent code-reviewer --model opus --allowedTools "Read,Grep,Glob,Bash"
```

**Improvement notes.** Naming is confusingly close to `reviewer` (both files acknowledge and disambiguate). It appears in no pipeline diagram — the Feature pipeline goes straight from Implementer to Verifier with no code-diff review stage, so code-reviewer is only reachable via direct specialist routing.

---

## build-error-resolver

**Purpose.** Surgical build fixer: repairs build/type/compilation errors with the smallest possible diff. "Fix the error. Only the error. Nothing else." Explicitly prohibited from refactoring or improving anything.

**Inputs.** Build error output (TS error codes TS2345/TS2322/TS2339/TS2304/TS2307/TS7006/TS2741/TS18046; Go, Rust, Python error catalogs included). **Outputs.** Minimal edits plus a report (files changed, errors fixed, build status PASS/STILL FAILING, per-fix rationale, remaining errors).

**Frontmatter (verbatim).**
- `name: build-error-resolver`
- `description: Specialist that fixes build errors, type errors, and compilation failures with the smallest possible diff. Strictly prohibited from refactoring, redesigning, or making changes beyond what is needed to fix the error. Use after a build fails and you need targeted, minimal fixes.`
- `model: sonnet` | `color: yellow`
- `tools: ["Read", "Grep", "Glob", "Bash", "Edit"]`

**Internal workflow.** Phase 1 read all errors (parse file:line:col, group by file, fix in appearance order since downstream errors cascade) → Phase 2 locate and understand (±20 lines context) → Phase 3 apply minimum fix (only causal lines; comment non-obvious fixes) → Phase 4 verify and repeat (max 7 iterations; if errors increase, revert and try differently) → Phase 5 report.

**Dependencies.** Skills: `using-superpowers`, `systematic-debugging`. Escalates to the Planner. Never commits (GitOps's job).

**Memory/context.** None beyond the build output.

**Failure recovery.** Escalates to Planner (with options and trade-offs) when a fix requires a public API change, a new dependency, an architectural type redesign, or after 7 iterations. Never suppresses with `@ts-ignore`, never adds `any`, never changes signatures to silence call-site errors.

**Example invocation.**
```bash
echo "tsc is showing 12 errors. Fix each with the minimum change and re-run tsc until clean. No refactoring." | \
  claude -p --agent build-error-resolver --model sonnet --allowedTools "Read,Grep,Glob,Bash,Edit"
```

**Improvement notes.** Notable as the only agent besides golden-rule loaders that skips `golden-rule` in favor of `systematic-debugging`. QUICK_START permission "Read, Edit" omits its Bash/Grep/Glob.

---

