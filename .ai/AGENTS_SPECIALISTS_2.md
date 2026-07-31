# Specialist Agents: database-architect, tdd-guide, refactor-cleaner

<!-- split-from-AGENTS.md -->
> Part of the agent reference. Index: [AGENTS.md](AGENTS.md)

## database-architect

**Purpose.** Database design and migration safety: schema design (normalization, data types, multi-tenancy patterns), expand-contract zero-downtime migrations, query optimization (EXPLAIN ANALYZE, index strategy, N+1 elimination), data modeling patterns (soft delete, audit trail, event sourcing).

**Inputs.** Schema requirements, slow queries, migration needs. **Outputs.** Schema designs, migration plans with rollback (per its migration file template: forward, rollback, estimated impact, pre/post-conditions), query optimizations with before/after; handoffs to planner and security-scanner.

**Frontmatter (verbatim).**
- `name: database-architect`
- `description: Database design and migration specialist. Handles schema design, migration planning, query optimization, and data modeling. Use when database schema changes, migrations, or query performance issues need attention.`
- `model: sonnet` | `color: amber`
- `tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]`

**Internal workflow.** Pre-flight (engine and version, ORM, migration conventions, table sizes, golden-rule approval) → apply design principles (1NF/2NF/3NF table, type selection rules, multi-tenancy pattern selection with hard rules for shared-schema tenancy) → expand/migrate/contract migration phases → migration checklist (rollback exists, no direct renames, no NOT NULL without default, CONCURRENTLY indexes, batched backfills, staging-tested) → query optimization investigation process.

**Dependencies.** Skills: `using-superpowers`, `golden-rule`, `database-migration-patterns`, `performance-guidelines`; conditionally `api-design-patterns`, `security-checklist`, `clean-architecture`. Handoff targets: planner, security-scanner.

**Memory/context.** None documented beyond project files.

**Failure recovery.** None specified; relies on its NEVER list (no in-place renames/type changes in prod, no unbatched million-row backfills, no FLOAT for money, no skipped rollbacks, etc.).

**Example invocation.**
```bash
echo "Design the schema for the multi-tenant billing system, with migration plan and rollback." | \
  claude -p --agent database-architect --model sonnet --allowedTools "Read,Write,Edit,Bash,Grep,Glob"
```

**Improvement notes.** Missing from coordinator classification rows (present only in its Handoff Table). No output/report format section, unlike most peers.

---

## tdd-guide

**Purpose.** Enforces test-first development: "Never write implementation code before the failing test exists." Drives RED → GREEN → REFACTOR with hard coverage gates.

**Responsibilities.** Writing failing tests first and verifying they fail, minimal implementation to green, refactoring under green tests, enforcing the 8 mandatory edge-case categories, and 80% coverage on statements/branches/functions/lines.

**Inputs.** Feature/bugfix request. **Outputs.** Tests plus implementation, `TDD Session Report` (test counts by type, coverage delta, edge-case checklist, RED→GREEN→REFACTOR status, full-suite result).

**Frontmatter (verbatim).**
- `name: tdd-guide`
- `description: Test-driven development specialist. Enforces write-tests-first methodology. Use when implementing new features, fixing bugs, or refactoring — ensures 80%+ coverage with RED/GREEN/REFACTOR discipline.`
- `model: sonnet` | `color: orange`
- `tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]`

**Internal workflow.** RED (write failing test, run, verify proper failure — a test that passes immediately is wrong) → GREEN (minimum code to pass, rerun) → REFACTOR (dedupe, rename, extract; full suite must stay green; commit). Requires unit + integration tests always, E2E for critical paths. Includes an "Eval-Driven TDD" extension for agent features (baseline eval, pass@1/pass@3 rates, pass^3 stability for release-critical paths via the `eval-harness` skill).

**Dependencies.** Skill referenced: `eval-harness`. Pipeline: Coordinator → TDDGuide → Verifier → GitOps (coordinator.md); HANDOFF_PROTOCOL.md additionally defines a TDDGuide→Implementer handoff (`Status: TESTS WRITTEN — RED PHASE COMPLETE`, constraint: do NOT modify test files).

**Memory/context.** None documented.

**Failure recovery.** REFACTOR failures → revert and refactor more carefully. Coverage below 80% → implementation is not complete, add tests. No escalation format defined.

**Example invocation.**
```
TaskCreate:
  prompt: |
    You are the tdd-guide agent.
    Read your agent definition: .claude/agents/tdd-guide.md
    HANDOFF FROM: coordinator
    ---
    Task: Add user authentication using strict TDD
    Expected Output: failing tests first, then minimal implementation, 80%+ coverage
    Return To: verifier
  agent: tdd-guide
```

**Improvement notes.** No Mandatory Skill Loading section. The two docs disagree on its pipeline shape: coordinator's TDD pipeline has no Implementer, but HANDOFF_PROTOCOL.md defines a TDDGuide→Implementer handoff and the coordinator's own hard rule says "TDD Guide MUST produce tests before Implementer writes code." Overlaps tester (both write tests) — differentiator is ordering discipline, and tdd-guide also writes implementation, which tester never does.

---

## refactor-cleaner

**Purpose.** Dead code cleanup and consolidation: detects unused files/exports/dependencies/duplicates with tools (knip, depcheck, ts-prune, eslint unused-directives, autoflake, vulture), verifies, and removes them in risk-ordered batches.

**Inputs.** A codebase with suspected dead code. **Outputs.** Removed code in committed batches, `Refactor Cleaner Report` (removed counts, skipped RISKY items with reasons, test results before/after, bundle size delta, commits created).

**Frontmatter (verbatim).**
- `name: refactor-cleaner`
- `description: Dead code cleanup and consolidation specialist. Finds unused files, exports, dependencies, and duplicates using analysis tools, then safely removes them batch by batch. Use when codebase has accumulated dead code.`
- `model: sonnet` | `color: teal`
- `tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]`

**Internal workflow.** Phase 1 detection (all tools in parallel) → Phase 2 risk classification (SAFE = remove directly; CAREFUL = grep-verify dynamic imports first; RISKY = public API, skip unless explicitly confirmed) → Phase 3 verification per item (full-text grep including string-interpolated names, test references, `git log -S`, package.json exports/main) → Phase 4 batch removal (Batch 1 unused deps → Batch 2 unused exports → Batch 3 unused files → Batch 4 duplicate consolidation), running tests and committing after each batch.

**Dependencies.** External tools: knip, depcheck, ts-prune, eslint, autoflake, vulture. Pipeline: Coordinator → RefactorCleaner → Verifier → GitOps. HANDOFF_PROTOCOL.md defines RefactorCleaner→Verifier (`Tests Must Pass: Yes — any failures mean rollback this batch`).

**Memory/context.** None beyond git history.

**Failure recovery.** Test failure after a batch → rollback that batch (per its handoff contract). "When NOT to use" table: active feature development, pre-deployment, no test coverage, unfamiliar code, public npm packages without version bump.

**Example invocation.**
```bash
echo "Clean up dead code from the auth refactor. Classify SAFE/CAREFUL/RISKY and remove in batches." | \
  claude -p --agent refactor-cleaner --model sonnet --allowedTools "Read,Write,Edit,Bash,Grep,Glob"
```

**Improvement notes.** Its Phase 4 runs `git commit` after every batch, directly conflicting with the system-wide convention that only GitOps commits (stated in implementer.md, build-error-resolver.md, documenter.md, opensource-packager.md) and with its own pipeline routing through GitOps afterwards. No skill-loading section.

---

