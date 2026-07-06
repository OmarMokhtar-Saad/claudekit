# {{PROJECT_NAME}}

{{PROJECT_DESCRIPTION}}

## Technology Stack

- **Language**: {{LANGUAGE}}
- **Framework**: {{FRAMEWORK}}
- **Build System**: {{BUILD_SYSTEM}}
- **Test Framework**: {{TEST_FRAMEWORK}}

## Development Commands

```bash
# Build
{{BUILD_CMD}}

# Test
{{TEST_CMD}}

# Lint
{{LINT_CMD}}

# Coverage
{{COVERAGE_CMD}}
```

## Coverage Targets

- New code: 80%
- Overall: 70%
- Critical paths: 90%

## Architecture

{{ARCHITECTURE_DESCRIPTION}}

## Project Structure

```
{{PROJECT_STRUCTURE}}
```

## ClaudeKit Integration

This project uses [ClaudeKit](https://github.com/OmarMokhtar-Saad/claudekit) for multi-agent workflows.

### AI-Assisted Code Changes (MANDATORY)

When making ANY code change, use the ops.json pipeline:

1. `/generate-ops <task>` — Create ops.json
2. `/validate-ops <path>` — Run validator + dry-run
3. `/execute-ops <path>` — Execute with backup

### Skills (slash commands)

| Command | Purpose |
|---------|---------|
| `/plan <task>` | Create implementation plan |
| `/review` | Validate plan (90% threshold) |
| `/implement` | Execute approved plan |
| `/verify` | Run quality checks |
| `/debug <issue>` | Diagnose bugs (read-only) |
| `/docs <target>` | Generate documentation |
| `/git <operation>` | Git operations |
| `/coordinator <task>` | Multi-agent orchestration |

### Operations Config Format

```json
{
  "plan": "plan-name",
  "operations": [
    {
      "type": "code_edit",
      "path": "{{EXAMPLE_FILE_PATH}}",
      "edits": [{ "find": "exact text", "replace": "new text" }]
    }
  ]
}
```

### Governance

See `.claude/local/CONSTITUTION.md` for project-specific rules and quality gates.

## Scripts Directory

Operations scripts are located in `.claude/operations/scripts/`:
- `validate-config-json.py` — Validate ops.json (29 safety guards)
- `execute-json-ops.py` — Execute operations with backup
- `restore-backup.py` — Restore from backup

Scripts are auto-discovered from `.claude/operations/scripts/`.
