# AI Session Changelog

Reverse-chronological log of AI working sessions on this repository. Append an entry per significant session: date, model, scope, changes, follow-ups. (Product changes go in `CHANGELOG.md` — this file tracks the *work sessions* themselves.)

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
- Remaining 009 follow-ups (recorded in plan, not done): split large SKILL.md bodies into
  core + references/; command-file Mandatory Skills trimming (8 commands at 4); usedBy
  field semantics.

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
