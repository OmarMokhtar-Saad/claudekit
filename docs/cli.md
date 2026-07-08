# ClaudeKit CLI Reference

## Installation

```bash
pip install -e .
```

This makes `claudekit` (and shorthand `ck`) available globally.

## Commands

### `claudekit init [target] [options]`

Initialize ClaudeKit in a project directory.

```bash
claudekit init .                          # Current directory, full mode
claudekit init /path/to/project --minimal # Minimal install
claudekit init . --language typescript    # Pre-configure for TypeScript
claudekit init . --force                  # Overwrite existing installation
```

**Options:**
| Flag | Description |
|------|-------------|
| `--mode full\|minimal` | Installation mode (default: full) |
| `--language LANG` | Pre-configure for language |
| `--force` | Overwrite existing installation |

### `claudekit doctor`

Run health checks on the current ClaudeKit installation.

```bash
claudekit doctor            # exit 0 on pass/warn, 1 on failure
claudekit doctor --strict   # treat warnings as failures (exit 1)
```

Checks: Python version, Bash, Git, agents, commands, skills, hooks, registry integrity, config validity.

### `claudekit diff [target]`

Show which ClaudeKit-managed files you've locally modified, using the install
manifest (`.claude/.claudekit-manifest.json`, per-file sha256). When the kit
source is also available, modified files are refined into `locally modified`
(you edited it), `kit-updated` (the file already matches a newer kit), or
`both changed`; files you added under `agents/ commands/ skills/ hooks/` are
listed as `custom`.

Pre-manifest installs (before v2.1) don't error: `diff` falls back to comparing
the project's managed assets directly against the kit source, classifying each
file as `identical` / `differs` / `custom` / `not installed`. Provenance is
unknown in this mode — `differs` may be a local edit or just an older kit
version.

```bash
claudekit diff              # report modified/missing/unchanged/custom files
```

### `claudekit update [target]`

Re-install ClaudeKit over an existing project. Detects locally-modified managed
files and warns before overwriting; the installer stages + backs up the previous
`.claude/` first (recoverable). Reuses the mode/language from the manifest.
Project-custom assets (files under `agents/ commands/ skills/` that the kit
doesn't manage) are preserved across the update.

Pre-manifest installs work too: `update` warns, asks for confirmation (or
`--yes`), reinstalls in full mode, and writes a manifest so the next update is
precise.

```bash
claudekit update            # prompts if local edits would be overwritten
claudekit update --yes      # non-interactive
```

### `claudekit uninstall [target]`

Remove ClaudeKit-managed files (per the manifest), moving them to a timestamped
`backups/uninstall-<stamp>/` first so the removal is recoverable.

```bash
claudekit uninstall --dry-run   # list what would be removed
claudekit uninstall --yes       # remove (non-interactive)
```

### `claudekit eval`

Run behavioral evals against the prompt corpus (task 010): each eval spawns a real agent
in an isolated fixture workspace and asserts on its *behavior* — artifacts extractable and
valid, refutation catches planted defects, no fabricated verification numbers, reported
counts match executed ground truth. Complements the structural test suite, which only
asserts the prompt text.

```bash
claudekit eval --list       # available evals
claudekit eval --dry-run    # validate definitions + workspace build (free)
claudekit eval              # run all (real API calls, ~$0.2–1.5 per eval)
claudekit eval --only planner-delivers-artifacts
```

Definitions live in `evals/definitions/*.json`; fixtures in `evals/fixtures/`. Run after
any prompt-corpus change and before releases.

### `claudekit check-command "<cmd>"` / `claudekit check-path <path>`

Validate a shell command or file path against the security layer (a denylist
speed bump — see `docs/HOOKS.md` and `SECURITY.md`). Exit 0 = allow, 2 = block.

```bash
claudekit check-command "rm -rf /"       # exit 2, reason on stderr
claudekit check-path /etc/passwd         # exit 2
```

### `claudekit validate <ops.json>`

Validate an operations config file.

```bash
claudekit validate operations/my-plan/ops.json
claudekit validate ops.json --verbose
```

### `claudekit execute <ops.json>`

Execute an operations config with automatic backup.

```bash
claudekit execute ops.json --dry-run    # Preview changes
claudekit execute ops.json              # Apply changes
claudekit execute ops.json --verbose    # Debug output
```

### `claudekit rollback`

Rollback from a previous backup.

```bash
claudekit rollback --list               # List available backups
claudekit rollback --backup backups/my-plan-20260316-120000  # Restore
claudekit rollback --backup <dir> --dry-run  # Preview restore
```

### `claudekit agents`

List all installed agents with their metadata.

```bash
claudekit agents
```

### `claudekit config [key]`

Show or query configuration.

```bash
claudekit config                        # Show full config
claudekit config project.build_cmd      # Query specific key
```
