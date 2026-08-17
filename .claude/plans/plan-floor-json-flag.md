# Implementation Plan: `--json` output for check-context-floor.py

## Overview
Add a `--json` flag to `scripts/check-context-floor.py` that emits the floor measurement as a
single JSON object (`{"sizes": {...}, "budgets": {...}, "total": N, "ok": bool}`) instead of the
human table, so CI jobs and agents can consume the floor gate mechanically. Record the change in
`CHANGELOG.md` under `[Unreleased] > Added`.

## Scope
- **In Scope:** new `--json` output mode in the script; docstring usage line; behavioral tests in
  `tests/test_context_floor.py`; CHANGELOG `[Unreleased] > Added` entry.
- **Out of Scope:** changing any budget value; changing table output or exit-code semantics of the
  existing `--check` path; wiring `--json` into `.github/workflows/ci.yml` (CI keeps using
  `--check`); `ck doctor` integration.

## Prerequisites
- `.claude/settings.local.json` present with `ECC_HOOK_PROFILE=minimal` (repo self-hosting gotcha).
- No new dependencies: `json` is stdlib, satisfying the stdlib-only rule for `scripts/`.

## Context Summary (discovery)
- `scripts/check-context-floor.py` (90 lines): `BUDGETS` dict, `measure() -> dict[str, int]`
  returning the same keys as `BUDGETS`, and `main()` which reads `"--check" in sys.argv[1:]`, prints
  a table, and returns `1 if failures and check else 0`.
- `tests/test_context_floor.py` (81 lines): behavioral tests that shell out via
  `run_gate(*args)` → `subprocess.run([sys.executable, SCRIPT, *args], cwd=REPO_ROOT)`; a temp-root
  test proves the gate fails when over budget. New tests follow the same subprocess pattern.
- `.github/workflows/ci.yml` invokes the script with `--check` only — unchanged by this plan.
- Lint constraints: `ruff check src/ tests/ scripts/`, line-length 100; `mypy` targets py3.9, so
  keep the quoted-annotation style already used (`-> "dict[str, int]"`).

## Implementation Steps

### Step 1: Document the flag in the module docstring
- **File:** `scripts/check-context-floor.py`
- **Action:** Modify
- **Description:** Add a third usage line for `--json` beneath the existing `--check` line.

### Step 2: Import `json`
- **File:** `scripts/check-context-floor.py`
- **Action:** Modify
- **Description:** Add `import json` above `import re` (stdlib, alphabetical — ruff isort-clean).

### Step 3: Add the `--json` branch to `main()`
- **File:** `scripts/check-context-floor.py`
- **Action:** Modify
- **Details:** Parse `sys.argv[1:]` once into `args`; keep `check = "--check" in args`. When
  `--json` is present, compute `ok = all(size <= BUDGETS[name] for name, size in sizes.items())`,
  print `json.dumps({"sizes": sizes, "budgets": BUDGETS, "total": total, "ok": ok}, indent=2)` and
  return early — nothing else is written to stdout/stderr, so the output is parseable. Exit code
  stays consistent with `--check`: `1` only when `--check` is also passed and `ok` is false,
  otherwise `0`. Table path below the branch is untouched.

### Step 4: Behavioral tests
- **File:** `tests/test_context_floor.py`
- **Action:** Modify
- **Details:** Add `import json`, then three tests after `test_gate_fails_when_over_budget`:
  1. `test_json_output_shape` — `run_gate('--json')` exits 0, stdout parses as JSON, has exactly
     keys `sizes`/`budgets`/`total`/`ok`, `sizes` keys equal `budgets` keys, `total ==
     sum(sizes.values())`, `ok is True` for the current repo.
  2. `test_json_output_is_only_json` — stdout contains no table markers (`TOTAL`, `OK:`), proving
     the JSON is machine-parseable in one read.
  3. `test_json_with_check_over_budget` — reuse the temp-root oversize fixture shape with
     `--json --check`: exit 1, `payload['ok'] is False`.

### Step 5: CHANGELOG entry
- **File:** `CHANGELOG.md`
- **Action:** Modify
- **Description:** Insert a bullet at the top of `[Unreleased] > Added` describing the flag and its
  JSON shape.

## Testing Strategy
- `python3 -m pytest tests/test_context_floor.py -q` (new tests) then the full suite
  `python3 -m pytest tests/ -q`.
- `ruff check src/ tests/ scripts/` and `mypy` for lint/type gates.
- Manual evidence: `python3 scripts/check-context-floor.py --json | python3 -m json.tool` and
  `python3 scripts/check-context-floor.py --json --check; echo $?` (expect `0` today).
- Regression evidence: `python3 scripts/check-context-floor.py --check` still prints the table and
  exits 0 (CI path unchanged).

## Rollback Plan
- `git checkout -- scripts/check-context-floor.py tests/test_context_floor.py CHANGELOG.md`, or
  revert the single commit. All three edits are additive; no files created or deleted, so rollback
  cannot orphan anything.

## Risk Assessment
- **Low Risk:** docstring line, `json` import, CHANGELOG bullet — no behavior touched.
- **Low Risk:** new tests — additive, follow the existing subprocess harness.
- **Medium Risk:** the `main()` edit is on the shared code path CI depends on. Mitigation: the
  `--json` branch returns before any table printing and the `--check` failure logic below it is
  left byte-identical; `test_repo_within_budget` and `test_gate_fails_when_over_budget` guard the
  old behavior.
- **Blast radius:** `scripts/check-context-floor.py` is referenced only by
  `tests/test_context_floor.py` and `.github/workflows/ci.yml` (`--check`) — not a hub node.
