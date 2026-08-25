# Rejection brief — `retro2-trim`

Append-only; one section per non-approving review round. The session id is a local transcript filename (`transcript-miner.py <session-id> --around retro2-trim`), never a credential. Absolute paths and session tokens never appear here.

<!-- round: 2 -->
## Round 2 — REVISE (75)

- recorded: 2026-08-25T09:55:03Z
- session: unknown
- prompt_version: 967b2ea
- trail: 60/REJECTED -> 75/REVISE
- defect_type / trigger: (unclassified — assigned by /flow-retro or a human; a guessed classification is worse than an absent one)

### Findings
- [MAJOR] heldout MANIFEST pins a stale plan_sha256 for plan-fleet-skill-enhancement.md after a concurrent workstream moved it; applying heldout yields 5 failures in tests/test_heldout_set.py. Fix: run heldout-
- [MINOR] SESSION_ID_SHAPE is duplicated as two literals (reflection.py, review-record.py) with no test pinning them equal.

### 5-whys (a writing template, not a clustering method)
1. Why was this rejected? 
2. Why? 
3. Why? 
4. Why? 
5. Root cause: 

