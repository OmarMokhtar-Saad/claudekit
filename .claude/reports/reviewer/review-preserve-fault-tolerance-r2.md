=== REVIEW ===
SCORE: 96
DECISION: APPROVED
- [MINOR] `test_what_could_not_be_preserved_is_reported_with_a_count` asserts only the absence of the old failure line, not the presence of the new `WARNING: N file(s) could NOT be preserved` message; a positive assertion would catch a regression in the count/format itself.
=== END REVIEW ===
