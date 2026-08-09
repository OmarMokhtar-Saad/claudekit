# AI Session Changelog

Reverse-chronological log of AI working sessions on this repository. Append an entry per significant session: date, model, scope, changes, follow-ups. (Product changes go in `CHANGELOG.md` — this file tracks the *work sessions* themselves.)

## 2026-08-09 — Claude (Sonnet 5) — Fixed AGENTS_KNOWN_ISSUES.md #9 (legacy ops.json schema in shared template)

- Executed the approved plan `plan-workflow-file-templates-ops-schema.md` / ops config
  `ops-workflow-file-templates-ops-schema.json` in worktree
  `agent/workflow-file-templates-ops-schema`, via `execute-json-ops.py` (7 operations: 1
  `file_create`, 6 `code_edit`, all succeeded, 0 errors).
- `_shared/WORKFLOW_FILE_TEMPLATES.md`'s Operations Config Template swapped from the
  legacy schema (`version`/`plan_ref`/`file`/`changes`/`type: create|modify|delete|move|rename`)
  — which `validate-config-json.py` rejects outright — to the canonical modern schema
  (`plan` + `operations`; `file_create`/`file_delete`/`code_edit`; `path`/`edits`;
  `additionalProperties: false`), with a validator-clean worked example and a rules table.
  Schema ownership pinned to `generate-operations-config` SKILL.md + `operations-schema.json`.
- New `tests/test_agent_doc_ops_examples.py`: materializes every ops-config-shaped JSON
  fence in `.claude/agents/**` + `.claude/skills/**` into a throwaway project and runs the
  real validator against it (10 tests, all pass) — regression guard so the legacy-schema
  bug class cannot silently return.
- Retired the issue: `.ai/AGENTS_KNOWN_ISSUES.md` #9 marked FIXED, `.ai/AGENTS_PROTOCOLS.md`
  warning replaced, `.ai/TECH_DEBT.md` row 1 removed, `.ai/BACKLOG.md` P1 item removed,
  `CHANGELOG.md [Unreleased] → Fixed` entry added.
- DoD gate: 779 tests pass, ruff/mypy/shellcheck clean, gen-docs/gen-registry `--check`
  green (counts unchanged: 29/42/75/19). Plan/ops artifacts could not be written to
  `.claude/plans/` (sensitive-path gate blocks direct Edit/Write there even with
  `ECC_HOOK_PROFILE=minimal`, distinct from the ops-enforcement hook) — they were kept at
  the worktree root instead, same accommodation the plan's own artifact-location note
  describes for planning-time writes.

## 2026-08-09 — Claude (Fable 5) — Worktree-per-agent + multi-account/cross-tool collaboration

- Owner /goal directive: research → plan → review → implement worktree parallelism +
  dual-Claude-account + cross-tool (Cursor) collaboration in claudekit, then apply to
  AppiumLens. Research (3 web-researcher agents, cached to `.claude/reports/research/`):
  worktree-per-agent is the 2026-converged pattern; `CLAUDE_CONFIG_DIR` is the dual-account
  mechanism; AGENTS.md standard + file-based contract is the cross-tool layer.
- Pipeline run on the repo's own conventions: `plan-worktree-multi-agent.md` rev 1 scored
  **71.3 REVISE** by opus reviewer (15 findings — isolation mechanism unverified vs
  executor cwd guard, /batch collision, registry path leak, missing input validation,
  gen-docs prose lines); rev 2 scored **93.3 APPROVED**. All 7 non-blocking suggestions
  folded into implementation.
- Landed: `worktree-manager.py` (validated slugs, git-ignored registry, atomic+locked
  writes, max 5, safe remove, base pinned to SHA at create) + 20 behavioral tests incl.
  isolation proof (execute-json-ops.py cwd-scoped inside a worktree, escape rejected);
  `/worktree` command; coordinator Worktree Isolation Protocol; gitOps Multi-Agent Merge
  Protocol; /batch reconciled (waves ≤5, workers never merge); `cross-tool-collaboration`
  skill; `docs/PARALLEL_AGENTS.md`; counts 41/75 across gated + maintainer docs;
  `.agents/` mirrors synced (.codex deferred, noted in CHANGELOG).
- AppiumLens applicability delivered: `AppiumLens/.claude/plans/plan-parallel-agents-pilot.md`
  (device/port matrix per worktree — APPIUM_PORT/SYSTEM_PORT/WDA via WORKTREE_PORT_OFFSET,
  one UDID per worktree; 3-task disjoint pilot; success criteria).
