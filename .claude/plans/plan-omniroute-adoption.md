# Implementation Plan: OmniRoute adoption — items A and E

Ops config: `.claude/plans/plan-omniroute-adoption.ops.json` (6 operations, validator APPROVED)
Branch: `feat/omniroute-adoption` (worktree `.claude/worktrees/omniroute-adoption`)
Revision 2 — addresses reviewer round 1 (SCORE 82 / REVISE): the drift check's severity is now
semver-aware. Change A is unchanged from round 1 (explicitly approved).

## Overview

Two bounded changes distilled from `.claude/reports/research/omniroute-adoption-proposal.md`:
**A** makes tier degradation a checked data structure (`degrade_to` per capability tier,
validated by `gen-model-policy.py`) instead of one English sentence in CLAUDE.md, and
**E** makes `ck doctor` report install-vs-kit version drift from the manifest it already writes.
Item C (`changelog.d/` fragments) is deliberately excluded as an owner-gated release-process change;
item B (limit-hit state) is deferred per the report.

## Design precheck (ownership / where the value sits)

Both changes extend artifacts that already own the data in question, and neither invents a new
source of truth. **A**: `.claude/model-policy.json` is already the single table for
tier→model and role→escalation; `degrade_to` is the missing symmetric edge, and
`scripts/gen-model-policy.py:load_policy` is already the fail-closed reader every consumer goes
through (`run-evals.py:92` and the tests read the JSON directly but only for `["model"]`, so an added
key is inert to them). **E**: `.claudekit-manifest.json` already records `version` and a `source`
commit (install.sh:696); the value of E sits entirely in `cmd_doctor`, which loads that manifest
already (main.py:422) and simply never compared the two numbers. No file carrying the value is
outside the model.

Rejection-brief search (`review-record.py rejections search`) returned 13 keyword matches, all on
unrelated plans (e2e pipeline lanes, reflection receipts, retro backfill heldout digests). No prior
brief covers model-policy schema or doctor drift; treated as unknown, not as absence of risk.

## Scope

- **In scope:** `degrade_to` in the tier table + its validation; a semver parser and one drift check
  in `cmd_doctor`; behavioural tests in the two existing test files; a `[Unreleased]` CHANGELOG entry.
- **Out of scope:** agent frontmatter (must not change), `changelog.d/`, limit-hit state machinery,
  component counts, CLAUDE.md prose, fleet sync (fleet is HELD).

## Prerequisites

- `.claude/settings.local.json` with `ECC_HOOK_PROFILE=minimal` present (this repo runs its own hooks).

## Implementation Steps

### Step 1: Add `degrade_to` to the tier table
- **File:** `.claude/model-policy.json` · **Action:** Modify
- most-capable → `"balanced"`, balanced → `"fast"`, fast → `null` (terminal), each inserted
  directly after that tier's `"model"` line.
- Three `_readme` lines describing `degrade_to` as the fallback chain as data, appended after the
  "Regenerate/verify agent frontmatter" line.

### Step 2: Validate `degrade_to` in `load_policy()`
- **File:** `scripts/gen-model-policy.py` · **Action:** Modify (extends the existing tier loop)
- Per tier: the key must be present (an absent key is not a terminal chain), and a non-null target
  must name a known tier.
- Then a second pass walks every chain from every tier to its terminal `null`, raising on a repeat
  (which covers both a self-reference and a longer cycle). This is the substantive check: a cycle
  makes "degrade one tier, never stop" loop forever, and every hop in a cycle is individually valid,
  so the one-step check alone cannot catch it.
- Raises `ValueError`, which `main()` already converts to `ERROR: …` on stderr + exit 1, matching the
  docstring's fail-closed philosophy. No behaviour change for frontmatter.

### Step 3: Semver-aware install-vs-kit drift in `cmd_doctor`
- **File:** `src/claudekit/cli/main.py` · **Action:** Modify (two insertions)
- **3a — module-level `_parse_semver(text)`**, inserted immediately before `cmd_doctor`. Returns
  `(major, minor, patch)` or `None`. Stdlib only, no `packaging`/`pkg_resources`. `None` means
  UNKNOWN, never "equal", so an unsigned hand-edited manifest can only ever produce a skip and can
  never crash doctor. Pre-release/build suffixes (`3.1.0rc1`, `3.1.0+meta`) and wrong-arity strings
  (`3.1`, `3.1.0.4`) are unknown rather than guessed — this kit has never shipped one and inventing
  an ordering would be a comparison nobody reviewed.
- **3b — the check**, inserted immediately before the ejected-install skip block so both provenance
  checks sit together. Severity is deliberately non-uniform:
  - **equal** → `check(..., True)` pass.
  - **major or minor differs** → `check(..., "warn")` with a fix hint. Genuinely actionable, and
    `--strict` is right to redden.
  - **patch only differs** → a plain `info()` line, routed *around* `check()` on purpose so it can
    touch neither the readiness score nor `--strict`.
  - **manifest missing / unreadable / `"unknown"` / unparseable / ejected** → `check(..., "skip")`,
    honouring the `check()` docstring ("the absence it reports is by design") and the ejected-install
    precedent (an ejected tree keeps no manifest, so it skips by construction).
- The message names both sides explicitly — "this project records vX" vs "the claudekit package on
  this machine is vY" — and the fix hint states both directions, so the known false positive (a stale
  dev venv making `__version__` older than the manifest) reads as what it is instead of as mystery.
- Uses a fresh `_load_manifest(".")` rather than the existing `_manifest` local, which falls back to
  the eject record — an eject record has no `version` field, so reusing it would misreport ejected trees.

