# Hooks

ClaudeKit ships 32 hook scripts (plus `lib.sh`, a shared helper library). 29 are
reachable: wired into Claude Code through `.claude/settings.json`, or resolved by a
gate wrapper. They enforce guardrails, capture telemetry, and automate housekeeping
around the agent workflow.

**Three ship unwired**, and the count must not be read as saying otherwise:
`auto-checkpoint.sh` and `check-comment-replacement.sh`, promoted out of
`templates/hooks/` in task 008 batch 1 where nothing invoked them either -- promotion
changed where they live, not whether they run -- and `post-implement.sh`, which has
shipped unwired for far longer and is described as such further down this very file.
This page opened by claiming all of them were wired while contradicting itself at the
`post-implement.sh` entry below, so the sentence was wrong before batch 1 and the
promotion only widened the gap.
`tests/test_structure.py::TestHookWiringIsHonest` pins this, so the prose cannot drift
from the tree again.

> **`PreToolUse` runs through `dispatch.sh` -- that event only.** It is the
> per-event dispatcher front end: it runs every handler registered for that event in
> `dispatch-registry.json`, decodes each exit code (`0 -> ALLOW`, `2 -> DENY`,
> **anything else -> ERROR**), clamps `advisory` handlers, and takes the **most
> restrictive** outcome, so a result can never depend on registration order and a
> handler that crashes can never fail open. The other seven events are still
> invoked directly: `exit 2` is not honoured on them, and several of their hooks
> are backgrounded with `&`, which the dispatcher does not model yet. So "one
> dispatcher per event" is the design; **one of the eight events** is routed
> through it, and the merge rule and the event-log records apply to that event
> alone.

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

> **The event log may contain guard stderr.** When a hook decision is recorded,
> up to 512 bytes of the handler's stderr is kept as `stderr_preview` in
> `.claude/runtime/events/*.jsonl`. A guard that blocks a secret-bearing write and
> echoes the offending text back as its reason will therefore land that text on
> disk. The directory is gitignored and advisory stdout is not captured, so this
> is a local-disk disclosure rather than a leak into version control — but a hook
> author should quote the *rule* that was violated, not the value that violated
> it.

## `ECC_HOOK_PROFILE` — enforcement level

A single environment variable controls how aggressively hooks enforce:

| Profile | Behavior |
|---------|----------|
| `minimal` | Blocking/enforcement hooks are **off**. Advisory + telemetry hooks still run. Use this when working *on ClaudeKit itself* so your own edits aren't blocked. |
| `standard` | **Default.** Enforcement hooks block, including the command guard. The one permissive path: if the `claudekit-agents` Python package isn't installed the guard can't run, so it warns that the command was **not checked** rather than denying every command. |
| `strict` | Everything in `standard`, plus a missing validator **blocks** too (no permissive path at all), and expensive checks (`format-typecheck`) and the opt-in advisory gates (`file-guard-gate`, `injection-scan-gate`) run. |

Set it in your shell or in `.claude/settings.local.json` (git-ignored):

```json
{ "env": { "ECC_HOOK_PROFILE": "strict" } }
```

Unset defaults to `standard`.

### `ECC_OPS_ENFORCEMENT=off` — keep the profile, drop one gate

Sets only the `ops-enforcement` hook (the Edit/Write source-file gate) to pass-through while every other `standard` hook keeps binding. Put it in the same `env` object. Only the literal `off` opts out; any other value leaves the gate on.

## Hook catalog

### Enforcement (blocking) — `PreToolUse`

| Hook | Trigger | Profile | Purpose |
|------|---------|---------|---------|
| `ops-enforcement.sh` | Edit/Write | off in `minimal` | Enforces the plan→ops.json→execute flow; blocks ad-hoc edits outside allowed areas |
| `config-protection.sh` | Edit/Write | off in `minimal` | Blocks edits to protected config files |
| `block-no-verify.sh` | Bash | off in `minimal` | Blocks `git commit/push --no-verify` (which would skip hooks) |
| `commit-quality.sh` | Bash | off in `minimal` | Enforces commit-message quality |
| `command-guard.sh` | Bash | **`strict` blocks**, `standard` warns, `minimal` off | Denylist speed bump over shell commands (`CommandValidator`). A flagged command blocks under `standard` too; only a validator that is **missing or crashed** takes the permissive path (and `strict` closes that). See `SECURITY.md`. |
| `concurrency-guard.py` | Bash | **`minimal` is advisory** (records `WOULD-BLOCK`), else blocks | Blocks tree-wide git that clobbers a concurrent session in a shared tree: `add`/`stage` with `-A|-u|.`, `commit -a`, `reset --hard|--merge|--keep` or bare `reset`, `checkout|restore|switch` with a tree-wide pathspec, `checkout -f`/`switch -f`, `clean -f`, `stash`/`stash push` unscoped, `rm .`, `worktree remove -f`. Tokenises with `shlex`, so flag order, `--`, clusters, `git -C`, `bash -lc` and multi-line scripts are all handled. Scoped and restorative forms (`add -A -- <path>`, `stash push <path>`, `stash pop`) stay allowed. `CK_ALLOW_BROAD_GIT=1` downgrades to a warning. See `.ai/CONCURRENCY.md`. |
| `pre-commit.sh` | Bash (`git commit`) | always | Validates ops.json configs and scans staged files for secrets |
| `pre-push.sh` | Bash (`git push`) | always | Full validation suite before a push to remote |

