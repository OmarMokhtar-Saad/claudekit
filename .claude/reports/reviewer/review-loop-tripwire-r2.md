=== REVIEW ===
SCORE: 94
DECISION: APPROVED
- [MINOR] `scores` filters to int before computing `peak`, so a malformed score entry that inflates the streak count via `is_rejecting` is dropped from the non-monotonic check; `len(scores) >= 3` guards it, but a 3-streak with one malformed score suppresses the notice while the tripwire still fires. Acceptable trade-off (never fabricate a peak from None); worth a one-line comment if self-documenting is wanted.
=== END REVIEW ===
