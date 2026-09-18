# Code review — policy-effort-per-role (ROUND 2)

Target: `.claude/plans/plan-policy-effort-per-role.md` + `.claude/plans/ops-policy-effort-per-role.json`
Reviewer: code-reviewer (Opus) — adversarial, prompted to refute
Revision: `63677c1` + uncommitted working tree (plan revised in place by the planner; baseline
re-stamped by the coordinator — not stamped by me). Fresh scratch clone executed, regenerated,
mutated, reverted, removed. The real tree was never written to.
Round scope: the round-1 fixes only — the two rejection tests, plus the two Low dispositions.

SUMMARY
  Critical: 0 | High: 0 | Medium: 0 | Low: 0 (round-1 Low 1 accepted by the plan; Low 2 reworded)

VERDICT: APPROVE

---

## INHERITED FINDINGS

### [H1] Rejection test asserted the fixture's starting state, not "nothing was written"
  Status: **discharged**
  Evidence: the fix replaces `assertIsNone(effort_of("planner"))` with a `snapshot()` helper
  (tests/test_model_policy.py:367-373) that reads the **exact bytes of every fixture agent file**
  and compares the whole dict before/after (lines 378/382 and 388/392). I reproduced round 1's
  exact killing conditions — executed the 6 ops with `--no-approval` (6 successful, 0 errors),
  then ran the plan's `python3 scripts/gen-model-policy.py` (`Model policy applied: 22 agent
  roles, 22 rewritten`), leaving every real agent file carrying an `effort:` line, which is the
  state that made `assertIsNone` unsatisfiable. In that state:
  ```
  tests/test_model_policy.py::EffortIsProjectedPerRole::test_an_invalid_effort_value_is_rejected PASSED [ 50%]
  tests/test_model_policy.py::EffortIsProjectedPerRole::test_an_invalid_role_override_is_rejected PASSED [100%]
  2 passed in 0.11s
  ```
  and the full file: `32 passed in 1.00s`. `gen-model-policy.py --check` rc 0.
  The new assertion is also strictly *stronger* than the one I proposed: it snapshots all fixture
  agents rather than just `planner`, so a stray write to any of them is caught.

### [L1] Off-position `effort:` key normalised in value but never repositioned
  Status: **accepted as a documented limitation** (planner chose not to fix)
  Evidence: recorded in the plan's Risk Assessment. This was Low precisely because it causes no
  corruption and no duplication — verified by probe in round 1. Documenting it is a legitimate
  disposition; it does not block.

### [L2] Plan overclaimed mutation specificity ("flip its named test and no other")
  Status: **discharged** — reworded in the plan.

---

## New verification this round

**Mutant 3 (new, targeting the new shape): make the rejection path leak one byte into an agent
file before raising.** Injected `_leak()` (appends a single `b"X"` to the first agent file) at
*both* effort-rejection sites in `load_policy`, immediately before each `raise ValueError`:

```
E  AssertionError: {'pla[36014 chars]...clarification.\nX'} != {'pla[36014 chars]...clarification.\n'}
tests/test_model_policy.py:382: AssertionError
E  AssertionError: {'pla[36014 chars]...clarification.\nX'} != {'pla[36014 chars]...clarification.\n'}
tests/test_model_policy.py:392: AssertionError
FAILED tests/test_model_policy.py::EffortIsProjectedPerRole::test_an_invalid_effort_value_is_rejected
FAILED tests/test_model_policy.py::EffortIsProjectedPerRole::test_an_invalid_role_override_is_rejected
2 failed, 30 passed in 1.08s
```

Both tests die on a **single byte**, and only those two fail. Reverted; `32 passed in 1.00s` and
the script verified byte-identical to its pre-mutant state.

**Methodological note, recorded because it nearly produced a false pass.** My first attempt at
mutant 3 globbed `.claude/agents/*.md` relative to the process CWD and the suite reported
`32 passed` — a clean, confident, *wrong* "the test doesn't catch this". The cause: `run()`
(tests/test_model_policy.py:37-39) sets no `cwd`, while the script resolves
`AGENTS_DIR` from `os.path.abspath(__file__)` (gen-model-policy.py:23-24), i.e. the tmp tree.
The mutant had been writing into the scratch repo root, never touching the fixture. A mutant that
misses its target is indistinguishable from a test that is genuinely strong; only re-pointing the
leak at `AGENTS_DIR` produced the real result above. The passing run was discarded, not reported.

## POSITIVE OBSERVATIONS

- The fix does not merely satisfy the round-1 finding — it generalises it. Snapshotting *all*
  fixture agents as bytes is the honest encoding of "wrote nothing", and its docstring says so.
- The fail-closed guarantee is now pinned at byte granularity at both rejection sites, so a
  partial write during validation cannot pass unnoticed.
- The planner fixed the mechanism rather than re-anchoring the assertion to the new expected
  value, which is the failure mode the round-1 finding was warning about.

## REVIEW COVERAGE (round 2 — delta only)

- Correctness: checked (ops re-executed, regenerated, the two named tests run in the post-regen state)
- Reliability: checked (new one-byte leak mutant kills both tests)
- Security / Performance: unchanged from round 1; no new surface in this delta
- Full `pytest tests/ -q` not run this round (budget); `tests/test_model_policy.py` is green at 32
  passed and `gen-model-policy.py --check` is rc 0.

Zero Critical and zero High: by the exit rule, the review is over.

=== REVIEW ===
SCORE: 95
DECISION: APPROVED
=== END REVIEW ===
