# Implementation Plan: Land the ops parse gate with the ambiguity verdict ordered first

## Overview

Land the "result gate" for the ops pipeline — a check that the text an edit *leaves behind*
still parses as Python — with two ordering rules built in rather than bolted on: the precise
**ambiguous-anchor** verdict outranks the generic parse verdict, and the gate is
**differential** (it refuses breakage a plan causes, not breakage it inherits).

## Scenario: (b) — the parse gate is NOT on main

Verified, not assumed:

- `grep -n 'parse_check\|check_parses\|PRECOMPILE\|ops_precompile'` on
  `.claude/operations/scripts/execute-json-ops.py` at `main` (d2ca6d0): **no matches**.
- `.claude/operations/scripts/ops_precompile.py`: **does not exist** on main.
- The gate lives only on `feat/ops-parse-gate`, in exactly two commits — `6257987`
  (`feat(ops): gate the pipeline on what the edit LEAVES...`) and `ceffecc` (a plan-index
  regeneration). That branch is **37 commits behind main**.

**Decision: re-implement on this branch, do not port the commits.** The Iron Law routes
implementation through ops.json and the operations engine, and a `git cherry-pick` is not an
engine operation. The two commits also carry `.claude/plans/INDEX.md`, `archive/README.md`
and archived plan artifacts that are stale by 37 commits and would conflict or resurrect
retired index rows. So this config **vendors the reviewed source of `ops_precompile.py` and
`test_ops_parse_gate.py`** (both taken from `6257987`, then modified as described below) and
re-applies the executor wiring as `code_edit` operations against main's current text. The
branch stays unmerged and can be deleted after this lands.

## The defect, as verified (the reported description is WRONG)

The report claimed the parse gate runs before the ambiguous-match check, so an ambiguous
anchor yields `parse-gate: result does not parse` instead of `Pattern appears N times
(ambiguous match)`. **That reproduces as a symptom but the stated cause is false.** Probed
against the branch executor in a scratch tree:

```
$ python3 execute-json-ops.py ops-ambig.json --dry-run --no-approval
Parse: every Python file this plan touches still parses after the edits
[1/1] CODE_EDIT: src/victim.py
  Edit 1: FAILED - Pattern appears 2 times in current content (ambiguous match)
RESULT-JSON: {... "status": "ambiguous-pattern"}
```

The gate **already defers on ambiguity**: `ops_precompile.check()` records an ambiguous
anchor in `misses`, which does not increment `bad`, so it returns `ok=True` and the executor's
precise verdict wins. Reordering the two checks would be a **no-op** for this case.

The real cause of the broken projection test is different. The fixture
`tests/test_validator_sequence_mode.py::make_project` writes
`code.py = "header\n    return 1\nfooter\n"`, which **is not valid Python** — `IndentationError:
unexpected indent`. The gate reads *absolutely*, so it refuses config `A` before it applies:

```
$ python3 execute-json-ops.py A.json --no-approval
PARSE GATE: refusing — applying this ops.json would leave a Python file that does not parse.
  BREAK code.py: unexpected indent at line 2
RESULT-JSON: {... "reason": "parse-gate: result does not parse"}
```

`A` never applies, so it never duplicates the anchor, so `B` is never ambiguous and
`test_projected_verdict_agrees_with_the_executor`'s `assert "ambiguous match" in applied.stdout`
fails. Under `--no-parse-check` the same pair produces `ambiguous match` normally, which
isolates the gate as the cause.

**So the fix is not a reorder — it is to make the parse check differential**, mirroring
`_new_shadows`, which already computes a `before` set and subtracts it. That is the real
inconsistency in the ported module: the shadow check is differential, the parse check is not.

The absolute reading has a second, worse consequence found while probing: **no ops.json could
edit any part of an already-unparseable `.py`** unless that single plan happened to make the
whole file parse — i.e. the Iron Law path could not be used to repair a syntax error, which is
exactly when it is most wanted.

The ordering invariant is nevertheless made **explicit and pinned** by this plan. Today it is
an emergent property of `bad` not being incremented, with no test binding it; a future edit to
`check()` could turn ambiguity into a refusal and nothing would object.

## Scope

- **In scope:** vendoring `ops_precompile.py` (differential parse check + explicit ordering
  comment), the executor wiring and `--no-parse-check`, the gate's behavioural test file with
  new mutation proofs, the `test_ops_hardening.py` injected-engine fixture, CHANGELOG.
- **Out of scope:** merging or deleting `feat/ops-parse-gate` (owner-gated); the known
  `unresolved`-path string-splitting limitation carried over from the branch; any change to
  `validate-config-json.py` or its projection logic; `--stamp-baseline`.

## Prerequisites

- Branch `fix/parse-gate-ordering` off `main` @ `d2ca6d0`, in worktree `.ck-agent-memory-wt`.
- `.claude/settings.local.json` with `ECC_HOOK_PROFILE=minimal` present (CONTRIBUTING.md).

## Files this config writes (all 5 paths)

