# Implementation Plan: the live hook findings (three fixed, one deferred with numbers)

**Status:** EXECUTED 2026-08-24. Tier 2 (four hook scripts + one test file). 7 ops configs.

The hook half of the eleven findings `plan-backlog-triage-pass.md` confirmed live.

| Finding | Verdict now | Action |
| --- | --- | --- |
| `auto-checkpoint.sh` prune math | **REAL, and sharper than the review said** | fix |
| `auto-checkpoint.sh` registry read/modify/write is unlocked | REAL | fix |
| `session-start.sh` `PM_INSTALL`/`PM_RUN` dead | REAL | fix |
| failure output truncated to `tail -20` | REAL | fix |
| `log()` copy-pasted across 14 hooks | REAL, and **bigger than it looks** | **deferred, measured** |

## 1 — the prune math: two guards that disagree by one

There are **two** guards, and they do not say the same thing:

- shell, `auto-checkpoint.sh:69` — `[ "$count" -lt "$MAX_CHECKPOINTS" ] && return 0`, i.e.
  *prune when count ≥ max*;
- python, `:86` — `if len(checkpoints) <= max_cp: sys.exit(0)`, i.e. *skip when count = max*.

So at exactly `count == max` the shell decides to prune and the python decides not to, the
append then takes the registry to `max + 1`, and the next run prunes back. **Measured by
executing the real block against fixtures rather than reading it** — with
`MAX_CHECKPOINTS=3` the registry size oscillates `3 → 4 → 3 → 4`, from every starting
size:

    max=3 start=2: [3, 4, 3, 4, 3]
    max=3 start=3: [4, 3, 4, 3, 4]
    max=3 start=4: [3, 4, 3, 4, 3]

It is bounded, so not a leak — but the configured cap is exceeded on every other
checkpoint, and each extra registry entry is a retained git stash the user did not ask to
keep. Fix: the python guard becomes `< max_cp`, which is what the shell guard already
implies, and the `+1` (reserving room for the checkpoint about to be appended) becomes
correct rather than compensating.

**A near-miss worth recording.** My first simulation extracted the wrong `python3 -c` block
from the file — a three-line counter — and "proved" the registry grows without bound. Caught
by printing what had been extracted before trusting the numbers. Executing the wrong code is
not better than reading the right code.

## 2 — the registry is mutated twice with no mutex

`prune_old_checkpoints` does a read-modify-write, and the append after the stash does
another. Two concurrent Stop hooks — which this repo treats as a real scenario, since
`session-start.sh` warns about live concurrent sessions — can interleave and leave a
truncated or half-written `checkpoints.json`.

Fixed with the mutex idiom this repo already ships in `suggest-compact.sh:31`: `mkdir` as a
portable atomic lock (flock is Linux-only) plus `find -mmin +1` stale recovery (`date -r`
and `stat` differ across platforms).

**One deliberate difference from that sibling.** `suggest-compact.sh` *skips its work* when
the lock is held, because a lost counter increment is harmless. A skipped checkpoint is
not: it is the user's uncommitted work. So this lock waits briefly and, if it still cannot
acquire, **proceeds anyway with a logged WARN** rather than dropping the checkpoint. The
protected sections are short; the failure mode chosen is "possible size overshoot" and
never "lost work".

## 3 — `PM_INSTALL` / `PM_RUN` are written eight times and read never

`session-start.sh:17-51`. The startup summary prints `$PM` only. Removed; `$PM` and its
detection stay.

## 4 — `tail -20` hides the root cause

`post-implement.sh:98,130` and `pre-push.sh:150` print only the last 20 lines of a failed
build/test/lint run, and the first error is usually far above the last 20 lines of a test
summary. Raised to the last 60, with the full output's location named so the reader is
never left guessing where the rest went.

## 5 — DEFERRED: `log()` across 14 hooks. Measured, and the number changes the decision

`lib.sh` already ships `hlog()`, and `commit-quality.sh` already delegates to it
(`log() { hlog "$1" "$2"; }`) — so the target state exists and one hook is already there.
But:

- the 14 local `log()` definitions are **four distinct implementations**, not one repeated:
  the plain appender (2 files), the appender that also echoes ERROR/WARN to stderr (6),
  a two-positional-arg one-liner (2), and a variant that hardcodes the hook name and writes
  to **`$LOG`** rather than `$LOG_FILE` (3);
