# Implementation Plan: Enforce the review-record approval gate inside the executor (G2)

## Overview

`review-record.py check` binds a reviewer verdict to sha256(ops.json), but nothing calls it:
the requirement exists only as prose in `.claude/commands/implement.md:39`, and the implementer's
tool grant (`Bash(python3 .claude/operations/scripts/*)`) lets it run `execute-json-ops.py`
directly. A drifted or never-reviewed ops.json executes cleanly. This plan moves the gate into
the only code path that can mutate the tree — `execute_json_config()` — so removing it is
observable, and deletes the duplicated prose so there is one source of truth.

## Scope

- **In scope:** approval enforcement in `execute-json-ops.py`, an explicit `--no-approval`
  escape hatch, a behavioral test file, and the `implement.md` STEP 0 rewrite.
- **Out of scope:** `review-record.py` (unchanged — the executor imports and reuses it),
  hooks, agent prompts, settings.json, CHANGELOG/docs, the evals corpus.

## Prerequisites

None. `review-record.py` already implements `record_paths`, `cmd_check` and the exit-code
contract (0 ok / 2 DRIFT / 3 no record / 4 not authorising).

## Design decisions (evidence-based)

1. **Inverse resolution without touching review-record.py.** `resolve_ops()` maps plan.md →
   ops.json across four naming forms (`plan-x.ops.json`, `ops-x.json`, `x.ops.json`, `x.json`).
   `_approval_slugs()` inverts all four from the config filename, and additionally tries the
   config's own `"plan"` field, so a copy/rename does not shed a recorded verdict. `cmd_check`
   only uses its `plan` argument for `plan_slug()` — it never opens the file — so the executor
   calls it with a synthetic `plan-<slug>.md`. No new subcommand is required.
2. **Reuse, do not reimplement.** `review-record.py` is imported by path via `importlib`
   (its filename is not a module name) and `cmd_check` is invoked with an
   `argparse.Namespace`. Drift and threshold rules stay in exactly one place.
3. **Gate scope (revised after review — MAJOR 1).** `_gate_applies()` gates a config when ANY
   of: `ECC_OPS_GATE_ALL=1` (blanket, fail-closed everywhere); the config sits in a `plans/`
   directory; a review record already exists for a candidate slug; or a plan document
   (`plan-<slug>.md` / `<slug>.md`) exists beside the config or in the project's
   `.claude/plans/`. The last clause is what closes the "write it to /tmp and run it" hole for
   pipeline work: shedding the gate now requires abandoning the plan document too.
   Blanket gating is NOT yet the default only because four suites this workstream does not own
   execute ungated ad-hoc configs (`test_worktree_manager.py:230` runs `wt/ops.json`;
   `test_ops_hardening.py`, `test_run_command_ops.py`, `test_work_loss_protection.py` run temp
   configs with no records anywhere). `ECC_OPS_GATE_ALL` is the migration switch: once those
   suites set an opt-out, flip the default in `_gate_applies()` — a one-line change.
4. **Dry-run is exempt.** `--dry-run` writes nothing: backup dir, manifest, `atomic_write`
   and transaction registration are all behind `if not dry_run` (execute-json-ops.py:795, 815,
   822). It is also the pre-review sanity check that `/plan` and `implement.md` STEP 0 step 4
   run *before* any record can exist. Gating it would make the workflow unrunnable.
5. **Fail CLOSED.** Missing/unimportable `review-record.py`, an unreadable record, or a raised
   exception all refuse a gated config. Only the ungated population (no record, not in `plans/`)
   passes on module-load failure.
6. **Escape hatch.** `--no-approval` prints `Approval: BYPASSED (--no-approval)` on stdout and a
   `!!! APPROVAL GATE BYPASSED` banner on stderr. Honest limitation, stated in the docstring: a
   deliberate rename to an unrecorded slug is equivalent to `--no-approval`, only less visible.
   The gate closes the *silent* bypass, not a determined one — consistent with the repo's
   "speed bump, not a sandbox" framing. See the SECURITY limitation in Risks.

## Implementation Steps

### Step 1: Behavioral test file
- **File:** `tests/test_ops_approval_gate.py`
- **Action:** Create
- **Details:** 13 tests over the full matrix — no record / drift / CONDITIONAL / REJECTED /
  REVISE / APPROVED-below-90 / APPROVED-90+ / `--no-approval` / `--dry-run` / config outside
  `plans/` (ungated) / config outside `plans/` with a sibling plan.md (gated) /
  `ECC_OPS_GATE_ALL=1` on an ad-hoc config (gated) / renamed config with a live record. The
  no-record test also parses the `RESULT-JSON:` line and asserts `status == "failed"` and a
  `reason` starting with `approval-gate:` — refusal and ordinary operation failure share exit
  code 1, so that reason string is the entire distinguishing contract and must be bound. Every test builds a throwaway project under
  `tmp_path` (never the repo tree), forces `ECC_HOOK_PROFILE=minimal`, runs the real executor
  as a subprocess with `cwd` = that project, and asserts on the *working tree* afterwards
  (refused runs leave `src/app.py` byte-identical), not on internal structure.

