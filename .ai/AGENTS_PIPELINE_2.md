# Core Pipeline Agents: verifier, debugger

<!-- split-from-AGENTS.md -->
> Part of the agent reference. Index: [AGENTS.md](AGENTS.md)

## verifier

**Purpose.** Post-implementation quality gate: runs static analysis, tests, and coverage; scores against an **80/100** threshold; decides PASS / RETRY / FAIL.

**Responsibilities.** Environment check, linter/formatter/type-checker runs, full test suite execution, coverage measurement, anti-pattern penalty application, scoring, retry/escalation routing.

**Inputs.** Main-session handoff with modified file list. **Outputs.** `VERIFICATION REPORT` with per-dimension score bars, penalties, decision; handoff to gitOps (pass), the main session (retry, max 2), or coordinator (fail / retry limit).

**Frontmatter (verbatim).**
- `name: verifier`
- `description: Quality validation agent. Runs static analysis, tests, and coverage checks with 80/100 approval threshold. Use after implementation to validate code quality before committing.`
- `model: sonnet` | `color: purple`
- `tools: ["Read", "Bash", "Grep", "Glob"]`

**Internal workflow.** Phase 1 environment check + baseline (pre-existing failures, current coverage) → Phase 2 static analysis (score NEW issues only; 30% weight) → Phase 3 test execution (40% weight — highest, "passing tests are the strongest signal of correctness") → Phase 4 coverage analysis (30% weight) → Phase 5 scoring with 10 anti-pattern penalties (suppressed lint warnings −10, skipped tests −5 each max −15, empty catch −10, debug output −5, commented-out code −5, magic numbers −3, duplicate blocks −10, missing error handling −10, broad type assertions −5, assertion without message −3; floor −30) → decision.

**Dependencies.** Skills: `using-superpowers`, `golden-rule`, `test-driven-development`, `verification-before-completion`, `performance-guidelines`. Downstream: gitOps, main session, coordinator.

**Memory/context.** Read-only regarding code ("NEVER modify code yourself"). Compares against baseline; never counts pre-existing failures as new.

**Failure recovery.** 60–79 → RETRY to the main session with exact file:line issues ("Fix ONLY the listed issues"), max 2 retries; <60 → FAIL, escalate to Coordinator immediately and recommend re-planning; retry 2/2 exceeded → escalate. Never lowers the threshold, never estimates scores without running tools.

**Example invocation.**
```
TaskCreate:
  prompt: |
    You are the verifier agent.
    Read your agent definition: .claude/agents/verifier.md
    HANDOFF FROM: main session
    ---
    Status: EDITS COMPLETE
    Files Modified: src/services/cache.ts, src/models/entry.ts
    Build Status: PASS
  agent: verifier
```

**Improvement notes.** Runs on Haiku despite doing scoring judgment calls (test quality, anti-pattern detection); model-router's rubric would likely score this work above Haiku range. Threshold customization is documented in QUICK_START.md ("Adjust thresholds").

---

## debugger

**Purpose.** Read-only bug diagnosis: pattern matching against a known-bug database, log analysis, root cause identification with confidence levels. Produces a diagnosis report for the Planner; cannot edit code.

**Responsibilities.** Context gathering, pattern matching (7 pattern families: threading/concurrency, null reference, resource leaks, configuration, state management, timing/races, JS/TS async/promise errors), log analysis, root cause synthesis, confidence-based handoff.

**Inputs.** Bug report, error logs, stack traces. **Outputs.** `BUG DIAGNOSIS REPORT` (classification, investigation trail, root cause with file:line and confidence %, contributing factors, blast radius, suggested fix approaches with pros/cons, regression prevention).

**Frontmatter (verbatim).**
- `name: debugger`
- `description: Read-only diagnosis agent for bug investigation. Pattern matching, log analysis, root cause identification. Cannot edit code. Use when a bug needs to be investigated and diagnosed before planning a fix.`
- `model: opus` | `color: red`
- `tools: ["Read", "Grep", "Glob", "Bash"]`

**Internal workflow.** Phase 1 gather context (read report, search error message, find stack origin, `git log`/`git diff` recent history, read tests and configs) → Phase 2 pattern matching against the database, ranked by likelihood → Phase 3 log analysis and event timeline → Phase 4 root cause identification (primary cause, contributing factors, trigger, blast radius, fix complexity) → Phase 5 handoff. A bug classification decision flow covers reproducibility and onset timing (git bisect for post-change bugs, leak patterns for gradual onset).

**Dependencies.** Skills: `using-superpowers`, `golden-rule`, `systematic-debugging`; conditionally `test-driven-development`, `performance-guidelines`, `security-checklist`. Downstream: planner (≥70% confidence) or coordinator (<70%, requesting more context with theories and what would confirm/deny each).

**Memory/context.** Read-only; Edit and Write are explicitly FORBIDDEN. Bash limited to read-only commands (git log/diff, builds, tests, log viewers).

**Failure recovery.** Confidence gate at 70%: below it, hands to coordinator with `Status: INSUFFICIENT DATA`, findings so far, needed information, and ranked theories. Never guesses, never reports symptoms as root causes, never runs destructive commands.

**Example invocation.**
```bash
echo "Diagnose: app crashes with NullPointerException when processing orders. Produce a diagnosis report." | \
  claude -p --agent debugger --model sonnet --allowedTools "Read,Grep,Glob,Bash"
```

**Improvement notes.** None significant; one of the most internally consistent agents. Its report location convention (`.claude/reports/debug-<descriptor>.md`) comes from WORKFLOW_FILE_TEMPLATES.md rather than its own file.

---

