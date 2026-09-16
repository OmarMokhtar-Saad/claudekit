# Implementation Plan: Fix the author != reviewer identity model

## Overview

The author != reviewer gate shipped in `61ed9c1` compares **session ids**. Because
`_session_id()` falls back to a proven process-tree match, and because that match
deliberately refuses `agent-` transcripts (`review-record.py:483`) so every subagent
resolves to its **parent** session, the author and the reviewer in a normal ClaudeKit run
are always the same id. The gate therefore refuses every legitimate execution (exit 6),
and the CHANGELOG claims the opposite — that it "does not bind".

This plan changes the identity axis from session to **asserted agent role**, keeps exit 6
and the 0-5 contract intact, leaves already-recorded verdicts executable, and states in
code, CHANGELOG and plan that the result is **attestation, not enforcement**.

## Design precheck (ownership / data model)

The identity data model is: an author sidecar
(`.claude/reports/reviews/<slug>.author.json`) written by `record_author`, and a review
record (`<slug>.json`) written by `write_verdict`. Both are written by the same OS
process family — the main agent's Bash calls — because a subagent produces verdict
*text*, never the recording command. Session id is therefore not an identity axis at all:
it measures "which Claude Code session ran the script", which is one value for the whole
pipeline. The only axis the system can carry is the **role the caller asserts** for each
write. The files that carry the value are `review-record.py` (both writers + `cmd_check`),
`validate-config-json.py` (the stamp-time author write) and the two command prompts that
invoke `write`.

### Honest value statement (this is not enforcement)

A role-based gate is **attestation**. The caller asserts "this verdict came from a
`reviewer`"; nothing observes it. A caller who wants to bypass it asserts
`--reviewer-role reviewer` while reviewing its own plan, exactly as it could pass
`--session-id`. What it buys, stated plainly and claimed nowhere beyond this:

1. **It ends the deadlock** — the current gate is unsatisfiable by any normal run.
2. **Bypass becomes deliberate and greppable.** Recording a verdict with no reviewer role
   leaves `reviewer_role: null` in the record; asserting a false role leaves a literal
   string in a committed JSON file that a later audit can diff against the transcript.
   The previous failure mode — accidental self-review nobody noticed — is closed.
3. **Provenance for audit**: every record after this says which role claims the verdict.

It does **not** prevent a self-review by a caller that wants one. The word "enforcement"
must not appear for this mechanism in the code, the CHANGELOG or this plan. The
alternative considered was pure advisory (warn, never exit 6). Rejected because it
regresses to the `a-passing-check-can-measure-nothing` failure: a warning nobody must act
on is measured by nothing. The chosen rule refuses only on a **positively asserted
non-reviewer role**, which is a claim the caller made, not an absence.

### Rejection-brief search

`review-record.py rejections search "author reviewer identity session role"` — run at
plan time; treated as a prior, not a proof. Nothing in the store contradicts this design;
the two live in-repo priors are memory entries `a-passing-check-can-measure-nothing`
(a check that measured nothing) and this gate (a check that bound harder than claimed).
This plan avoids a third by making the binding condition an explicit caller assertion and
by proving both directions in tests.

## Scope

- **In scope:** the identity axis in `review-record.py` (`record_author`, `write_verdict`,
  `cmd_check`, CLI flags, exit-code docs), the stamp-time call in
  `validate-config-json.py`, the `write` invocations in `/review` and `/refine`, the
  CHANGELOG correction, and behavioural tests.
- **Out of scope:** redesigning the review system, changing the approval threshold,
  exporting session ids from hooks, `_session_id`'s process-tree fallback itself (see
  below), the rejection-brief store, and any agent-model/routing change.

## Decision: does `_session_id`'s process-tree fallback still feed this comparison?

**No.** After this change no gate compares sessions. `reviewer_session` and the sidecar's
`session` field are still written, but purely as **provenance**, and the code says so in
a comment at each site. The fallback itself stays untouched because the rejection-brief
store (its original consumer) needs it, and removing it would silently degrade brief
attribution. The defect was never the fallback — it was that a docstring's "in practice
this is unknown" aside was accepted as a behavioural claim for a gate. That claim is
deleted from the CHANGELOG and is not restated anywhere.

## Prerequisites

- `.claude/settings.local.json` present with `ECC_HOOK_PROFILE=minimal` (repo gotcha).
- No re-review of `plan-context-recovery-refinement` is required; `plan-output-filters` was
  never recorded on disk at all (see Migration).

## Implementation Steps

