# Implementation Plan: Task 015 — End-to-End Pipeline Flow Tests (spec only)

## Overview
Author `review/tasks/015-e2e-pipeline-flow-tests.md`, a task spec for a NEW session that will
build a full plan -> review -> implement -> verify E2E test suite. This workstream (WS-6 of a
6-way decomposition) writes the spec only; it ships no tests, no scripts, no source changes.

## Scope
- **In Scope:** exactly one new file, `review/tasks/015-e2e-pipeline-flow-tests.md`, matching the
  house format of `review/tasks/007..014` (Problem / Root Cause / Files / Priority / Estimated
  Time / Risk / Step-by-step Implementation / Acceptance Criteria / Testing Strategy / Rollback
  Plan), plus a 41-case test catalogue with an explicit deterministic-vs-live lane split.
- **Future-ownership note (not this ops.json):** 015's *implementation* session will additively
  touch `scripts/run-evals.py` (a new `flow` kind, gated on a `stages` key) and `evals/`, both of
  which task 010 owns. That is a deliberate extension, not a fork — coordinate with 010's owner
  before that session starts. This workstream's ops.json touches neither file.
- **Out of Scope:** `.ai/BACKLOG.md` pointer (integration adds it), `tests/`, `scripts/`,
  `.claude/**`, `evals/`, CI workflows, and any implementation of the described tests.

## Prerequisites
- Read of tasks 010 (eval framework) and 012 (test-suite behavioral upgrade) so the spec
  complements rather than duplicates them — 010 owns per-agent evals, 012 owns per-unit tests,
  015 owns the composition.
- Awareness of the sibling workstreams the spec depends on: WS-1 (approval gate moved into
  `execute-json-ops.py`), WS-2 (lifecycle gates), WS-5 (ops-enforcement exemption decision memo).

## Implementation Steps

### Step 1: Create the task spec
- **File:** `review/tasks/015-e2e-pipeline-flow-tests.md`
- **Action:** Create
- **Description:** Full task spec in house format.
- **Details:** Sections as listed above. Central content is the catalogue of 41 enumerated cases
  (E2E-01..E2E-41) across nine groups: happy path, approval-gate matrix, hook-profile matrix,
  Iron Law, lifecycle gates, failure/recovery, isolation, delivery contract, spawn mechanisms.
  Every case states preconditions, the exact command, the observable assertion, and the failure
  signature it catches. Lane split: 36 LANE A (deterministic — hooks, ops engine, gates, path
  guard, lints; run per-PR in CI, no API), 4 LANE B and 1 hybrid (live `claude -p` spawns — budget-capped,
  opt-in/nightly, extending `scripts/run-evals.py` with a `flow` kind). WS-dependent cases are
  specified as `xfail(strict=True)` with a named reference, never skipped. The `.md` and
  `.claude/**` ops-enforcement exemption cases and the headless `.claude/**` write gate are
  specified as **characterization** tests that record current behavior without endorsing it,
  cross-linked to the WS-5 memo. Acceptance requires an enumerated mutation proof for each of the
  nine groups (the one non-mutable half is named with its reason).

## Testing Strategy
Spec-only workstream — no runtime behavior changes, so no code tests apply.
Validation performed here:
- `python3 .claude/operations/scripts/validate-config-json.py .claude/plans/plan-e2e-pipeline-test-task.ops.json` exits 0.
- After execution: the new file exists, is the only changed path (`git status --porcelain`), and
  its heading set matches the section list used by `review/tasks/012` and `014`.
- Numbering is free: `review/tasks/` currently holds 001..014, so 015 does not collide.

## Rollback Plan
`git rm review/tasks/015-e2e-pipeline-flow-tests.md` (or revert the commit). The file is additive
documentation with zero references from code, docs, or the registry at creation time; nothing
imports it and no gate reads it, so removal is a clean no-op.

## Risk Assessment
- **Low Risk:** creating a new, unreferenced markdown file under `review/tasks/`. No hooks fire on
  `.md`, no docs-drift or registry-drift gate counts task files, no CI job globs this directory.
- **Medium Risk:** spec accuracy — the catalogue asserts behavior of WS-1/WS-2 surfaces that do not
  exist yet. Mitigated by naming the dependency explicitly per group and requiring `xfail(strict)`
  rather than inventing API shapes; the implementing session must assert WS-1's chosen override
  surface, not one this spec fabricates.
- **High Risk:** none.
