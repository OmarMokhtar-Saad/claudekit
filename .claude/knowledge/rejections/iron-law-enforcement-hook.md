# Rejection brief — `iron-law-enforcement-hook`

Append-only; one section per non-approving review round. The session id is a local transcript filename (`transcript-miner.py <session-id> --around iron-law-enforcement-hook`), never a credential. Absolute paths and session tokens never appear here.

<!-- round: -1 -->
## Round -1 — CONDITIONAL (86)

- recorded: 2026-08-25T10:08:04Z
- session: bfab483e-36df-43d1-86ab-269d6040db4c
- prompt_version: unknown
- trail: 86/CONDITIONAL
- defect_type / trigger: (unclassified — assigned by /flow-retro or a human; a guessed classification is worse than an absent one)

### Findings
- [MAJOR] `ruff check --add-noqa &lt;path&gt;` is ALLOWED and rewrites every matching source file in place. ops.json op 1 (`.claude/hooks/iron-law-gate.py`), `_RUFF_WRITE_FLAGS` — the table lists `--fix`, `--un
- [MAJOR] `pytest --debug=&lt;path&gt;` is ALLOWED and creates/truncates an arbitrary file. ops.json op 1, `_PYTEST_WRITE_FLAGS` — pytest's `--debug[=DEBUG_FILE_NAME]` writes an internal tracing log to a caller
- digest-fbdbbbcfa538d6b0
- digest-6b0e4edf97389292
- [MINOR] Stale counts in the plan: `.claude/plans/plan-iron-law-enforcement-hook.md:124` and :536 say "24 `SANCTIONED` commands"/"24-command SANCTIONED corpus" and :355 says "24 SANCTIONED × … 55 BLOCKED", but
- [MINOR] The plan's own R4 concedes `python3 scripts/gen-docs.py --check` will FAIL after this lands (hook count 20→21), i.e. one of CLAUDE.md's six mandatory DoD gates cannot pass at commit time for this very

### 5-whys (a writing template, not a clustering method)
1. Why was this rejected? 
2. Why? 
3. Why? 
4. Why? 
5. Root cause: 

