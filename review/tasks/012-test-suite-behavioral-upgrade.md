# Task 012 — Test Suite Behavioral Upgrade

## Problem
The suite is ~85% structure-theater: 11 of 14 test files rely on `os.path.exists`/keyword-grep assertions that pass forever regardless of whether the asset works (testing-review). Specifics:
- **One test is red right now:** `tests/test_validator.py::TestFileOperationsValidation::test_max_deletions_exceeded` fails because `validate_file_operations` in `validate-config-json.py` has **no aggregate max-deletions cap** — a real product gap (an ops config can delete unbounded files in one shot), not just a broken test.
- **CLI in-process coverage is 0%:** `tests/test_cli.py` spawns subprocesses, so `src/cli/main.py` (272 stmts) is instrumentation-invisible; `cmd_doctor`, `cmd_config` traversal, `cmd_agents` frontmatter parsing are untested for actual output.
- **The best-covered code is dead code:** `src/security/*` at 92%/73% coverage but zero production call sites (fixed by task 002 — the tests then become the guard for a live component).
- **Missing categories:** no adversarial tests running hooks against malicious payloads (test_security_hooks.py only checks existence/shebang/keywords); no CommandValidator bypass tests (`bash -c`, chaining, homoglyphs); no frontmatter-schema golden tests; no install-path coverage for `--full`/`--force`/ERR-trap/settings.json presence (the missing-hook-wiring P0 was invisible to the suite); no language-detection matrix; no config.env injection test.

## Root Cause
Tests were written to demonstrate presence of features ("the skill file exists and mentions RTL") rather than to falsify behavior. Subprocess-only CLI testing was the path of least resistance. The red test indicates tests aren't run before shipping (confirmed: CI runs that file but the failure predates the review — the `|| true` culture, task 011).

## Files
- `.claude/operations/scripts/validate-config-json.py` (add `MAX_DELETIONS` guard; also fix the unguarded legacy `file_op['path']` KeyError at ~line 458, and the 26-vs-29 guard-count docstring fiction)
- `tests/test_validator.py` (red test goes green via the code fix)
- `tests/test_cli.py` → in-process rewrite (import `main`, call `cmd_*` with fabricated args, capture stdout)
- `tests/test_install.py` (extend per task 005's acceptance list)
- `tests/test_security.py` (bypass corpus, per task 002)
- New: `tests/test_hooks_behavioral.py` (task 003), `tests/test_frontmatter_schema.py`, `tests/test_registry_integrity.py`, `tests/test_asset_lint.py` (dangerous-instruction grep), `tests/test_docs_drift.py` (task 006), `tests/test_packaging.py` (task 001)
- Prune/demote: keyword-grep bodies of `test_checkpoint.py`, `test_i18n.py`, `test_mcp.py`, `test_modes.py`, `test_new_commands.py`, `test_new_skills.py`, `test_spec_driven.py`, `test_security_hooks.py`

## Priority
**P1** (the red test + MAX_DELETIONS is a same-day P1; the rewrite is the quarter's testing workstream).

## Estimated Time
1.5–2 weeks, interleaved with tasks 002/003/005 whose fixes these tests lock in.

## Risk
Low. Net-new tests can't break users. Main risk is over-asserting on incidental behavior (exact stdout strings) — assert on contracts (exit codes, JSON fields, file effects). Keep the suite fast (<30 s) and deterministic (tempdir-isolated; the current suite's discipline here is good — preserve it).

## Step-by-step Implementation
1. **Day 1:** add `MAX_DELETIONS = 3` (constant, documented) aggregate check in `validate_file_operations`; red test goes green. Wrap `validate_backup_compatibility`'s legacy conversion so malformed configs produce an error message, not a traceback. Reconcile the guard count (name guards; drop the fictional numbering).
2. **In-process CLI tests:** refactor `main.py` minimally for testability (cmd functions accept an args namespace — they already do; add `main(argv=None)`); tests for: `doctor` correct counts + exit codes in a fixture install (missing test 11), `config` dotted-key traversal + missing-key error (12), `agents` table on fixture frontmatter, `validate/execute/rollback` arg plumbing (mock subprocess), malformed config.json → `err()`-style message not traceback (code-review §9), `NO_COLOR` respected once implemented.
3. **Behavioral hook tests** (with task 003): fixture JSON payloads → exit-code/stderr assertions for every blocking hook; adversarial corpora for file-guard and prompt-injection-scanner (missing tests 9–10).
4. **Security bypass corpus** (with task 002): `bash -c 'rm -rf /'`, `python3 -c "os.system(...)"`, chaining, `busybox rm`, symlink escapes, encoded traversal (missing tests 3–5).
5. **Installer matrix** (with task 005): `--full` asserts settings.json + chmod'd hooks + modes (missing test 1); `--force` idempotency; ERR-trap preservation test (13); language-detection parametrized matrix (14); config.env injection allowlist proof (15).
6. **Asset contract tests:** frontmatter schema for every agent/command/skill (required keys, valid `model:` values, `allowed-tools` sanity) (6); registry cross-reference resolution in pytest (7); dangerous-instruction lint with allowlist (8).
7. **Prune theater:** collapse the pure-existence test files into one `test_structure.py` inventory check driven by the manifest; delete keyword assertions that duplicate the frontmatter-schema test. Target pyramid: ~70% behavioral unit / ~20% integration / ~10% asset-golden (testing-review).
8. Wire everything into CI (task 011) with the coverage gate; ratchet `--fail-under` from 60 → 70 as CLI tests land.

## Acceptance Criteria
- `pytest tests/ -q` fully green locally and in CI (no known-red tests shipped).
- `src/cli/main.py` in-process coverage ≥ 70%; `src/security/` branches (symlink, depth ValueError) covered.
- An ops.json with 4 `file_delete` ops is rejected with a "too many deletions" error.
- Deliberately gutting a hook's logic while keeping its keywords fails the behavioral suite (the exact failure mode the old suite missed).
- Suite runtime < 60 s; zero network access; zero flakes across 20 consecutive runs.

## Testing Strategy
(Meta) Mutation-style spot checks: for each new behavioral test, verify it fails against the pre-fix code (git stash the fix, run, confirm red). Track the structural-vs-behavioral ratio in a comment in conftest.py and hold the line in review.

## Rollback Plan
Tests are additive; revert individual files if a gate proves flaky. The one production change (MAX_DELETIONS) is behind a named constant — if 3 proves too strict for legitimate large refactors, raise it or add an ops-level `allow_bulk_delete: true` escape with a required reason field; never silently remove the cap.
