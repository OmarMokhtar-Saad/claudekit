# Rejection brief — `fleet-a2b-d1-d3`

Append-only; one section per non-approving review round. The session id is a local transcript filename (`transcript-miner.py <session-id> --around fleet-a2b-d1-d3`), never a credential. Absolute paths and session tokens never appear here.

<!-- round: 2 -->
## Round 2 — REVISE (75)

- recorded: 2026-08-25T09:15:59Z
- session: unknown
- prompt_version: 035b1fc
- trail: 75/REVISE -> 75/REVISE
- defect_type / trigger: (unclassified — assigned by /flow-retro or a human; a guessed classification is worse than an absent one)

### Findings
- [MAJOR] THIRD-PARTY-LICENSES.md is absent from the sdist and wheel while the CC BY-SA file ships; LICENSE points at a file not in the distribution
- [MAJOR] Inserting prose into LICENSE between title and copyright drops automated MIT detection below threshold
- [MAJOR] README.md still claims "No restrictions." which is false once a share-alike file ships
- digest-3759dc0a2a673b56
- [MINOR] prompt-evaluation's "license is unstated" was never verified against the parent repo
- [MINOR] The spent config reds test_queued_ops_configs_validate_against_head; A7 documents regeneration but not archival
- [MINOR] Unquoted $PINS in the defect-pinning sed/for loop word-splits on paths containing spaces

### 5-whys (a writing template, not a clustering method)
1. Why was this rejected? 
2. Why? 
3. Why? 
4. Why? 
5. Root cause: 