### Step 2: Approval gate in the executor
- **File:** `.claude/operations/scripts/execute-json-ops.py`
- **Action:** Modify (4 edits)
- **Details:**
  - Add `APPROVAL_SCRIPT`, `PLANS_DIR_NAMES`, `_approval_slugs()`, `_load_review_record()`,
    `check_approval()` above `execute_json_config`, and widen its signature with
    `require_approval: bool = True` (default-on: an unaware caller gets the gate).
  - Invoke the gate immediately after the plan/format/operations banner and before the
    baseline check, i.e. before the lock, backup dir, manifest and any write. Refusal prints an
    actionable message and emits `RESULT-JSON` with `reason="approval-gate: ..."`, returning
    `False` → exit 1. Transaction/rollback, backups, post-state snapshot, signal handling and
    the single-emission `RESULT-JSON` invariant are untouched.
  - Defensive details from review: `_load_review_record()` documents why the module is
    deliberately not registered in `sys.modules`; `check_approval()` verifies `record_paths`
    and `cmd_check` exist before use and treats any exception from the `argparse.Namespace`
    call shape as a refusal; `argparse.Namespace` is used directly, matching the file's
    existing import style.
  - `main()` gains `--no-approval` and threads `require_approval=not args.no_approval`.

### Step 3: Remove the duplicated prose check
- **File:** `.claude/commands/implement.md`
- **Action:** Modify (1 edit)
- **Details:** STEP 0 item 1 no longer instructs the implementer to run
  `review-record.py resolve|check` or to interpret exit codes 2/3/4; it states that the executor
  enforces the record, how to react to an `APPROVAL GATE:` refusal, and that `--no-approval`
  requires explicit user authorization. Steps 2–6 (validator, dry-run, clean tree) unchanged.

## Testing Strategy

- `python3 -m pytest tests/test_ops_approval_gate.py -q` — 11 behavioral tests.
- Regression: `python3 -m pytest tests/test_ops_hardening.py tests/test_run_command_ops.py
  tests/test_work_loss_protection.py tests/test_worktree_manager.py tests/test_validator.py -q`
  must stay green (they exercise ungated ad-hoc configs).
- Full suite + `ruff check src/ tests/ scripts/` + `mypy` + `python3 scripts/gen-docs.py --check`.
- Pre-verified during planning: the patch was applied to a scratch copy of the executor and the
  new suite run against it — 13 passed; `py_compile` clean; `ruff --line-length 100` reports only
  the 4 pre-existing findings already present in the unpatched file (`.claude/` is not in the
  repo's ruff target set).

## Rollback Plan

The executor edits are additive and confined to new helpers plus one guarded block; reverting
means restoring `.claude/operations/scripts/execute-json-ops.py` and `.claude/commands/implement.md`
from the engine's own `backups/<plan>-<timestamp>/` (or `git checkout --`) and deleting
`tests/test_ops_approval_gate.py`. No data migration, no state to unwind.

## Risk Assessment

- **Low:** dry-run and ad-hoc-config behavior unchanged (covered by two dedicated tests);
  additive CLI flag; no change to transaction/rollback/RESULT-JSON paths.
- **SECURITY (residual, accepted, HIGH visibility / LOW likelihood):** the gate is heuristic,
  not mandatory, until `ECC_OPS_GATE_ALL=1` becomes the default. A caller that writes an
  ops.json to a path with no `plans/` parent, no matching review record and no matching plan
  document — e.g. renaming the slug — executes ungated. This is materially reachable today:
  `.claude/agents/implementer.md:8` grants unrestricted `Bash` (contradicting
  `INVOCATION.md:100`; owned by another workstream and being fixed at integration). The change
  is still a strict improvement — it removes the *accidental* and *silent* bypass and makes the
  deliberate one require forgery — but it must not be described as an unconditional gate.
  Closing it fully = the `_gate_applies()` default flip plus an opt-out in the four sibling
  suites.
- **Low — evals corpus (NOT owned here):** the fixture `implementer-no-fabrication` ships
  `.claude/plans/ops-negate.json` with no review record. `tests/test_evals.py:40-57` only
  `json.loads` that fixture and never invokes the executor, so the suite is unaffected; only a
  live `ck eval` run of that eval would now be refused. The owner of `.claude/evals/**` should
  seed a record or pass `--no-approval` in the eval's commands.
- **Medium — agent-facing behavior change:** the implementer will start seeing `APPROVAL GATE:`
  refusals for plans that were never reviewed. That is the intended outcome, but the agent
  prompt (`.claude/agents/implementer.md`, another workstream) may still describe the old
  prose check; whoever owns it should align it with `implement.md`.
- **Medium — documentation:** this is a user-visible behavior change and needs a CHANGELOG
  `[Unreleased]` entry. `CHANGELOG.md` is owned by another workstream — flagged, not edited.
- **High:** none. The gate cannot leave a partial tree: it refuses before the lock, backup
  directory, manifest and every write.

## Deployment note (execution ordering — REQUIRED)

This workstream must be executed **LAST** in its batch. Five sibling `.claude/plans/*.ops.json`
configs from the same batch already exist; the moment this gate lands they all become gated
(they sit in a `plans/` directory and own plan documents), and any sibling executed afterwards
without a `review-record.py write` record will hard-fail with `APPROVAL GATE:`. Before or
immediately after landing this change, write a review record for every pending sibling config,
or execute them first. Anyone replaying this plan later must preserve that ordering.

## Cross-workstream dependencies (do not edit here)

- `CHANGELOG.md` — `[Unreleased]` entry for the new gate and `--no-approval`.
- `.claude/agents/implementer.md` — drop any surviving `review-record.py check` instruction.
- `.claude/evals/**` (fixture for `implementer-no-fabrication`) — see Medium risk above.
- `review-record.py` — deliberately unchanged; no new subcommand needed.
