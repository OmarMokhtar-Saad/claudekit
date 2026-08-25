# Rejection brief — `reflection-lifecycle-gates`

Append-only; one section per non-approving review round. The session id is a local transcript filename (`transcript-miner.py <session-id> --around reflection-lifecycle-gates`), never a credential. Absolute paths and session tokens never appear here.

<!-- round: -1 -->
## Round -1 — CONDITIONAL (88)

- recorded: 2026-08-25T10:08:04Z
- session: bfab483e-36df-43d1-86ab-269d6040db4c
- prompt_version: unknown
- trail: 88/CONDITIONAL
- defect_type / trigger: (unclassified — assigned by /flow-retro or a human; a guessed classification is worse than an absent one)

### Findings
- digest-f7e3718c2c2ac3a0
- digest-7dd5bcb8c6fea6be
- [MAJOR] The escape hatch can be blocked by a sibling PreToolUse hook. The only channel for a receipt is the command line (`reflection.py receipt --json '{...}'`), because `is_receipt_cli()` refuses `&lt; &gt;
- [MINOR] Documented hook count becomes misleading. Verified `scripts/gen-docs.py:55-58` globs `*.sh` only, so the plan's zero-drift claim (plan line 88-93) is factually correct and `test_shell_lint.py` is unaf
- [MINOR] `ECC_HOOK_PROFILE=minimal` suppresses blocking but keeps recording (op 2), diverging from the wholesale line-1 short-circuit every other hook uses (`ops-enforcement.sh:13`, `command-guard.sh:33`). The

### 5-whys (a writing template, not a clustering method)
1. Why was this rejected? 
2. Why? 
3. Why? 
4. Why? 
5. Root cause: 

