# {{PROJECT_NAME}}

A Kotlin project using ClaudeKit for multi-agent development workflows.

## Technology Stack

- **Language**: Kotlin 2.x
- **Build System**: Gradle (Kotlin DSL)
- **Test Framework**: JUnit 5, MockK

## Development Commands

```bash
# Build
./gradlew build

# Test
./gradlew test

# Lint
./gradlew detekt

# Coverage
./gradlew koverReport

# Clean
./gradlew clean build
```

## Architecture

- `src/main/kotlin/.../` — Application source
- `src/main/kotlin/.../domain/` — Business logic
- `src/main/kotlin/.../data/` — Data access
- `src/main/kotlin/.../api/` — API layer
- `src/test/kotlin/` — Tests

## ClaudeKit Integration

Use the ops.json pipeline for all code changes.
Scripts: `.claude/operations/scripts/`
