# {{PROJECT_NAME}}

A TypeScript project using ClaudeKit for multi-agent development workflows.

## Technology Stack

- **Language**: TypeScript 5.x
- **Build System**: npm / yarn / pnpm
- **Test Framework**: Jest / Vitest

## Development Commands

```bash
# Install
npm install

# Build
npm run build

# Test
npm test

# Lint
npm run lint

# Coverage
npm run test -- --coverage

# Format
npx prettier --write .
```

## Coverage Targets

- New code: 80%
- Overall: 70%
- Critical paths: 90%

## Architecture

- `src/` — Application source
- `src/domain/` — Business logic, types, interfaces
- `src/services/` — Service implementations
- `src/api/` — API routes/controllers
- `src/utils/` — Shared utilities
- `tests/` — Test files

## ClaudeKit Integration

Use the ops.json pipeline for all code changes:

1. `/generate-ops <task>` — Create ops.json
2. `/validate-ops <path>` — Validate
3. `/execute-ops <path>` — Execute with backup

Scripts: `.claude/operations/scripts/`
