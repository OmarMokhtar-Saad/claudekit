# Plan: review records keep their round history

Slug: `review-round-history` · Ops: `.claude/plans/ops-review-round-history.json`
Tier: **3** (touches the approval machinery — security-relevant surface)
Origin: ruvnet/ruflo review item 3 (agent reliability scoring), blocked on data.

## Problem

`review-record.py write` writes one record per ops slug and **overwrites it**
(`review-record.py:248`). A re-review after revision destroys the verdict it
replaces. Measured on the live corpus today:

```
records: 51   decisions: {'APPROVED': 51}   scores: min=90 max=96 mean=93.0
has round history? False      has agent/author? False
```

Every record is an approval scoring 90-96 — not because reviews always pass,
but because **only the passing round survives**. This session is the proof: the
plan behind `afc4ba8` was scored **80/100 CONDITIONAL with two MAJOR findings**,
revised, then **95/100 APPROVED**. Only the 95 exists on disk. The two MAJORs —
one of which later turned out to rest on a false premise, proven by mutation —
left no trace.

Consequences:

1. **The proposed agent-reliability scoring cannot be built.** Rounds-to-clean
   and score trajectory are the signal; both are erased at write time.
2. **`.claude/model-policy.json` tiering stays a judgement call**, because the
   outcome data that would inform it is discarded.
3. **Nobody can tell whether the review floor's 3-round ceiling ever binds** —
   the field that would answer it does not exist.
4. The survivorship bias is invisible: the corpus *looks* like a 100% approval
   rate with a tight 90-96 band, which is a strictly misleading summary of how
   review actually goes.

## Non-goals

- **No agent attribution.** Nothing in the pipeline passes the authoring or
  reviewing agent's identity to `review-record.py`, and inventing a field the
  callers never populate would add a second misleading signal. Attribution is a
  separate change to the agent prompts and is not attempted here.
- No scoring, ranking, or model-policy change. This makes the data exist; using
  it is a later, evidence-backed step.
- No change to what `check` reads or how it gates. See Safety below.

## Design

On `cmd_write`, before writing: if a record already exists for this slug and
parses, fold it into the new record as a prior round.

```python
prior = <existing record, if it parses>
rounds = list(prior.get("rounds") or [])       # the prior record's own history
rounds.append({k: prior[k] for k in ROUND_KEYS if k in prior})
record["rounds"] = rounds[-MAX_ROUNDS:]
record["round"] = len(record["rounds"]) + 1
```

`ROUND_KEYS = ("score", "decision", "findings", "recorded_utc", "ops_sha256")`
— enough to reconstruct the trajectory and to see *which artifact* each verdict
was bound to, which is the point of the hash.

`MAX_ROUNDS = 20`: history is for a review loop with a documented ceiling of 3,
so 20 is far above any real run while bounding a pathological loop. When the cap
drops entries the write says so on stderr rather than truncating silently.

An unreadable existing record is **not** fatal and **not** silently discarded:
the write proceeds (refusing would make a corrupt file block all future
approvals) and warns that history was lost.

The catch is deliberately `except Exception`, matching `cmd_check` (:309) and
`cmd_diff` (:380), which handle this same "read an existing record" operation
the same way. A narrower `(json.JSONDecodeError, OSError)` looks tighter but is
not: a record holding **invalid UTF-8** raises `UnicodeDecodeError` — a
`ValueError`, neither of those — and would crash the write, bricking every
future approval for that slug. That is exactly the failure this fallback
exists to prevent, so the catch covers the whole corruption class rather than
the two members of it that come to mind first.

### Safety — why this cannot weaken the gate

`cmd_check` reads `score`, `decision`, and `ops_sha256` from the record's **top
level**, and those are written exactly as before; `rounds` is additive. The
threshold, the drift comparison, and the fail-closed paths are untouched. The
regression tests below assert the gate's behaviour directly rather than
inferring it from the diff.

## Files

| File | Change |
|---|---|
| `.claude/operations/scripts/review-record.py` | `ROUND_KEYS`, `MAX_ROUNDS`, history fold in `cmd_write` |
| `tests/test_review_record.py` | history accumulates; gate semantics unchanged |
| `CHANGELOG.md` | `[Unreleased] / Added` |

## Test plan (behavioural)

- Two writes for one slug → second record has `rounds` of length 1 carrying the
  first verdict's score/decision/hash; `round == 2`.
- Three writes → `rounds` length 2, **in chronological order**.
- A REVISE followed by an APPROVED preserves the REVISE — the exact case the
  corpus currently erases.
- **The gate still gates**: after a second write, `check` on the approved config
  exits 0; a REVISE-then-nothing record still refuses execution; a drifted
  ops.json still reports DRIFT (exit 2). These pin the Safety claim.
- A corrupt existing record → write succeeds, warns, `rounds == []`. Tested
  **twice**, for both halves of the corruption class: invalid JSON that is valid
  UTF-8, and invalid UTF-8 bytes. The second is the one a narrow catch misses.
- Cap: `MAX_ROUNDS + 3` writes → length capped, oldest dropped, notice emitted.

Every assertion is proved by mutation: revert the fold and the history tests
fail; revert nothing and the gate tests still pass.

## Rollback

`git revert` of the single commit. The `rounds` key is additive and ignored by
every existing reader, so records written while it was live stay valid
afterwards — no migration in either direction.

## Review

Round 1 scored **88/100 REVISE** (2 MAJOR). Both were the same defect and its
missing test: the prior-record read caught only `(json.JSONDecodeError,
OSError)`, so a record with invalid UTF-8 would raise an uncaught
`UnicodeDecodeError` and brick the slug — while the test named for that claim
supplied only valid-UTF-8-but-invalid-JSON and so never exercised it. Verified
before acting (`UnicodeDecodeError` is a `ValueError`; `isinstance` against both
caught types is `False`). Fixed by broadening the catch to the file's existing
convention and adding the invalid-UTF-8 test. The MINOR (operator visibility of
folded findings counts) is not taken: the trail line already prints every
round's score and decision, and a findings tally adds noise to the common
single-round case.

## Risk

Low-to-moderate: the file is approval machinery, so the risk is not the feature
but the blast radius of touching it. Mitigated by keeping every gate-relevant
field and code path untouched, and by asserting the gate's behaviour in tests
rather than reasoning about it.
