# Implementation Plan: P0.5 Residuals (mypy blind spot, schema tightening, gate messaging)

**Revision 3** — round-2 blockers fixed: the distinguishability test now pins something, and
the shipped mutant attribution matches the plan. See "Revision 3 changes" at the end.

## Overview

Four residuals from `.ai/BACKLOG.md` §P0.5 / `review/code-review-triage.md`. Each was
re-measured by execution. **Two are real and fixed here (R1, R2). One is real but far
narrower than stated (R4a). Two are false premises and are dropped with no work invented
(R3 entirely; R4b's "fix" half).** 7 operations, 19 edits, 4 files changed plus 1 new and
1 extended test file.

## Premise verification (measured, not assumed)

| Residual | Claim | Measured verdict |
|---|---|---|
| R1 | `check_untyped_defs` off => blind spot | **CONFIRMED.** `mypy` = "Success: no issues found in 18 source files". `mypy --check-untyped-defs` = **3 errors in 2 files**. Small, so no staging needed. |
| R2 | nested typos validate clean | **CONFIRMED by execution.** Injecting `hooks["pre-commit"]["enabeld"]=True` validates successfully today. |
| R2b | naive tightening might reject the shipped config | **CONFIRMED — the trap is real.** Blanket `additionalProperties:false` fails with `hooks/pre-push: 'description' was unexpected`. Undeclared-but-present keys: `description` on `pre-commit`, `post-implement`, `pre-plan`, `pre-push`, `post-tool-use`, and `tools` on `post-tool-use`. All six are declared *before* the tightening. |
| **R3** | `install.sh` never delivers the schema, so doctor's check has nothing to match | **FALSE PREMISE — DROPPED. No change needed.** See below. |
| R4a | "verdict exists but doesn't authorise" and "no record" report identically | **PARTLY TRUE — scoped down to one edit.** `review-record.py` **already** separates them (exit 2 DRIFT / 3 NO RECORD / 4 NOT APPROVED, each with its own stderr block). Only `execute-json-ops.py`'s machine-readable reason collapses them. `review-record.py` is not touched. |
| R4b | E2E-09's 89/90 boundary | **FALSE PREMISE for "fix"; TRUE for "unpinned".** Measured: APPROVED 88 -> 4, 89 -> 4, 90 -> 0, 91 -> 0; REJECTED 40 -> 4; CONDITIONAL 95 -> 4. Already correct. **Test only, zero production change.** |

### R3: why it is a false premise (the correction)

The premise rests on `grep -c "config.schema.json" install.sh` = 0, which is true, and on
the inference that doctor therefore reads the schema out of the *installed project*. It does
not.

`find_claudekit_root()` (`src/claudekit/cli/main.py:62-88`) resolves the **kit source**, never
the CWD or the install target. Its order is: `$CLAUDEKIT_HOME` -> walk the parents of
`main.py`'s own `__file__` -> `<sys.prefix>/share/claudekit` -> `~/claudekit` -> `~/.claudekit`.
`_check_config_schema` (`:163-164`) then reads `<kit-root>/config.schema.json`. The installed
project is never consulted.

**My original measurement was contaminated and I withdraw it.** I ran
`CLAUDEKIT_HOME="$T" ck doctor --strict` inside the target, which *forced* the root to `$T` —
a directory that of course had no schema. That produced the `[!] not found` I reported. It was
an artifact of my own invocation, not the product's behaviour.

Re-measured correctly, with `CLAUDEKIT_HOME` unset:

```
$ ./install.sh <fresh-target> --full --force            # rc=0, no config.schema.json in target
$ cd <fresh-target> && env -u CLAUDEKIT_HOME ck doctor
[✓] Hooks config.json matches config.schema.json         # ALREADY PASSES, unchanged
  Warnings: 3/27
$ find_claudekit_root() -> /Users/omarmokhtar/IdeaProjects/claudekit   (schema exists: True)
```

The pip-installed configuration is covered too: `setup.py:54` ships `config.schema.json` into
`<prefix>/share/claudekit` (`MANIFEST.in:7`), which `main.py:80-83` resolves.

**Is there any configuration where the check genuinely fails?** Only if `CLAUDEKIT_HOME` is
pointed at a directory that has `.claude/agents` but no `config.schema.json` — i.e. at an
installed *project* rather than a kit checkout. Every reference in the tree
(`MANIFEST.in:4`, `.claude/plans/phase-1-HANDOFF.md:14`, `tests/test_gate_scope.py:177`)
documents `CLAUDEKIT_HOME` as pointing at a **checkout or install root**, never at a target
project. So there is no supported invocation that fails, and I am **not** proposing the
change. Op 4 (`install.sh`), op 7 (`tests/test_install.py`) and the R3 CHANGELOG bullet are
removed.

Two secondary points, both correct and worth recording even though R3 is dropped:
- The test I had written (`test_config_schema_is_installed`) asserted only file existence and
  byte-equality. It never ran `ck doctor` and never asserted the verdict line, so it would
  have gone green against a change with zero user-visible benefit. Had any part of R3
  survived, its test would have had to assert doctor's actual verdict from an installed
  tmpdir with `CLAUDEKIT_HOME` unset (pattern: `tests/test_gate_scope.py:196-203`).
- The proposed `cp` sat at `install.sh:360`, before the atomic staging swap (`:554-559`) and
  outside the manifest walk (`:564-588`). **General rule for future installer edits: a
  `$TARGET_DIR` write placed before the swap is neither staged nor manifest-tracked.**

## Scope

- **In Scope:** `pyproject.toml`, `config.schema.json`, `CHANGELOG.md`, `tests/`, plus `.claude/operations/scripts/restore-backup.py` and `.claude/operations/scripts/execute-json-ops.py` (explicitly granted).
- **Out of Scope (file ownership — parallel workstreams):** `templates/`, `.claude/hooks/`, `.ai/BACKLOG.md`, `.ai/REVIEW_GUIDE.md`, `src/claudekit/cli/main.py`. **`install.sh` is no longer touched at all.**
- **Out of Scope (deliberately):** the other two P0.5 approval-gate residuals (`recorded` computed before `_gate_applies()`; the `ECC_OPS_GATE_ALL=1` migration having no test). Only messaging was requested.

## Prerequisites

- `jsonschema` from `tests/requirements.txt` (pinned `4.25.1`, a **test** dependency). It is imported lazily and optionally by `src/claudekit/cli/main.py:170` inside a `try/except ImportError`, and must never become a *hard* runtime dependency. This plan adds no import of it outside `tests/`.
- `ECC_HOOK_PROFILE=minimal` in `.claude/settings.local.json` (repo self-hosting gotcha).

## Implementation Steps

### Step 1: Turn on `check_untyped_defs`, scoping out the file we do not own
- **File:** `pyproject.toml` — **Modify** (op 1)
- Add `check_untyped_defs = true` to `[tool.mypy]`.
- Add `[[tool.mypy.overrides]]` for `claudekit.cli.main` setting `check_untyped_defs = false`, with an inline comment naming the exact debt (`main.py:581`, `identical` and `differs`) and stating the override is removed when those annotations land. This is **not** `ignore_errors`: it disables one flag for one module, and only because `main.py` is owned by a parallel workstream this batch.
- **Verified:** with this override and step 2 unapplied, `mypy` reports exactly 1 error (the `restore-backup.py` one), proving the override isolates `main.py`. With step 2 applied, `mypy` exits 0 and the DoD gate stays green.

### Step 2: Fix the one real `check_untyped_defs` error we own
- **File:** `.claude/operations/scripts/restore-backup.py` — **Modify** (op 2, 2 edits)
- Add `from typing import List` after `import sys` (module-alphabetical, matching the existing block).
- `restored_files = []` -> `restored_files: List[str] = []`. It is only ever appended `file_path`, a `str`. **No `# type: ignore` anywhere in this plan.**

### Step 3: Close every nested object in the config schema
- **File:** `config.schema.json` — **Modify** (op 3, 13 edits)
- First declare the six keys the shipped config already uses but the schema never declared: `description` on the five bare hooks, `tools` on `post-tool-use`. **Order matters** — tightening before declaring rejects a valid config.
- Then add `"additionalProperties": false` to: the `hooks` container, all 9 hook option objects, `global`, `project`, `security`.
- Each edit's `find` is the whole literal block for one named object (unique by name), so the diff is readable per-object rather than one 10 KB blob.
- Closing `hooks` itself means a typo'd *hook name* is rejected. Intended — see Risk Assessment.

### Step 4: Name the approval-gate refusal cause
- **File:** `.claude/operations/scripts/execute-json-ops.py` — **Modify** (op 4)
- Replace the single `f"approval-gate: review-record check exit {code} ..."` return with a `{2,3,4} -> phrase` map: drift / no record exists / a record exists but its verdict does not authorise execution. The numeric code, slug and `why` are **retained** in brackets; an unmapped code falls back to the old generic phrasing, so the gate stays fail-closed (every non-zero code still returns `False`). Stdlib only.

### Steps 5-6: Tests
- **`tests/test_config_schema.py`** — **Create** (op 5). New file.
- **`tests/test_ops_approval_gate.py`** — **Modify** (op 6), two classes appended.

### Step 7: CHANGELOG
- **File:** `CHANGELOG.md` — **Modify** (op 7). Two bullets at the top of `[Unreleased] -> ### Fixed`: R2 (user-visible: changes what configs validate) and R4a (user-visible: `RESULT-JSON` reason text). **R1 is deliberately omitted — maintainer-only, no user-observable effect. The R3 bullet is removed.**

## Testing Strategy — mutants and the cases that must flip

| Test | Surgical mutant | Must flip |
|---|---|---|
| `test_config_schema.py::test_misspelled_nested_key_is_rejected` | Delete `"additionalProperties": false` from the `pre-commit` (or `global`/`project`/`security`) object | That parametrised case FAILS (typo validates) |
| `::test_misspelled_hook_name_is_rejected` | Delete `"additionalProperties": false` from the `hooks` container | FAILS |
| `::test_shipped_config_validates` | Delete the added `"description"` declaration from `pre-push` | FAILS — the guard against a tightening that rejects a valid config |
| `::test_unknown_root_key_still_rejected` | Delete root `additionalProperties` | FAILS (regression guard on what already worked) |
| `test_ops_approval_gate.py::test_refusal_causes_are_distinguishable` | Collapse the `cause` map back to one string | FAILS (`len(reasons) == 3` -> 1) |
| same | Revert op 4 entirely (unfixed executor) | FAILS via `_cause`'s format assertion |
| `::test_unauthorised_verdict_names_the_verdict` | Map exit 4 to the exit-2 (DRIFT) phrase | FAILS on `assert "drift" not in reason` |
| `::test_drift_names_drift_not_absence` | Map exit 2 to the exit-3 phrase | FAILS |
| `::test_score_below_threshold_refuses` | `APPROVAL_THRESHOLD = 89` | FAILS at 89 |
| `::test_score_at_threshold_executes` | `APPROVAL_THRESHOLD = 91`, **or `score < T` -> `score <= T`** | FAILS at 90 (guards against over-blocking) |

`test_refusal_causes_are_distinguishable` compares only the **cause segment**, not the whole
reason. Comparing whole reasons pins nothing, because the exit code stays in the string: the
collapse mutant still yields three distinct reasons, and so does the *pre-fix* message. Measured
pre-fix, the `why` clause is **identical** across all three cases (`config lives in a plans/
directory`), so the exit code is the sole differentiator. The helper therefore also asserts the
new `" [review-record exit"` sentinel is present, which is what makes the test fail against the
unfixed executor instead of passing on it. Verified by driving the real method:

| world | `len(causes)` | verdict |
|---|---|---|
| fixed (correct) | 3 | PASSES |
| collapse mutant (one constant `cause`) | 1 | FAILS |
| unfixed executor (today) | — | FAILS on the format assertion |

The threshold rows were **corrected in revision 2**: `score < T` -> `score <= T` does *not* flip
`test_score_below_threshold_refuses` (89 still refuses under `<=`); it flips
`test_score_at_threshold_executes`. The pair still pins the boundary from both sides — only my
attribution of which mutant hits which row was wrong.

**All gate assertions are on exit codes and the tree**, not summary text: `proc.returncode != 0` / `== 0`, `result_json(...)["status"]`, and `target_text(project) == ORIGINAL` (refused runs leave the tree byte-identical). The `reason` substring assertions are the one place text is checked, because *distinctness of the message* is the thing under test.

**Fixture location:** the approval-gate tests reuse the existing `project` fixture (`tmp_path`) and invoke the executor directly with `ECC_HOOK_PROFILE=minimal`. **No test in this plan executes a hook**, so the `ops-enforcement.sh:43` `$TMPDIR` exemption (`/private/tmp/claude-*`, `/tmp/claude-*`, `/var/folders/*`) cannot mask a failure here.

**Verification commands (run after execution, in order):**
```bash
mypy --check-untyped-defs      # before ops 1+2: expect 3 errors in 2 files
mypy                           # after ops 1+2: must be "Success"
python3 -m pytest tests/test_config_schema.py tests/test_ops_approval_gate.py -q
python3 -m pytest tests/ -q
ruff check src/ tests/ scripts/
python3 -c "import json,jsonschema; jsonschema.validate(
  json.load(open('.claude/hooks/config.json')), json.load(open('config.schema.json')))"
python3 scripts/gen-docs.py --check && python3 scripts/gen-registry.py --check
```

## Rollback Plan

- Every op is a `code_edit` or one new-file create; `git checkout -- <path>` reverts any step, `git rm tests/test_config_schema.py` removes the only new file. The executor also writes a timestamped `backups/residuals-*` directory.
- Steps are independent: R1 (ops 1-2), R2 (op 3 + op 5), R4 (op 4 + op 6). Only op 7 references R2 and R4a.
- Highest-consequence revert is op 3: if a config is found to legitimately use an undeclared key, revert op 3 and op 5 together and re-enumerate.

## Risk Assessment

- **Low — R1 (ops 1-2).** 3 measured errors, 1 fixed, 2 scoped out by a documented single-flag override. No runtime behaviour changes.
- **Low — R4a/R4b (ops 4, 6).** Op 4 adds strings to a message that already refuses; it cannot make a refusing run execute or vice versa, and the `.get(code, generic)` fallback preserves fail-closed behaviour. Op 6 is test-only. R4b changes no production code.
- **Medium — R2 (op 3).** Tightening a schema can reject configs that used to pass. Mitigated by enumerating every key present in the repo config *and* the installer-generated config (the installer copies the repo `config.json` and overwrites only `project.{build,test,lint,coverage}_cmd`, so the key set is identical — verified; `templates/mcp/mcp-settings.json` is not governed by this schema). The tightened schema was executed against the real config: validates clean, 8 typo mutants rejected, 0 leaks. **Residual risk:** a user who hand-added a custom hook name or option key will now see a `ck doctor` failure. That is the intended signal (it was never doing anything), and it is called out in the CHANGELOG.
- **Blast radius:** `execute-json-ops.py` is the operations engine — a hub. The edit is confined to one `return` inside `check_approval()`, covered by the existing 9-case matrix plus 6 new cases. No `.claude/project-graph.json` exists, so no hub query was possible.

## Revision 3 changes

1. **`test_refusal_causes_are_distinguishable` now pins something.** As written in revision 2 it
   compared whole reason strings and passed in all three worlds — including against unfixed
   code. It now compares only the cause segment via a `_cause()` helper that asserts the new
   format sentinel. Proven to flip both ways (table above). This was the one test in the batch
   that pinned nothing, and the reviewer was right to block on it.
   *Note back to the reviewer:* the proposed fix (`split(" [review-record exit")[0]` alone) fixes
   the collapse mutant but still **passes against unfixed code**, because the pre-fix string
   lacks the sentinel so `split` returns it whole and the embedded exit codes keep the three
   distinct. The format assertion is what closes that half; both halves are now verified.
2. **Shipped mutant attribution corrected** in `TestApprovalThresholdBoundary`'s docstring. The
   plan prose was fixed in revision 2 but the string that lands in the repo still carried the
   disproved attribution.
3. **Exit-2 / exit-4 discrimination made explicit** — `test_unauthorised_verdict_names_the_verdict`
   gains `assert "drift" not in reason`, since `"does not authorise execution"` appears in both
   phrases. Verified: that substring is in both; `"drift"` is in the code-2 phrase only.
4. **Orphaned `R3` dropped** from op 7's description; **quad-quote** docstring opener replaced.

Re-verified after these edits: `py_compile` OK, `ruff check` clean, exactly 2 blank lines before
the new class, single trailing newline, all `find` anchors still unique, validator APPROVED.

## Revision 2 changes

1. **R3 dropped entirely** (ops 4 and 7 of revision 1, plus its CHANGELOG bullet). False premise; my supporting measurement was contaminated by my own `CLAUDEKIT_HOME` override. Evidence and the "is there any failing configuration?" analysis are above. `install.sh` and `tests/test_install.py` are no longer touched.
2. **Op 6's `add_after` splice corrected.** `execute-json-ops.py:700-703` splices `find + add_after` inline, and the anchor ends at `assert target_text(project) == PATCHED` **without** its terminating newline (`tests/test_ops_approval_gate.py:206`). The payload now begins `\n\n\n` (two blank lines before the new class) and ends with **no** trailing newline, letting the file's original newline terminate it. Verified by materialising the spliced file: exactly 2 blank lines before `class TestRefusalCauseIsSpecific`, file ends with exactly one `\n`, `py_compile` OK. **General lesson recorded: a leading `\n` is necessary but not sufficient — you must also account for whether the anchor ends mid-line, and for what the payload's own tail collides with.**
3. **`jsonschema` sentence corrected** in the plan and in op 5's module docstring. The old wording ("nothing in `src/` ... imports it") was false — `main.py:170` imports it lazily under `except ImportError`. Now: "imported lazily and optionally by `main.py:170`; must never become a *hard* runtime dependency."
4. **R4b mutant table rows swapped** (see the note under the table).

### One correction back to the reviewer, on the op-6 finding

The **defect was real and the fix is applied**, but the stated mechanism does not reproduce.
The claim was that `ruff check src/ tests/ scripts/` would fail on E302/W391. Measured on the
buggy splice:

```
$ ruff check --config pyproject.toml <buggy-file>
All checks passed!
$ ruff check --select E302,W391 <buggy-file>
warning: Selection `E302` has no effect because preview is not enabled.
warning: Selection `W391` has no effect because preview is not enabled.
All checks passed!
```

`select = ["E","F","W","I"]` (`pyproject.toml:51-52`) does not enable E302/W391 — ruff gates
those behind `preview`, which is set nowhere in this repo. Separately, CI's ruff step
(`.github/workflows/ci.yml:63`) is `ruff check src/claudekit scripts` and does not lint
`tests/` at all. So the buggy version would have shipped **green**, which makes the finding
more interesting rather than less: it is a real style defect that **no gate in this repo would
have caught**. I kept the fix (it is free and correct) and flag the gate gap as a follow-up.

## Follow-ups for the owner (not done here)

1. **`src/claudekit/cli/main.py:581`** — annotate `identical` and `differs` (`List[str]`), then delete the `[[tool.mypy.overrides]]` block from step 1. That is the whole remaining distance to `check_untyped_defs` repo-wide. Owned by a parallel workstream this batch.
2. **Lint gate gap** — E302/W391 are not enforced (ruff preview off), and CI does not lint `tests/` at all while the DoD command does. Either enable `preview` for the pycodestyle subset or align CI's ruff paths with the DoD command; today the two disagree.
3. **Remaining P0.5 approval-gate residuals** — `recorded` is computed before `_gate_applies()`, so a transient lookup fault refuses ungated ad-hoc configs; and the refusal names `slugs[0]`, which for an `ops.json` outside a plans dir is the literal slug `'ops'` (measured), pointing at a plan that does not exist.
4. **`ECC_OPS_GATE_ALL=1` default-flip migration** still has no test and no CI job.
5. **`CLAUDEKIT_HOME` foot-gun** — pointing it at an installed project (rather than a kit checkout) makes doctor's schema check warn, and `--strict` then fails. Undocumented and easy to hit; consider validating that the target looks like a kit root, or falling back to the source root when the schema is absent.
