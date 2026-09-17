# CODE REVIEW — qa-agents hardening (Tier 3, EXECUTING reviewer)

Target: `.claude/plans/plan-qa-agents-hardening.ops.json` (11 ops) + payloads
Revision: `c8e3169` + uncommitted working tree (plan/payloads untracked)
Method: full repo copied to a scratch dir; ops applied there with `--no-approval`; the real tree was never modified. Baseline comparison tree = second pristine copy at the same revision.

## What I EXECUTED (not read)

| Command (scratch copy) | Result |
|---|---|
| `execute-json-ops.py <ops.json> --no-approval` | `RESULT-JSON {"status": "success"}`, 11/11 ops, 0 errors |
| `shellcheck .claude/hooks/command-guard.sh` | clean |
| `ruff check src/ tests/ scripts/ .claude/operations/scripts/` | **1 error** (F401) |
| `mypy` | **1 error** in 1 file (42 checked) |
| new tests (4 files) | **1 failed, 26 passed, 1 skipped** |
| 22 executor-CLI test files, before vs after | before **14 failed / 808 passed**; after **43 failed / 779 passed** → **29 NEW failures** |
| `gen-docs.py --check` | OK (agents=22 commands=57 skills=81 hooks=28) |
| `gen-registry.py --check` | OK |
| `check-context-floor.py --check` | OK (84817/99500) |
| payload leak grep (`qa-agents|DECISIONS.md|claude-kit`) | 0 hits |
| mutation control A (`_preflight_validate → True`) | kills 2 tests — load-bearing |
| mutation control B (restore `2>&1` in `run_validator`) | kills 2 tests — load-bearing |

Read only (not executed): the plan prose, the ops config, and the unexecuted risk claims about coordinator worktree flows.

---

## CRITICAL

**[C1] The new executor preflight gate breaks 29 existing tests and shadows five downstream security gates**
File: `.claude/operations/scripts/execute-json-ops.py:1581-1594` (post-state)
Evidence: identical 22-file run, same tree revision, `-p no:randomly`:
before `14 failed, 808 passed`; after `43 failed, 779 passed`. Sample:
```
tests/test_ops_parse_gate.py:287:  assert res.returncode == 1  ->  assert 2 == 1
  stdout: 'Deliberate override: --skip-validation
           RESULT-JSON: {"mode":"refused","status":"validation_failed","error_count":3}'
tests/test_ops_file_modes.py:182:  'unsupported create mode' not in output  (refused earlier)
```
New failures by file: `test_ops_parse_gate.py` (10), `test_ops_hardening.py` (8), `test_ops_file_modes.py` (3), `test_ops_content_by_path.py` (2), `test_run_command_ops.py` (2), `test_work_loss_protection.py` (2), `test_ops_approval_gate.py` (1), `test_validator_sequence_mode.py` (1).
Impact: two-fold. (a) The suite is red — the DoD gate ("zero failures tolerated") fails, so this cannot merge as-is. (b) More seriously, these tests exist to prove the *downstream* gates fire through the CLI: the parse gate, the setuid/create-mode refusal, the tampered-payload digest check, the ambiguous-anchor abort, and the `run_command` allowlist. The preflight now refuses first, so each of those enforcement paths is no longer exercised end-to-end. Blanket-adding `--skip-validation` to these invocations would restore green while leaving the preflight itself untested in those files and would also be the exact "allowlist before an early return" shape. This is a coverage regression in the Iron Law's single path, not just a test-expectation churn.
Class: `gate-shadows-the-gate-it-precedes` (new)
Fix: decide per file whether the test's subject is downstream of validation; for those, add `--skip-validation` *and* an assertion that the preflight would have refused without it. Do not weaken the gate. The plan lists this as `UNVERIFIED` with 10 candidate files; the real set is 8 files / 29 tests, including three the plan never named (`test_ops_hardening.py`, `test_ops_content_by_path.py`, `test_ops_file_modes.py`).

---

## MAJOR

**[H1] A shipped mutation control fails on the unmutated tree**
File: `tests/test_command_guard_crash.py:129` (payload `test_command_guard_crash.py`)
Evidence:
```
TestMutationControls::test_dropping_the_exit_code_condition_reopens_the_bypass
AssertionError: the mutant still blocked ... assert 2 == 0
```
Impact: the plan's central claim — "every mutation control is a test that runs in CI and FAILS if the mutant survives" — is false for this one, and it is red out of the box. Root cause is a real design fact, not a flake: `ECHOING_REFUSAL` writes its `ImportError` text to **stdout**, while the discriminator greps `$ERR` (stderr). With the channel split in place, dropping the `RC -ne 2` condition changes nothing, so the rc-2 exclusion is *not* what closes this bypass — the stdout/stderr split is. The test asserts the wrong cause. (Confirmed: re-introducing `2>&1` in `run_validator` makes this control pass and breaks `test_crashing_validator_is_permissive_under_standard` — i.e. the split is the load-bearing control.)
Class: `mutation-proof-overclaim` (the same class the plan's own prior-rejection search surfaced as `e2e-lane-a`'s MAJOR — third entry in this repo; it has now earned a mechanical check: run every new test file before the verdict, which this review did and the planner did not)
Fix: either point the mutant at the channel split (assert the rc-2 exclusion via a validator that writes its refusal text to **stderr**), or restate the test as a control over the split and delete the misattributed one.

