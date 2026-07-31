# Session State

> Update this file at the end of every significant AI working session. It is the resume point.

**Last updated:** 2026-07-31 · **By:** Claude (Sonnet 5) — token-waste workflow fixes session

## Current project state

- v2.1.0 complete on `main`; **593 tests passing**; all local gates green (pytest/ruff/mypy/gen-docs/gen-registry; shellcheck not installed locally, unchanged pre-existing gap).
- Release to PyPI **pending user decision** (tag push triggers release.yml / Trusted Publishing).
- The 2026-07-05 audit (`review/`) is the work queue: tasks 001–006+009+011 done; 007, 008, 010, 012–014 open.
- 6 commits landed on `main` this session, **not pushed** (see below).

## Recent changes (this session)

- Token-waste workflow fixes (plan: `.claude/plans/plan-token-waste-workflow-fixes.md`,
  origin: transcript analysis of a 2026-07-30/31 session that burned 80.3M billed context
  tokens over 381 API calls). New governing contract: subagent handoffs pass file paths,
  never file bodies. Implemented phases 5, 1+2, 3, 4 (phase 6 turned out already shipped,
  see below) — 6 commits, `51db588`..`3546f1e`:
  - `/plan`, `/refine`, `/review` no longer leak full plan/ops.json payloads into the main
    session context via `tee`, re-typed Writes, non-persisting shell variables, or `cat`'d
    heredoc interpolation — the exact leaks that produced the 80.3M-token burn.
  - `suggest-compact.sh` was a complete no-op (registered on PreToolUse, whose stdout the
    model never sees, plus doubly backgrounded) — fixed to PostToolUse, foreground, cadence
    40 calls.
  - The path-not-payload rule is now written into `INVOCATION.md`/`HANDOFF_PROTOCOL.md`/
    `planner.md` so future commands/agents don't regress it.
  - Found and fixed a real pre-existing bug along the way: `/review`'s ops-file lookup only
    checked one of this repo's two valid naming conventions (`*.ops.json` vs `ops-*.json`).
  - Added `tests/test_delivery_contract_smoke.py`: a permanent, zero-LLM-cost regression
    test that runs `/plan`'s actual scripted bash block (and an assembled `/refine`
    2-iteration run) against a stub `claude` binary emitting a ~40KB fake payload, proving
    it lands on disk/validates but never reaches stdout.
  - **Phase 6 (task 009 lazy skill loading) required no work** — verified already fully
    shipped in `fe7396e` (2026-07-08), three weeks before this plan's Phase 6 was drafted.
    `TestContextBudget`'s three gates all still pass. Corrected the plan doc rather than
    re-doing already-done work.
- A background agent spawned earlier in this session for phases 1–3 hit the account's
  session usage limit mid-run and had to be resumed manually from its partial/uncommitted
  state — worth knowing if you see an orphaned background-agent task in this session's history.

## Important files for orientation

`.claude/plans/phase-1-HANDOFF.md` (the previous handoff, still accurate for Phase-1 detail) · `review/FINAL-REPORT.md` + `review/roadmap.md` (audit + plan of record) · `.claude/settings.json` (enforcement truth) · `scripts/gen-docs.py` (count gate) · `src/claudekit/cli/main.py` (CLI) · `.claude/hooks/lib.sh` (hook helpers).

## Pending work (priority order)

1. **User-gated:** tag `v2.1.0`, publish to PyPI, announce. Recipe: [PLAYBOOK.md](PLAYBOOK.md) §Release.
2. Task 008 — corpus consolidation (merge candidates listed in [BACKLOG.md](BACKLOG.md); get owner sign-off first).
3. Task 010 — eval framework (`evals/` fixtures + `ck eval`).
4. Tasks 012/013/014 — behavioral tests, OSS health files, supply-chain signing.
5. Task 009 follow-ups (recorded as out-of-scope in `plan-context-budget-lazy-skills.md`,
   the core work is DONE): splitting large SKILL.md bodies into core + references/,
   `usedBy` field semantics cleanup, command-file mandatory-skill trimming.

## Blocked / waiting

- PyPI publish → owner go-ahead.
- Plugin packaging (007) and consolidation deletions (008) → owner sign-off (user-visible surface changes).
- QA-pack decision → owner: qa-agents contributed 3 generic manual-QA agents (bug-reporter,
  exploratory-coach, test-scenario) worth a domain pack, not core (see CHANGELOG_AI 2026-07-08).
- AppiumLens sync → owner: selective strategy required (real project customization in ~26 kit
  files + 15 project skills); blind `ck update` would work but degrade its local fixes.
- ~~Spawn-mechanism contradiction~~ **RESOLVED 2026-07-08 by experiment**: both claims had
  wrong causality — invalid frontmatter had unregistered all agents from BOTH mechanisms.
  Fixed kit-wide; INVOCATION.md documents the tested reality (Task tool in-session,
  `claude -p` headless, ~13s cold boot measured).
- ~~`<example>`-blocks-inside-YAML-frontmatter~~ **FIXED 2026-07-08**: all 28 agents
  rewritten to description block scalars; structural regression test in
  tests/test_behavior_spec.py::TestAgentRegistration.
- ~~Registry reconciliation~~ **RESOLVED 2026-07-08 by task 009 (`fe7396e`)**: agent .md
  files are now the single source of truth; `scripts/gen-registry.py --check` gates drift.

## Known risks

- First real release.yml run is untested end-to-end (Trusted Publishing config could need iteration).
- `ck update` three-way behavior is warn-and-overwrite-with-backup, not a true merge — user data loss is guarded but UX is rough (roadmap §2.2).
- Docs drift risk is CI-gated for counts only; prose claims can still rot — sweep during release prep.

## Suggested first task for a fresh session

Run the DoD gate (see [MODEL_ONBOARDING.md](MODEL_ONBOARDING.md) §5) to confirm the tree is green, then pick up the top unblocked pending item.
