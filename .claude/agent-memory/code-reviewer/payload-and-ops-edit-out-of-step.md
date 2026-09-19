---
name: payload-and-ops-edit-out-of-step
description: A review fix landed in a payload file but not in the matching ops.json code_edit ships a red test; always execute the ops and run the new test file unmutated
metadata:
  type: project
---

A plan's change surface lives in two places that are edited independently: the payload files under
`.claude/plans/payloads/<plan>/` and the inline `code_edit` strings inside `ops-<plan>.json`. A
round-2 fix applied to only one of them executes cleanly (ops report 7/7, 0 errors) and still leaves
the suite red.

Measured 2026-09-19 on `context-budget-gate`: the reviewer asked for a tool to be added to the hook's
guard table; the planner updated the hook payload *and* the test that asserts the registry matcher
carries the same token, but left the matcher string in the ops.json `code_edit` unchanged. Execution
succeeded, `gen-docs --check` passed, ruff and mypy passed, and
`test_registry_registers_the_gate_as_blocking` was the one red test out of 24.

**Why:** ops execution validates hashes and anchors, never the post-state semantics — nothing in the
pipeline compares a payload's assumptions against the inline edits (see also
[[executor-preflight-shadows-downstream-gates]]).

**How to apply:** on any round of a plan review, execute the ops in a scratch clone and run the new
or changed test files on the UNMUTATED tree before touching mutants. A green mutant matrix says
nothing about whether the tree is green to begin with. When a prior round's finding names a constant,
token or table, grep for it in BOTH the payload and the ops.json `code_edit` strings.