- 753 tests green; all six gates pass. Follow-ups backlogged: corpus-wide
  disable-model-invocation contradiction (~30 skills, ties into task 009), ck doctor
  manifest entry for the manager script.

## 2026-08-02 (later) — Claude (Fable 5) — Work-loss protection + fleet rollout ×3

- Incident-driven (concurrent session's git checkout wiped 5 rounds of accumulated work on
  one file in a kitted project): landed `46d437c feat(safety)` — destructive-git screening
  in CommandValidator (reset --hard/clean -f/checkout --/worktree restore/stash drop;
  benign forms allowed), `--stamp-baseline` drift gate (executor aborts pre-write on sha256
  mismatch, /implement stamps by default), post-state checkpoints + `restore-backup.py
  --post` forward recovery, concurrent-session warning in session-start (.claude/locks/).
  15 tests in test_work_loss_protection.py; 730 total green.
- Found + fixed a silent screening hole: user projects had NO command screening (validator
  rc-127 permissive path — no console script on PATH, no src/ tree). pip-installed
  claude-kit locally and added a third hook fallback `python3 -m claudekit.security`
  (commit `fix(hooks)`); verified the guard now blocks `git reset --hard` (rc 2) from
  inside AppiumLens.
- Graph-sidecar automation landed earlier today (`38e246c`): session-start graph status
  line + explore record-back. Fleet rolled out 3× today (graph, safety, hook-fallback) to
  all 16 kitted projects; settings.local.json intact each time (installer preservation
  held — no hand-restores needed).

## 2026-08-02 — Claude (Fable 5) — Project graph sidecar (Graphify-inspired)

- Researched Graphify-Labs/graphify (tree-sitter/NetworkX codebase→knowledge-graph tool)
  on owner request; vendoring ruled out (hard rule 8). Borrowed three patterns stdlib-only
  instead, landed as `2ae85c8 feat(graph)`: `.claude/operations/scripts/project-graph.py`
  (build/query/hubs/path/stale over `.claude/project-graph.json`), confidence tiers
  (extracted/inferred/ambiguous) on every edge, GOD-NODE fan-in/out ranking, sha256
  staleness detection. codebase-mapping skill gained Step 7 (emit sidecar) + stale→merge
  refresh; explore/planner/refactor-cleaner go graph-first with exit-3→grep fallback.
  34 behavioral tests in `tests/test_project_graph.py` incl. byte-identity guard on the
  skills/templates twins. All gates green (706 tests).
- Design decisions: no Skill Loading/registry coupling (agents call the script directly);
  build refuses overwrite without --force (ledger convention); god-node thresholds are
  flags, not config keys. AppiumLens exploration grounded the design (TestingDetailPanel
  3,953 LOC etc. as the target god-node class).
- Follow-up (approved plan, not yet executed): pilot `ck update` on AppiumLens + smoke
  test (hubs must surface TestingDetailPanel), then fleet fan-out — remember the
  settings.local.json clobber caveat from the 2026-07-31 rollout.

## 2026-07-31 — Claude (Fable 5) — Full fleet rollout

- On explicit owner instruction ("all projects"), rolled the kit out across the entire
  ~/IdeaProjects folder: 6 managed projects `ck update`d (AppiumLens hold lifted by
  owner) + 11 fresh installs (qa-agent-pro, ApiForge, AutomationApp, Eatizaz, SehhatyApp,
  appium-lens-public, Lean, codemanifest, CodeManifest-1/2/new; `--force` over old
  hand-copied `.claude/` fragments, backed up first). All 17 validated: doctor --strict
  22/22 each + per-project asset checks (review-record.py, new review.md/plan.md,
  scratchpad hook allowance).
- Upstreamed AppiumLens' field fix into the kit before overwriting it (`354f905`:
  ops-enforcement.sh allows session-scratchpad/OS-temp targets — false cross-project
  denials), then re-synced the 5 projects updated before the fix landed.
- Kit bug filed (BACKLOG P2): settings.local.json is manifest-managed and gets clobbered
  by `ck update`; hand-preserved in every project this rollout.
- Deleted the accidental "LeanApis ai-agent-system AppiumLens MobileUIAutomator" dir
  (unquoted-spaces artifact, owner-approved). Skipped non-projects: backups, report
  outputs, scratch dirs.

## 2026-07-31 (later) — Claude (Fable 5) — Remaining-fixes implementation