| # | Path | Action |
|---|------|--------|
| 1 | `.claude/operations/scripts/ops_precompile.py` | Create |
| 2 | `tests/test_ops_parse_gate.py` | Create |
| 3 | `.claude/operations/scripts/execute-json-ops.py` | Modify (4 edits) |
| 4 | `tests/test_ops_hardening.py` | Modify (1 edit) |
| 5 | `CHANGELOG.md` | Modify (1 edit) |

### Post-review corrections (Tier 1, executed with `--no-approval` after the APPROVED 93 record)

`plan-parse-gate-ordering-review-fixes.ops.json` closes the reviewer's two remaining MINORs:
it adds the maintainer-facing note to `.ai/KNOWLEDGE_BASE.md` (a new engine-level gate that
future reviewers and implementers need written down) and corrects this document's own file
table header, which said 6 paths while listing 5. It writes `.ai/KNOWLEDGE_BASE.md` and
`.claude/plans/plan-parse-gate-ordering.md`.

## Implementation Steps

### Step 1: Create `.claude/operations/scripts/ops_precompile.py`
- **Action:** Create
- **Details:** The reviewed module from `6257987`, with three changes:
  1. New `_parsed_before(path, created)` helper — `ast.parse` of the on-disk text, returning
     `False` only for a genuine pre-existing `SyntaxError`. A created path has no baseline and
     returns `True` (judged absolutely). An `OSError` returns `True` — fails closed rather than
     granting an exemption on the strength of a file it could not read.
  2. The `except SyntaxError` branch consults it: a pre-existing break emits a `PRE` line and
     `continue`s **without incrementing `bad`**; a new break still emits `BREAK` and refuses.
  3. A new `unparsed` counter, incremented on the `PRE` branch. It is deliberately *not*
     `bad` — it does not refuse the run — but `--quiet` promises silence only when every
     touched file *parses*, and a `PRE` file did not. Without it, `check(..., quiet=True)`
     returned `[]` and a pre-existing break went completely silent. **This was found by
     test 6 below during staging, not by inspection**, and it is the one category of
     silent pass this module exists to prevent.
  4. The comment block above the `misses` loop states the ordering invariant explicitly and
     names the tests that pin it.
- Confirmed `ast.parse`-clean and `mypy --python-version 3.9 --check-untyped-defs` clean.
  (`ruff` excludes `.claude/`; `E501` is ignored repo-wide.)

### Step 2: Create `tests/test_ops_parse_gate.py`
- **Action:** Create
- **Details:** The 41 behavioural tests from `6257987`, plus 9 appended (see Tests).

### Step 3: Wire the gate into the executor
- **File:** `.claude/operations/scripts/execute-json-ops.py`
- **Action:** Modify — 4 `code_edit` edits, every `find` verified to occur exactly once:
  1. `PRECOMPILE_SCRIPT` + `check_parses()` inserted above `execute_json_config`, whose
     signature gains `check_parse: bool = True`. `check_parses` fails closed on a missing,
     unloadable or crashing checker.
  2. The gate call site, inserted **after** the drift/baseline report and **before** the
     `DRY RUN MODE` banner, so it runs in dry-run too. Its comment block records both
     ordering rules.
  3. `--no-parse-check` argparse flag.
  4. `main()` threads `check_parse=not args.no_parse_check`.
- **Ordering note:** the gate's *call site* stays where it is — it must precede any write. The
  ambiguity precedence is expressed by `ops_precompile` declining to refuse a miss, not by
  moving this call.

### Step 4: Carry the gate into the injected-engine fixture
- **File:** `tests/test_ops_hardening.py`
- **Action:** Modify — `_engine_with_injection` copies the engine to `tmp_path`; the engine
  resolves the gate relative to its own location and fails closed, so the fixture must copy
  `ops_precompile.py` alongside it. `pathlib` and `SCRIPTS_DIR` are already in scope.

### Step 5: CHANGELOG
- **File:** `CHANGELOG.md`
- **Action:** Modify — one `[Unreleased]` entry describing the gate and both ordering rules.

## Tests — mutation proof for every new behaviour

Nine tests appended in Step 2. Each names the mutation it kills.

**Ordering invariant (both directions — either alone fails to bind):**

1. `test_ambiguity_outranks_the_parse_gate_in_the_executor` — end-to-end. Asserts
   `ambiguous match` in stdout, `"status": "ambiguous-pattern"` in RESULT-JSON, **and**
   `PARSE GATE: refusing` absent, and the tree byte-identical. **Reds if the two checks are
   swapped back** (i.e. if `check()` refuses a miss): stdout loses the precise sentence and
   `operations` flattens to `[]`.
2. `test_the_parse_gate_still_fires_for_a_unique_match_that_breaks` — the opposite direction.
   A uniquely-matching edit leaving unparseable text is still refused, by the gate, before any
   write. **Reds if deferring on ambiguity is over-applied into a blanket no-op.**
3. `test_an_ambiguous_anchor_alone_does_not_fail_the_gate` — unit half: `ok is True`, and the
   report still *says* `ambiguous` and `not checked`. Pins that deferring is not silence.

