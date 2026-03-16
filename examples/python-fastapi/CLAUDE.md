# FastAPI Example

A Python FastAPI project with ClaudeKit multi-agent workflows pre-configured.

## Technology Stack

- **Language**: Python 3.11+
- **Framework**: FastAPI
- **Build System**: pip + pyproject.toml
- **Test Framework**: pytest + httpx

## Development Commands

```bash
# Install
pip install -e ".[dev]"

# Run server
uvicorn src.main:app --reload

# Test
python -m pytest tests/ -v

# Lint
ruff check . && mypy src/

# Coverage
python -m pytest tests/ --cov=src --cov-report=html

# Format
ruff format .
```

## Project Structure

```
src/
├── main.py           # FastAPI app entry point
├── domain/
│   ├── models.py     # Pydantic models / entities
│   └── services.py   # Business logic interfaces
├── api/
│   ├── routes/       # API route handlers
│   └── deps.py       # Dependency injection
├── data/
│   ├── database.py   # Database connection
│   └── repos.py      # Repository implementations
└── config.py         # App configuration
tests/
├── test_api/         # API endpoint tests
├── test_domain/      # Business logic tests
└── conftest.py       # Shared fixtures
```

## Coverage Targets

- New code: 80%
- Overall: 70%
- Critical paths: 90%

## Architecture

Clean Architecture with strict layer boundaries:

```
API Layer (routes, deps) → Domain Layer (models, services) → Data Layer (repos, database)
```

**Forbidden**: API layer importing directly from Data layer.

## ClaudeKit Commands

| Command | Purpose |
|---------|---------|
| `/plan <task>` | Create implementation plan with ops.json |
| `/review` | Validate plan (90% threshold) |
| `/implement` | Execute approved plan |
| `/verify` | Run quality checks (80% threshold) |
| `/debug <issue>` | Diagnose bugs (read-only) |
| `/docs <target>` | Generate documentation |
| `/git <op>` | Git operations |

## Operations Config

Scripts: `.claude/operations/scripts/`

```json
{
  "plan": "add-user-endpoint",
  "operations": [
    {
      "type": "code_edit",
      "path": "src/api/routes/users.py",
      "edits": [{ "find": "# routes", "add_after": "\n@router.get('/users')\nasync def list_users():\n    pass" }]
    }
  ]
}
```
