# {{PROJECT_NAME}}

A Go project using ClaudeKit for multi-agent development workflows.

## Technology Stack

- **Language**: Go 1.22+
- **Build System**: Go modules
- **Test Framework**: testing + testify

## Development Commands

```bash
# Build
go build ./...

# Test
go test ./... -v

# Lint
golangci-lint run

# Coverage
go test ./... -coverprofile=coverage.out
go tool cover -html=coverage.out

# Format
gofmt -w .
```

## Architecture

- `cmd/` — Application entrypoints
- `internal/` — Private application code
- `internal/domain/` — Business logic, interfaces
- `internal/handler/` — HTTP handlers
- `internal/repository/` — Data access
- `pkg/` — Public library code

## ClaudeKit Integration

Use the ops.json pipeline for all code changes.
Scripts: `.claude/operations/scripts/`