- Implemented `.claude/plans/plan-remaining-fixes-2026-07-31.md` end to end — 9 commits:
  ops-hardening landed as 4 conventional commits (post-approval 2-edit delta identified
  and recorded as prose-only; rejected finally-reset confirmed absent); approval-binding
  rebased against HEAD and executed via the ops engine itself (review-record.py, 20
  tests, delta review mode) with a same-session `fix(security)` follow-up closing 2
  background-review findings (slug sanitization, symlink-chain check); shellcheck gate
  surfaced (`ck doctor` warn + tests/test_shell_lint.py, 21 visible per-script results);
  100KB `.ai/AGENTS.md` split into 13 byte-preserving files each <10KB.
- Fleet rollout deliberately NOT executed: all 6 projects at manifest 2.1.0 but every
  tree dirty (54–535 files) — blocked on owners per the plan's own step-2 rule.
- Suite: 638 (595 → +20 review-record, +2 write-safety, +21 shell-lint). All DoD gates
  green including shellcheck for the first time.

## 2026-07-31 — Claude (Sonnet 5) — Token-waste workflow fixes

- Origin: transcript analysis of a 2026-07-30/31 session that burned 80.3M billed context
  tokens over 381 API calls, root-caused to full plan/ops.json payloads leaking into the
  main session context via `tee`, re-typed Writes, non-persisting shell variables, and
  `cat`'d heredoc interpolation. Plan: `.claude/plans/plan-token-waste-workflow-fixes.md`.
  New governing contract: subagent handoffs pass file paths, never file bodies.
