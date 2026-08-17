# Plan: `run_command` operation type

**Status:** APPROVED by owner 2026-08-17 ("do"). Follows plan-token-efficiency.md item 3.
**Why:** The schema forces opus to hand-transcribe machine-generatable text — 58% of
ops-task-014.json (30.5 KB) was a pip lockfile (~7.6k opus output tokens). There is no way
to say "run pip-compile". This adds one, without weakening the Iron Law.

## Security design (the point of this plan)

1. **argv array, `shell=False`** — `"command": ["pip-compile", "requirements.in"]`.
   No shell ever spawns: no metacharacters, no expansion, no injection surface.
2. **Executable allowlist, fail closed** (`ALLOWED_RUN_COMMANDS` in shared.py):
   pip-compile, black, isort, ruff, prettier, gofmt, goimports, rustfmt — deterministic
   generators/formatters only. argv[0] must be a bare basename (no `/`), resolved via PATH.
   Anything else → REJECTED. Honest framing per Hard Rule 6: this is a guardrail against
   accident and prompt-drift, not a sandbox — the allowlisted tools themselves read config
   files from the tree.
3. **Per-project extension** via env `CLAUDEKIT_RUN_COMMAND_EXTRA_ALLOW` (colon-separated
   basenames) — set in `.claude/settings.local.json` env, mirroring `ECC_HOOK_PROFILE`.
4. **`reason` required (≥10 chars)**, same as file_delete.
5. **Cap: 5 run_command ops per plan** (GUARD 32).
6. **Ordering: run_command ops must come AFTER all file ops** (GUARD 33). Commands cannot
   be rolled back by the transaction; a later file-op failure must never strand command
   side effects inside a rolled-back batch. Executor enforces it too (defense in depth).
7. **Timeout**: optional `timeout` field, default 120s, hard cap 600s.
8. **No path args escaping the project**: reject any argv element that is an absolute path
   or contains `..` (GUARD 34). Null-byte checks as elsewhere (GUARD 25 family).
9. **Not rolled back — but drift-visible**: post-state snapshot still runs; RESULT-JSON
   records exit code. Dry-run prints the argv and does NOT execute.

## Operations

1. `shared.py` — add `ALLOWED_RUN_COMMANDS` + `allowed_run_commands()` (env-extended).
2. `operations-schema.json` — add run_command variant (type, command[], reason,
   optional id/description/timeout).
3. `validate-config-json.py` — GUARDs 30–34 (`validate_run_commands()`); exempt
   run_command from the path requirement; keep it out of baseline stamping (no path).
4. `execute-json-ops.py` — `execute_run_command()` (subprocess.run, shell=False,
   cwd=project root, capture output, timeout); dispatch + stats + ordering re-check;
   epilog update.
5. Docs: `generate-operations-config` SKILL.md (single source of truth), planner.md
   schema summary, CHANGELOG.
6. Tests: `tests/test_run_command_ops.py` — behavioral (real validator + executor via
   subprocess): accept allowlisted, reject non-allowlisted / shell-string / absolute
   argv0 / `..` args / missing reason / >5 ops / ordering violation; dry-run does not
   execute; execute runs an env-extra-allowed harmless command and propagates failure
   exit; timeout kills.

## Rollback

Revert the commit; no data migration. run_command absent from schema → old configs
unaffected (additive change).

## Risk

Medium. The allowlist is the load-bearing control; tests pin it. MAX_DELETIONS-style
constant pattern reused. No change to file-op semantics.
