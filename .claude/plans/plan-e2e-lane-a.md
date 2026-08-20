# Implementation Plan: Task 015 LANE A — end-to-end pipeline composition tests

## Overview
Land the deterministic (offline, CI-runnable) half of `review/tasks/015-e2e-pipeline-flow-tests.md`
as ONE new pytest module, `tests/test_pipeline_e2e.py`, carrying 11 tests that assert the pipeline's
**composition** — the seams between stages and the interaction between independently-correct gates.
Everything the spec's catalogue already covers at unit level is dropped rather than duplicated, and
the spec itself is amended to record why.

## Scope
- **In scope:** `tests/test_pipeline_e2e.py` (new, 11 tests); a reconciliation section appended to
  `review/tasks/015-e2e-pipeline-flow-tests.md`.
- **Out of scope:** LANE B (live `claude -p` spawns), the `flow` kind in `scripts/run-evals.py`,
  `.github/workflows/e2e.yml`, `.ai/TESTING_GUIDE.md`, CHANGELOG. **`scripts/run-evals.py` is not
  touched**: the spec routes only LANE B through the new `flow` kind, and nothing in LANE A needs a
  model, a stage carry map, or a budget cap. Docs/CHANGELOG updates are the landing PR's job, not
  this plan's (the module is additive and user-invisible).
- **Not owned here:** any hook, `.claude/settings.json`, `execute-json-ops.py`, agents, skills,
  CLAUDE.md, `.ai/**`, `install.sh`.

## Prerequisites
None. WS-1 (approval gate inside the executor), WS-2 (reflection lifecycle gates) and the Iron Law
gate have all landed, so **no case needs `xfail(strict=True)`** — the spec's step 4/5 xfail
discipline is obsolete and is retired in the reconciliation note.

## Reconciliation of the stale spec (evidence-first)

The spec was written before several of the things it tests existed. Divergences found by reading the
tree, and how this plan resolves each:

1. **Iron Law is enforced now.** `.claude/hooks/iron-law-gate.py` (commit `f5587b4`) is wired on
   `PreToolUse`/`Bash` and carries its own 174-case suite (`tests/test_iron_law_hook.py`, including
   per-guard surgical mutants). LANE A adds no command-allowlist coverage; it adds the composition:
   the gate running *through settings.json's wrapper*, alongside the other Bash hooks.
2. **The approval gate lives in the executor** (`59d6e27`) and its matrix — no record / drift /
   CONDITIONAL / REJECTED / below-threshold / APPROVED / `--no-approval` / `--dry-run` / relocated
   config — is already fully covered by `tests/test_ops_approval_gate.py` (10 tests). E2E-05..12 are
   therefore **dropped as duplicates**. Only E2E-41 (the CONDITIONAL -> revise -> re-approve round
   trip, which no single-shot case can express) is kept.
3. **`ops-enforcement.sh` was rewritten** (`d878496`) with the tracked `.ops-source-globs` marker;
   `tests/test_ops_enforcement_scope.py` (20 tests) covers the opted-in and plain-project matrices.
   LANE A's contribution is that the profile matrix is exercised **through the wired `bash -c`
   command string from settings.json**, not by invoking the hook file — the "present but unwired"
   failure mode that every existing hook test is blind to.
4. **Hook count is 21 and `.claude/hooks/` contains `.py` hooks.** Nothing in this module counts or
   globs `*.sh`; the fixture copies the whole hooks directory and the chain is derived from
   settings.json, so `.py` hooks participate automatically.
5. **The reflection ledger moved** (`21778c6`). No path is assumed: `CLAUDEKIT_REFLECTION_DIR` /
   `CLAUDEKIT_REFLECTION_INBOX` are redirected per test.
6. **`tests/conftest.py` exists** (`13a14da`). Its `scoped_env` helper is imported and used for the
   in-process receipt mint; the fixture factory stays module-local (see Step 1 rationale).
7. **Mode preservation (`4c57198`) and installer hook shipping (`749e34d`)** have their own suites
   (`test_ops_file_modes.py`, `test_hook_delivery.py`). Not duplicated.

Additional divergence found while prototyping, not in the briefing:

