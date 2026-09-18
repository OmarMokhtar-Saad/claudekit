# Code review — context-budget-gate (round 3, final; ceiling)

Target: `.claude/plans/plan-context-budget-gate.md` + `.claude/plans/ops-context-budget-gate.json`
(7 ops; payloads `.claude/plans/payloads/context-budget-gate/{context-budget-gate.py,test_context_budget_gate.py}`)
Reviewer: code-reviewer (Opus)
Revision: 342f4a2a9c86691d0f404c75e614e76953fbf397 + uncommitted working tree
(plan artifacts untracked; `git rev-parse HEAD` confirmed at the top of this round)
Round scope: the delta the coordinator named since the round-2 verdict — ops op 3 matcher, plan lines
49/175, plan mutant-2 prose, CHANGELOG op text. Baseline was re-stamped by the coordinator; this
reviewer did not stamp.
Method: fresh scratch clone (`git archive HEAD`) + plan payloads under the session scratchpad; ops
executed there with `--no-approval`; the real tree was never mutated.

SUMMARY
  Critical: 0 | High: 0 | Medium: 1 | Low: 1

VERDICT: APPROVE WITH SUGGESTIONS

Zero Critical and zero High — **the review is over**. The two findings below are follow-ups; neither
blocks the merge and neither justifies a fourth round (the ceiling would have been reached anyway).

---

## The round-2 blocker is fixed, measured

`pytest tests/test_context_budget_gate.py -q` on the freshly executed scratch clone, UNMUTATED:

    Operations: 7 total · Successful: 7 · Errors: 0
    ........................                                                 [100%]
    24 passed in 1.77s

Executed artifacts grepped in place, not inferred from the plan:

    .claude/hooks/dispatch-registry.json:49
      {"id": "context-budget-gate", "file": "context-budget-gate.py", "runner": "python3",
       "tier": "blocking", "matcher": "Write|Edit|NotebookEdit|Bash|Agent|Task"},

    CHANGELOG.md [Unreleased]
      "…prints one advisory per 20 guarded calls at `CK_CONTEXT_WARN` (200,000) and, in a main
       session, refuses the call at `CK_CONTEXT_BLOCK` (400,000)…"
      "…a subagent's `transcript_path` is its own `<session-id>/subagents/agent-*.jsonl`…"

    plan-context-budget-gate.md:49  and :175 — both now carry
      `Write|Edit|NotebookEdit|Bash|Agent|Task`

That closes H1-r2, M1-r2 and the CHANGELOG half of L3.

---

## MEDIUM

### [M1-r3] The rewritten mutant-2 prose is now wrong in the other direction — and it is refutable in 2 seconds
- File: `plan-context-budget-gate.md:152-157`
- New plan text: "A whole-file reader returns the SAME verdict … what changes is `read_bytes` … **Mutant
  2a (delete the seek only) flips nothing observable except `read_bytes`; there is no verdict-flip
  variant.**"
- The first half is correct and was the round-2 ask. The last sentence is false, and the test's own
  docstring already says so (`tests/test_context_budget_gate.py:319-320`: "Deleting the seek (reading
  the FIRST 64 KB) flips the exit code, because the over-BLOCK record sits on line 2").
