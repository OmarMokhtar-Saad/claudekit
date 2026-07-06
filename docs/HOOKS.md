# Hooks

ClaudeKit ships 17 hook scripts (plus `lib.sh`, a shared helper library) wired
into Claude Code through `.claude/settings.json`. They enforce guardrails,
capture telemetry, and automate housekeeping around the agent workflow.

> **Not a sandbox.** Blocking hooks raise the cost of a mistake; they are not a
> security boundary. For untrusted code, run Claude Code under OS-level
> isolation. See `SECURITY.md`.

## How hooks are wired

Hooks are registered under `.claude/settings.json` (installed by `install.sh`),
keyed by Claude Code **hook events**:

| Event | When it fires |
|-------|---------------|
| `PreToolUse` | Before a tool runs (can **block** the tool) |
| `PostToolUse` | After a tool succeeds |
| `PostToolUseFailure` | After a tool errors |
| `UserPromptSubmit` | When you submit a prompt |
| `SessionStart` | At the start of a session |
| `Stop` / `SubagentStop` | When the (sub)agent finishes a turn |

Each hook resolves the repo root and sources `lib.sh`:

```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$SCRIPT_DIR/lib.sh" ] && . "$SCRIPT_DIR/lib.sh"
```

### The blocking contract

Claude Code blocks a `PreToolUse` tool **only** when the hook exits with code
**2** and writes the reason to **stderr**. Exit 0 (or exit 1 with a message on
stdout) does **not** block. ClaudeKit's blocking hooks use the `deny` helper in
`lib.sh`, which logs, prints the reason to stderr, and `exit 2`. They also
**fail closed**: an unparseable tool payload is treated as a block, never a
silent allow.

## `ECC_HOOK_PROFILE` — enforcement level

A single environment variable controls how aggressively hooks enforce:

| Profile | Behavior |
|---------|----------|
| `minimal` | Blocking/enforcement hooks are **off**. Advisory + telemetry hooks still run. Use this when working *on ClaudeKit itself* so your own edits aren't blocked. |
| `standard` | **Default.** Enforcement hooks block; the command guard **warns only**. |
| `strict` | Everything in `standard`, plus the command guard **blocks** and expensive checks (`format-typecheck`) run. |

Set it in your shell or in `.claude/settings.local.json` (git-ignored):

```json
{ "env": { "ECC_HOOK_PROFILE": "strict" } }
```

Unset defaults to `standard`.

## Hook catalog

### Enforcement (blocking) — `PreToolUse`

| Hook | Trigger | Profile | Purpose |
|------|---------|---------|---------|
| `ops-enforcement.sh` | Edit/Write | off in `minimal` | Enforces the plan→ops.json→execute flow; blocks ad-hoc edits outside allowed areas |
| `config-protection.sh` | Edit/Write | off in `minimal` | Blocks edits to protected config files |
| `block-no-verify.sh` | Bash | off in `minimal` | Blocks `git commit/push --no-verify` (which would skip hooks) |
| `commit-quality.sh` | Bash | off in `minimal` | Enforces commit-message quality |
| `command-guard.sh` | Bash | **`strict` blocks**, `standard` warns, `minimal` off | Denylist speed bump over shell commands (`CommandValidator`). See `SECURITY.md`. |
| `pre-commit.sh` | Bash (`git commit`) | always | Validates ops.json configs and scans staged files for secrets |
| `pre-push.sh` | Bash (`git push`) | always | Full validation suite before a push to remote |

### Advisory — `PreToolUse` / `UserPromptSubmit`

| Hook | Event | Profile | Purpose |
|------|-------|---------|---------|
| `security-reminder.sh` | Edit/Write | `standard` + `strict` | Non-blocking reminder when touching sensitive files |
| `suggest-compact.sh` | PreToolUse (all) | all incl. `minimal` | Suggests `/compact` when the session grows large (background) |
| `pre-plan.sh` | UserPromptSubmit | always | Detects near-duplicate plans before one is created |