**Why not warn on any difference (reviewer round 1, MAJOR).** The fleet's steady state is many
projects sharing one global `claude-kit` install on staggered syncs. Warning on any difference would
make `ck doctor --strict` — a command in this repo's own Definition of Done — permanently red across
the fleet the moment a release lands, over a condition nobody is meant to act on. A gate people learn
to ignore is worse than no gate. The round-1 `shellcheck`-missing precedent does not carry: that is a
one-time per-machine tooling gap, whereas version drift recurs on every release for every project not
yet re-synced.

### Step 4: Tests for `degrade_to`
- **File:** `tests/test_model_policy.py` · **Action:** Modify (extends the existing classes; no new file)
- `MalformedPolicyFailsClosed` gains four cases via the existing `assert_rejected` helper (which also
  proves nothing was written): unknown target, a two-tier cycle, a self-reference, and an absent key.
- `ModelPolicyIsTheSourceOfTruth` gains `test_the_shipped_degrade_chain_terminates`, which imports
  `load_policy` and walks the real table to its null — a property, not a pinned literal map.

### Step 5: Tests for the drift severities
- **File:** `tests/test_doctor_gate.py` · **Action:** Modify (extends `TestMinimalInstallPassesStrict`,
  reusing its class-scoped real install plus `_copy`/`_edit_manifest`; `ENV` there already pins
  `ECC_HOOK_PROFILE=minimal`)
- Fresh install → the check passes (positive control: install.sh must stamp the version this CLI reports).
- Minor behind → warns, names both sides and the fix, plain doctor still exits 0.
- Major gap under `--strict` → exits 1. The gap `--strict` exists to catch.
- Patch gap under `--strict` → exits 0 **and** the informational line is present. Both halves are
  asserted, because dropping the report entirely would also pass a `--strict`-only test.
- Patch gap scoring → readiness score identical to the same tree without the gap, no `Warnings:`/
  `Failed:` line, and the reported line carries the `[*]` prefix rather than any of `check()`'s own
  (`[✓]`/`[!]`/`[-]`) — three independent proofs that it bypassed `check()`.
- Uncomparable recorded versions, parametrised over `"unknown"`, `"not-a-version"`, `"3.1"`,
  `"3.1.0rc1"`, `""`, `"3.1.0.4"` → skip, exit 0, no traceback.
- Manifest deleted → skip line present, no drift verdict.
- Version fixtures are **derived from the manifest** (`_bumped`), not hardcoded, so they keep testing
  the intended gap after the next version bump.
- The round-1 test `test_drift_reddens_strict_like_every_other_warning` is gone: it pinned the
  behaviour this revision replaces.

### Step 6: CHANGELOG
- **File:** `CHANGELOG.md` · **Action:** Modify — two bullets under `[Unreleased]`, the second stating
  the semver-aware severity split. No counts touched.

## Testing Strategy

Verified by reconstructing the post-state in a scratch copy of the worktree and executing it
(nothing in the worktree was modified):

- `python3 scripts/gen-model-policy.py --check` → `Model policy in sync: 22 agent roles.` exit 0
  (Change A does not touch frontmatter).
- `pytest tests/test_model_policy.py tests/test_doctor_gate.py -q` → **72 passed** (55 before: +5 policy,
  +12 doctor including the parametrised skip cases).
- `pytest tests/test_doctor_score.py tests/test_cli.py tests/test_doctor_alias_scope.py
  tests/test_behavior_spec.py tests/test_eval_replay.py -q` → 95 passed.
- `ruff check` on all four changed source files → clean. `mypy` → `Success: no issues found in 35 source files`.
- Still to run at DoD time on the real tree: full `pytest tests/ -q`, `gen-docs.py --check`,
  `gen-registry.py --check`, `check-context-floor.py --check`, `check-plan-artifacts.py --check`,
  `shellcheck`.

## Rollback Plan

Every operation is an additive edit to a tracked file: `git checkout -- <path>` per file, or revert
the commit. `degrade_to` has no reader other than the validator, and the doctor change is one helper
plus one self-contained block, so partial rollback of either change is safe and independent of the other.

## Risk Assessment

- **Low:** `degrade_to` is inert to every other policy reader — `run-evals.py:92`,
  `tests/test_eval_replay.py`, `tests/test_behavior_spec.py` read only `["model"]`; no digest or
  snapshot pins the policy file's bytes.
- **Low:** the readiness score is unmoved in every branch. The new skip leaves the denominator
  (`main.py` `_applicable`), and the patch-level report is not a check at all. The applicable *count*
  drops by one in the patch-only case — a check that is not emitted is not counted — which is the
  intended shape and is asserted rather than hidden.
- **Low:** `check-plan-artifacts.py --check` passes; all six op paths are named above.
- **Medium (known false positive, now legible):** `__version__` resolves from installed `claude-kit`
  metadata first, falling back to the hard-coded source value. A developer with an older `claude-kit`
  in the active venv sees the project reported as *newer*; the message and fix hint name that direction
  explicitly. Both sides are `3.1.0` today (pyproject.toml:10) and the positive-control test passes.
- **Medium:** requiring `degrade_to` on every tier is stricter than "validate it if present" — any
  hand-written or trimmed policy table without it now fails closed. No such table exists in-repo
  (`subset_policy` derives from the shipped file), and fail-closed is the file's stated philosophy.
- **Medium:** a warn on a major/minor gap does redden `--strict` for a project that is genuinely
  behind. That is the intended, actionable case; the fleet-noise case (patch bumps) is routed around
  scoring entirely.
- **Not applicable:** no project graph (`.claude/project-graph.json` absent), no security surface,
  no schema migration, no deletions, no `run_command` ops.

## Notes on ops mechanics

`add_after` is literal concatenation: every inserted payload carries its own leading newline and no
accidental trailing one. The post-state was reconstructed, compiled, linted, type-checked and executed
before handoff rather than trusted to the validator, which does not compile it.
