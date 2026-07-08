# AI Session Changelog

Reverse-chronological log of AI working sessions on this repository. Append an entry per significant session: date, model, scope, changes, follow-ups. (Product changes go in `CHANGELOG.md` — this file tracks the *work sessions* themselves.)

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
