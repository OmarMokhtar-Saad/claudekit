# {{PROJECT_NAME}}

A Python project using ClaudeKit for multi-agent development workflows.

## Technology Stack

- **Language**: Python 3.11+
- **Build System**: pip / poetry / uv
- **Test Framework**: pytest

## Development Commands

```bash
# Install dependencies
pip install -e ".[dev]"

# Run tests
python -m pytest tests/ -v

# Lint
ruff check .
mypy .

# Coverage
python -m pytest tests/ --cov=src --cov-report=html

# Format
ruff format .
```

## Coverage Targets

- New code: 80%
- Overall: 70%
- Critical paths: 90%

## Architecture

Follow clean architecture principles:
- `src/` — Application source code
- `src/domain/` — Business logic, entities, interfaces
- `src/data/` — Data access, external integrations
- `src/api/` — API endpoints, request handling
- `tests/` — Test files mirroring src/ structure

## ClaudeKit Integration

### AI-Assisted Code Changes

Use the ops.json pipeline for all code changes:

1. `/generate-ops <task>` — Create ops.json
2. `/validate-ops <path>` — Run validator + dry-run
3. `/execute-ops <path>` — Execute with backup

### Commands

| Command | Purpose |
|---------|---------|
| `/plan <task>` | Create implementation plan |
| `/review` | Validate plan (90% threshold) |
| `/implement` | Execute approved plan |
| `/verify` | Run quality checks |
| `/debug <issue>` | Diagnose bugs |
| `/docs <target>` | Generate documentation |
| `/git <operation>` | Git operations |
| `/coordinator <task>` | Multi-agent orchestration |

### Scripts Directory

Operations scripts: `.claude/operations/scripts/`
