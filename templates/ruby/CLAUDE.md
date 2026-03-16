# {{PROJECT_NAME}}

A Ruby project using ClaudeKit for multi-agent development workflows.

## Technology Stack

- **Language**: Ruby 3.x
- **Build System**: Bundler
- **Test Framework**: RSpec, SimpleCov

## Development Commands

```bash
# Install dependencies
bundle install

# Test
bundle exec rspec

# Lint
bundle exec rubocop

# Coverage
COVERAGE=true bundle exec rspec

# Format
bundle exec rubocop -a
```

## Coverage Targets

- New code: 80%
- Overall: 70%
- Critical paths: 90%

## Architecture

- `app/` — Application source (Rails) or `lib/` (gem/library)
- `app/models/` — Domain models, business logic
- `app/controllers/` — Request handling
- `app/services/` — Service objects, use cases
- `lib/` — Library code, utilities
- `spec/` — RSpec test files mirroring app/ structure

## ClaudeKit Integration

Use the ops.json pipeline for all code changes.
Scripts: `.claude/operations/scripts/`