8. **E2E-33 is rewritten, not dropped** (revised after review; the first revision withdrew it, which
   was wrong — the fix is to assert the property the design HAS). The
   executor holds a project-wide lock: a second run that meets a held lock exits non-zero with the exact
   shipped string `Another CodeManifest executor is running (lock: .codemanifest.lock)`
   (`execute-json-ops.py:191`). Racing two executors would be a coin flip dressed as a test, so the
   lock is HELD BY A CHILD PROCESS until the test releases it: no timing dependence, and both halves
   of E2E-31 (refusal + no stale lock poisoning the next run) are asserted. Worktree isolation stays
   covered by `tests/test_worktree_manager.py::TestIsolationProof`.
9. **E2E-28 (SIGINT mid-batch) lands narrowed** (revised after review). The invariants asserted are
   timing-independent — exit 130, one `interrupted` verdict, a rolled-back tree — because the signal
   is aimed at a `run_command` sleep placed after the file operations. Only the "consistent at an
   arbitrary instant" refinement is deferred.

## Per-group verdict (the honest accounting)

Revised after review: two rows that were called ALREADY-COVERED left a real behaviour covered by
NOTHING, and three more are PARTIAL, not covered. Corrected below.

| Spec group | Verdict | Evidence / residue |
|---|---|---|
| A — happy path (E2E-01/02/03) | **NEW ×1 (composed)** | Each script is unit-tested with hand-built inputs (`test_extract.py`, `test_validator.py`, `test_review_record.py`, `test_ops_hardening.py`); nothing feeds stage N's real output to stage N+1. |
| A — E2E-04 | out of scope | LANE B. |
| B — E2E-05/06/08/10/11/12 | **ALREADY-COVERED** | `tests/test_ops_approval_gate.py` (10 tests). |
| B — E2E-07 | **PARTIAL** | `test_ops_approval_gate.py:123-132` asserts only non-zero + untouched tree. Residue: stderr must distinguish "verdict does not authorise" from "no record". Follow-up in that module, not folded in here. |
| B — E2E-09 | **PARTIAL** | The parametrisation uses `(50, "APPROVED")`; the 89/90 threshold BOUNDARY is unpinned. Follow-up in that module. |
| B — E2E-41 round trip | **NEW ×1** | No existing test revises an approved artifact and re-approves it; both failure directions (approval laundering / dead end) are unasserted today. |
| C — E2E-13/14/15 | **RECONCILED -> NEW ×3** | `test_hooks_behavioral.py` runs hooks by file path from a hardcoded list. These run the settings.json command strings, so an unwired hook is red. |
| C — E2E-16 | **PARTIAL** | `test_packaging.py:91` / `test_hook_delivery.py:33` prove `settings.local.json` never ships. Residue, covered by nothing: the case's actual point — this repo's own `minimal` override emitting a warning that NAMES it, and asserted gitignored. Follow-up. |
| D — E2E-17/18 | **RECONCILED -> NEW ×1 (paired)** | Block-and-allow in ONE test for `agent_type=implementer` across the wired Bash chain, with per-hook attribution. |
| D — E2E-19/20/21 | **ALREADY-COVERED** | `test_hooks_behavioral.py` (malformed payload fails closed), `test_ops_enforcement_scope.py` (`.md` / `.claude/**` characterization). |
| E — E2E-22..26 | **ALREADY-COVERED**; precedence **NEW ×1** | `tests/test_reflection_gate.py` (42 tests). What it cannot cover: the reflection checkpoint outranking iron-law-gate.py's PERMISSION of the ops command. |
| F — E2E-27/29/30 | **ALREADY-COVERED** | `test_ops_hardening.py`, `test_work_loss_protection.py`. |
| F — E2E-31 | **RECONCILED -> NEW ×1** (was wrongly marked covered) | `ExecutionLock` (`execute-json-ops.py:150-197`) and `.codemanifest.lock` appear in ZERO test files. E2E-31's "no stale lock left behind that blocks the next run" is covered by nothing; `test_ops_hardening.py` covers rollback/dry-run/abort only. |
| F — E2E-28 (SIGINT) | **NEW ×1, narrowed** (was deferred) | The timing-independent half lands: interrupt during a `run_command` sleep placed after the file ops, assert exit 130, a single `interrupted` verdict, and a rolled-back tree. The "consistent at an arbitrary instant" refinement stays deferred. |
| G — E2E-32 | **ALREADY-COVERED** | `test_worktree_manager.py::TestIsolationProof`. |
| G — E2E-33 | **RECONCILED -> NEW ×1** (withdrawal reversed) | Rewritten to the property the design HAS: a run that meets a held lock refuses (`Another CodeManifest executor is running`) and does not mutate. The lock is held by a child process until the test releases it — no timing dependence. |
| G — E2E-34 | **RECONCILED -> NEW ×1** (hook half; executor half covered) | `test_security.py` / `test_worktree_manager.py` cover the EXECUTOR path guard. `ops-enforcement.sh`'s cross-project deny branch is referenced by no test (`CROSS-PROJECT` appears nowhere under `tests/`). |
| H — E2E-35 | **ALREADY-COVERED** | `test_delivery_contract_smoke.py` executes `/plan`'s real scripted block against a stub `claude`. |
| H — E2E-36 | **NEW ×1** | No test lints the agent/command corpus for payload-reprint instructions. |
| I — E2E-40 (A half) | **ALREADY-COVERED** | `test_behavior_spec.py:148-156` — a STRUCTURAL frontmatter check (key / blank / indented-block-scalar continuation), not a YAML parse. Corrected from the previous revision, which paraphrased it as "parses as YAML". |

