# Frozen held-out review set

`flow-analyst` refuses to recommend shipping a prompt edit without one of these, and until
now none existed — so the analyst could analyse but never conclude. This is that set.

## What it is

14 fixtures drawn from the 88 committed verdict records in `.claude/reports/reviews/`,
selected **deterministically** (see `MANIFEST.json:note`): for each distinct recorded score
90–96, the smallest and the largest configuration by operation count, restricted to records
whose plan file still exists. That spans 1–18 operations and 0–25 edits and includes the
only multi-round record in the usable set.

Each fixture pins the plan, the approved ops snapshot, the recorded score/decision, and the
**sha256 of both artifacts**. Freezing is by hash rather than by copy: the artifacts are
already committed, and a second copy is a second thing to drift.

## What it can and cannot tell you — read this before quoting a result

**All 88 records are APPROVED.** So this set answers exactly one question: *does the edited
prompt still approve what it approved?* It catches an edit that makes the reviewer harsher
— a false-rejection regression. **It cannot catch an edit that makes the reviewer laxer**,
because there is not one recorded rejection to hold out. That corpus is what the rejection
briefs are now accumulating; when it is large enough, half of this harness is still missing
until rejection fixtures are added here.

Anyone quoting "no regression against the held-out set" must quote that sentence with it.

## The protocol — how a proposed prompt edit is scored

1. **Baseline** is the manifest: every fixture's recorded decision (all `APPROVED`, ≥90).
2. **Integrity first.** `python3 scripts/heldout-check.py --verify` must print `OK` for all
   14. Any `DRIFTED` fixture means the frozen artifact changed underneath the set; re-freeze
   it deliberately (and say why) before measuring anything.
3. **Replay.** On a branch carrying the proposed edit, re-review each fixture — `/review`,
   or `claude -p --agent reviewer` — and save the verdicts:
   ```json
   { "prompt_version": "<git short sha>",
     "verdicts": { "<fixture id>": { "score": 93, "decision": "APPROVED" } } }
   ```
4. **Score it.** `python3 scripts/heldout-check.py --results <file>`:
   - **exit 5** — at least one fixture flipped `APPROVED` → non-`APPROVED`. **The edit does
     not ship.** This flip is the gate; nothing else is.
   - **exit 0** — no flip. The mean score delta is printed and is **reported, not gated**:
     the same plan can score 92 or 94 across runs, and gating on noise makes the harness a
     coin toss.
   - a fixture missing from the results file is a **failure**, not a skip.
5. Attach the run to the proposal. `flow-analyst` may propose without one; it may not
   recommend shipping without one.

**Step 3 is manual and is not automated — stated, not implied.** Automating it means
spawning `claude -p` fourteen times: real token cost, non-deterministic output, and it must
never sit in CI. `heldout-check.py` automates the two halves that ARE deterministic —
fixture integrity and the comparison — and the replay stays an owner-invoked step.

## Re-freezing

Editing a pinned plan invalidates its fixture on purpose — including between the moment
this set is written and the moment it is executed, which **happened twice while it was
being written** (`plan-dispatcher-payload.md` and `plan-fleet-skill-enhancement.md` moved
under it, and `--verify` caught both). That is the mechanism working.

```bash
python3 scripts/heldout-check.py --freeze   # names every artifact that moved
```

`--freeze` re-records the hashes and prints one `RE-FROZE` line per changed artifact.
State in the commit **why** each moved. Re-freezing to turn a red run green is the one
thing this file exists to prevent, and nothing but review stops it.
