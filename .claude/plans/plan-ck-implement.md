# Plan: `ck implement <ops.json>`

Parent spec: `.claude/plans/plan-token-spend-remediation.md` section E, item 1.
Ops config: `.claude/plans/ops-ck-implement.json`.

## Overview

The implementer agent spends 44 turns / 1.4 M tokens to run three scripts in a fixed order:
`validate-config-json.py`, `execute-json-ops.py --dry-run`, `execute-json-ops.py`, then the
validation commands the plan names. Nothing in that sequence needs a model. `ck implement`
is that sequence as one CLI command, so Tier 1/2 work costs one Bash call instead of a
subagent boot plus a 1.4 M-token conversation. The Iron Law is unchanged: the work still
flows through an ops.json and the operations engine — only the caller changes.

## Scope

- `src/claudekit/cli/main.py` — `cmd_implement` plus three helpers (`_plan_for_ops`,
  `_plan_validation_commands`, `_shell_free_argv`, `_result_json_field`, `_run_stage`), the
  `implement` subparser, the dispatch entry, and an `import shlex`.
- `tests/test_cli_implement.py` — behavioural tests: a real ops config executed in a
  throwaway project via `python -m claudekit.cli.main implement`.
- `docs/cli.md` — a `### claudekit implement <ops.json>` section between `execute` and
  `rollback`.
- `CHANGELOG.md` — one `[Unreleased]` bullet.

Out of scope: changing the executor or validator, the approval gate, the implementer agent
prompt, and `scripts/check-plan-artifacts.py` (not shipped in an installed tree, so the CLI
carries its own light plan resolution).

## Implementation Steps

### 1. `cmd_implement` in `src/claudekit/cli/main.py`
- Stages, in order: validate → `--dry-run` execute → execute → the plan's validation
  commands. The first stage that does not exit 0 stops the run; the exit code is returned.
- The plan is resolved from the config name — `ops-<slug>.json` → `plan-<slug>.md` or
  `<slug>.md`, looked up beside the config then in `.claude/plans/`, walking hyphen
  boundaries longest-first so `ops-<slug>-followup.json` finds `plan-<slug>.md`. `--plan`
  overrides.
- Validation commands are the first ```bash fence under a `## Validation commands`,
  `## Testing Strategy`, `## Tests` or `## Verification` heading.
- They run **without a shell**: a plan is a document, and `shell=True` would hand whatever
  it contains to `sh`. A command carrying a pipe, redirect or chain is reported as skipped.
- Exactly one `RESULT:` line is printed, on every path including failure.
- **Done when:** `claudekit implement <ops.json>` prints one `RESULT:` line and the ops
  config's edits are on disk.

### 2. Behavioural tests in `tests/test_cli_implement.py`
- A `project` fixture builds a throwaway tree in `tmp_path` carrying the live
  `.claude/operations/scripts/`, a plan doc and a real ops config.
- Cases: happy path (the validation command asserts the edit landed, which also proves
  ordering); a failing validation command → non-zero exit; a config that fails validation →
  nothing written and no execute stage; a shell-only validation command → skipped, not
  shelled out.

### 3. `docs/cli.md` and `CHANGELOG.md`
- Reference section between `execute` and `rollback`; one `[Unreleased]` bullet.

## Validation commands

```bash
python3 -m pytest tests/test_cli_implement.py -q -p no:cacheprovider
ruff check src/ tests/ scripts/ .claude/operations/scripts/
python3 scripts/gen-docs.py --check
```

## Rollback Plan

`git checkout -- src/claudekit/cli/main.py docs/cli.md CHANGELOG.md` and
`rm tests/test_cli_implement.py`. Other sessions hold uncommitted paths — never
`git checkout -- .`.

## Risk Assessment

- **MEDIUM — running commands out of a document.** The validation commands come from a
  markdown file. They are run with `subprocess.run(argv)` and no shell, and any command
  whose `shlex` tokens include a shell operator is skipped rather than reinterpreted, so a
  plan cannot smuggle a pipeline into execution. It can still name an arbitrary program —
  the same trust level as the plan itself, which already authorises file edits.
- **LOW — plan resolution misses.** No plan, or no validation fence, is a warning and an
  exit-0 run of the three engine stages, never a failure: `ck implement` must not become a
  reason to skip the engine.
- **LOW — `--no-approval` passthrough.** The flag is forwarded to the executor only when
  the caller passes it; the approval gate's default is unchanged.

## Archived configs

- `.claude/plans/archive/ops-ck-implement/ops.json` (4 operations)
- `.claude/plans/archive/ops-ck-implement/ops-drift-test.json` (1 operation)
- `.claude/plans/archive/ops-ck-implement/ops-count.json` (2 operations)