### Step 1: Document the new identity axis in the module docstring
- **File:** `.claude/operations/scripts/review-record.py`
- **Action:** Modify
- **Details:** Usage block gains `--reviewer-role` / `--author-role`. Exit code 6 is
  re-described as "the verdict is attributed to a role that may not authorise execution
  (self-review)". Codes 0-5 keep their exact meanings; nothing that reads them changes.

### Step 2: Add the role vocabulary and normaliser
- **File:** `.claude/operations/scripts/review-record.py`
- **Action:** Modify
- **Details:** After `SELF_REVIEW_EXIT = 6`, add `REVIEWER_ROLES` (`reviewer`,
  `code-reviewer`, `security-scanner`, `verifier`), `AUTHOR_ROLE_DEFAULT = "author"` and
  `_ROLE_RE`. Add `_role(explicit)`: explicit flag, then `$CLAUDEKIT_AGENT_ROLE`, then
  `"unknown"`; anything not matching `[a-z][a-z0-9-]{1,31}` is lower-cased and, if still
  invalid, becomes `"unknown"` with a stderr NOTE — never invented, never silent.

### Step 3: Record the author's role
- **File:** `.claude/operations/scripts/review-record.py`
- **Action:** Modify
- **Details:** `record_author(ops, session_id=None, role=None)` writes `"role"` into the
  sidecar; `cmd_author` passes `--author-role`. FIRST KNOWN AUTHOR WINS is unchanged, so
  a sidecar that already exists keeps its (role-less) content — deliberate, see Migration.
  Add `load_author_role(slug)` returning `"unknown"` for absent/unreadable/missing-key,
  mirroring `load_author`.

### Step 4: Record the reviewer's role
- **File:** `.claude/operations/scripts/review-record.py`
- **Action:** Modify
- **Details:** `write_verdict(..., reviewer_role=None)` records `"reviewer_role"`
  alongside `reviewer_session`, which is re-commented as provenance only. `cmd_write`
  forwards the flag. The field is additive: `cmd_check` still reads score/decision/sha
  off the top level, and the record is not part of the hashed artifact.

### Step 5: Replace the session comparison in `cmd_check`
- **File:** `.claude/operations/scripts/review-record.py`
- **Action:** Modify
- **Details:** Replace the `author == reviewer` session block with, in order, after the
  drift and threshold checks so each refusal still reports its own cause:
  1. `reviewer_role == "unknown"` -> exit 0 with a NOTE naming both roles and saying the
     gate did not bind (back-compat; the pre-change corpus).
  2. `reviewer_role not in REVIEWER_ROLES` -> exit 6: the verdict is attributed to a role
     that does not review (covers `author`, `implementer`, `planner`, `main-agent`).
  3. `reviewer_role == author_role` -> exit 6: same role on both sides.
  Message says "attested", names both roles, and points at recording a fresh
  `reviewer`/`code-reviewer` verdict. No occurrence of the word "enforced".

### Step 6: CLI flags
- **File:** `.claude/operations/scripts/review-record.py`
- **Action:** Modify
- **Details:** `write` gains `--reviewer-role`; `author` gains `--author-role`. Both are
  free-form strings validated by `_role`, not `choices=`, so a new agent role does not
  need a code change to be recordable (it simply will not be in `REVIEWER_ROLES` until
  someone adds it — a refusal, which is the safe direction).

### Step 7: Stamp-time author role
- **File:** `.claude/operations/scripts/validate-config-json.py`
- **Action:** Modify
- **Details:** `_mod.record_author(args.config)` becomes
  `_mod.record_author(args.config, role=_mod.AUTHOR_ROLE_DEFAULT)` — the constant is wired
  up rather than removed, so the author-side role string has one definition and cannot
  drift from `REVIEWER_ROLES` in the same module. `--stamp-baseline` is run by the
  implementer/main agent, never by a reviewer, so `"author"` is the truthful assertion and
  it is outside `REVIEWER_ROLES` — this is what makes the gate bind at all. The call stays
  inside the existing fail-soft `try`, so a signature mismatch can still never fail a
  valid config.

### Step 8: Update the executor's exit-6 cause string
- **File:** `.claude/operations/scripts/execute-json-ops.py`
- **Action:** Modify
- **Details:** The cause map at `:975` still says the verdict "was written by the session
  that authored this ops.json". It becomes the role wording and names the remedy
  (`--reviewer-role`). Exit 6 keeps its number and its map slot; entries 2/3/4 are
  untouched, so the executor's distinct remedies survive.