**Result: 11 NEW tests · 6 rows RECONCILED · 9 rows ALREADY-COVERED · 3 rows PARTIAL with the residue named and handed on as follow-ups.**

## Implementation Steps

### Step 1: create `tests/test_pipeline_e2e.py`
- **File:** `tests/test_pipeline_e2e.py`
- **Action:** Create
- **Description:** One module, 11 tests, plus a module-local `project` fixture.
- **Grouping rationale (one module, not a family):** the spec's `tests/fixtures/pipeline/` vendored
  fixture is rejected — a vendored `.claude/` goes stale against the tree it guards. The fixture is
  built at test time by copying the live `hooks/`, `operations/scripts/` and `settings.json`, so
  drift is impossible by construction. The fixture factory stays in this module rather than in
  `tests/conftest.py`: it is used by exactly one module, and `conftest.py` is a shared file other
  workstreams edit.
- **Details (load-bearing choices):**
  - **DO NOT "tidy" the fixture into `tmp_path`.** The fixture project is created **beside the repo** (`dir=REPO.parent`, prefix `.ck-e2e-`) and
    removed on teardown. Under `$TMPDIR` on macOS the path is `/var/folders/...`, which
    `ops-enforcement.sh` exempts as OS scratch — every hook assertion would pass vacuously. Same
    reasoning, and the same comment, as `tests/test_ops_enforcement_scope.py`.
  - `ECC_HOOK_PROFILE` is passed explicitly to every subprocess (`env_for()`), and
    `ECC_OPS_GATE_ALL` / `ECC_OPS_SOURCE_GLOBS` are popped, so no result depends on the maintainer's
    session or on an ambient export.
  - The wired-chain runner parses `settings.json` `PreToolUse` entries, matches on the tool name,
    and executes each hook's own `bash -c '...'` command string with the payload on stdin. Verdicts
    are collected **per hook**, so every assertion names which hook blocked — a chain-level
    "something exited 2" would be a tautology.
  - The reflection receipt is minted through the shipped library with `conftest.scoped_env`, bound
    to the session token and the pending active set. Hand-writing a receipt is what the gate exists
    to reject.
  - No test writes anywhere under `<repo>/.claude/**` or mutates the real tree.

### Step 2: reconcile the spec
- **File:** `review/tasks/015-e2e-pipeline-flow-tests.md`
- **Action:** Modify (one insertion after the Root Cause paragraph)
- **Description:** Record the eight divergences above, the dropped/deferred cases, the retirement of
  the `xfail(strict=True)` discipline, and the LANE A totals as delivered — so the spec's catalogue
  is never read as a to-do list that this PR failed to complete.