- 6 commits (`51db588`..`3546f1e`): `suggest-compact.sh` fixed (was a no-op — PreToolUse
  stdout is never shown to the model, plus doubly backgrounded; now PostToolUse,
  foreground, cadence 40); `/plan` scripted+interactive paths stop leaking; `/refine`
  restructured around fixed `PLAN_FILE`/`OPS_FILE` paths instead of a shell variable that
  doesn't persist across Bash calls; the path-not-payload rule codified into
  `INVOCATION.md`/`HANDOFF_PROTOCOL.md`/`planner.md`; `/review` audited and found to have
  the identical leak (`cat`'d the whole plan into a prompt) — fixed, then a follow-up
  commit corrected an over-narrow ops-file-naming assumption in that fix (this repo
  intentionally supports both `*.ops.json` and `ops-*.json`, per `.ai/FAQ.md`).
- Added `tests/test_delivery_contract_smoke.py`: zero-LLM-cost regression test running
  `/plan`'s actual scripted bash block (extracted from the command file, not hand-copied)
  and an assembled `/refine` 2-iteration run against a stub `claude` binary emitting a
  ~40KB fake payload — asserts it lands on disk/validates but never reaches stdout. Chosen
  over a live opus smoke-test run because the property under test (does the transport leak
  bytes) is model-independent, and a background agent earlier in this same session had
  already hit the account's usage limit mid-run.
- Plan's Phase 6 (task 009 lazy skill loading) turned out to require zero work: verified
  already fully shipped in `fe7396e` (2026-07-08), three weeks before this plan's Phase 6
  was drafted (`TestContextBudget`'s three gates still pass). Corrected the plan doc
  instead of re-implementing already-shipped work.
- Suite: 593 (was 591 pre-session; +2 from the new smoke test). All local DoD gates green
  except shellcheck (still not installed locally — pre-existing, unrelated to this session).
- Follow-up not done this session: pushing these 6 commits (user-gated, not requested).

## 2026-07-08 — Claude (Fable 5) — E2E validation + gap fixes + eval framework (010)

- Ran the full pipeline headless on a fixture (plan→review→implement→verify): works,
  $1.86 total; refutation/evidence behaviors verifiably fired; verifier numbers matched
  ground truth. Found + fixed: `.claude/**` writes hard-blocked headless (stdout is now the
  explicit delivery contract; recreated ghost script extract-json-from-plan.py);
  implementer stalling on out-of-scope verification (now hands off "verification pending").
- Fixed: PostToolUseFailure hook SyntaxError (logged all failures as "unknown"); verifier
  now diff-scoped by default (--all for repo-wide).
- `/plan` `/review` `/refine` are dual-mechanism: Task tool interactive default, claude -p
  scripted. AppiumLens's 3 command overrides converge (not restored on next update).
- **Task 010 shipped:** `ck eval` + scripts/run-evals.py + evals/ (4 behavioral evals with
  planted-defect refutation test, fabrication tripwire, ground-truth match; per-eval cost
  budgets; offline framework tests in pytest). Suite: 564.

## 2026-07-08 — Claude (Fable 5) — Context budget: lazy skill loading (task 009 core)

- Measured the problem first: 16,120 preloaded skill lines across 18 agents (coordinator
  12 skills / 2,397 lines); registry agentMapping had 30 entries incl. 10 agents with NO
  skill section and 2 commands. Registry drift follow-up from the corpus session: resolved.
- Two-tier skill loading: ≤3 mandatory per agent + on-demand with per-skill triggers;
  AGENT_TEMPLATE protocol updated. Preload now 6,649 lines (−59%); worst agent 559.
- scripts/gen-registry.py regenerates agentMapping from agent files (--check gate, same
  pattern as gen-docs; added to CLAUDE.md commands). agentMapping now 18 honest entries.
- Budget gate tests (TestContextBudget): max-3 mandatory, trigger required per on-demand
  entry, registry --check green. Suite: 552. Plan:
  `.claude/plans/plan-context-budget-lazy-skills.md`.
- Follow-ups CLOSED same day: 8 commands trimmed to 3 mandatory + on-demand trigger;
  usedBy now generated from reverse agentMapping (0 "all" fictions remain, 38 skills
  honestly on-demand-only); SKILL.md splitting measured and skipped (only 3 kit skills
  >300 lines; on-demand loading made size pay-per-use). Fleet re-rolled; output-cap env
  vars (BASH_MAX_OUTPUT_LENGTH, MAX_MCP_OUTPUT_TOKENS) added to 5 projects'
  settings.local.json. AppiumLens MCP server trimming left to owner (filesystem server
  is demonstrably used; no usage evidence for sequential-thinking/greptile).

## 2026-07-08 — Claude (Fable 5) — Agent-registration root cause + fix (spawn contradiction resolved)

- Empirical test settled the Task-tool-vs-`claude -p` question: invalid YAML frontmatter
  (bare `<example>` blocks between fields) had unregistered ALL 28 agents from BOTH
  mechanisms — `claude -p --agent explore` returned "agent not found"; a clean-frontmatter
  probe agent worked (14s). Both prior claims had wrong causality.
- Fixed all 28 agents (examples moved into description block scalars; name/model/color/tools
  preserved), rewrote INVOCATION.md around the two verified mechanisms, corrected stale
  claims in refine.md/gan-build.md, added TestAgentRegistration guard (suite: 549).
- Rolled to all 6 projects via ck update; AppiumLens's 3 Task-tool command overrides restored
  (tracked as locally-modified) pending a cold-boot timing test in ITS MCP-heavy env.

## 2026-07-08 — Claude (Fable 5) — Frontier-behavior corpus upgrade

- Defined a 10-pattern operating spec (what separates frontier-model behavior from
  Opus/Sonnet under the same prompts) and audited the corpus against it with 3 parallel
  agents (shared docs + core agents / commands / skills + registry).
- Applied ~35 surgical edits across `_shared/` (4 docs), 8 agents, 12 commands, 5 skills.
  Fixed 8 contradictions incl. two unexecutable contracts (reviewer --dual self-spawn,
  planner tools vs INVOCATION). Full details: CHANGELOG.md [Unreleased] Changed.
- Model routing: planner→opus, verifier→sonnet (agent frontmatter + command spawn lines +
  .ai/AGENTS.md diagrams).
- 24 anchor tests in tests/test_behavior_spec.py (suite: 547). Plan:
  `.claude/plans/plan-fable-behavior-corpus.md`.
- **Follow-up surfaced, NOT done:** registry `agentMapping`/`usedBy` no longer matches the
  agent .md load lists (implementer 5 vs 15, coordinator 12 vs 16, `usedBy:["all"]` honored
  nowhere) — needs a single source of truth + drift gate; blocks task 009's budget math.

## 2026-07-08 — Claude (Fable 5) — Fleet audit + legacy-install lifecycle

- **Fleet audit:** surveyed all 12 `.claude`-bearing projects in ~/IdeaProjects against the kit
  (4 parallel review agents). Verdicts: the 13 "extra" commands + `i18n-workflow` in
  LeanApis/ai-agent-system are byte-identical round-trips of `templates/commands|skills/`
  (nothing to upstream; per-asset keep/delete calls recorded for task 008); zero graft-worthy
  edits in any project (all version lag); AppiumLens/MobileUIAutomator ran pre-Phase-1 kit
  generations, and the 3 near-current projects were running commands with
  `--dangerously-skip-permissions` (the exact Phase-1 regression) — now fixed by resync.
- **Product change (plan: `.claude/plans/plan-legacy-install-lifecycle.md`):** legacy
  (pre-manifest) installs are now first-class: `ck diff` falls back to kit-source comparison
  (identical/differs/custom/not-installed) and refines manifest diffs into locally-modified /
  kit-updated / both-changed + custom listing; `ck update` works on pre-manifest installs;
  install.sh preserves project-custom agents/commands/skills across reinstalls (old-manifest
  precise mode; asset-dir heuristic for legacy). 7 new behavioral tests (523 total); ruff clean
  across tests/ (was CI-exempt); docs/cli.md + CHANGELOG updated.
- **Fleet resync (via the new `ck update`):** qaforge-ai, LeanApis, ai-agent-system,
  MobileUIAutomator, qa-agents → v2.1.0 manifest-tracked, diff-clean; customs preserved
  (qa-agents' 3 QA agents + 4 commands; MobileUIAutomator's 9 project skills). AppiumLens
  deliberately NOT auto-updated (real customization + open spawn-mechanism question).
- Open decisions surfaced to owner: QA-pack (3 generic QA agents from qa-agents), AppiumLens
  selective sync, Task-tool vs `claude -p` spawn contradiction, `<example>`-in-frontmatter
  YAML validity audit.

## 2026-07-08 — Claude (Fable 5) — /adapt self-adaptation capability

- Added `/adapt` command (`.claude/commands/adapt.md`) and `project-adaptation` skill (`.claude/skills/project-adaptation/SKILL.md`): ClaudeKit now teaches an AI, when the kit is added to **any** project in **any** language, what to change (config.json commands, CLAUDE.md, CONSTITUTION.md, hook profile, .agentignore), how to verify it works (hook block test, four commands, ops round-trip, doctor), and how to keep enhancing the fit (/hookify, /learn, decision recording).
- Registered in skills-registry.json (`usedBy: coordinator, explore`); counts now 40 commands / 74 skills — regenerated via gen-docs; README + docs/ARCHITECTURE + .ai/ counts updated; CHANGELOG `[Unreleased]` Added entry.

## 2026-07-08 — Claude (Fable 5) — AI handover & knowledge-transfer session

- Created the `.ai/` AI operating system: 36 documents covering onboarding, architecture, catalogs (agents/commands/skills/hooks/prompts), knowledge (decisions/knowledge-base/memory/domain/glossary), process guides (development/review/testing/security/performance/debugging/troubleshooting), planning (status/session-state/roadmap/backlog/tech-debt), and meta (playbook/checklists/faq/migration/dependencies/knowledge-graph).
- Created root `CLAUDE.md` (repo previously had none — only user-project templates).
- Sources: full-repository analysis; `review/` audit (2026-07-05); `.claude/plans/phase-1-HANDOFF.md`; git history through `0c9223b`. `.ai/AGENTS.md` (the deep per-agent reference incl. 16 cataloged prompt-layer inconsistencies) was produced by a subagent that read every agent file.
- **No product code, prompts, hooks, or tests modified.** Docs-only session.
- Follow-ups: P1 items in [BACKLOG.md](BACKLOG.md) (WORKFLOW_FILE_TEMPLATES legacy schema fix first); release remains user-gated.

## 2026-07-05/06 — Claude (Opus 4.8, 1M context) — Phase 1 "Fix What's Broken"

- Executed audit tasks 001–006 + 011 in four waves (A–D) on `phase-1-fix-whats-broken`; 14 commits; merged via PR #1.
- Packaging fixed (installable wheel, src-layout, version single-sourcing, bundled assets) · hooks made real (exit 2/stderr/fail-closed, lib.sh, telemetry via stdin JSON) · security layer wired (validator hardening, command-guard, CLI) · skip-permissions eradicated · installer made safe (staging/backup/atomic swap, manifest, settings.json installed) · versions/docs reconciled (renumbering, gen-docs + docs-drift CI, canonical slug) · CI made honest (11 jobs, 2-OS matrix).
- Record: `.claude/plans/phase-1-HANDOFF.md`. Post-merge fix `0c9223b` (py3.12+ setuptools).

## Earlier — v1.0.0 → v2.0.0 (2026-03-16/17)

Original corpus build-out (agents/commands/skills/hooks/templates/modes/MCP/i18n) — see CHANGELOG.md. Delivery-shell defects from this era were the subject of the 2026-07-05 audit (`review/FINAL-REPORT.md`, 49/100).
