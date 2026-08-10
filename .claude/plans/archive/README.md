# Archived ops configs

Ops configs whose anchors no longer match HEAD live here. `tests/test_delivery_contract_smoke.py::test_queued_ops_configs_validate_against_head` gates the parent directory: a queued (non-archived) ops config that fails `validate-config-json.py` fails the suite, so stale plans get caught mechanically instead of at execution time.

Move a config here when it is **spent** (already executed — anchors consumed by its own edits) or **stale** (the target files changed underneath it — regenerate via `/plan` before executing).

| File | Why archived |
|---|---|
| `ops-hardening-implementer-contract.json` | Spent — executed before archiving; its output is the ops-hardening working-tree changes (see `plan-ops-hardening-implementer-contract.md`). |
| `ops-review-approval-binding.json` | Superseded — never executed as-is; its command-file edits targeted pre-2026-07-31 `review.md`. Its two `file_create` payloads (`review-record.py`, `tests/test_review_record.py`) were reused byte-for-byte by `ops-approval-binding-rebased.json`. Kept as the reviewed design record (3 review rounds). |
| `ops-approval-binding-rebased.json` | Spent — executed 2026-07-31 (RESULT-JSON: 9/9 ops success). The rebase of the above against HEAD, per `plan-remaining-fixes-2026-07-31.md` §2. |
| `ops-task-014-supply-chain-hardening.json` | Spent — executed 2026-08-01 (RESULT-JSON: 11/11 ops success). All supply chain hardening operations applied: action SHA pins, MCP version pins, hash-pinned test deps, CI guards. |
| `ops-workflow-file-templates-ops-schema.json` | Spent — executed 2026-08-10 in worktree `agent/workflow-file-templates-ops-schema` (7/7 ops success), merged as `dfaf6e5`. Fixed AGENTS_KNOWN_ISSUES.md #9 (legacy ops schema in `_shared/WORKFLOW_FILE_TEMPLATES.md`); plan: `plan-workflow-file-templates-ops-schema.md`. |