### Step 9: Teach the recording prompts to assert the role
- **Files:** `.claude/commands/review.md`, `.claude/commands/refine.md`
- **Action:** Modify
- **Details:** Every `review-record.py write` invocation gains
  `--reviewer-role reviewer`. These are the only in-repo callers that record a verdict on
  a reviewer subagent's behalf.

### Step 10: Correct the CHANGELOG
- **File:** `CHANGELOG.md`
- **Action:** Modify
- **Details:** Replace the "does not bind" bullet. The new entry states: the session-based
  comparison was wrong and over-bound (every subagent resolves to its parent session, so
  author and reviewer always collided and the gate refused every legitimate run); the
  comparison is now over an asserted agent role; it is **attestation, not enforcement**,
  and what that does and does not buy; records written before this change keep executing.

### Step 11: Behavioural tests
- **Files:** delete `tests/test_author_not_reviewer.py`, create
  `tests/test_review_identity_roles.py`
- **Action:** Delete + Create
- **Details:** The old file's four session-identity tests assert the exact behaviour being
  removed, so they are replaced rather than patched; every invariant that is still true
  (hash unmoved, sidecar location, first-known-author-wins, ordering vs. a rejecting
  verdict, real non-dry-run executions, forced `ECC_HOOK_PROFILE`) is carried over
  verbatim into the new file. New coverage below.

### Step 12: Disclose the `--no-approval` execution (manual, post-execution)
- **File:** `.claude/plans/archive/README.md`
- **Action:** Modify — **deliberately NOT an ops.json operation**
- **Details:** The disclosure row records a fact that does not exist until the run has
  happened (that this config was executed with `--no-approval`, and why). An operation
  inside this same config would write the row before the run it describes, which is the
  `installer-writes-after-preservation` failure shape: an artifact asserting an event that
  has not occurred. The executing agent adds the row at archive time, in the Tier-1 style
  already used in that file, naming the reason (self-referential fix to the gate being
  fixed) and the reviewer that scored this plan. See "Executing this plan's own ops.json".

## Testing Strategy

Each test drives the real scripts in a real temp tree, with a named mutation that turns it
red:

| Test | Mutation that makes it FAIL |
| --- | --- |
| `test_author_role_reviewing_itself_is_refused` (exit 6, executor refuses, payload unchanged) | delete the `reviewer_role not in REVIEWER_ROLES` branch in `cmd_check` -> exit 0, edit applies |
| `test_reviewer_role_authorises_execution` (positive control; identical setup, role `reviewer`) | remove `reviewer` from `REVIEWER_ROLES` -> the approved run is refused |
| `test_same_session_no_longer_blocks` (one session id on both sides + role `reviewer` -> exit 0, edit applies) | restore the `author == reviewer` session comparison -> exit 6 (this is the regression test for the shipped defect) |
| `test_missing_reviewer_role_does_not_block` (pre-change record: no role anywhere -> exit 0 + "did not bind" on stderr) | make `cmd_check` refuse on `unknown` -> exit 6, and both archived plans brick |
| `test_role_is_recorded_in_both_artifacts` (sidecar `role`, record `reviewer_role`) | drop either field from its writer |
| `test_rejecting_verdict_still_reports_its_own_cause` (score 70 -> exit 4, not 6) | move the role block above the threshold check |
| `test_self_review_is_not_reported_as_drift` (no `DRIFT` / `NOT APPROVED` text) | reuse exit 2 or 4 for the role refusal |
| `test_role_refusal_is_not_called_enforcement` (stderr says "attested", never "enforc") | reintroduce enforcement language |
| `test_author_sidecar_never_touches_the_ops_json` (sha256 before/after) | write the role into the ops.json instead of the sidecar -> DRIFT |
| `test_first_known_author_wins` | make `record_author` overwrite |
| `test_stamp_baseline_records_the_author_role` (drives `validate-config-json.py --stamp-baseline`, asserts sidecar `role == "author"`) | drop the `role=` argument in `validate-config-json.py` |

Full-suite commands from CLAUDE.md all run before the change is called done:
`python3 -m pytest tests/ -q`, `ruff check`, `mypy`, `gen-docs.py --check`,
`gen-registry.py --check`, `gen-model-policy.py --check`, `check-context-floor.py --check`,
`check-plan-artifacts.py --check`.

## Migration / back-compat (verified against `.claude/reports/reviews/`)

`ls .claude/reports/reviews/` returns exactly three matching files —
`context-recovery-refinement.author.json`, `context-recovery-refinement.json`,
`context-recovery-refinement.ops.json` — so the two plans are **not** in the same state and
this fix does not unblock both.

