# Implementation Plan: Approval gate binds `operations/<slug>/ops.json` configs

Tier 3 (security-relevant: the executor's approval gate). Branch `fix/approval-gate-ops-dir-layout`.
Ops config: `.claude/plans/plan-approval-gate-ops-dir-layout.ops.json` (9 ops, 3 phases).

## Overview

Some projects' CLAUDE.md requires ops configs at `operations/<plan-slug>/ops.json`
(AppiumLens 1311 configs, LeanApis 12, qa-agents 3). These projects can never get a
verdict recorded. `resolve` cannot find the config. The record key is taken from the
filename, so every plan keys as `ops`. The reviewer's anchored block also gets lost
between the Task reply and the saved report. This plan fixes all three, and fixes the
same key logic in the third place that has it.

## Phase 0: Design precheck

**Ownership model.** A review record belongs to one ops config. Its key comes from
the config's own path, and the same function derives it on both sides:
`review-record.py ops_slug()` (write/check/diff) and
`execute-json-ops.py _approval_slugs()` (the executor gate).
`scripts/check-plan-artifacts.py resolve_plan()` repeats the same slug derivation to
find the plan for a config.

**Where the bug is.** For the directory layout, the config's identity is its
**directory name**, but all three derive it from the **filename**, which is always
`ops.json`. That is why every such config keys as `ops`. Separately, `resolve_ops()`
only looks in `.claude/plans`, so it never finds `operations/`.

**The fix.** Update exactly the three key derivations and the one resolver:

- A bare `ops.json` keys by its resolved parent directory name **verbatim**: no
  suffix strip and no `plan-`/`ops-` strip. Revision 2 changed this; see below.
- The resolver adds two candidates:
  - `operations/<slug>/ops.json`
  - `operations/<plan-stem>/ops.json`

  Both are rooted at the plan's own project (`_project_root(start=plans_dir)`), not cwd.

**Rejection-brief search.** Query: `approval gate ops slug resolve`. 14 matches came back
(e2e-lane-a, iron-law-enforcement-hook, reflection-lifecycle-gates,
e2e-pipeline-test-task). After reading them, none concern record keying or ops resolution;
the matches are only on shared words.

Two lessons from those briefs do apply:

1. **No claimed mutation proof without running it.** Every red/green claim below was
   run (see Testing Strategy).
2. **The gate must bind on a real execution, not `--dry-run`.** The executor tests run
   the real executor without `--dry-run`.

## Revision 2 (reviewer round 1: 84 REVISE, one MAJOR)

**The finding.** v1 applied the `plan-`/`ops-` strip to directory-derived names too.
`operations/x/ops.json`, `operations/ops-x/ops.json` and `operations/plan-x/ops.json`
therefore all keyed as `x`. Three different configs shared one record, and each
approval overwrote the last. No test covered it.

**The change.** A directory-derived key is now the directory name verbatim, in all
three places:
- `ops_slug()`: returns the name directly
- `_approval_slugs()`: puts it first in the candidate list and skips the strip
- `resolve_plan()`: skips the strip

Each directory still resolves from its plan, because `resolve_ops()` tries both
`operations/<slug>/` and `operations/<plan-stem>/`:

| Plan file | Directories tried |
|---|---|
| `plan-x.md` | `operations/x`, `operations/plan-x` |
| `plan-ops-x.md` | `operations/ops-x` |

The executor derives the same verbatim key from the path it is given.

**Edge cases.**
- A directory named exactly `ops-` or `plan-` keys as `ops-` or `plan-`. No strip
  can empty it.
- An empty directory name only happens for `/ops.json`. It falls back to the
  existing filename derivation (`ops`).
- `.` and `..` cannot occur after `resolve()`.
- A **leading-dot** directory `.x` keys as `.x`, but `record_paths()` strips leading
  dots, so it shares a record file with `x`. This is a pre-existing property of
  that sanitiser: it already maps `a b` and `a_b` to one file for flat configs.
  It stays fail-closed: when one write clobbers the other, `check` on the
  clobbered config exits 2 (DRIFT). A test pins this. `record_paths()` is not
  changed here, because changing it would move existing flat keys.

**The `plan` field fallback cannot authorise the wrong config.**
`_approval_slugs()` still also tries the config's stripped `plan` field. Take
`operations/ops-alpha/ops.json` declaring `"plan": "alpha"`: it yields
`["ops-alpha", "alpha"]` and can reach alpha's record, in two ways:
1. Through `check_approval`'s `recorded` list.
2. Through `cmd_check`'s legacy `plan_slug` fallback.

Either way, `cmd_check` compares **sha256 of the config being executed** with the
record's `ops_sha256`. Any byte difference means DRIFT, exit 2, refused. A test
pins this with a real execution: the target stays byte-identical.

Only a byte-identical copy passes. That copy is the exact artifact that was approved,
the same content binding the existing `test_renamed_config_with_live_record_still_gated`
relies on.

## Scope

**In scope**
- `.claude/operations/scripts/review-record.py`:
  - `resolve_ops()` resolves the directory layout.
  - `ops_slug()` keys a bare ops.json by its directory.
  - `_project_root()` accepts an optional `start` path.
  - The `cmd_resolve` "tried" message lists the new form.
- `.claude/operations/scripts/execute-json-ops.py`: `_approval_slugs()` gets the same
  directory keying.
- `scripts/check-plan-artifacts.py`: `resolve_plan()` gets the same directory keying
  (third consumer of the key).
- `.claude/agents/reviewer.md` and `.claude/commands/review.md`: prompt fix for gap 3.
- Tests:
  - `tests/test_review_record.py`
  - `tests/test_ops_approval_gate.py`
  - `tests/test_check_plan_artifacts.py`
- `CHANGELOG.md` `[Unreleased]` entry.

**Out of scope** (listed so the reviewer can see these were considered)
- **Migrating or deleting the stale record.** `.claude/reports/reviews/ops.json` is a
  tracked record keyed `ops`, bound to `.claude/plans/request-shaping/ops.json`
  (APPROVED 91, 2026-09-01). After this change nothing reads it. Deleting a tracked
  file is owner-gated, so it stays.
- **`.claude/plans/ops-<slug>/ops.json` (ClaudeKit's own archive layout).** It now
  keys by directory, which is correct, but `resolve_ops()` does not search
  `.claude/plans/*/`. See open questions.
- **Hook patterns.** `hooks/lib.sh` `OPS_FIND_EXPR` does not match a bare `ops.json`;
  `OPS_REGEX` already does. This is validation scope, not approval.
- **Gating on the directory alone.** `_gate_applies()` does not treat `operations/`
  as a gated directory by itself. A directory-layout config is gated only when a
  `plan-<slug>.md` exists or a record exists, the same as any config outside
  `plans/`.

## Prerequisites

- Checked-out branch `fix/approval-gate-ops-dir-layout`; gitignored
  `.claude/settings.local.json` present (`ECC_HOOK_PROFILE=minimal`).
- **Order of steps, because of the stamp trap.** If `--stamp-baseline` is used, stamp
  this ops.json **before** recording the review verdict. Stamping afterwards changes
  the hash and the gate reports DRIFT.

## Implementation Steps

### Phase 1: Core key and resolution (ops `p1-review-record`, `p1-executor-slugs`, `p1-plan-artifacts`)

#### Step 1: `review-record.py`
- **File:** `.claude/operations/scripts/review-record.py`
- **Action:** Modify (op `p1-review-record`, 6 edits)
- **Details:**
  1. Add the module constants `DIR_LAYOUT_ROOT = "operations"` and
     `DIR_LAYOUT_NAME = "ops.json"` just above `plan_slug()`.
  2. `ops_slug()`: when the filename is exactly `ops.json` and the resolved parent
     has a name, return that name **verbatim**. Otherwise fall through to the
     unchanged suffix and prefix strip.
     - `resolve()` matters: a relative `ops.json` given from inside its own directory
       must still key by that directory.
     - Flat names never reach this branch, so their keys stay the same.
     - Update the docstring to match.
  3. `resolve_ops()`: collect the four flat candidates as before, plus
     `_project_root(plans_dir)/operations/{slug}/ops.json` and
     `.../operations/{stem}/ops.json`.
     - If the plan has no `plan-` prefix, slug and stem are the same path and the
       existing `not in seen` check removes the duplicate.
     - More than one existing candidate still gives **AMBIGUOUS** (return None,
       exit 3 from `resolve`).
  4. `cmd_resolve`: the "tried" line adds `operations/{slug}/ops.json`.
  5. `_project_root(start=None)`: walk up from `Path(start).resolve()` when `start` is
     given, otherwise from cwd.
     - Every existing caller passes nothing, so their behavior is unchanged.
     - Rooting at the plan means a caller in a subdirectory, or in another project,
       resolves the plan's own `operations/`, not cwd's.

#### Step 2: executor approval slugs
- **File:** `.claude/operations/scripts/execute-json-ops.py`
- **Action:** Modify (op `p1-executor-slugs`)
- **Details:**
  - `_approval_slugs()`: for a bare `ops.json` whose resolved parent has a name,
    append that name **verbatim** as the first candidate and skip the filename
    strip. Flat configs keep the unchanged suffix and prefix strip.
  - The config's `plan` field is still tried after it, stripped as before.
  - Agreement with `ops_slug()` holds for every form. The parity test pins it on the
    real modules, including `ops-x`, `plan-x`, `ops-`, `plan-`, `.x` and a relative
    `ops.json`.
  - **The config's `plan` field fallback still works.**
    - AppiumLens sets `"plan"` to the directory name, so the two collapse into one
      slug.
    - When they differ, the result is `[dir, stripped-plan]`, as for flat configs.
    - A sibling whose `plan` field names another config's approved slug reaches that
      record but is refused by the sha256 binding (see Revision 2).
    - A **different** config can no longer borrow a record through the shared key
      `ops`, or through a shared prefix-stripped key.
  - `_gate_applies()` needs no change. It now searches `plan-<dir>.md` in the
    config's directory and in `.claude/plans`; before, it searched the useless
    `plan-ops.md`.

#### Step 3: plan-artifacts gate
- **File:** `scripts/check-plan-artifacts.py`
- **Action:** Modify (op `p1-plan-artifacts`)
- **Details:**
  - `resolve_plan()`: for a bare `ops.json`, the slug is the directory name
    **verbatim**, with no prefix strip, matching the other two sides.
    - The existing candidates `plan-<slug>.md` and `<slug>.md` still bind both
      directories `resolve_ops()` produces for `plan-lens.md`: `lens` via
      `plan-lens.md`, and `plan-lens` via `plan-lens.md` as `<slug>.md`.
  - Before this fix, an `operations/x/ops.json` with no `plan` field resolved no plan
    and **passed with every operation unchecked**.
  - The default scan (`rglob ops-*.json | *.ops.json`) is unchanged, so this only
    affects explicit arguments.

### Phase 2: Prompt gap 3 (ops `p2-reviewer-prompt`, `p2-review-command`)

#### Step 4: reviewer prompt
- **File:** `.claude/agents/reviewer.md`
- **Action:** Modify (op `p2-reviewer-prompt`)
- **Details:**
  - The reviewer has no Write tool (`tools: ["Read", "Grep", "Glob"]`), so it never
    writes the report file; the caller does.
  - The sentence "Mandatory, not conditional on the caller asking for it." becomes
    "in the reply itself: callers save that reply verbatim as the report."
  - Budget: +13 chars. `reviewer.md` counts toward the pipeline-agent-bodies budget,
    which currently stands at 42962/43000 chars, so headroom is 38.

#### Step 5: /review Task-tool path
- **File:** `.claude/commands/review.md`
- **Action:** Modify (op `p2-review-command`)
- **Details:**
  - **Old wording (2 lines):** "save its raw output to a file and record it
    yourself — a review whose verdict was never recorded is not an approval:"
  - **New wording (2 lines):** save the reply VERBATIM and record from that file;
    never a rewrite or summary; no `=== REVIEW ===` block means nothing is recorded
    (re-ask the reviewer, never compose a block).
  - The line count stays at 125, which is the `.claude/lint-baseline.json` ratchet.
  - This is the gap that bit AppiumLens: the caller saved its own reworded
    `REVIEW REPORT` to `.claude/reports/reviewer/<slug>-review.md`, and that report
    had only a prose `DECISION:`. The "fails closed" sentence that follows still
    covers what the removed clause said.

### Phase 3: Tests and changelog (ops `p3-test-review-record`, `p3-test-approval-gate`, `p3-test-plan-artifacts`, `p3-changelog`)

#### Step 6: `tests/test_review_record.py`
- **Action:** Modify (op `p3-test-review-record`)
- **`TestOpsResolution`, 3 new tests:**
  - resolves `operations/demo/ops.json` and `operations/plan-demo/ops.json` (case a)
  - resolves from an unrelated cwd, given an absolute plan path
  - a flat config and a directory config together → AMBIGUOUS, exit 3
- **New class `TestDirectoryLayoutKeying`:**
  - two plans `alpha` and `beta` get `alpha.json` and `beta.json`, no `ops.json`,
    and both `check` exit 0 (case c)
  - editing the config after approval → `check` exit 2 DRIFT (case d)
  - `operations/x`, `operations/ops-x` and `operations/plan-x` get `x.json`,
    `ops-x.json` and `plan-x.json`. The earlier record `x.json` is byte-identical
    after the other two approvals, and all three `check` exit 0.
  - directories named exactly `ops-` and `plan-` key verbatim, with no `_.json`
  - `.x` then `x`: the clobbered `x` is refused (exit 2), so the sanitiser collision
    fails closed
  - all four flat names still write a record keyed `demo` (case e)

#### Step 7: `tests/test_ops_approval_gate.py`
- **Action:** Modify (op `p3-test-approval-gate`)
- **New class `TestOperationsDirectoryLayout`:** it runs the real executor in a
  `tmp_path` project, without `--dry-run`.
  - approved directory config executes, target patched (case b)
  - drifted directory config refuses, target byte-identical (case d)
  - with a sibling plan's record present, the reason reads "no review record exists"
    with `slug 'beta'` (pre-fix it read DRIFT against `slug 'ops'`) (case c, gate side)
  - approving `operations/ops-alpha` after `operations/alpha` leaves alpha
    executable, target patched (reviewer's MAJOR, gate side)
  - a sibling `operations/ops-alpha/ops.json` declaring `"plan": "alpha"` with
    different bytes → refused with DRIFT, target byte-identical (plan field fallback)
  - key parity: both real modules are loaded by path, and
    `ops_slug(p) == _approval_slugs(p, "")[0]` must equal the expected key for
    10 forms plus a relative `ops.json`. The 4 flat forms give `x`; the directory
    forms `x`, `ops-x`, `plan-x`, `ops-`, `plan-` and `.x` give their names verbatim.

#### Step 8: `tests/test_check_plan_artifacts.py`
- **Action:** Modify (op `p3-test-plan-artifacts`)
- **Details:** `operations/lens/ops.json` and `operations/plan-lens/ops.json`, each
  with no `plan` field. The plan `plan-lens.md` does not name `src/x.py`. Each config
  → exit 1, and stderr names the path.

#### Step 9: CHANGELOG
- **File:** `CHANGELOG.md`
- **Action:** Modify (op `p3-changelog`)
- **Details:** new `[Unreleased]` entry. It covers:
  - the symptom and root cause
  - the new resolution forms
  - that flat keys are unchanged
  - that records keyed `ops` are no longer read, with the remedy: re-run `/review`
  - the prompt change

## Testing Strategy

**Isolation.** All new tests run in `tmp_path` trees through the real scripts
(subprocess, or import by path). They set `ECC_HOOK_PROFILE=minimal` through the
existing `_env()` helper or the `_run` harness, and run no git commands.

**Mutation proof: run by the planner, in scratchpad copies (revision 2), not asserted.**
All three copies use the same four test files (`test_review_record.py`,
`test_ops_approval_gate.py`, `test_check_plan_artifacts.py`,
`test_approval_machinery.py`) with the revision-2 test edits applied.

- **`pre`: original code.** 10 failed, 113 passed. Failing:
  - `test_resolves_the_operations_directory_layout`
  - `test_directory_layout_resolves_from_the_plan_not_the_cwd`
  - `test_a_flat_and_a_directory_config_are_ambiguous`
  - `test_two_directory_plans_get_distinct_records`
  - `test_prefixed_sibling_directories_get_distinct_records`
  - `test_a_bare_prefix_directory_keys_verbatim`
  - `test_a_sibling_plans_record_is_not_this_configs_record`
  - `test_approving_a_prefixed_sibling_leaves_this_approval_valid`
  - `test_recorder_and_executor_derive_the_same_key`
  - `test_a_directory_layout_config_resolves_to_the_plan_its_directory_names`
- **`v1`: rejected prefix-strip code.** 4 failed, 119 passed. These are exactly the
  reviewer's finding:
  - `test_prefixed_sibling_directories_get_distinct_records`
  - `test_a_bare_prefix_directory_keys_verbatim`
  - `test_approving_a_prefixed_sibling_leaves_this_approval_valid`
  - `test_recorder_and_executor_derive_the_same_key`
- **`post`: revision 2.** 123 passed, 0 failed.
- **Guards that pass everywhere.** `test_a_plan_field_naming_an_approved_sibling_does_not_authorise`
  and `test_a_dot_directory_never_authorises_its_undotted_sibling` pass in all three
  copies. They pin the fail-closed contract rather than the fix.
- **Lint.** `ruff check` on the 6 touched Python files → clean.
- **Revision 1 comparison.** That run included `test_rejection_briefs.py`, and no test
  failed only in the post copy. The rejection-brief failures there were environmental
  (partial tree); in the real repo that file gives 92 passed.

**Implementer DoD (run on the real tree after execution).**
```bash
ECC_HOOK_PROFILE=minimal python3 -m pytest tests/ -q
ruff check src/ tests/ scripts/ .claude/operations/scripts/
mypy
python3 scripts/check-context-floor.py --check
python3 scripts/check-plan-artifacts.py --check .claude/plans/plan-approval-gate-ops-dir-layout.ops.json
python3 scripts/gen-docs.py --check && python3 scripts/gen-registry.py --check
python3 scripts/gen-model-policy.py --check
python3 scripts/lint-corpus.py 2>/dev/null || true
```
The last line is a best-effort check of the command line ratchet; `tests/test_lint.py`
also covers it.

**Downstream confirmation** (read-only, optional). From `~/IdeaProjects/AppiumLens`:
```bash
python3 <claudekit>/.claude/operations/scripts/review-record.py resolve .claude/plans/plan-android-sdk-split-root-fix.md
```
Expected: `operations/android-sdk-split-root-fix/ops.json`, exit 0.

## Rollback Plan

- The change is 9 in-place `code_edit` ops with no creates or deletes. The executor's
  backup manifest restores all 9 files. Alternatively, run
  `git checkout -- <the 9 paths>` before committing, or `git revert` the commit.
- Record files are only ever added. A directory-layout record written after this
  change (e.g. `alpha.json`) is not read by the old code, which looks for `ops`.
  Rolling back therefore returns those plans to NO RECORD. That fails closed and
  corrupts nothing.

## Risk Assessment

- **High: security surface.** The approval gate is what authorises mutation.
  - The change narrows which record a config can match. A config no longer shares
    the key `ops`, and no key is removed from any flat config.
  - A directory config that previously **resolved** a record keyed `ops` now gets
    NO RECORD. That fails closed.
  - Route this to `reviewer` for the plan, then `code-reviewer` for the diff, which
    must run the mutation proofs.
- **Medium: 7 AppiumLens plans become AMBIGUOUS.** Measured read-only: these plans
  have both a flat `.claude/plans` config and an `operations/<slug>/ops.json`. Before
  this change `resolve` silently picked the flat one; after it, `resolve` exits 3
  AMBIGUOUS. Examples:
  - `plan-flow-a-setup-panel-skip-fix.md`
  - `plan-ios-supervised-proxy-flow.md`
  - `plan-ios-usb-wifi-regression-fix.md`

  The requirement is "Preserve AMBIGUOUS behavior". It is also the fail-loud choice,
  but it breaks `/review` for those 7 until one config is archived. See open
  questions.
- **Medium: stale records.**
  - ClaudeKit's tracked `.claude/reports/reviews/ops.json`, bound to
    `.claude/plans/request-shaping/ops.json`, is no longer read.
  - The 8 archived `.claude/plans/archive/ops-*/ops.json` configs now key as
    `findings-changelog` etc. None of those keys has a record (checked), so nothing
    can mis-bind.
- **Medium: remaining shared record files, all fail-closed.**
  - A flat `.claude/plans/x.json` and `operations/x/ops.json` both key `x`. The flat
    forms already share `x` among themselves, and a plan owning both is AMBIGUOUS at
    `resolve`.
  - `.x` and `x` share one file through `record_paths()`.
  - In both cases a clobbering write makes the other config DRIFT. It is never
    authorised. The `.x` case is pinned by a test.
- **Low: `_project_root(start)`.** An optional parameter; every existing caller
  passes nothing, so they are unaffected.
- **Low: prompt budget.**
  - `reviewer.md` grows 13 chars against 38 of headroom.
  - `review.md` stays at 125 lines.
- **Low: `check-plan-artifacts.py`.** Its default scan globs never match a bare
  `ops.json`, so CI output for ClaudeKit's own plans is unchanged.
- **Not hub files.** `.claude/project-graph.json` does not exist, so hub analysis was
  skipped (exit-3 path). Blast radius was mapped by grep instead:
  - `ops_slug`: `write_verdict`, `cmd_check`, `cmd_diff`, the backfill miner.
    - The miner's `_SLUG_MENTION_RE` requires an `ops-` or `plan-` prefix, so a bare
      `ops.json` never reaches it.
  - `resolve_ops`: `cmd_resolve`, `cmd_record_code_review`.
    - `cmd_record_code_review` also gains the directory layout, which is intended.
  - `_approval_slugs`: `check_approval` and `_gate_applies`.
  - Queued-ops gate (`tests/test_delivery_contract_smoke.py`): walks files and does
    not use the keys.

## Open design questions (owner)

1. **Flat plus directory for one plan.** Keep AMBIGUOUS, which is implemented and
   matches the requirement, or make flat win? Measured: 7 plans in AppiumLens.
2. **Resolve ClaudeKit's own directory layout too?** Should `resolve_ops()` also
   search `.claude/plans/ops-<slug>/ops.json`? These configs now **key** correctly but
   still do not **resolve** from a plan.
3. **Stale `ops` records.** Delete the tracked `.claude/reports/reviews/ops.json`
   (owner-gated deletion), or leave it to drain?
4. **Gate by directory.** Should `operations/` count as a gated directory in
   `_gate_applies()`, so that a directory config without a `plan-<slug>.md` is still
   gated without `ECC_OPS_GATE_ALL=1`?