### Telemetry & housekeeping

| Hook | Event | Purpose |
|------|-------|---------|
| `post-tool-use.sh` | PostToolUse (Edit/Write/Bash) | Records file modifications; re-validates ops.json if changed |
| `command-log-audit.sh` | PostToolUse (Bash) | Appends an audit log of executed commands (background) |
| `session-start.sh` | SessionStart | Loads project context at session start |
| `cost-tracker.sh` | Stop | Accumulates token/cost telemetry (background) |
| `desktop-notify.sh` | Stop | Desktop notification when a turn ends (background) |
| `format-typecheck.sh` | Stop | Runs formatter + type-checker (`strict` only; background) |

`post-implement.sh` ships but is **not currently wired** in `settings.json`; it
is available for teams that want a post-implementation build/test gate.

### `lib.sh` — shared helpers

Not a hook. Sourced by the others; provides `resolve_root`,
`extract_json_field` (fail-closed JSON parsing), `hlog` (structured logging to
`.claude/hooks/hooks.log`), `deny` (stderr + `exit 2`), and the `*.ops.json` /
`ops-*.json` matching expressions.

## Project commands (`config.json`)

Hooks that build/test/lint read their commands from
`.claude/hooks/config.json` so nothing is hard-coded:

```json
{
  "project": {
    "build_cmd": "pip install -e .",
    "test_cmd": "pytest tests/ -v",
    "lint_cmd": "ruff check .",
    "coverage_cmd": "pytest --cov=src"
  }
}
```

| Key | Python | TypeScript | Java |
|-----|--------|------------|------|
| `build_cmd` | `pip install -e .` | `npm run build` | `./gradlew build` |
| `test_cmd` | `pytest tests/ -v` | `npm test` | `./gradlew test` |
| `lint_cmd` | `ruff check .` | `npm run lint` | `./gradlew check` |
| `coverage_cmd` | `pytest --cov=src` | `npm test -- --coverage` | `./gradlew jacocoTestReport` |

## Disabling hooks

- **Turn off enforcement:** set `ECC_HOOK_PROFILE=minimal`.
- **Disable a specific hook:** remove its entry from `.claude/settings.json`.
- **Disable everything:** remove the `hooks` block from `settings.json` (or
  delete `settings.json`; Claude Code then runs with no hooks).

## Self-testing a hook

Hooks read a JSON payload on stdin. You can exercise one directly:

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"rm -rf /"}}' \
  | ECC_HOOK_PROFILE=strict bash .claude/hooks/command-guard.sh
echo "exit=$?"   # 2 = blocked
```

`tests/test_hooks_behavioral.py` runs exactly this style of check for every
blocking hook (block on bad input, allow on good, fail-closed on malformed
JSON).

## Adding a custom hook

1. Create `.claude/hooks/my-hook.sh`, source `lib.sh`, and use `deny` to block:

   ```bash
   #!/usr/bin/env bash
   set -uo pipefail
   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
   [ -f "$SCRIPT_DIR/lib.sh" ] && . "$SCRIPT_DIR/lib.sh"
   PAYLOAD="$(cat)"
   CMD="$(extract_json_field "$PAYLOAD" command)" || deny "unparseable payload"
   case "$CMD" in *dangerous*) deny "blocked: dangerous command";; esac
   exit 0
   ```

2. `chmod +x .claude/hooks/my-hook.sh`.
3. Register it under the appropriate event in `.claude/settings.json`.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Hook not blocking | Confirm it exits **2** with stderr (not exit 1). Check `ECC_HOOK_PROFILE` isn't `minimal`. |
| Edits blocked while developing ClaudeKit | Set `ECC_HOOK_PROFILE=minimal` in `.claude/settings.local.json`. |
| Hook not running at all | Check it's registered in `.claude/settings.json` and executable. |
| Diagnosing behavior | Read `.claude/hooks/hooks.log`. |
| `strict` blocks safe commands | Add them to `security.allowedCommands` in `config.json`, or drop back to `standard`. |
