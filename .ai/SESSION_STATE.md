# Session State

> Update this file at the end of every significant AI working session. It is the resume point.

**Last updated:** 2026-08-09 (end of session) · **By:** Claude (Fable 5) — worktree-per-agent
parallelism + multi-account/cross-tool collaboration landed (plan reviewed 93.3/100 by opus
reviewer; `worktree-manager.py` + 20 behavioral tests incl. isolation proof; coordinator/
gitOps/batch protocols; `cross-tool-collaboration` skill; `docs/PARALLEL_AGENTS.md`; counts
41 commands / 75 skills). **753 tests passing, all six gates green.** AppiumLens pilot recipe
written to `AppiumLens/.claude/plans/plan-parallel-agents-pilot.md` — pilot NOT yet run.
Resume point: (1) run the AppiumLens pilot (2 worktrees + device/port matrix), (2) fleet sync
to distribute the new assets, (3) backlog: corpus-wide disable-model-invocation contradiction
(ties into task 009). Fleet is otherwise synced per 2026-08-02.
Note: claude-kit is pip-installed on this machine (hooks use the module fallback);
`ck` console script is at ~/Library/Python/3.9/bin (not on PATH yet).

## Current project state

- v2.1.0 complete on `main`; **638 tests passing**; ALL local gates green including
  shellcheck (now installed + surfaced via `ck doctor` warn and `tests/test_shell_lint.py`).
- Release to PyPI **pending user decision** (tag push triggers release.yml / Trusted Publishing).
- The 2026-07-05 audit (`review/`) is the work queue: tasks 001–006+009+011 done; 007, 008, 010, 012–014 open.
- **~20 commits on `main` ahead of origin, not pushed** — spans the token-waste transport
  fixes, the ops-hardening engine work, approval-binding, and the maintainer-docs split.
- **Working tree is CLEAN** for the first time in three sessions — the long-uncommitted
  ops-hardening change is landed (4 conventional commits, provenance of its 2 post-approval
  edits recorded in the `docs(agents)` commit message).

## Recent changes (remaining-fixes session, 2026-07-31 later)

Implemented `.claude/plans/plan-remaining-fixes-2026-07-31.md` end to end:
- **Item 1** — ops-hardening committed as 4 commits (`fix(ops)`, `docs(agents)`,
  `docs(architecture)`, `docs(plans)`). §1.1 evidence check ran first: archived config has
  74 code_edits vs 72 scored; the 2 extra are prose-only implement.md contract fixes,
  noted in the commit; the rejected `finally`-reset is confirmed absent.
- **Item 2** — approval-binding rebased and landed (`feat(review)`): `review-record.py`
  binds verdicts to sha256(ops.json); `/implement` gates on APPROVED>=90 via
  resolve+check; delta review mode with size ceiling; 20 behavioral tests. Executed via
  the ops engine itself (9/9 RESULT-JSON success); spent config archived. Follow-up
  `fix(security)` closed 2 findings from the background security review (slug
  sanitization, symlink-chain check) + 2 regression tests.
- **Item 3** — `feat(doctor)`: shellcheck availability surfaced (warn + 21 visible
  per-script test PASS/SKIPs). Zero shellcheck findings at introduction.
- **Item 5** — `docs(maintainer)`: 100KB `.ai/AGENTS.md` split into an index + 12 files,
  all <10KB, byte-preserving (reconstruction diff empty); Known-Issues references updated
  repo-wide; suggest-compact proxy decision recorded; 2 new P3 backlog lines.
- **Item 4 (fleet) — EXECUTED later this session on explicit owner instruction**
  ("all projects"): all 6 managed projects updated via `ck update` (AppiumLens included —
  owner lifted the hold) and the kit freshly installed into 11 more git projects
  (qa-agent-pro, ApiForge, AutomationApp, Eatizaz, SehhatyApp, appium-lens-public, Lean,
  codemanifest, CodeManifest-1/2/new; `--force` where an old hand-copied `.claude/`
  existed, backed up first). All 17 validated: `ck doctor --strict` 22/22 each, plus a
  per-project check that review-record.py, the new review.md/plan.md, and the
  ops-enforcement scratchpad allowance actually landed. Every project's
  `settings.local.json` was preserved across update by hand (see kit bug below).
  AppiumLens' field fix (scratchpad/temp-dir allowance in ops-enforcement.sh) was
  upstreamed as `354f905` BEFORE overwriting it, then re-synced to the 5 projects updated
  earlier. Non-projects skipped: AppiumLens_backup, "AutomationApp copy", OpenReport,
  SehhatyAppAndroidStudio, allure-report, private, test; the accidental
  "LeanApis ai-agent-system AppiumLens MobileUIAutomator" dir (unquoted-spaces artifact)
  deleted on owner approval.
- **Kit bug found during rollout:** `settings.local.json` is manifest-managed, so
  `ck update` clobbers per-project permission allowlists/MCP config with the kit's copy —
  contradicts its own ".gitignore: never shipped" framing. Worked around manually; filed
  in BACKLOG P2.

## Previous session (same day, earlier)

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
