=== REVIEW ===
SCORE: 95
DECISION: APPROVED
- [MINOR] The new module-level `reinstall_over(project, mode="--minimal")` duplicates `TheReceiptRecordsOnlyWhatTheKitOwns.reinstall(self, project)` almost line-for-line (same subprocess args, env, timeout); only the mode parameter differs. CLAUDE.md's "no new near-duplicate assets" would be better served by promoting the existing method to a shared module-level helper. Not blocking: test-only, low-risk, no correctness impact.
=== END REVIEW ===
