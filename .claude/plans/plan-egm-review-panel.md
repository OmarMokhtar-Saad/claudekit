# Plan: /review runs two zero-context critics beside reviewer (EGM design + readiness)

**Date**: 2026-11-05 | **Requested by**: Omar — chose "only inside /review" (no auto review; TOKEN-MODEL-POLICY v8 unchanged) and "add a can-this-test-fail check" after a seeded-defect benchmark.
**Tier**: 2 (prompt corpus + one test; no security/schema surface; the /implement gate is unchanged).

## Evidence

Seeded-defect benchmark, 2 claudekit plans × 6 planted defects, all arms on the balanced tier:
reviewer 5/12; EGM 7-persona panel 7/12 (14 agents, ~159 findings); EGM design + readiness alone 7/12;
reviewer + design + readiness 8/12. Every arm missed both "untestable" defects (vacuous assertions).

## Design

- Two new agents, text adapted from google/elephant-goldfish-model @0dfb5bf (Apache-2.0):
  `plan-design-critic` (design_critic persona + feature-spec standard) and `plan-readiness-critic`
  (implementation_readiness persona + implementation-readiness standard). REVIEW mode only, standard
  inlined, tools Read+Grep, `omitClaudeMd: true`, untrusted-content line, 8-finding / 3,000-char cap,
  final `PANEL: <n> blocker, <n> major` line. Model/effort from model-policy (balanced).
- `/review` launches reviewer + both critics in ONE message (parallel); critics get only the plan path.
  Only reviewer's verdict is recorded (review-record.py unchanged), so the /implement gate is unchanged.
  The session then prints `=== PANEL ===` with critic Blocker/Major findings that reviewer's ISSUES do
  not already cover, and recommends revising before /implement when any Blocker remains — advisory.
  `--no-panel` skips the critics.
- reviewer.md: one checklist line — flag any test/validation step that would pass if the change were
  wrong or missing (Major).
- Attribution: `.claude/agents/_shared/EGM-LICENSE.txt` (Apache-2.0 text) + `EGM-NOTICE.md`.

## Files:
- .claude/agents/plan-design-critic.md
- .claude/agents/plan-readiness-critic.md
- .claude/agents/_shared/EGM-LICENSE.txt
- .claude/agents/_shared/EGM-NOTICE.md
- .claude/agents/reviewer.md
- .claude/commands/review.md
- .claude/model-policy.json
- .claude/skills/skills-registry.json (generator)
- AGENTS.md, docs/AGENTS.md, docs/ARCHITECTURE.md (gen-docs counts)
- CHANGELOG.md
- tests/test_review_panel.py

## Validation
- `python3 -m pytest tests/test_review_panel.py tests/test_model_policy.py tests/test_agent_frontmatter.py tests/test_skill_loading_contract.py tests/test_structure.py -q`
- `gen-docs.py --check`, `gen-registry.py --check`, `gen-model-policy.py --check`, `check-context-floor.py --check`, `ruff check tests/`
- Re-run of the benchmark plan-A through the real `/review` panel path is owed (manual).

## Out of scope
Auto review after /plan (policy v8 stays); the other 5 EGM personas; installing the EGM plugin.