## Testing Strategy
The module *is* the test change. Its own falsifiability was measured before writing this plan
(numbers below) by mutating one table/branch at a time in a working copy and asserting the EXACT set
of tests that flip. No mutant disables a whole function except where that function IS the guard
under test (M4/M5), and those two are declared as such.

Verification commands for the landing PR:
```
ruff check tests/
python3 -m pytest tests/test_pipeline_e2e.py -q
python3 -m pytest tests/ -q
```

## Measured evidence

Isolated module: **11 passed in 6.96–7.78 s** across 12 runs (profiles `standard`, `minimal` and
`ECC_HOOK_PROFILE` unset — identical results, i.e. no ambient dependence, and no flake in 10
consecutive runs including the SIGINT case).
Full suite, measured in the same throwaway copy on the same machine: **1204 passed / 144.0 s**
without the module → **1215 passed / 159.8 s** with it. The module alone accounts for **7.0 s** of
that; the remaining ~9 s is run-to-run variance (an earlier paired measurement on the real tree gave
143.2 s → 141.4 s, i.e. the delta is not resolvable at suite level). Reported as measured, both
pairs, rather than picking the flattering one. Well under the 30 s bar either way.

### Mutation proof — accounting corrected after review

The previous revision's claim that "no mutant flipped a test outside its declared set" was false at
suite level and is withdrawn. The column below is explicitly **module-scoped**: tests IN
`tests/test_pipeline_e2e.py` that went red. Suite-wide collateral was then MEASURED for the two
mutants the review named, and is recorded as measured, not predicted.

| # | Surgical mutant | Tests in THIS MODULE that went red |
|---|---|---|
| M1 | `ops-enforcement.sh`: drop the `minimal` short-circuit | `..._is_inert_under_minimal` |
| M2 | `ops-enforcement.sh`: `${ECC_HOOK_PROFILE:-standard}` -> `:-minimal` | `..._defaults_to_enforcing_when_profile_is_unset` |
| M3 | `lib.sh` `deny()`: `exit 2` -> `exit 1` | `..._blocks_a_source_edit_under_standard`, `..._defaults_to_enforcing...` |
| M4 | `iron-law-gate.py`: `decide()` returns allow | `..._permits_the_ops_path_and_blocks_direct_mutation` |
| M5 | `reflection.py`: `pending_checkpoint()` returns `None` | `..._checkpoint_outranks_the_iron_law_allowance` |
| M6 | `review-record.py`: verdict/threshold branch neutered | `..._conditional_revise_reapprove_roundtrip` |
| M7 | `execute-json-ops.py`: `execute_code_edit` succeeds without writing | `..._plan_artifacts_flow_...`, `..._conditional_revise_reapprove_roundtrip` |
| M8 | seeded `return the complete plan` line in `.claude/agents/explore.md` | `..._instructs_a_payload_reprint` |
| M9 | `ExecutionLock.acquire()` always returns True | `..._lock_refuses_a_second_run_and_leaves_no_stale_lock` |
| M10 | `ExecutionLock.release()` stops unlinking the lock file | `..._lock_refuses_a_second_run_and_leaves_no_stale_lock` |
| M11 | `ops-enforcement.sh`: cross-project deny branch removed | `..._blocks_a_cross_project_edit` |
| M12 | `execute-json-ops.py`: `_result_emitted` latch removed | **NONE — the case stayed green** |
| M13 | `_signal_handler`: no rollback on interrupt | `..._sigint_mid_batch_reports_exactly_once_and_rolls_back` |

Measured suite-wide collateral (full suite re-run per mutant):
- **M1: 5 failed / 1210 passed**, across `test_ops_enforcement_scope.py`, `test_hooks_behavioral.py`,
  `test_delivery_contract_smoke.py` and this module.
- **M3: 33 failed / 1182 passed**, across those three plus `test_reflection_ledger.py` — every
  existing case that asserts the exit-2 blocking contract, exactly as the review predicted.
- The remaining mutants were measured module-scoped only; no suite-wide claim is made for them.

