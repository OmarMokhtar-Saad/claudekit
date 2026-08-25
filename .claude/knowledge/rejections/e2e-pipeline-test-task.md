# Rejection brief — `e2e-pipeline-test-task`

Append-only; one section per non-approving review round. The session id is a local transcript filename (`transcript-miner.py <session-id> --around e2e-pipeline-test-task`), never a credential. Absolute paths and session tokens never appear here.

<!-- round: -1 -->
## Round -1 — CONDITIONAL (86)

- recorded: 2026-08-25T10:08:04Z
- session: bfab483e-36df-43d1-86ab-269d6040db4c
- prompt_version: unknown
- trail: 86/CONDITIONAL
- defect_type / trigger: (unclassified — assigned by /flow-retro or a human; a guessed classification is worse than an absent one)

### Findings
- [MAJOR] Lane-count arithmetic does not reconcile with the case-by-case (A)/(B) markings. Footer claims "33 LANE A · 7 LANE B" (ops.json content, "Totals" line near end of the file body), but only E2E-04, E2E-
- [MAJOR] Acceptance Criteria's "Mutation proof, one per group" claim (ops.json content, Acceptance Criteria section) enumerates proofs for only 4 of the 9 groups (C, F, B, H) despite asserting one per group. G
- [MINOR] No explicit case exercises the full CONDITIONAL -&gt; revise -&gt; re-approve -&gt; execute cycle (the "revision confirmation" gap in the WS-6 task brief). E2E-06 (digest drift) and E2E-07 (CONDITIONA
- [MINOR] Plan's stated "Out of Scope" list (plan-e2e-pipeline-test-task.md:13-14: tests/, scripts/, .claude/**, evals/) is correct for this workstream's own ops.json (single file_create, verified), but the spe
- [MINOR] House-format and boundary checks pass: task 015 content matches the Problem/Root Cause/Files/Priority/Estimated Time/Risk/Step-by-step/Acceptance Criteria/Testing Strategy/Rollback Plan structure of r

### 5-whys (a writing template, not a clustering method)
1. Why was this rejected? 
2. Why? 
3. Why? 
4. Why? 
5. Root cause: 

<!-- round: -2 -->
## Round -2 — CONDITIONAL (85)

- recorded: 2026-08-25T10:08:04Z
- session: bfab483e-36df-43d1-86ab-269d6040db4c
- prompt_version: unknown
- trail: 85/CONDITIONAL
- defect_type / trigger: (unclassified — assigned by /flow-retro or a human; a guessed classification is worse than an absent one)

### Findings
- [MAJOR] plan-e2e-pipeline-test-task.md:9 says "a 40-case test catalogue" and ops.json:7 description says "(40 enumerated cases, lane-split)" — both stale from before E2E-41 was added. The catalogue itself (op
- [MINOR] No other cross-reference breakage found: E2E-41 is correctly folded into the Group B mutation-proof list in Acceptance Criteria ("E2E-05..09, E2E-12, E2E-41 red"), and no id collisions exist across E2

### 5-whys (a writing template, not a clustering method)
1. Why was this rejected? 
2. Why? 
3. Why? 
4. Why? 
5. Root cause: 

