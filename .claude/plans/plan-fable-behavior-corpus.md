# Plan: Encode frontier-model operating behavior into the corpus (Opus/Sonnet uplift)

## Goal

Make the prompt corpus elicit frontier-grade (Fable-class) operating behavior from
Opus/Sonnet/Haiku agents. The gap is behavioral, not raw reasoning: parallelism,
persistence, verification, adversarial self-check, evidence-first reporting, context
economy. Encode each pattern ONCE at the highest-leverage shared point; surgical
per-role additions only where the shared doc can't carry it.

## Spec

10 patterns, defined in the session scratchpad (fable-behavior-spec.md), summarized:
(1) parallel execution, (2) persistence/follow-through, (3) verification before
completion, (4) adversarial self-check, (5) evidence-first outcome-first reporting,
(6) calibrated autonomy, (7) read-before-conclude, (8) context economy, (9) root
cause over symptom, (10) structured decomposition/resumability.
Corollary: model routing — judgment-dense roles on opus.

## Constraints

- Context budget NET-NEUTRAL or better (task 009): extend existing shared docs; no new
  always-loaded files; trim where possible. No new near-duplicate assets (task 008).
- Counts unchanged unless gen-docs regenerated. Registry consistency if mappings change.
- Behavioral/structural test coverage for every protocol addition (test_structure.py style).

## Change set (filled from 3 audit agents)

1. `_shared/AGENT_TEMPLATE.md` — add Parallel Execution, Persistence, Context Economy
   sections; resolve 100-token-cap vs evidence-paste contradiction.
2. `_shared/VERIFICATION_PROTOCOL.md` — add Adversarial Self-Check gate step.
3. Core agents (coordinator, planner, implementer, reviewer, verifier, explore, debugger,
   tester) — role-specific one-liners where shared doc can't carry it.
4. Core commands (/plan /implement /review /verify /refine /audit /coordinator) — mandate
   parallel fan-out where workflows serialize independent steps; outcome-first reporting.
5. Skills — strengthen/remap per audit (verification-before-completion, using-superpowers,
   multi-agent-coordination); fix unowned patterns.
6. Model routing — planner (and any other judgment-dense role flagged) → opus.

## DoD

pytest green (523+) · ruff · mypy · gen-docs --check · structural tests for new sections ·
CHANGELOG [Unreleased] · conventional commits.
