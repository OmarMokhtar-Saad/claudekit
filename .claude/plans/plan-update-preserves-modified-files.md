# Plan: ck update keeps locally-modified managed files

Tier 2, parent-applied. Ops: `.claude/plans/plan-update-preserves-modified-files.ops.json`.

## Problem (measured 2026-09-23 on qa-agents at 27b0efee, kit c01e16f)

`ck update --yes` left 68 modified tracked files: every agent, skill and command was the
kit copy again, settings.json was reordered kit-first, skills-registry.json was copied
(project entries dropped), runtime/events/local.jsonl was rewritten and the manifest
churned on every run. The manifest's hashes only drove a warning.

## Changes

- `.claude/operations/scripts/install_overrides.py`
- `.claude/operations/scripts/preserve_assets.py`
- `CHANGELOG.md`
- `install.sh`
- `src/claudekit/cli/main.py`
- `tests/test_cli.py`
- `tests/test_install_overrides.py`

1. `install_overrides.py`: `_deep_merge` keeps project key order; `modified_files` /
   `keep-modified` list managed files whose on-disk hash differs from the receipt (kit
   hash of the staged copy returned); `merge_registry` / `registry` merges the registry.
   Follow-up (parent-applied, same session): `modified_files` walks the staged kit,
   so a shipped file on disk that the receipt never recorded is kept too.
2. `install.sh`: help text; registry merged when the project has one; kept-modified
   files copied back over staging unless `--force`; `runtime/` moved from the backup into
   the new tree; manifest excludes runtime, receipts kept files with the kit hash, reuses
   `installed_at` when nothing changed and carries foreign keys.
3. `preserve_assets.py`: never walks the backup's `runtime/`.
4. `main.py`: `ck update --force`; default update no longer passes `--force` to the
   installer for receipted trees (legacy trees still do).
5. Tests: git-backed reinstall-over-modified-tree test asserting zero tracked changes;
   registry/merge/modified_files unit tests; manifest stability; CLI flag test.
6. CHANGELOG `[Unreleased]`.

## Verification

pytest tests/test_install_overrides.py tests/test_cli.py; full suite; ruff; mypy; gates;
shellcheck; `ck doctor --strict`; `ck update --yes` twice on a qa-agents worktree at
27b0efee: second run shows zero `M` lines.
