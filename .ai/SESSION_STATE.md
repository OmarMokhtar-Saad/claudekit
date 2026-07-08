# Session State

> Update this file at the end of every significant AI working session. It is the resume point.

**Last updated:** 2026-07-08 · **By:** Claude (Fable 5) — fleet audit + legacy-install lifecycle session

## Current project state

- v2.1.0 complete on `main`; **523 tests passing**; all local gates green (pytest/ruff/mypy/gen-docs/bash -n; shellcheck not installed locally).
- Release to PyPI **pending user decision** (tag push triggers release.yml / Trusted Publishing).
- The 2026-07-05 audit (`review/`) is the work queue: tasks 001–006+011 done; 007–010, 012–014 open.
- **Uncommitted work on `main` from two sessions** (this one + /adapt + .ai/ docs) — needs conventional commits; see CHANGELOG_AI.md 2026-07-08 entries for the split.

## Recent changes (this session)

- Legacy-install lifecycle (plan: `.claude/plans/plan-legacy-install-lifecycle.md`): `ck diff`
  source-fallback + three-way classification + custom listing; `ck update` on pre-manifest
  installs; install.sh custom-asset preservation. +7 behavioral tests; docs/cli.md; CHANGELOG.
- Fleet resync: qaforge-ai, LeanApis, ai-agent-system, MobileUIAutomator, qa-agents updated to
  v2.1.0 manifest-tracked and diff-clean (this killed live `--dangerously-skip-permissions`
  usage in 3 projects). AppiumLens intentionally left (selective sync pending owner decision).
- Fleet audit findings recorded in CHANGELOG_AI.md: nothing upstreamable (all round-trips of
  kit templates); per-template keep/delete verdicts feed task 008.
- Earlier same day: `/adapt` command + `project-adaptation` skill; `.ai/` operating system; root CLAUDE.md.

## Important files for orientation

`.claude/plans/phase-1-HANDOFF.md` (the previous handoff, still accurate for Phase-1 detail) · `review/FINAL-REPORT.md` + `review/roadmap.md` (audit + plan of record) · `.claude/settings.json` (enforcement truth) · `scripts/gen-docs.py` (count gate) · `src/claudekit/cli/main.py` (CLI) · `.claude/hooks/lib.sh` (hook helpers).

## Pending work (priority order)

1. **User-gated:** tag `v2.1.0`, publish to PyPI, announce. Recipe: [PLAYBOOK.md](PLAYBOOK.md) §Release.
2. Task 008 — corpus consolidation (merge candidates listed in [BACKLOG.md](BACKLOG.md); get owner sign-off first).
3. Task 010 — eval framework (`evals/` fixtures + `ck eval`).
4. Task 009 — context-budget reduction (hook dispatcher consolidation, ≤2 mandatory skills/agent).
5. Tasks 012/013/014 — behavioral tests, OSS health files, supply-chain signing.

## Blocked / waiting

- PyPI publish → owner go-ahead.
- Plugin packaging (007) and consolidation deletions (008) → owner sign-off (user-visible surface changes).
- QA-pack decision → owner: qa-agents contributed 3 generic manual-QA agents (bug-reporter,
  exploratory-coach, test-scenario) worth a domain pack, not core (see CHANGELOG_AI 2026-07-08).
- AppiumLens sync → owner: selective strategy required (real project customization in ~26 kit
  files + 15 project skills); blind `ck update` would work but degrade its local fixes.
- Spawn-mechanism contradiction → needs an empirical test: INVOCATION.md canonicalizes
  `claude -p --agent`; AppiumLens field evidence (2026-06-30) claims that times out and
  Task-tool invocation works. Both can't be right; affects /plan, /review, /refine.
- `<example>`-blocks-inside-YAML-frontmatter in current kit agents (planner, coordinator,
  reviewer, explore, implementer) — possibly invalid YAML; audit + fix pattern kit-wide.

## Known risks

- First real release.yml run is untested end-to-end (Trusted Publishing config could need iteration).
- `ck update` three-way behavior is warn-and-overwrite-with-backup, not a true merge — user data loss is guarded but UX is rough (roadmap §2.2).
- Docs drift risk is CI-gated for counts only; prose claims can still rot — sweep during release prep.

## Suggested first task for a fresh session

Run the DoD gate (see [MODEL_ONBOARDING.md](MODEL_ONBOARDING.md) §5) to confirm the tree is green, then pick up the top unblocked pending item.
