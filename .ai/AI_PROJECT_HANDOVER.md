# AI Project Handover

**From:** Claude (Opus 4.8 executed Phase 1; Fable 5 wrote this handover) · **Date:** 2026-07-08 · **To:** any future AI model or human maintainer.

This is the narrative companion to [STATUS.md](STATUS.md) (snapshot) and [SESSION_STATE.md](SESSION_STATE.md) (resume point). If you read only one handover file, read this one, then follow its links.

## What you are inheriting

A conceptually excellent, recently-repaired system. The 2026-07-05 external audit (`review/FINAL-REPORT.md`) called it "conceptually top-decile, executionally bottom-decile" (49/100) — the ideas (ops.json transaction engine, scored review gates, anti-anchoring dual review, file-based handoffs) were sound, but packaging never installed, hooks never blocked, security was dead code, and versioning was incoherent. Phase 1 (tasks 001–006 + 011) fixed all of that in 14 commits merged 2026-07-06. Today: the wheel builds and self-checks, hooks demonstrably block, the security layer runs, CI is honest, 516 tests pass.

## The three documents that were my "plan of record"

1. `review/roadmap.md` — v2.1 → v3.0 → 24-month vision. Still the strategic plan.
2. `review/tasks/001–014` — file-level task specs. 001–006, 011 done; **007–010, 012–014 open**.
3. `.claude/plans/phase-1-HANDOFF.md` — the detailed Phase-1 record (waves A–D, gotchas, commit map). Historically accurate; superseded for "what next" by this folder.

## What is deliberately NOT done

- **No release tag / PyPI publish.** Mechanics fully wired (`release.yml`, Trusted Publishing, PyPI name `claude-kit`). Waiting on the owner. Don't publish unilaterally.
- **No consolidation deletions** (task 008) — merging 10 agents / 13 skills changes user-visible surface; needs sign-off.
- **The 90/100 and 80/100 gates are still prompt-enforced only.** Task 010 (eval framework + machine-parseable verdicts + hook gating) makes them mechanical. Until then, don't advertise them as hard guarantees.

## Where the bodies are buried

- **The prompt corpus has 16 cataloged internal inconsistencies** — see [AGENTS.md](AGENTS.md#known-issues). The worst is `_shared/WORKFLOW_FILE_TEMPLATES.md` shipping the *legacy* ops.json schema that the validator rejects (issue #9). Fix that one before it causes a field failure.
- **`hooks/config.json`** looks deprecated but its `project.*` command section feeds 6+ hooks. Don't delete it.
- **Version fallbacks** in `src/claudekit/__init__.py` and `.claude/operations/scripts/shared.py` must bump with pyproject; tests catch it, but only if you run them.
- **macOS/bash-3.2 compatibility** is where shell regressions hide; CI has a macOS matrix, trust it.
- **`ck update`** is backup-then-overwrite with warnings, not a true three-way merge. Users with heavy local edits will grumble; roadmap §2.2 has the design.
- The old `omarmokhtar/claudekit` slug and `--dangerously-skip-permissions` are both extinct and CI-gated; treat any reappearance as a regression.

## Working style expectations (learned the hard way)

Evidence before claims (run the command, paste the output); behavioral tests over existence tests; never hand-edit counts (gen-docs); conventional commits with AI co-author line; fix root causes, not symptoms; when a prompt and a validator disagree, the validator wins and the prompt gets fixed; honest framing in security docs ("speed bump, not a sandbox") is a project value — do not market-speak it away.

## Handover completeness map

Everything an outside model needs is in this folder: orientation ([MODEL_ONBOARDING.md](MODEL_ONBOARDING.md), [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md), [CONTEXT.md](CONTEXT.md)), architecture ([ARCHITECTURE.md](ARCHITECTURE.md), [KNOWLEDGE_GRAPH.md](KNOWLEDGE_GRAPH.md)), catalogs ([AGENTS.md](AGENTS.md), [COMMANDS.md](COMMANDS.md), [SKILLS.md](SKILLS.md), [HOOKS.md](HOOKS.md), [PROMPTS.md](PROMPTS.md)), knowledge ([KNOWLEDGE_BASE.md](KNOWLEDGE_BASE.md), [DECISIONS.md](DECISIONS.md), [MEMORY.md](MEMORY.md), [DOMAIN.md](DOMAIN.md), [GLOSSARY.md](GLOSSARY.md)), process ([WORKFLOW.md](WORKFLOW.md), [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md), [REVIEW_GUIDE.md](REVIEW_GUIDE.md), [TESTING_GUIDE.md](TESTING_GUIDE.md), [SECURITY_GUIDE.md](SECURITY_GUIDE.md), [PLAYBOOK.md](PLAYBOOK.md), [CHECKLISTS.md](CHECKLISTS.md)), and planning ([ROADMAP.md](ROADMAP.md), [BACKLOG.md](BACKLOG.md), [TECH_DEBT.md](TECH_DEBT.md), [STATUS.md](STATUS.md), [SESSION_STATE.md](SESSION_STATE.md)).

When you hand over next, follow [MODEL_ONBOARDING.md](MODEL_ONBOARDING.md) §9.
