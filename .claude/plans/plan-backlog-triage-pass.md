# Implementation Plan: a partial triage pass over the BACKLOG's `code-review.md` entry

**Status:** EXECUTED 2026-08-24 (partial by design — see below). Tier 1, one maintainer
doc. 1 ops config.

## Read `plan-code-review-triage.md` first — and an error to record

`plan-code-review-triage.md` (Workstream 13, unexecuted) already owns this ground, and I
**overwrote that file** with an early draft of this one before checking whether the path
existed. Restored from `HEAD`; this plan took a new slug. The mistake is recorded because
the near-miss is the point: a heredoc onto a plan path is a silent overwrite, and nothing
in the operations engine was involved to stop it — `git status` showing `M` instead of `??`
was the only signal.

Two substantive differences with that plan, both of which it owns and this pass does not
resolve:

- **It counts 103 findings; this pass counts 75.** Not a contradiction — 103 is every
  severity (P0-P3), 75 is P2/P3 only, which is the scope the BACKLOG entry describes. Its
  number is the right one for a full triage.
- **It puts the triage in a NEW file, `review/code-review-triage.md`, and explicitly holds
  `.ai/**` out of scope** ("owner holds BACKLOG/REVIEW_GUIDE). This pass edited
  `.ai/BACKLOG.md` instead, because the handoff assigned exactly that and asked for the
  count in that entry to be re-derived. **Flagged rather than reconciled**: if the owner
  prefers Workstream 13's shape, the 30 verdicts below move to `review/code-review-triage.md`
  and the BACKLOG entry goes back to a pointer.

## Scope

`.ai/BACKLOG.md` filed this as "76 unfixed P2/P3 findings". A later grep for `P2|P3`
returned **88**, and the entry was updated to quote that instead. **Both numbers are
wrong**, in the same way: they count *mentions*, including the severity-scale legend at
`review/code-review.md:7` and prose that merely names a severity.

Parsed structurally — a `### P2/P3 —` heading, or a bullet opening `**P2**` / `**P3**` —
the file holds **75** findings. That is the number this triage works from, and re-deriving
it was the first task, exactly as the handoff instructed.

## What was actually verified

**30 of 75**, each by opening the file the finding names and checking the line:

- **19 already fixed.** Most were closed incidentally by later work rather than by anyone
  working this list — including the `atomic_write` mode-stripping P2 that the BACKLOG entry
  records as having cost real damage before it was fixed.
- **11 still real**, with a current file:line for each. The two highest-value: `ExecutionLock`
  is not a lock on Windows and its `release()` unlinks a lock another process may hold
  (`execute-json-ops.py:159-183`), and `config.schema.json:75` still advertises "195+
  patterns" for a hook with ~60 that is wired into nothing.

**45 remain unverified and are recorded as unchecked**, not as "probably fine". Claiming
otherwise would make this triage the same shape as the gate that scanned nothing.

## Two traps, recorded because both nearly produced a wrong verdict

1. **A finding whose path moved is not a finding that went away.** §6's eight findings target
   `templates/hooks/`, which no longer exists — so they read as retired. Batch 1 *promoted*
   those hooks into `.claude/hooks/`, and four of the eight are still live against the
   promoted files.
2. **`lib.sh` existing is not the duplicate-`log()` fix.** It looked like it. `lib.sh` does
   not define `log()`; 14 hooks still define their own. Caught by grepping for the symbol
   instead of reasoning from the file's existence.

Both errors came from reasoning about a fix rather than grepping for it — the same root as
the gate defect fixed in `plan-queued-ops-gate.md`.

## Not in scope

Fixing any of the 11. Each needs its own plan; three touch the enforcement layer
(`ExecutionLock`, `file-guard.sh`, the unwired-hook schema claim) and are owner-gated.

## Definition of Done

Documentation only: gen-plan-index, the delivery-contract smoke tests, and the full suite.
