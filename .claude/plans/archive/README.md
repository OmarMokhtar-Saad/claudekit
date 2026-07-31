# Archived ops configs

Ops configs whose anchors no longer match HEAD live here. `tests/test_delivery_contract_smoke.py::test_queued_ops_configs_validate_against_head` gates the parent directory: a queued (non-archived) ops config that fails `validate-config-json.py` fails the suite, so stale plans get caught mechanically instead of at execution time.

Move a config here when it is **spent** (already executed — anchors consumed by its own edits) or **stale** (the target files changed underneath it — regenerate via `/plan` before executing).

| File | Why archived (2026-07-31) |
|---|---|
| `ops-hardening-implementer-contract.json` | Spent — executed before archiving; its output is the ops-hardening working-tree changes (see `plan-ops-hardening-implementer-contract.md`). |
| `ops-review-approval-binding.json` | Stale AND unsafe — never executed, anchors target pre-2026-07-31 `review.md`, and its op-2 replacement text would reintroduce the `PLAN TO REVIEW: $PLAN_CONTENT` payload leak fixed by `plan-token-waste-workflow-fixes.md`. Regenerate against HEAD under the path-not-payload contract before pursuing. |
