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
claudekit doctor
```

Checks: Python version, Bash, Git, agents, commands, skills, hooks, registry integrity, config validity.

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
