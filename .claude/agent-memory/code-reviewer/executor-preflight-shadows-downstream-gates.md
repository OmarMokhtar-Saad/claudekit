---
name: executor-preflight-shadows-downstream-gates
description: A validate-first gate in execute-json-ops.py main() refuses before the parse/mode/digest/allowlist gates, turning 29 CLI tests red and removing their coverage
metadata:
  type: project
---

Adding a preflight `validate-config-json` gate to `execute-json-ops.py` `main()` made 29
existing tests fail across 8 files (`test_ops_parse_gate`, `test_ops_hardening`,
`test_ops_file_modes`, `test_ops_content_by_path`, `test_run_command_ops`,
`test_work_loss_protection`, `test_ops_approval_gate`, `test_validator_sequence_mode`).

**Why:** those tests drive the CLI with deliberately invalid configs to prove the
DOWNSTREAM gates fire. An earlier refusal is indistinguishable from the later one at the
exit code, so the later gate stops being exercised at all.

**How to apply:** when reviewing any new early gate on the executor, measure before/after
on the 22 test files that invoke `execute-json-ops.py` (`-p no:randomly`, two identical
copies of the tree). Adding `--skip-validation` to the failing invocations restores green
while deleting the coverage — treat that as a finding, not a fix. Related:
[[allowlist-before-early-return]].
