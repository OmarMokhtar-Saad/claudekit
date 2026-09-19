# Plan: `security.projectTools` — exempt project tool heads from the allowlist and host patterns

Ops config: `.claude/plans/ops-project-tools.json`.
Parent spec: `.claude/plans/plan-token-spend-remediation.md` section E, item 3.

## Overview

Device/build tools (`adb`, `emulator`, `gradle`, `./gradlew`, `xcrun`) drive a *device or a
build sandbox*, not the host. Two host-scoped controls in
`src/claudekit/security/command_validator.py` misfire on them:

1. the **allowlist** check (`safe_mode=True`) refuses `adb` outright — "Command not in
   allowlist: adb" is the single largest source of refused turns in the qa-agents fleet
   (parent spec, work item C.1);
2. the whole-command **host patterns** (`DANGEROUS_PATTERNS` + `_git_restore_violation`)
   read a device-side argument as a host command — `adb shell find /sdcard -delete` trips
   the host `find -delete` pattern although nothing on the host is touched.

A new `security.projectTools` array in `.claude/hooks/config.json` names the heads that are
exempt from exactly those two checks. **The blocklist is untouched**: `rm -rf /` is refused
before the exemption is ever consulted, in both modes, whatever `projectTools` says.

## Scope

Paths this ops config writes:

- `src/claudekit/security/command_validator.py` — `project_tools` on `__init__`, two new
  helpers, the host-pattern guard in `validate()`, the allowlist exemption in
  `_validate_segment()`, `projectTools` in `from_config()`
- `config.schema.json` — the `projectTools` array (the `security` object is
  `additionalProperties: false`, so without this the key is an invalid config)
- `tests/test_project_tools.py` — behavioural tests (new file)
- `CHANGELOG.md` — one `[Unreleased]` bullet

Out of scope: any qa-agents file (explicitly forbidden by the task brief); adding a
`projectTools` key to this repo's own `.claude/hooks/config.json` (a stdlib-only Python repo
has no `adb`/`gradle`, so the key would be inert here); `docs/HOOKS.md` (owned by another
session — the schema `description` carries the documentation instead).

## Implementation Steps

### 1. `CommandValidator.__init__` — accept and normalise the heads
`project_tools: Optional[Set[str]] = None`, stored as basenames
(`{t.split("/")[-1].strip("\\") for t in ...}`) so `./gradlew` and `/usr/bin/adb` both
register as their head. Default `None` → empty set → byte-identical behaviour.

### 2. Two helpers: `_is_project_tool` and `_all_heads_are_project_tools`
The host-pattern scan is whole-command by construction (`[^;&|]*` spans a line), so it may
only be skipped when **nothing in the command runs on the host outside a project tool**.
`_all_heads_are_project_tools` returns True only when every segment head (after stripping
env assignments) is a declared tool, and returns **False** — i.e. keeps the host scan — when
the command contains a command substitution or a redirect, because `_split_segments` drops
redirect targets and substitution payloads are only blocklist-checked. One non-project
segment (`adb shell x; rm -rf /`) brings the host patterns straight back.

### 3. `validate()` — guard the host patterns
The `DANGEROUS_PATTERNS` loop and `_git_restore_violation` move under
`if not self._all_heads_are_project_tools(command):`. Everything below (the per-line
segmentation, substitution scan, blocklist) is unchanged and still runs.

### 4. `_validate_segment()` — exempt the head from the allowlist only
`if self.project_tools and (base in self.project_tools or normalized in self.project_tools):
return True, "OK"` sits **after** every deny check (`_SHELL_BUILTIN_DENY`, `deny_base`
blocklist, `base`/`normalized` blocklist) and after the `blocklist_only` early return, so a
blocklisted head can never be whitelisted by naming it a project tool. This ordering is the
repo's own `allowlist-before-an-early-return` lesson applied deliberately.

### 5. `from_config()` — read `security.projectTools`

### 6. `config.schema.json` — declare the array

### 7. `tests/test_project_tools.py` — behavioural coverage
Both the class and the shipped wiring (`python3 -m claudekit.cli.main check-command` against
a tmp project's `.claude/hooks/config.json`), because a unit test of the class alone would
not prove `from_config` reads the key.

### 8. `CHANGELOG.md` — one `[Unreleased]` bullet

## Validation commands

```bash
python3 -m pytest tests/test_project_tools.py tests/test_security.py tests/test_validator_segmentation.py -q -p no:cacheprovider
ruff check src/ tests/ scripts/ .claude/operations/scripts/
python3 -c "import json;json.load(open('config.schema.json'))"
```

## Rollback Plan

Four string edits on three tracked files plus one new file.
`git checkout -- src/claudekit/security/command_validator.py config.schema.json CHANGELOG.md
&& rm tests/test_project_tools.py` restores the pre-change state. Never `git checkout -- .`:
other sessions hold ~80 uncommitted paths.

## Risk Assessment

- **HIGH — the exemption widens the security surface by design.** A declared project tool's
  *arguments* are no longer read as host commands, so `adb shell rm -rf /sdcard` is allowed.
  That is the requested behaviour (the destructive target is the device), and it is why the
  key is opt-in, empty by default, and never exempts a blocklisted head. Framing stays
  honest: this was always a denylist speed bump, not a sandbox.
- **MEDIUM — the host-pattern skip could be smuggled.** Mitigated by refusing the skip for
  any command containing `$( )`/backticks or a redirect, and by requiring *every* segment
  head to be a project tool. Tested in both directions.
- **MEDIUM — `config.schema.json` is modified by another concurrent session.** The baseline
  hash is stamped immediately before execution; if that session writes first, the executor
  refuses on drift rather than clobbering. The edit itself is a single key insertion.
- **LOW — no default is added to this repo's `.claude/hooks/config.json`.** The key is
  honoured, schema-valid and documented; populating it is a per-project decision.

## Archived configs

- `.claude/plans/archive/ops-project-tools/ops.json` (4 operations)

