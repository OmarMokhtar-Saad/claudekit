# Implementation Plan: Code-Review Triage (Workstream 13)

## Overview
`review/code-review.md` (2026-07-05) holds 103 discrete findings that have never been
tracked. One of them (`atomic_write` mode preservation) shipped real damage on 2026-08-19
before an incidental `git log --diff-filter=M --summary` audit caught it. This plan
produces `review/code-review-triage.md`: a per-finding status (FIXED / LIVE / OBSOLETE /
UNVERIFIABLE) verified against the current tree by execution or reading, plus a
"what should have caught this" gate-gap section.

## Scope
- **In Scope:** create `review/code-review-triage.md` (new file, analysis only).
- **Out of Scope:** fixing any finding; editing `review/code-review.md`; editing `.ai/**`
  (owner holds BACKLOG/REVIEW_GUIDE); any product-code change. This workstream changes
  no behavior.

## Prerequisites
- None. Verification already performed against branch `perf/token-efficiency` @ `c167298`.

## Implementation Steps

### Step 1: Create the triage document
- **File:** `review/code-review-triage.md`
- **Action:** Create
- **Description:** Full triage of all 103 findings, grouped by the original review's
  section numbering (§1-§11), each with Status, current file:line, recurrence Class,
  Priority + one-line justification, and the evidence that produced the verdict.
- **Details:** Headline counts at the top (total / LIVE / FIXED / OBSOLETE /
  UNVERIFIABLE) so the real state is readable in ten seconds. Includes a
  "What should have caught this" section mapping each LIVE finding to the gate that
  could catch it mechanically, and naming the ones that cannot be mechanised.

## Testing Strategy
- No behavioral change, so no test additions. Verification of the document itself is the
  evidence trail already recorded inline per finding (commands run, files read).
- `python3 scripts/gen-docs.py --check` must stay green (no component counts introduced).

## Rollback Plan
- `git rm review/code-review-triage.md` — the file is new and nothing references it.

## Risk Assessment
- **Low Risk:** single new markdown file under `review/`, imported by nothing, executed by
  nothing. No hook, CI job, or installer path reads `review/**`.
- **Medium Risk:** none.
- **High Risk:** none.
- **Blast radius note:** no god-node touched; `review/` is a leaf documentation directory.