**[H2] `mypy` gate fails — the refactored validator main passes `Optional[dict]` where `dict` is required**
File: `.claude/operations/scripts/validate-config-json.py:1044` (post-state)
Evidence: `error: Argument 2 to "stamp_baseline" has incompatible type "Optional[dict[Any, Any]]"; expected "dict[Any, Any]"  [arg-type]`
Impact: CI type gate red. Behaviourally, `full_verdict` can return `(True, [], None)` on a file that parses in one path and not another, and `stamp_baseline` would then receive `None` — a latent crash in the stamping path, which is exactly where a hash/verdict deadlock would be most confusing.
Class: `refactor-widens-a-type-without-widening-the-callee` (new)
Fix: have `full_verdict` return a non-optional dict when `is_valid` is True (assert/narrow), or guard the `stamp_baseline` call.

**[H3] `ruff` gate fails — unused import in a new test file**
File: `tests/test_command_guard_crash.py:20` — `import sys` (F401)
Impact: lint gate red; blocks the DoD.
Class: `new-file-ships-lint-red` (new)
Fix: drop the import from the payload (payload sha256 must be re-stamped).

---

## Security verification (item 4) — all PASS

- Blocks are still `exit 2` + stderr, fail closed: `command-guard.sh:109-133`; `deny` reached for any `RC -ne 0` after the 127 branch; `strict` still denies on validator-unavailable. `shellcheck` clean, bash-3.2 constructs only.
- The crash discriminator **cannot** convert a real refusal into rc 127: rc 2 is excluded outright, the pattern is line-anchored, and it is consulted only for rc ∉ {0,2,127} on a stderr channel the validator alone writes. `TestVerdictWins::test_refusal_echoing_a_crash_token_still_blocks` (the `ImportError`-in-refusal bypass test) **passes** (rc 2, no "NOT checked").
- No qa-agents project text leaked: `grep -rn "qa-agents\|DECISIONS.md\|claude-kit" .claude/plans/payloads/qa-agents-hardening/` → 0 hits.

## Positive observations

- The ops config executed cleanly first try, all payload sha256 pins matched, and `add_before` concatenation produced parseable, ruff-clean sources for the three inserted function blocks (the known literal-concat trap was handled).
- Both hand-applied mutants killed real assertions — the gate tests and the channel-split test are genuinely load-bearing.
- Generator gates (docs counts, registry, context floor) are all unaffected, exactly as the plan predicted.
- Scope discipline is real: the diff carries no downstream project strings and no qa regressions.

## Coverage

Correctness, security, reliability: executed. Performance: n/a. Full `pytest tests/ -q` was NOT run (only the 22 executor-CLI files + the 4 new ones); the true full-suite failure count is ≥29 new failures.

Scratch trees removed after the run.

Round 1 verdict was REJECTED (60): [C1] 29 new failures + gate shadowing, [H1] failing
mutation control, [H2] mypy, [H3] ruff. Superseded by the Round 2 block at the end of this
file.

---

# ROUND 2 — re-review of the rewritten plan (14 ops, was 11)

Scope: the rewritten `plan-qa-agents-hardening.md` / `.ops.json` and four re-stamped payloads.
Method unchanged except the scratch copies now **include `.git`** (two copies at `c8e3169`:
one executed, one left pristine as the baseline), so `tests/test_day_one_blockers.py` and the
git-dependent suites run for real. Real tree never modified.

## Executed in Round 2 (real numbers)

| Command | Result |
|---|---|
| `execute-json-ops.py <ops.json> --no-approval` | `status: "success"`, **14/14 ops**, 0 errors |
| `ruff check src/ tests/ scripts/ .claude/operations/scripts/` | **All checks passed!** |
| `mypy` | **Success: no issues found in 42 source files** |
| `shellcheck install.sh .claude/hooks/*.sh` | clean |
| 4 new test files | **30 passed, 1 skipped** (was 1 failed) |
| the 8 files from [C1] | **231 passed, 2 skipped, 0 failed** (was 29 failed) |
| **`pytest tests/ -q` FULL, executed tree** | **19 failed, 11459 passed, 79 skipped, 1 xfailed** (1127s) |
| **`pytest tests/ -q` FULL, pristine baseline copy** | **18 failed, 11431 passed, 77 skipped, 1 xfailed** (1352s) |
| failure diff (after − before) | **exactly 1**, analysed below; **0 fixed-but-hidden** |
| `gen-docs.py --check` / `gen-registry.py --check` / `check-context-floor.py --check` | OK / OK / OK |
| `check-plan-artifacts.py --check` | **FAILS** — see [M1] |

