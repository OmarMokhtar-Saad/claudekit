# {{PROJECT_NAME}}

A Swift project using ClaudeKit for multi-agent development workflows.

## Technology Stack

- **Language**: Swift 5.9+
- **Build System**: Swift Package Manager
- **Test Framework**: XCTest

## Development Commands

```bash
# Build
swift build

# Test
swift test

# Lint
swiftlint

# Coverage
swift test --enable-code-coverage
```

## Architecture

- `Sources/` — Application source
- `Sources/Domain/` — Business logic, protocols
- `Sources/Data/` — Data access, networking
- `Sources/App/` — Application entry, configuration
- `Tests/` — Test targets

## ClaudeKit Integration

Use the ops.json pipeline for all code changes.
Scripts: `.claude/operations/scripts/`
