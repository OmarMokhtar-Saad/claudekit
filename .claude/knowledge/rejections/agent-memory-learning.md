# Rejection brief — `agent-memory-learning`

Append-only; one section per non-approving review round. The session id is a local transcript filename (`transcript-miner.py <session-id> --around agent-memory-learning`), never a credential. Absolute paths and session tokens never appear here.

<!-- round: 2 -->
## Round 2 — REVISE (81)

- recorded: 2026-09-06T17:53:53Z
- session: ae05f7f4-0be8-454d-9a3d-f5868dc6cc94
- prompt_version: aebd260
- trail: 82/REVISE -> 81/REVISE
- defect_type / trigger: (unclassified — assigned by /flow-retro or a human; a guessed classification is worse than an absent one)

### Findings
- [CRITICAL] session-start.sh op splits the helper invocation across two lines so gen-docs.py _is_helper_module() does not classify session-memory-context.py as a helper; HOOK_GLOBS includes *.py so the hook count
- [CRITICAL] tests/test_reflection_ledger.py TestReceiptToLedgerBridge methods take (self, tmp_path, monkeypatch) but call ref.bridge_receipt_to_ledger; ref is a fixture -> AttributeError; the sanitizer proof neve
- [MAJOR] Two contradictory measured totals (16,198 chars in the research note vs 13,759 in plan + CHANGELOG). Fix: one number, labelled.
- [MINOR] registry description string differs from both SKILL.md copies.
- [MINOR] session-start.sh withhold branches print nothing to stdout unlike the neighbouring block.
- [MINOR] render_closed/cmd_record drop evidence: stamps.
- [MINOR] Stop propose step has no ECC_HOOK_PROFILE short-circuit.
- [MINOR] numeric proofs unverified by the reviewer; hand to code-reviewer.

### 5-whys (a writing template, not a clustering method)
1. Why was this rejected? 
2. Why? 
3. Why? 
4. Why? 
5. Root cause: 

