# Implementation Plan: correct the commit counts in the period close

**Status:** EXECUTED 2026-08-24. Tier 1, two maintainer docs. 1 ops config.

`SESSION_STATE.md` said **26 commits ahead** and `CHANGELOG_AI.md` said **four commits**.
Both were **predictions**, written before committing on the assumption of one commit per
plan. The period landed **three** commits and the tree is **24** ahead of `origin/main`.

Corrected rather than left to be discovered, for the obvious reason: a wrong number in the
resume point is precisely the class this period spent its time on — a count quoted from an
expectation instead of derived from the thing being counted, which is how the BACKLOG entry
triaged this period reached 76 and then 88.

Both files now also say that the last commit bundles three plans, so the numbered list of
work items is not misread as one commit each. That commit carries a `Plan-Id:` trailer per
plan, which is what `gen-plan-index.py` reads.

## Definition of Done

Two maintainer docs: gen-plan-index, the delivery-contract smoke tests, `git rev-list
--count origin/main..main` matching the number written.

## Config 02 — retire the number instead of correcting it again

The corrected **24** became **25** the instant the correction commit landed. A commit count
written inside a commit is stale the moment it lands, so a third correction would have been
the same mistake a third time. The resume point now carries the **command** —
`git rev-list --count origin/main..main` — plus a snapshot explicitly labelled as one, and
leads with the fact that does not decay: the work is unpushed and pushing is owner-gated.
