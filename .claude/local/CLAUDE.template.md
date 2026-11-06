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

When making ANY code change, follow the plan flow:

1. `/plan <task>` — Write plan.md (Tier + `Files:` list)
2. `/review` — Reviewer scores it; `review-record.py plan-write` records the approved plan
3. Edit directly in the main session; plan-gate allows only the listed files

### Skills (slash commands)

| Command | Purpose |
|---------|---------|
| `/plan <task>` | Create implementation plan |
| `/review` | Validate plan (90% threshold) |
| `/implement` | Execute approved plan (main session edits) |
| `/verify` | Run quality checks |
| `/debug <issue>` | Diagnose bugs (read-only) |
| `/docs <target>` | Generate documentation |
| `/git <operation>` | Git operations |
| `/coordinator <task>` | Multi-agent orchestration |

### Governance

See `.claude/local/CONSTITUTION.md` for project-specific rules and quality gates.
