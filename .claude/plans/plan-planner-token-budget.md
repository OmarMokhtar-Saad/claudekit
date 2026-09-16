# Plan: planner-token-budget

**Tier:** 2 (multi-file prompt/policy/docs change; no code, no security or schema surface)
**Ops config:** `.claude/plans/archive/ops-planner-token-budget/plan-planner-token-budget.ops.json` (executed 2026-09-16)

## Problem
A `/plan` run takes up to an hour and 100k+ tokens. Measured causes (2026-09-16):
- planner routed to `most-capable` unconditionally; every other judgement role is `balanced` with escalation
- Phase 1 re-derives structure/stack/tests/CI/conventions on every run, including revisions, with no cap
- `/refine` defaults to 5 rounds, hardcodes opus for both roles (contradicting model-policy for the reviewer), has no stagnation exit, and its revision prompt does not tell the planner to skip discovery
- reviewer refutes anchors by reading files whole
The `reflection-gate` parse-failure BLOCKs in hooks.log are test-suite artefacts (`tests/test_dispatch_merge.py` feeds `not json`), not a runtime bug — out of scope.

## Changes
| File | Change |
|---|---|
| `.claude/agents/planner.md` | Discovery budget block (revision mode, index-first, tests on demand, call cap, batching); revision handling as bounded delta |
| `.claude/commands/refine.md` | MAX_ITER 3; REVISION MODE in both revision prompts; stagnation exit |
| `.claude/agents/reviewer.md` | Refutation budget |
| `CHANGELOG.md` | Unreleased entry |

## Owner decisions
- Planner stays on the most-capable tier: switching to balanced was tried and reverted 2026-09-16 (owner: quality drop and more rounds cost more than the per-token saving).

## Deferred (owner decision)
ops.json `content` by file path for large `file_create` payloads needs validator + executor changes (Tier 3). Not in this plan.

## Validation
`python3 scripts/gen-model-policy.py --check` · `python3 -m pytest tests/test_model_policy.py tests/test_delivery_contract_smoke.py tests/test_single_source_contracts.py -q` · full suite · `gen-docs --check`.

## Rollback
`python3 .claude/operations/scripts/rollback` / git checkout of the touched files (all tracked).
