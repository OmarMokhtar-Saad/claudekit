# {{PROJECT_NAME}}

A PHP project using ClaudeKit for multi-agent development workflows.

## Technology Stack

- **Language**: PHP 8.3+
- **Build System**: Composer
- **Test Framework**: PHPUnit, PHPStan

## Development Commands

```bash
# Install dependencies
composer install

# Test
./vendor/bin/phpunit

# Lint / Static Analysis
./vendor/bin/phpstan analyse

# Coverage
XDEBUG_MODE=coverage ./vendor/bin/phpunit --coverage-html coverage/

# Format
./vendor/bin/php-cs-fixer fix
```

## Coverage Targets

- New code: 80%
- Overall: 70%
- Critical paths: 90%

## Architecture

- `app/` — Application source (Laravel) or `src/` (library)
- `app/Models/` — Eloquent models, domain entities
- `app/Http/Controllers/` — Request handling
- `app/Services/` — Business logic, service classes
- `app/Repositories/` — Data access layer
- `tests/` — PHPUnit test files

## ClaudeKit Integration

Use the ops.json pipeline for all code changes.
Scripts: `.claude/operations/scripts/`
