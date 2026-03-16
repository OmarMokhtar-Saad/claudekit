# {{PROJECT_NAME}}

A C#/.NET project using ClaudeKit for multi-agent development workflows.

## Technology Stack

- **Language**: C# 12 / .NET 8
- **Build System**: dotnet CLI / MSBuild
- **Test Framework**: xUnit, NSubstitute, FluentAssertions

## Development Commands

```bash
# Build
dotnet build

# Test
dotnet test

# Lint / Format
dotnet format

# Coverage
dotnet test --collect:"XPlat Code Coverage" --results-directory ./coverage

# Clean
dotnet clean && dotnet build
```

## Coverage Targets

- New code: 80%
- Overall: 70%
- Critical paths: 90%

## Architecture

Follow Clean Architecture with solution structure:

- `src/` — Application source projects
- `src/Domain/` — Entities, interfaces, value objects
- `src/Application/` — Use cases, DTOs, service interfaces
- `src/Infrastructure/` — Data access, external services
- `src/Api/` — Controllers, middleware, configuration
- `tests/` — Test projects mirroring src/ structure

## ClaudeKit Integration

Use the ops.json pipeline for all code changes.
Scripts: `.claude/operations/scripts/`
