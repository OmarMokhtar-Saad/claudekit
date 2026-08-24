# Implementation Plan: record the 2026-08-24 intermittent sighting

**Status:** EXECUTED 2026-08-24. Tier 1, one maintainer doc. 1 ops config.

One full-suite run during this period failed exactly one member of the documented
receipt-clears-checkpoint family — `test_receipt_via_cli_clears_the_checkpoint` at
`tests/test_reflection_ledger.py:409` — and did not reproduce: standalone pass, 54/54 for
the file, and a clean full re-run at **2902 passed, 0 failed**.

**The point of this plan is the second half.** `receipt_diagnostic()` exists precisely so a
captured failure can explain this family, and it fired — into a run piped through `tail -4`
to keep the transcript small. Only the summary line survived. The BACKLOG entry already
records the same loss on 2026-08-21 via `/dev/null` and calls it "precisely the mistake this
item exists to prevent"; this is that mistake in a new costume, which generalises the
lesson: **the capture is not the weak link, the harness around the run is.** A summary-only
invocation defeats it exactly as completely as a redirect to nowhere.

The entry now carries an explicit rule for the next runner — never pipe a full-suite run
through `tail`/`head` when this family can fire; write the whole output to a file and
summarise from the file.

No cause is claimed. No retry was added. The assertion is unchanged.

## Definition of Done

One maintainer doc: the full suite (already green at 2902), gen-plan-index, delivery-contract
smoke tests.
