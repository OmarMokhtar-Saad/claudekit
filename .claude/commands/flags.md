---
name: flags
description: Show universal command flag reference
usage: /flags [--flag-name]
args:
  flag-name:
    description: Optional specific flag to show details for
    required: false
---

# /flags - Universal Command Flag Reference

Display the available universal flags that can be appended to any command.

## Flag Reference Table

| Flag | Shorthand | Values | Default | Description |
|------|-----------|--------|---------|-------------|
| `--mode` | `-m` | plan, execute, review, fix, refactor, test, document | execute | Operational mode |
| `--depth` | `-d` | 1-5 | 2 | Analysis thoroughness (1=quick, 5=exhaustive) |
| `--format` | `-f` | concise, detailed, json, ultra | detailed | Output format |
| `--persona` | `-p` | security, performance, architecture, testing, devops | none | Specialist lens |
| `--save` | `-s` | file path | none | Save output to file |
| `--checkpoint` | `-c` | (boolean) | false | Create checkpoint before execution |

## Mode Details

- **plan**: Generate a step-by-step plan without executing. Shows files affected and complexity estimate.
- **execute**: Run the task immediately (default behavior).
- **review**: Analyze existing code and provide feedback. No modifications.
- **fix**: Find and fix bugs, errors, and broken behavior.
- **refactor**: Restructure code without changing external behavior.
- **test**: Generate or run tests with focus on coverage and edge cases.
- **document**: Create or update documentation, docstrings, and comments.

## Depth Levels

| Level | Time | Scope |
|-------|------|-------|
| 1 - Quick | ~30s | Single file, obvious issues |
| 2 - Standard | ~1m | Target file + direct imports |
| 3 - Thorough | ~3m | Dependency chains, types, interfaces |
| 4 - Deep | ~5m | Full module, cross-references, tests |
| 5 - Exhaustive | ~10m+ | Entire codebase, architecture, security |

## Persona Specializations

- **security**: Vulnerabilities, injection, auth, secrets, OWASP top 10
- **performance**: Complexity, memory, N+1 queries, caching, bundle size
- **architecture**: Design patterns, SOLID, coupling, cohesion, boundaries
- **testing**: Coverage, edge cases, mocking, organization, assertions
- **devops**: CI/CD, deployment, infrastructure, monitoring, logging

## Combination Examples

```bash
# Security review at maximum depth, save as JSON
/review src/auth/ --persona=security --depth=5 --format=json --save=reports/auth-audit.json

# Quick fix with checkpoint for safety
/fix src/api/handler.ts --depth=1 --checkpoint

# Plan a refactor with architecture lens
/refactor lib/core/ --mode=plan --persona=architecture --depth=3

# Generate tests with concise output
/test src/utils/ --mode=test --depth=3 --format=concise

# Full ship pipeline with everything enabled
/ship --checkpoint --depth=4 --persona=devops --save=ship-report.md --format=detailed
```

## Behavior

1. If a specific `--flag-name` argument is provided, show detailed information for that flag only.
2. If no argument is provided, display the complete reference table above.
3. Flags are parsed case-insensitively and can appear in any order after the command name.
4. Unknown flags produce a warning but do not cause errors.
5. When the same flag is specified multiple times, the last value wins.
