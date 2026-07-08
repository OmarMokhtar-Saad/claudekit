# CLAUDE.md — Working on ClaudeKit Itself

You are working **on** ClaudeKit (the multi-agent orchestration kit for Claude Code), not *with* it in a user project. Full maintainer knowledge lives in [`.ai/`](.ai/README.md) — start with [.ai/MODEL_ONBOARDING.md](.ai/MODEL_ONBOARDING.md) if this is your first session. User-project templates (`.claude/local/CLAUDE.template.md`, `templates/*/CLAUDE.md`) are **product artifacts**, not instructions for you.

## What this repo is

Prompt corpus (28 agents · 40 commands · 74 skills in `.claude/`) + enforcement layer (19 hooks, `src/claudekit/security/`) + operations engine (`.claude/operations/scripts/`) + delivery shell (`src/claudekit/cli/`, `install.sh`, CI). Version 2.1.0 (unreleased tag); PyPI name `claude-kit`; CLI `claudekit`/`ck`; zero runtime dependencies.

## Session setup gotcha (read first)

This repo runs its own enforcement hooks on itself. If Edit/Write gets blocked by `ops-enforcement`, the gitignored `.claude/settings.local.json` with `ECC_HOOK_PROFILE=minimal` is missing — restore it (see CONTRIBUTING.md "Working on ClaudeKit itself"). Never bypass hooks by other means.

## Commands

```bash
python3 -m pytest tests/ -q               # full suite — 516 tests, all must pass
ruff check src/ tests/ scripts/           # lint (line-length 100)
mypy                                      # types (py3.9 target)
python3 scripts/gen-docs.py --check       # docs-drift gate (counts)
shellcheck install.sh .claude/hooks/*.sh  # shell lint
ck doctor --strict                        # installed-tree health
```

## How to work

- **Think:** read before writing; the `review/tasks/0XX-*.md` specs and `.ai/` docs likely already analyze your problem. Filesystem over documentation when they disagree.
- **Plan:** for multi-file changes, write the plan down (this repo's own `/plan` convention: `.claude/plans/plan-<slug>.md`). Get owner sign-off for anything user-visible (deletions, renames, releases).
- **Write code:** minimal diffs; root causes, not symptoms; Python stdlib-only in `src/` and ops scripts; bash 3.2/macOS-safe shell; no new near-duplicate assets — we are consolidating (task 008).
- **Test:** behavioral over structural — run the hook/installer/wheel and assert outcomes; regression test for every bug fix; force `ECC_HOOK_PROFILE` explicitly in tests.
- **Review:** findings need file:line + severity + suggested fix; per-asset checklists in [.ai/REVIEW_GUIDE.md](.ai/REVIEW_GUIDE.md); verify claims by executing, never by trusting prose.
- **Refactor:** preserve behavior, prove it with the suite; risk-ordered batches; update every reference (registry, coordinator routing, QUICK_START, INVOCATION, docs) when renaming assets.
- **Debug:** `.claude/hooks/hooks.log` → `ck doctor --strict` → the matching test file; recipes in [.ai/DEBUGGING_GUIDE.md](.ai/DEBUGGING_GUIDE.md).
- **Docs:** counts only via gen-docs; CHANGELOG `[Unreleased]` for user-visible changes; audience split is strict (docs/ = users, .ai/ = maintainers); update [.ai/SESSION_STATE.md](.ai/SESSION_STATE.md) + [.ai/CHANGELOG_AI.md](.ai/CHANGELOG_AI.md) before ending a work period.
- **Commit:** conventional commits (`type(scope): subject`), one concern per commit, `Co-Authored-By:` line for AI work. Only commit when the DoD gate passes.
- **Communicate:** concise, evidence-first; paste command output for claims; surface open decisions instead of deciding them (releases, deletions, plugin bet are owner-gated).

## Hard rules (never violate — reasoning in .ai/KNOWLEDGE_BASE.md)

1. Iron Law: implementation flows through ops.json + the operations engine; the implementer agent never gets Edit/Write.
2. Blocking hooks: `exit 2` + stderr + fail closed. Never exit 1/stdout for a block.
3. No `--dangerously-skip-permissions` anywhere (CI-gated); agent spawning per `.claude/agents/_shared/INVOCATION.md` with scoped `--allowedTools`.
4. Protected files stay protected; MAX_DELETIONS=3/plan stays.
5. Golden Rule: no code changes without explicit user approval.
6. Security framing stays honest: "denylist speed bump, not a sandbox."
7. Versions bump in three places together (pyproject, `src/claudekit/__init__.py`, `.claude/operations/scripts/shared.py`) and stay monotonic.
8. Never hand-edit component counts; never add Python runtime dependencies; never break bash-3.2/macOS.

## Definition of Done

All six commands above pass · behavioral test coverage for the change · CHANGELOG + docs updated · conventional commit · evidence recorded. Full checklists: [.ai/CHECKLISTS.md](.ai/CHECKLISTS.md).

## Quality gates (the product's own)

Plan review ≥90/100 (Plan 40 / Architecture 30 / Security 30; missing ops.json = AUTO-REJECT) · verification ≥80/100 (Static 30 / Tests 40 / Coverage 30) · security-module coverage ≥85% (CI). These gates are currently prompt-enforced; task 010 makes them mechanical — don't overstate them in docs until then.

## Current state & priorities

Phase 1 ("Fix What's Broken") merged 2026-07-06; release tag + PyPI publish are **user-gated**. Next: consolidation (008), eval framework (010), context budget (009). Live snapshot: [.ai/STATUS.md](.ai/STATUS.md) · resume point: [.ai/SESSION_STATE.md](.ai/SESSION_STATE.md) · work queue: [.ai/BACKLOG.md](.ai/BACKLOG.md).
