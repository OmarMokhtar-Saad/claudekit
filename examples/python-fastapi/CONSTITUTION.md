# FastAPI Example Constitution

**Version**: 1.0
**Status**: ACTIVE

## Article I: Architecture

Clean Architecture: API → Domain → Data. No direct API→Data imports.

## Article II: Code Quality

- Type hints on all public functions
- Pydantic models for all API schemas
- async/await for all I/O operations

## Article III: Testing

- 80% coverage on new code
- Test command: `python -m pytest tests/ -v`
- Use httpx.AsyncClient for API tests

## Article IV: Security

- No hardcoded secrets
- Input validation via Pydantic
- SQL injection prevention via parameterized queries
- CORS configuration required

## Article V: Operations

- All plans require ops.json
- Protected files: requirements.txt, pyproject.toml, *.md

## Article VI: Review

- Plan approval: 90/100
- Quality verification: 80/100
- Max 3 iterations before escalation
