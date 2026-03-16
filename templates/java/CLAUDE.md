# {{PROJECT_NAME}}

A Java project using ClaudeKit for multi-agent development workflows.

## Technology Stack

- **Language**: Java 21
- **Build System**: Gradle / Maven
- **Test Framework**: JUnit 5, Mockito, AssertJ

## Development Commands

```bash
# Build
./gradlew build

# Test
./gradlew test

# Lint / Quality
./gradlew check

# Coverage
./gradlew jacocoTestReport

# Clean build
./gradlew clean build
```

## Coverage Targets

- New code: 80%
- Overall: 70%
- Critical paths: 90%

## Architecture

Follow Clean Architecture with strict layer boundaries:

```
UI/API Layer → Domain Layer → Data Layer
```

- `src/main/java/.../api/` — Controllers, DTOs
- `src/main/java/.../domain/` — Entities, interfaces, use cases
- `src/main/java/.../data/` — Repositories, external services
- `src/test/java/` — Tests mirroring main structure

## ClaudeKit Integration

Use the ops.json pipeline for all code changes.
Scripts: `.claude/operations/scripts/`
