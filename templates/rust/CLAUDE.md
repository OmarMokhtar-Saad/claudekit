# {{PROJECT_NAME}}

A Rust project using ClaudeKit for multi-agent development workflows.

## Technology Stack

- **Language**: Rust (latest stable)
- **Build System**: Cargo
- **Test Framework**: built-in + cargo-nextest

## Development Commands

```bash
# Build
cargo build

# Test
cargo test

# Lint
cargo clippy -- -D warnings

# Coverage
cargo tarpaulin --out html

# Format
cargo fmt
```

## Coverage Targets

- New code: 80%
- Overall: 70%
- Critical paths: 90%

## Architecture

- `src/` — Application source code
- `src/lib.rs` — Library root, module declarations
- `src/main.rs` — Binary entrypoint
- `src/domain/` — Business logic, traits, types
- `src/api/` — HTTP handlers, request/response types
- `src/data/` — Data access, external integrations
- `tests/` — Integration tests

## ClaudeKit Integration

Use the ops.json pipeline for all code changes.
Scripts: `.claude/operations/scripts/`