- Measured — mutant 2a applied exactly as the plan names it (the `if size > TAIL_BYTES: handle.seek(...)`
  pair deleted, `blob = handle.read(TAIL_BYTES)` kept), then reverted:

      FAILED tests/test_context_budget_gate.py::test_only_the_tail_is_read
      AssertionError: only the last 64 KB may decide: the 900K record on line 2 is outside that
      window (rc=2, stderr='read_bytes=65536\nBLOCKED context-budget-gate: this session is at
      900K tokens of context (block at 400K)…')
      1 failed, 23 passed in 1.76s          # restored → 24 passed in 1.72s

  `read_bytes` is **unchanged** at 65,536 under this mutant; the only thing that moves is the exit
  code — the exact opposite of what the plan now asserts. There are two independent mutants here and
  the test kills both: 2a by `rc`, 2b (whole-file read) by `read_bytes`.
- Impact: none on shipped behaviour or coverage — the hook is correct and the test pins the property
  from both sides. The cost is that a future reader re-deriving the proof from the archived plan is
  told a verdict-flip variant does not exist, and will not apply the cheaper of the two mutants.
- Class: `mutation-proof-names-the-wrong-mechanism`
- Fix (one sentence, non-blocking): replace the last sentence with "Two mutants live here: 2a, delete
  the seek only → the FIRST 64 KB is parsed, the 900K record on line 2 decides, `rc` flips 0→2 with
  `read_bytes` unchanged; 2b, read the whole file → same verdict, `read_bytes` 65,536 → 40 MB. The
  test kills both."

**RATCHET — this class has now reached three entries on this artifact and earns a mechanical check:**
1. round 1 H1 — named mutant 2 survived; the test pinned the fragment-drop, not the tail seek;
2. round 2 M2-r2 — the plan explained mutant 2 by a verdict flip the whole-file reader does not cause;
3. round 3 M1-r3 — the correction over-swung and denied the verdict-flip variant that does exist.

Every one of them is a *prose* claim about a mutant that nobody executed. Proposed check: make named
mutants executable rather than described — a `payloads/<plan>/mutants/NNN-<slug>.patch` per named
mutant plus a one-line manifest `patch → test that must redden`, and a `scripts/check-mutants.py`
that, given a plan, applies each patch, runs the named test, asserts RED, and reverts. The plan's
"Named mutants" section then becomes a generated table, and a wrong mechanism claim becomes
impossible to write down. Not mechanisable cheaply for mutants that need multi-hunk edits — those
stay prose, flagged as such. Recommend filing this against `.ai/REVIEW_GUIDE.md` as the class's check;
it is a follow-up, not a condition of this merge.

## LOW

### [L1-r3] Warn counters are still never pruned and a payload without `session_id` shares one bucket
- File: `.claude/hooks/context-budget-gate.py:198-218`. Unchanged since round 1 (L2), by choice.
- Advisory-only state: worst case is one small file per session, forever, under an ignored directory.
- Class: `unbounded-state-accumulation`
- Fix: prune by mtime, or skip the write when `session_id` is absent. Follow-up.

---

## INHERITED FINDINGS

### [H1-r2] Registry matcher omitted `NotebookEdit` while the test asserted it — RED suite
- Status: **discharged**
- Evidence: executed `dispatch-registry.json:49` now carries
  `"matcher": "Write|Edit|NotebookEdit|Bash|Agent|Task"`; plan:49 and plan:175 match; full file
  `24 passed in 1.77s` on the unmutated executed tree (was `1 failed, 23 passed`).

### [M1-r2] CHANGELOG contradicted shipped behaviour (subagent carve-out, path shape)
- Status: **discharged**
- Evidence: the executed `[Unreleased]` entry now reads "in a main session, refuses the call at
  `CK_CONTEXT_BLOCK`", names `<session-id>/subagents/agent-*.jsonl`, and carries the subagent
  advisory sentence. Grepped in the executed `CHANGELOG.md`, not in the ops payload.

### [M2-r2] Mutant-2 prose named the wrong mechanism
- Status: **superseded** by M1-r3 — the verdict-flip overclaim is gone; a new, opposite overclaim
  replaced it. Net: the `read_bytes` mechanism is now stated correctly, which was the round-2 ask.

### [L1-r2 / round-1 L2] Counter pruning
- Status: **open** → carried as L1-r3.

### Round-1 H1, M1, M2, M3, L1, L3
- Status: **discharged in round 2** (three mutants hand-applied and each killed a distinct test;
  `_state_dir()` cwd guard measured; `NotebookEdit` verified to reach the handler through the real
  dispatcher at rc 2). Not re-derived here.

---

## POSITIVE OBSERVATIONS

- Seven ops, three rounds, and the executed tree is green on the first try this round: 7/7 ops, 0
  errors, 24/24 tests, no follow-on edit needed to make the suite pass.
- The coordinator's delta was exactly the delta claimed — every one of the four named changes is
  present in the executed artifacts and nothing else moved. That is what makes a ≤6-call round
  possible.
- The test file is the strongest part of this change: `test_only_the_tail_is_read` kills two distinct
  mutants (one by `rc`, one by `read_bytes`), and `test_the_leading_fragment_is_never_parsed` carries
  its own positive control. The plan's prose has been wrong about that test three times; the test has
  been right since round 2.

## NOT RE-VERIFIED THIS ROUND (do not read as clean)

- Full `pytest tests/ -q` — out of scope in all three rounds. Round 1's 21 unattributed failures on a
  scratch clone remain unattributed. **Run it on a clean clone before and after execution and diff the
  names before committing.** This is the one open evidence gap on the change.
- `ruff`, `mypy`, `gen-docs.py --check` — all clean in round 2 and none of the round-3 edits touch
  Python source (registry JSON, CHANGELOG prose, plan prose). Re-run them as part of the normal DoD
  gate, not as a condition of this review.
- The round-1 adversarial input matrix, 14-transcript efficacy run and concurrency probe were not
  repeated.

## REVIEW COVERAGE

Correctness: checked (mutant 2a executed this round; three mutants in round 2) · Security: checked (no
new surface; fail-open intact) · Performance: checked (`read_bytes <= 69,632` on a 40 MB transcript,
asserted by the suite) · Reliability: checked · Silent failures: checked · Code quality:
spot-checked · Full suite: NOT RUN.

=== REVIEW ===
SCORE: 92
DECISION: APPROVED
- [MINOR] plan-context-budget-gate.md:152-157 — the rewritten mutant-2 prose ends with "there is no verdict-flip variant"; measured, mutant 2a (delete the seek only) flips rc 0→2 with read_bytes unchanged at 65536, and the test's own docstring says so. Replace the sentence with the two-mutant form. Non-blocking.
- [MINOR] RATCHET: mutation-proof-names-the-wrong-mechanism has reached 3 entries on this artifact (r1 H1, r2 M2-r2, r3 M1-r3). Proposed check: per-plan mutants/*.patch + manifest + scripts/check-mutants.py that applies each patch, asserts the named test reddens, and reverts. File against .ai/REVIEW_GUIDE.md as a follow-up.
- [MINOR] context-budget-gate.py:198 — warn counters still never pruned; a payload without session_id shares one "unknown" bucket.
- [MINOR] Evidence gap: the full suite was never run in any round. Run `pytest tests/ -q --tb=no -rf` on a clean clone before and after execution and diff the failure names before committing.
=== END REVIEW ===
