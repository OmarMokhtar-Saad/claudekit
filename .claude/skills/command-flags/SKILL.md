---
name: command-flags
description: Use when parsing command arguments - provides universal flag system for all slash commands with --mode, --depth, --format, --persona, --save, --checkpoint support
---

# Command Flags Skill

Universal flags that can be appended to any command to modify behavior, output format, analysis depth, and persona.

## Flag Definitions

### `--mode=[name]`

Controls the operational mode for the current command.

| Mode | Description |
|------|-------------|
| `plan` | Generate a detailed plan without executing. Output steps, files affected, and estimated complexity. |
| `execute` | Execute the task immediately with default settings. |
| `review` | Review existing code/changes. Provide feedback without modifications. |
| `fix` | Identify and fix issues. Focus on bugs, errors, and broken behavior. |
| `refactor` | Restructure code without changing behavior. Improve readability, reduce duplication. |
| `test` | Generate or run tests. Focus on coverage and edge cases. |
| `document` | Generate or update documentation. Inline comments, docstrings, READMEs. |

**Default:** `execute`

### `--depth=[1-5]`

Controls analysis thoroughness. Higher values take longer but are more comprehensive.

| Depth | Name | Behavior |
|-------|------|----------|
| 1 | Quick | Surface-level check. Single file, obvious issues only. ~30 seconds. |
| 2 | Standard | Check the target file and direct imports. Basic validation. ~1 minute. |
| 3 | Thorough | Follow dependency chains. Check types, interfaces, tests. ~3 minutes. |
| 4 | Deep | Full module analysis. Cross-reference patterns, check edge cases, review tests. ~5 minutes. |
| 5 | Exhaustive | Entire codebase scan. Architecture review, security audit, performance analysis. ~10+ minutes. |

**Default:** `2`

### `--format=[fmt]`

Controls output format.

| Format | Description |
|--------|-------------|
| `concise` | Minimal output. One-liners, bullet points. No explanations. |
| `detailed` | Full explanations with context, reasoning, and examples. |
| `json` | Structured JSON output (see schema below). |
| `ultra` | Maximum verbosity. Step-by-step walkthrough with full context and alternatives. |

**Default:** `detailed`

#### JSON Output Schema

When `--format=json` is used, output conforms to:

```json
{
  "command": "<the command that was run>",
  "flags": {
    "mode": "<mode>",
    "depth": "<depth>",
    "format": "json",
    "persona": "<persona or null>",
    "save": "<path or null>",
    "checkpoint": "<true|false>"
  },
  "result": {
    "status": "success | partial | failure",
    "summary": "<one-line summary>",
    "items": [
      {
        "type": "finding | action | suggestion | error",
        "severity": "info | low | medium | high | critical",
        "file": "<file path or null>",
        "line": "<line number or null>",
        "message": "<description>",
        "details": "<extended context or null>"
      }
    ],
    "stats": {
      "files_analyzed": 0,
      "issues_found": 0,
      "actions_taken": 0,
      "duration_seconds": 0
    }
  },
  "metadata": {
    "timestamp": "<ISO 8601>",
    "agent": "claude-code",
    "project": "<project root>"
  }
}
```

### `--persona=[type]`

Applies a specialist lens to analysis and output.

| Persona | Focus Areas |
|---------|-------------|
| `security` | Vulnerabilities, injection attacks, auth flaws, secrets exposure, OWASP top 10. |
| `performance` | Time complexity, memory usage, N+1 queries, caching opportunities, bundle size. |
| `architecture` | Design patterns, SOLID principles, coupling, cohesion, module boundaries. |
| `testing` | Test coverage, edge cases, mocking strategy, test organization, assertion quality. |
| `devops` | CI/CD pipelines, deployment configs, infrastructure, monitoring, logging. |

**Default:** none (general-purpose analysis)

### `--save=[path]`

Save the command output to the specified file path.

- If `path` is a relative path, it is resolved from the project root.
- If `path` is a directory, a file is auto-named: `<command>-<timestamp>.<format>`.
- The file format matches `--format` (`.md` for concise/detailed/ultra, `.json` for json).
- The save happens after all other processing is complete.

### `--checkpoint`

Create a git-based checkpoint before executing the command.

- Stashes current working state with a descriptive label.
- Records the checkpoint in `.claude/checkpoints/registry.json`.
- If the command fails or produces undesired results, the checkpoint can be restored.
- Equivalent to running `/checkpoint save` before the command.

## Parsing Rules

1. Flags can appear anywhere in the command after the slash-command name.
2. Flags are case-insensitive: `--Mode=Plan` is the same as `--mode=plan`.
3. Boolean flags (`--checkpoint`) do not require a value.
4. Unknown flags are ignored with a warning.
5. Conflicting flags use last-wins: `--mode=plan --mode=fix` uses `fix`.
6. Shorthand aliases are supported:
   - `-m` for `--mode`
   - `-d` for `--depth`
   - `-f` for `--format`
   - `-p` for `--persona`
   - `-s` for `--save`
   - `-c` for `--checkpoint`

## Processing Algorithm

When a command is invoked with flags, process in this order:

1. **Parse** all flags from the command string.
2. **Validate** flag values against allowed options. Warn on invalid values and use defaults.
3. **Checkpoint** if `--checkpoint` is set, create a checkpoint first.
4. **Configure** the persona lens if `--persona` is set.
5. **Execute** the command with the specified `--mode` and `--depth`.
6. **Format** the output according to `--format`.
7. **Save** the output if `--save` is set.

## Usage Examples

```
/review src/auth/ --mode=review --depth=4 --persona=security
/fix src/api/handler.ts --mode=fix --depth=3 --format=json --save=reports/
/refactor lib/ --mode=refactor --depth=3 --checkpoint --persona=architecture
/test src/utils.ts --mode=test --depth=2 --format=concise
/ship --checkpoint --depth=4 --persona=devops --save=ship-report.md
```