The 18 baseline failures (`test_ops_enforcement_scope`, `test_pipeline_e2e`, `test_profiles`,
`test_hooks_behavioral`, `test_dispatch_payload`, `test_local_settings_healing`) are
**pre-existing at `c8e3169`** — identical set before and after, unrelated to this change
(scratch-copy hook-profile environment).

## INHERITED FINDINGS

**[C1] preflight gate shadows five downstream gates / 29 failures — Status: discharged.**
Evidence: the executor no longer calls `full_verdict`; `validate-config-json.py:915
preflight_verdict()` verdicts **schema + backup-compatibility only** and DEFERS an unparseable
config (`return True, [], None`) to the executor's own `config-load-error`. The 8 affected
files now run **231 passed / 0 failed**. The narrowing is load-bearing, measured by hand:
mutating `preflight_verdict` to `return full_verdict(config_file)` turns **12 downstream proofs
red** (ambiguous/missing anchor, tampered digest ×2, run_command allowlist ×2, symlink refusal,
rollback/backup evidence ×4, RESULT-JSON evidence ×2) — i.e. the shadowing this finding named
is now pinned by real tests.
The three `--skip-validation` edits are **not** blanket skips: each asserts
`returncode == 2` + `validation_failed` FIRST and only then steps past it
(`test_ops_parse_gate.py` both-keys, `test_ops_file_modes.py` setuid,
`test_ops_approval_gate.py` no-plan-field). Each still proves its downstream gate
(`PARSE GATE`, `unsupported create mode`, `no review record exists`).
The `plan_name` → `plan` fixture change is confined to `write_ops` (line 53); the two
remaining `plan_name` fixtures (lines 233, 368) drive `gate.check()` **in-process**, where the
preflight is not involved, so the legacy-schema and BOM assertions are untouched.
The validator-resolution defect is fixed as claimed: `_preflight_validate` now tries
`Path(__file__).parent` then `Path(shared.__file__).parent`, and still returns
`False` (refuses) when the validator is missing or lacks `preflight_verdict` — fail-closed.

**[H1] mutation control failed on the unmutated tree — Status: discharged.**
Evidence: all 11 tests in `test_command_guard_crash.py` pass unmutated. Both re-pointed
controls were hand-applied to the **real** hook:
- drop the `RC -ne 2` exclusion → `TestVerdictWins::test_stderr_refusal_carrying_a_crash_token_still_blocks` goes RED (3 failed, 8 passed);
- grep `"$OUT$ERR"` instead of `"$ERR"` → `TestVerdictWins::test_rc1_refusal_with_a_crash_token_on_stdout_still_blocks` goes RED (2 failed, 9 passed).
Each control now proves the property it names: the rc-2 exclusion and the channel split are
separately load-bearing, and neither control passes on its own mutant.

**[H2] mypy Optional[dict] → Status: discharged.** `mypy` clean; `--stamp-baseline` exits 1
rather than passing `None`.

**[H3] ruff F401 → Status: discharged.** `ruff` clean.

## NEW — MEDIUM

**[M1] `check-plan-artifacts.py --check` fails: the rewritten plan no longer names two paths its config writes**
File: `.claude/plans/plan-qa-agents-hardening.md` (vs ops 12 and 13)
Evidence:
```
PLAN/CONFIG DRIFT - a plan omits a path its config writes:
  plan-qa-agents-hardening.md: does not name docs/HOOKS.md
  plan-qa-agents-hardening.md: does not name docs/PARALLEL_AGENTS.md
```
Reproduces in the real tree as well — a Round 2 regression (the Round 1 plan named both in its
step 6). Impact: a listed DoD gate is red; the plan hides two of its artifacts from review.
Class: `plan-omits-an-artifact-its-config-writes`
Fix: name `docs/HOOKS.md` and `docs/PARALLEL_AGENTS.md` verbatim in the plan's steps.

## NEW — LOW

**[L1] The one new full-suite failure is an execution artifact, not a regression — but it must be handled at merge**
File: `tests/test_delivery_contract_smoke.py::test_queued_ops_configs_validate_against_head`
Evidence: after execution the config reports `plan-qa-agents-hardening.ops.json: -> REJECTED`,
because its `find` anchors have been consumed. Validating the **unexecuted** config in the real
tree gives `-> APPROVED`, so the config itself is sound.
Class: `queued-ops-config-must-be-archived-after-execution`
Fix: move the config to `.claude/plans/archive/` with a README row as part of the merge commit,
or the suite ships red.

## Round 2 verdict rationale

Zero Critical, zero High → by the exit rule the review is over. M1 and L1 are follow-ups that
do not justify a fourth round; both are one-line fixes outside the shipped code paths.

=== REVIEW ===
SCORE: 92
DECISION: APPROVED
- [MINOR] check-plan-artifacts.py --check fails: plan-qa-agents-hardening.md does not name docs/HOOKS.md or docs/PARALLEL_AGENTS.md, both written by its ops config
- [MINOR] archive plan-qa-agents-hardening.ops.json after execution, or test_delivery_contract_smoke::test_queued_ops_configs_validate_against_head stays red
=== END REVIEW ===