**M12 is a negative result and is reported as one.** Neutering the `_result_emitted` latch does NOT
redden the SIGINT case: the handler exits via `SystemExit`, so no second verdict is reachable on
that path. The `len(verdicts) == 1` assertion is therefore a consistency check, not a latch proof;
the case's binding guard is M13 (interrupt rollback). The test docstring says exactly this, so no
future reader can cite the case as latch coverage.

Every one of the 11 tests is bound by at least one mutant (M12 excepted, which binds nothing —
its case is bound by M13 instead).

## Follow-ups handed on (not folded in here, per review)

- `test_ops_approval_gate.py`: assert E2E-07's stderr distinction ("verdict does not authorise" vs
  "no record") and E2E-09's 89/90 threshold boundary. Cheap additions to the module that owns them.
- E2E-16: a test that makes this repo's own `minimal` override VISIBLE — a warning naming
  `.claude/settings.local.json` plus an assertion that it is gitignored.
- E2E-28's remaining half: "consistent at an arbitrary instant" needs a deterministic injection
  point in the executor; whoever owns `execute-json-ops.py` should decide whether to add one.
- The executor's Windows lock fallback is not a lock, and `release()` unlinks unconditionally
  (noted in the triage). M9/M10 now bind the Unix path; the Windows path remains uncovered by
  design (no Windows CI lane).

## Rollback Plan
Entirely additive. `git rm tests/test_pipeline_e2e.py` removes the gate with no other effect; revert
the spec edit independently. No production code, no shipped artifact, no CI config is touched, so
nothing here can affect a user install.

## Risk Assessment
- **Low:** additive test module; no production file changes; runtime cost inside noise.
- **Low:** the fixture creates a hidden sibling directory of the repo (`../.ck-e2e-*`). It is removed
  in a `finally`; a hard kill could leave one behind. Accepted deliberately — the alternative
  ($TMPDIR) makes the whole module vacuous on macOS.
- **Medium (cross-workstream, raise in the PR):** `test_wired_*` derive the chain from
  `.claude/settings.json`. Any workstream that rewires PreToolUse must expect these to move with it —
  that is the guard working, not a flake. Whoever owns settings.json should be told.
- **Medium (cross-workstream, pre-existing, NOT introduced here):** during measurement,
  `tests/test_reflection_ledger.py::TestCli::test_receipt_via_inbox_keeps_free_text_out_of_the_command_line`
  failed once in a full-suite run and passed both in isolation (54 passed) and in the following full
  run. That is an order/environment-dependent flake in an existing module; it is unrelated to this
  change and needs an owner.
- **Low (owner decision, unchanged):** the WS-5 memo on the `.md` / `.claude/**` exemptions still
  stands; this plan adds no new characterization tests, so it neither endorses nor prejudges it.

## Landing note (measured, not predicted)

`tests/test_delivery_contract_smoke.py::test_queued_ops_configs_validate_against_head` validates
every *queued* config in `.claude/plans/` against HEAD. `plan-e2e-lane-a.ops.json` passes while
queued (verified green in the real tree), but its `code_edit` anchor is consumed once executed — so
the full suite goes red in any tree where the config has been executed and left in `.claude/plans/`.
This was observed for real in the verification copy. **After execution, move
`.claude/plans/plan-e2e-lane-a.ops.json` to `.claude/plans/archive/` with a README entry**, exactly
as that test's docstring instructs. This is a landing step, not a defect.

## Verification performed (in a throwaway copy of the tree, never the real one)

- `validate-config-json.py .claude/plans/plan-e2e-lane-a.ops.json` -> APPROVED.
- Ops executed in the copy: 2/2 successful (`file_create` + `code_edit`), spec insertion lands with
  a blank line before the heading.
- `ruff check tests/test_pipeline_e2e.py` -> All checks passed.
- `pytest tests/test_pipeline_e2e.py -q` -> 11 passed; 10 consecutive runs, no flake (6.96–7.78 s).
- Full suite in the copy, config archived after execution -> **1215 passed, zero failures**
  (1204 + 11).
- All 13 mutants re-run against the delivered artifact; module-scoped results as tabled, with
  suite-wide collateral measured for M1 (5 red) and M3 (33 red) and M12 recorded as a negative.
- Copy deleted; `git status --porcelain` in the real tree shows only the two plan artifacts.
