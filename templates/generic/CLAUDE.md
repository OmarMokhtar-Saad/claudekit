# {{PROJECT_NAME}}

A project using ClaudeKit for multi-agent development workflows.

## Development Commands

```bash
# Build
# TODO: Add your build command

# Test
# TODO: Add your test command

# Lint
# TODO: Add your lint command
```

## Configuration

Update `.claude/hooks/config.json` with your project's commands:

```json
{
  "project": {
    "build_cmd": "your-build-command",
    "test_cmd": "your-test-command",
    "lint_cmd": "your-lint-command",
    "coverage_cmd": "your-coverage-command"
  }
}
```

## ClaudeKit Integration

Use the ops.json pipeline for all code changes:

1. `/generate-ops <task>` — Create ops.json
2. `/validate-ops <path>` — Validate
3. `/execute-ops <path>` — Execute with backup

Scripts: `.claude/operations/scripts/`
