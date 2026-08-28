# Plan — a tripwire for the review loop that never terminates

## Overview

**Approach:** `review-record.py write` already reconstructs a slug's full verdict history
into `rounds[]`. Read it. When a plan reaches three consecutive non-approving rounds,
say so loudly, on the record and on stderr — advisory, never blocking.

The review loop's ceiling is **documented but unenforced**. `review-record.py:65-66` says
in prose: *"The review loop's documented ceiling is 3 rounds; 20 is far above any real run
while still bounding a pathological loop."* `MAX_ROUNDS = 20` is a memory bound on the
array, not a signal to anyone. Nothing anywhere counts consecutive rejections, and nothing
tells a caller it is in a loop.

## 1. Scope (Steps)

| # | File | Change |
|---|---|---|
| A | `.claude/operations/scripts/review-record.py` | `LOOP_TRIPWIRE_ROUNDS`, `loop_advisory()`, wire into `cmd_write`, surface in the brief |
| B | `tests/test_review_record.py` | Behavioural coverage incl. two mutation-resistant cases |
| C | `CHANGELOG.md` | `[Unreleased]` entry |

## 2. Evidence — the loop this is built from

AppiumLens, `plan-network-ios-self-service-url-launch`, 2026-08-28, six rounds:

```
79 REVISE -> 78 REVISE -> 72 REVISE -> 86 CONDITIONAL -> 86 CONDITIONAL -> 81 REVISE
```

Three different concurrency mechanisms across six rounds (passive `isBound()` ->
`synchronized doBind` -> `AtomicBoolean` CAS ticket -> fair `ReentrantLock`). Each change
silently falsified javadoc, constants and tests written for its predecessor. By round 6 the
false javadoc had reached the ops payload destined for `src/main`, and the headline
concurrency test was vacuous for the second time.

Nothing in the machinery noticed. The loop was caught by a human writing a retrospective
afterwards (`.claude/reports/retrospective/2026-08-28-six-round-revise-loop.md`), and its
"three-strike split rule" has lived as prose in a report file ever since — which is exactly
the state this plan's own subject was in.

The backfilled ledger for that plan now classifies its rounds
`untested-behaviour` x3, `scope-overflow` x2 — i.e. the loop was a scope problem, and a
scope problem is precisely what more rounds cannot fix.

## 3. Design decisions

1. **Advisory, never blocking — and this is the load-bearing choice.** `cmd_write`'s job is
   to make a verdict durable. A tripwire that refused the write, or exited non-zero, would
   destroy the history that makes loop detection possible in the first place, and would do
   it on the round where the information is most valuable. It prints and records; it never
   changes the return code. Same reasoning the file already applies to `emit_brief`.
2. **CONSECUTIVE, not cumulative.** A plan that is rejected, fixed, approved, then reopened
   months later for a different reason is not in a loop. The counter resets on a verdict
   that authorises execution.
2b. **Reuse `is_rejecting`, never a decision-word test (round 2, reviewer MAJOR).** The
   first draft hand-rolled `_NON_APPROVING = ("REVISE", "REJECTED", "CONDITIONAL")`. But
   `write` will happily record `SCORE: 85 / DECISION: APPROVED` — a real verdict that
   `cmd_check` still refuses (exit 4) — and a word-only predicate reads that as an
   approval and silently resets a live streak. `is_rejecting(score, decision)`
   (`review-record.py:266`) exists precisely so "rejection" means one thing in this file
   and can never disagree with the gate. A second, subtly different predicate is the
   defect it was written to prevent.
3. **Non-monotonic score is reported separately, and the test is where the peak LAST
   occurs.** From the retro's rule 3: a score that holds or rises and then falls
   (86 -> 86 -> 81) is evidence the plan is too large to converge, not that the last round
   was sloppy. Two obvious conditions are both wrong (round 2, reviewer MINOR):
   `max > scores[0]` misses the retro's own plateau shape, since `86 > 86` is False; and
   `scores[-1] < max` alone calls a plain monotonic decline non-monotonic. Firing when the
   peak's LAST index is > 0 and the final score is below it handles both.
4. **The advisory lands in the record, not only on stderr.** stderr is read by whoever is
   watching at that second; `loop_advisory` in the JSON is readable by the next session,
   by `/flow-retro`, and by a human opening the file. The AppiumLens warning that nobody
   read (`WARNING: verdict NOT recorded`) is the cautionary case.
5. **Threshold 3, named, not inline.** `LOOP_TRIPWIRE_ROUNDS = 3` matches the ceiling
   already documented at line 65-66. One constant, so the prose and the behaviour cannot
   drift apart again.

## 4. Testing / Verification

- `python3 -m pytest tests/ -q` — zero failures.
- `ruff`, `mypy`, `shellcheck`, the four drift gates.
- Behavioural, in `tests/test_review_record.py` against the real script:
  1. three consecutive REVISE rounds fire the advisory; the exit code is still 0 and the
     record is still written (the non-blocking property, pinned);
  2. two REVISE then an APPROVED then a REVISE does **not** fire it (reset-on-approve);
  3. a CONDITIONAL counts as non-approving;
  4. the non-monotonic notice fires on a rise (`72 -> 86 -> 81`) AND on the retro's
     plateau shape (`86 -> 86 -> 81`), and not on a monotonic decline (`86 -> 80 -> 72`);
  4b. an `APPROVED` scored below the threshold does NOT reset the streak;
  5. `loop_advisory` is present in the written JSON, not only on stderr.
- **Mutation proof:** changing the counter from consecutive to cumulative must fail test 2;
  removing the advisory from the record must fail test 5. A tripwire that cannot fail is
  the failure class this repo keeps re-finding.

## 5. Rollback

Single-file behavioural change plus its tests; all `code_edit`, no creates or deletes. The
executor backs up each file before writing.

1. `restore-backup.py --list` then `--backup <dir>`.
2. Or `git checkout -- .claude/operations/scripts/review-record.py tests/ CHANGELOG.md`.
3. **Blast radius:** the advisory cannot change `cmd_write`'s return code, cannot change
   what `cmd_check` reads (`score`/`decision`/`ops_sha256` stay at the top level, untouched),
   and cannot withhold an approval. Worst case on a bug is a spurious or missing message.
4. **Downstream:** installed projects pick this up on their next `ck update`.