**Differential parse check (both directions):**

4. `test_a_preexisting_syntax_error_is_not_blamed_on_this_plan` — `ok is True`, `PRE` present,
   `BREAK` absent. **Reds if the check is made absolute again** (drop `_parsed_before`).
5. `test_a_new_break_in_a_file_that_did_parse_is_still_refused` — `ok is False`, `BREAK`
   present, `PRE` absent. **Reds if the exemption leaks to files that did parse.**
6. `test_a_preexisting_break_is_still_reported_not_silently_passed` — with `quiet=True`, the
   `PRE` line is still emitted. **Reds if a withheld refusal becomes a silent pass.**
7. `test_a_plan_may_repair_an_already_broken_file` — the motivating consequence: an edit that
   fixes the indentation reports `OK`.
8. `test_a_created_file_has_no_baseline_and_is_judged_absolutely` — `file_create` of broken
   Python is refused. **Reds if created files are exempted too.**

**Regression the whole change exists to fix:**

9. `tests/test_validator_sequence_mode.py::TestSequenceProjection::test_projected_verdict_agrees_with_the_executor`
   passes unmodified. Verified in a staged tree: with the differential gate, `A.json` applies
   (`status: success`), `B.json` then reports
   `Edit 1: FAILED - Pattern appears 2 times in current content (ambiguous match)`.
   That test file is **not** touched by this config — the fix is in the gate, not the fixture.

### Mutation proofs, executed in a staged copy of this tree (not the worktree)

The config was applied to a scratch copy and each behaviour reverted in turn:

| Mutation | Tests turned red |
|---|---|
| `if not _parsed_before(...)` -> `if False` (parse check made absolute again) | `test_a_preexisting_syntax_error_is_not_blamed_on_this_plan`, `test_a_preexisting_break_is_still_reported_not_silently_passed`, **`test_projected_verdict_agrees_with_the_executor`** — 3 failed, 53 passed |
| `bad += 1` added to the `misses` loop (**ordering swapped back**) | `test_ambiguity_outranks_the_parse_gate_in_the_executor`, `test_an_ambiguous_anchor_alone_does_not_fail_the_gate`, `test_missing_anchor_withholds_the_verdict_without_refusing`, and `test_ops_hardening.py::test_failed_run_reports_failed_status_in_result_json` — 4 failed, 67 passed |
| `return bad == 0, ...` -> `return True, ...` (gate no-oped) | 24 failed, 25 passed, incl. `test_the_parse_gate_still_fires_for_a_unique_match_that_breaks` and `test_a_created_file_has_no_baseline_and_is_judged_absolutely` |

The second row is the proof the task asks for: swapping the two checks back **is** caught, and
it independently reds the RESULT-JSON contract test the branch author was worried about.

**Full gate:** `python3 -m pytest tests/ -q`, `ruff check`, `mypy`, `gen-docs.py --check`,
`check-plan-artifacts.py --check`, `shellcheck`.

## Rollback

The config's own pre-write backup restores every modified file
(`restore-backup.py --list`, then restore the `parse-gate-ordering-*` directory). Manually:

1. `git checkout -- .claude/operations/scripts/execute-json-ops.py tests/test_ops_hardening.py CHANGELOG.md`
2. `rm .claude/operations/scripts/ops_precompile.py tests/test_ops_parse_gate.py`

Both created files are new, so removal is complete; the three modified files are tracked at
`d2ca6d0` and revert cleanly. No migration, schema or state change is involved.

**Partial rollback (keep the gate, disable it):** `--no-parse-check` on any single run. It is
loud on stderr and does not persist.

## Risk Assessment

- **Low:** CHANGELOG; `test_ops_hardening.py` fixture (test-only); `test_ops_parse_gate.py`
  (new file, no existing importer).
- **Medium:** `ops_precompile.py` is new but is on the mypy path (`pyproject.toml` `files`
  includes `.claude/operations/scripts`) — verified clean. The differential check adds one
  `ast.parse` of the on-disk text per touched Python file; negligible, and it is the same read
  `_new_shadows` already performs.
- **High:** `execute-json-ops.py` is the operations engine — the single sanctioned write path
  for this repo (Iron Law), so a fault here blocks all further ops work. Mitigations: the gate
  fails **closed** and writes nothing on refusal; `--no-parse-check` is the break-glass for
  repairing the checker itself; the four `find` anchors were each confirmed to occur exactly
  once; and this config **must be executed with `--no-parse-check`**, because the gate it
  installs does not yet exist when the run starts and `check_parses` fails closed on a missing
  checker. Record that in the execution receipt.

## Open question (could not be settled from the tree)

Whether `feat/ops-parse-gate` should be **deleted** after this lands, or kept and merged for
commit provenance. Deleting a branch is user-visible and owner-gated (CLAUDE.md), so this plan
leaves it untouched and re-implements instead. Flagging that the two approaches will show as
duplicate work in history if the branch is later merged.
