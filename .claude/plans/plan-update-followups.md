# Plan: ck update follow-ups (fleet run 2026-09-23)

**Tier 2** (several files, no security/schema surface). Ops: `.claude/plans/plan-update-followups.ops.json`.

## Problem

The 3.2.1 fleet run (14 repos, all clean) surfaced three follow-ups:

1. ~2000 `preserved:` lines per repo from `preserve_assets.py`.
2. A second run on an already-synced repo flips kit hooks 644 -> 755. Cause: a hook whose
   receipt hash was stale but whose bytes matched the new kit was "kept" (`cp -p`, project
   mode 644), receipted with the kit hash, and only the NEXT run (receipt now matching)
   installed the kit's 755 copy.
3. `ck doctor <path>` is rejected by argparse; every check is cwd-relative.

## Changes

- `.claude/operations/scripts/install_overrides.py`
- `.claude/operations/scripts/preserve_assets.py`
- `CHANGELOG.md`
- `docs/cli.md`
- `install.sh`
- `src/claudekit/cli/main.py`
- `tests/test_cli.py`
- `tests/test_install_overrides.py`
- `tests/test_preserve_assets.py`

1. `preserve_assets.py`: `write_log` + optional log path; `format_report(result, log_path)`
   prints a count (names inline only up to `INLINE_LIMIT`=10). `install.sh` passes
   `$BACKUP/preserved-files.log`.
2. `install_overrides.py modified_files`: bytes equal to the kit's are never kept, so the
   kit copy (mode included) wins on the first run and the second run changes no mode.
3. `main.py`: `doctor` takes optional `PATH` (default `.`); `cmd_doctor` chdirs there for
   the checks and restores the cwd. `docs/cli.md` documents it.
4. Tests: stale-receipt unit case; two-run mode no-op install test; report/log tests;
   doctor path test. CHANGELOG `[Unreleased]`.

## Verification

pytest tests/test_install_overrides.py tests/test_preserve_assets.py tests/test_cli.py;
full suite; ruff; mypy; gen-docs/registry/model-policy/context-floor/plan-artifacts/
plan-index gates; shellcheck; `ck doctor --strict` and `ck doctor <path>`.