### Advisory — `PreToolUse` / `UserPromptSubmit`

| Hook | Event | Profile | Purpose |
|------|-------|---------|---------|
| `security-reminder.sh` | Edit/Write | `standard` + `strict` | Non-blocking reminder when touching sensitive files |
| `file-guard-gate.sh` | Edit/Write | `strict` only | Advisory warning (never blocks) when the edit target is a sensitive file; wraps `file-guard.sh` |
| `injection-scan-gate.sh` | UserPromptSubmit | `strict` only | Advisory warning (never blocks) when a prompt matches a known injection pattern; wraps `prompt-injection-scanner.sh` |
| `suggest-compact.sh` | PreToolUse (all) | all incl. `minimal` | Suggests `/compact` when the session grows large (background) |
| `pre-plan.sh` | UserPromptSubmit | always | Detects near-duplicate plans before one is created |

### Telemetry & housekeeping

| Hook | Event | Purpose |
|------|-------|---------|
| `post-tool-use.sh` | PostToolUse (Edit/Write/Bash) | Records file modifications; re-validates ops.json if changed |
| `command-log-audit.sh` | PostToolUse (Bash) | Appends an audit log of executed commands (background) |
| `operations/scripts/output_filter.py` | PostToolUse (Bash) | Rewrites noisy command **stdout** before Claude sees it (see below) |

### Output filtering (`output_filter.py`)

Some commands spend most of their output saying nothing. A full `pytest tests/ -q` run here
emits ~12,940 bytes of all-passing progress dots before the one line anybody reads. The
filter replaces those lines with a one-line summary, using declarative JSON filters.

It is deliberately conservative:

- **It cannot touch a failed command.** Claude Code does not run `PostToolUse` for a Bash
  call that exits non-zero, and the `PostToolUseFailure` event has no output-rewriting
  field at all.
- **It never touches `stderr`,** and never touches the exit status. Only `stdout` is
  rewritten; every other field of the tool response is passed through unchanged.
- **It fails soft.** Any error and the original output stands, untruncated.
- **Gate-bearing commands are on a denylist** the project-local filter file cannot override:
  the `--check` generators, `validate-config-json.py`, `review-record.py`,
  `execute-json-ops.py`, `ck doctor`, `ruff`, `mypy`, `shellcheck`.

**Escape hatch — raw output on demand.** Prefix the command with `CK_RAW_OUTPUT=1`:

```bash
CK_RAW_OUTPUT=1 python3 -m pytest tests/ -q     # unfiltered
```

Every summary line the filter emits names that hatch, so it is discoverable from the
filtered output itself. To turn the filter off for a whole session, set
`"CK_OUTPUT_FILTER": "off"` in the `env` block of `.claude/settings.local.json`.

**Customising it per project.** `.claude/operations/scripts/output-filters.json` ships with
the kit and holds one filter (`pytest-progress`). Do not edit it. Create
`.claude/operations/scripts/output-filters.local.json` with the same shape instead: entries
there override the base ones by `id`, and because that file never ships it is never listed
in `.claudekit-manifest.json`, which is what makes an upgrade preserve it. Available
operations are `strip_lines_matching` (a per-line regex) and `tail_lines` (an integer, and
because dropping the head of an output can drop the start of a traceback the filter must
also set `"lossy": true` to use it).
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

`build_cmd` runs via `bash -c` in `pre-commit.sh` on every commit that touches
source files — treat it with the same care as a `package.json` script.
`pre-commit.sh` screens it through the same `CommandValidator` that gates the
Bash tool before running it, and refuses `config.json` outright if it's a
symlink (both close the "config.json is trusted input, no questions asked"
gap; fixed 2026-07-30).

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