- **`plan-context-recovery-refinement` — the one plan this migration path covers.** It has
  an author sidecar (session recorded, **no** `role` key) and an APPROVED-93 record (**no**
  `reviewer_role` key), both pre-dating the role model. Under the new `cmd_check`,
  `reviewer_role` resolves to `"unknown"` -> rule 1 -> **exit 0 with an explicit NOTE that
  the gate did not bind**. It executes with no re-review; work that was legitimately
  reviewed is not re-reviewed.
- **`plan-output-filters` — never blocked by the shipped defect; never recorded.** It WAS
  reviewed by a `reviewer` agent and scored 93/100 APPROVED, but `review-record.py write`
  was never run for it, so that verdict exists only in the session transcript. There is no
  record and no sidecar on disk. Nothing in this plan changes its state. To execute it,
  after this fix lands: run `validate-config-json.py <ops> --stamp-baseline` (which under
  the new code writes `role: "author"` into a fresh sidecar), then record its verdict with
  `review-record.py write ... --reviewer-role reviewer`. Under the OLD model that same
  sequence in one session would have produced exit 6; under the new one it authorises. If
  the verdict is recorded WITHOUT `--reviewer-role`, the role is `"unknown"`, the gate does
  not bind, and execution proceeds with the NOTE — recorded here so whoever executes it is
  not surprised in either direction.
- No sidecar or record is rewritten by this change. `record_author`'s first-known-author
  rule means an existing sidecar is not re-opened to add a role; that is correct — the
  role of a past write is not knowable now, and inventing one would be a lie in a
  provenance file.
- The `session`/`reviewer_session` fields remain on disk and keep their meaning; only
  their *use* changes (provenance, never a gate).

## Exit-code contract

Codes 0-5 are untouched, including their stderr blocks and the executor's cause map. Exit
6 keeps its number and its executor mapping; only its *reason string* changes (session ->
attested role). Hard rule 2 is unaffected: `review-record.py` is a script, not a hook; the
blocking hook path that consumes it (`execute-json-ops.py` -> approval gate) still fails
closed with its own `exit 2` semantics, and the cause map entry for 6 is updated in place.

## Executing this plan's own ops.json (deadlock)

This ops.json would hit the very gate it fixes. The code on disk at execution time is the
**pre-fix** `cmd_check`, which compares sessions: stamping the baseline records this
session as the author, recording any verdict records the same session as the reviewer, and
the check returns exit 6. There is no ordering of the normal steps that satisfies it. Read
of `execute-json-ops.py:1071-1090`: `--no-approval` skips
`check_approval` **entirely** (the whole `if not require_approval:` branch), prints
`Approval: BYPASSED (--no-approval)` on stdout and a `!!! APPROVAL GATE BYPASSED` banner on
stderr, and proceeds to the baseline-drift gate and the ops. It is therefore the correct
and honest mechanism: it is loud, it is recorded in the run output, and it does not
require self-issuing an APPROVED record.

**Execution instruction:** run with `--no-approval`, and disclose it in
`.claude/plans/archive/README.md` in the Tier-1 style this repo already uses, naming the
reason (self-referential fix to the gate) and the reviewer that scored the plan. Do **not**
run `review-record.py write` for this plan to manufacture an approval.

## Rollback Plan

- `git revert` this commit; `61ed9c1` behaviour returns (and re-deadlocks — so rollback is
  only a step toward reverting `61ed9c1` itself).
- No data migration to undo: no sidecar or record is rewritten, and `role` /
  `reviewer_role` are additive keys that older code ignores.
- Emergency path if the new gate ever misfires: `--no-approval`, disclosed.

## Risk Assessment

- **Low:** additive JSON keys; CHANGELOG and prompt edits; `validate-config-json.py`
  one-argument change inside an existing fail-soft `try`.
- **Medium:** `cmd_check` is on the only path that can mutate the tree — a logic error
  either bricks execution or opens the gate. Mitigated by the positive/negative control
  pair and by rule 1's explicit unknown-is-open behaviour.
- **Medium:** deleting `tests/test_author_not_reviewer.py` removes coverage until the
  replacement lands in the same ops.json; both operations are in one config, so no
  intermediate state is committed.
- **Named honestly, not mitigated:** the gate is attestation. A caller can assert
  `--reviewer-role reviewer` for its own plan and the system cannot tell. This is
  documented at the refusal site, in the CHANGELOG and here.
- `UNVERIFIED:` no `.claude/project-graph.json` consulted (none required for a 5-file
  change); no hub analysis run.