- **only 2 of the 14 source `lib.sh` at all.** Delegating means adding a `. lib.sh` line to
  12 hook scripts, each of which then inherits every other definition in that file.

That is a 12-file change to the hook layer — including `pre-commit`, `pre-push`,
`prompt-injection-scanner` and `file-guard` — in exchange for deduplication, with no
user-visible defect behind it. It is a reasonable change and it is **not** the kind to make
alongside three unrelated fixes, so it is filed with the measurement above rather than
attempted here.

## Testing

Behavioural, mutation-proven:

1. the pruner run against fixtures at `count == max`, asserting the registry lands **at**
   `max` and not `max + 1` — the oscillation reproduced before the fix and absent after;
2. two concurrent `create_checkpoint` runs leave valid JSON;
3. `PM_INSTALL` absent from the script, `PM` detection unchanged;
4. a failing command's output shows more than 20 lines and names where the full log is.

## What the property test found that the review did not

The `tail -20` finding named three sites. Asserting the **property** — no short tail on a
failure branch — instead of patching those three found **three more**: the coverage failure
path in `post-implement.sh`, and the lint and build failure paths in `pre-push.sh`, the last
two on the gate that stops a push, where the printed output is the only thing the user has
to act on. Six sites, not three.

It also forced the test to be honest about the other direction: a *success* summary's short
tail is correct (a coverage summary is exactly what you want short), and a regex over the
number alone cannot tell the two apart. The test now classifies each site by the marker the
hook prints immediately above it — the same signal the hook itself uses — and separately
asserts that success branches stay short, so "fix" cannot mean "print everything everywhere".

## Two of my own defects, caught by the new tests rather than by re-reading

1. **Backticks inside a `python3 -c "..."` string.** The comment explaining the prune fix used
   markdown backticks — inside a double-quoted *shell* string, where a backtick is command
   substitution. The shell would have executed `< max_cp` and spliced the result into the
   Python source. `shellcheck` flagged it as SC2006 within a minute. **This is the argument
   for the command-bash lint gate this session filed and did not land.**
2. **A test that forbade its own explanation.** The `PM_INSTALL` assertion matched the bare
   string anywhere in the file, so it failed on the comment recording why the variable was
   removed. Now it asserts no assignment and no expansion.

## Mutation proofs, against the shipped hooks

| Mutant | Result |
| --- | --- |
| pruner guard back to `<= max_cp` | cap + guard-agreement tests RED |
| the lock `exit 0`s under contention instead of proceeding | contention test RED |
| one failure `tail -60` back to `tail -20` | failure-path test RED |
| `PM_INSTALL=""` restored | dead-variable test RED |
| shipped | 11 passed |

**One mutant initially reported GREEN and that is worth more than the four that worked.**
`sed -i '' '0,/re/s/...'` silently does nothing on BSD sed — address `0` is a GNU extension —
so the "mutation" never applied and the test passed for the wrong reason. Verified the file
had actually changed, redid it with a targeted edit, and the test failed as designed. **A
mutation proof is only evidence if the mutation landed**, which is the same lesson as a gate
that cannot fail, one level up.

## A third defect of mine, found by watching the suite instead of the assertions

The suite stalled at 36%. The cause was **my own test from the previous commit**: the fake
wedged `bash` was `#!/bin/sh\nsleep 120`, so the shell **forked** the sleep.
`subprocess.run(timeout=)` kills the process it spawned — not the grandchild, which keeps
the inherited stdout pipe open, so the caller then blocks in `communicate()` until that
sleep ends. Two 120-second orphans per run, and a test that could take longer than the hang
it was written to disprove.

Fixed with `exec` (the fake now *becomes* the sleeping process, so the kill lands on the
thing holding the pipe) and 30s instead of 120.

**The important half is what it says about the product fix.** `timeout=` does not bound the
wall clock when the probe forks. That limit is now recorded at `PROBE_TIMEOUT` and stated in
the CHANGELOG entry rather than left as an implied absolute; closing it needs
`start_new_session=True` and a process-group kill — a Popen rewrite of both probes, filed
rather than folded in. **A green test told me nothing here; the stall did.**

## Definition of Done

The full `CLAUDE.md` gate list, `shellcheck` on the three hooks, and a `CHANGELOG.md`
entry — the checkpoint cap and the truncated failure output are both user-visible.
