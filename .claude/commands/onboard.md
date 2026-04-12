---
description: "Onboard to an unfamiliar codebase — generates structured guide and CLAUDE.md from code analysis"
argument-hint: "[--guide|--claude-md|--both]"
model: sonnet
---

# Onboard Command

Analyze an unfamiliar codebase and produce two artifacts: a scannable onboarding guide and a project-specific CLAUDE.md. Generated from the actual code — not from assumptions.

## Mandatory Skills

- **using-superpowers** - Core capabilities
- **codebase-onboarding** - Systematic analysis methodology

## Task

Onboard to codebase: $ARGUMENTS

---

## Output Modes

| Flag | Output |
|------|--------|
| `--guide` | Onboarding guide only (markdown) |
| `--claude-md` | CLAUDE.md only |
| `--both` (default) | Both artifacts |

---

## Execution Steps

### Phase 1: Reconnaissance (Parallel)

```bash
# Detect stack
ls package.json go.mod Cargo.toml pyproject.toml pom.xml 2>/dev/null

# Framework fingerprinting
ls next.config* nuxt.config* angular.json django/ flask/ fastapi/ 2>/dev/null

# Entry points
find . -maxdepth 3 -name "main.*" -o -name "index.*" -o -name "app.*" \
   -o -name "server.*" | grep -v node_modules | grep -v ".git" | head -15

# Top-level structure
find . -maxdepth 2 -not -path "*/node_modules/*" -not -path "*/.git/*" \
   -not -path "*/dist/*" -not -path "*/build/*" | sort | head -50

# Test structure
find . -maxdepth 4 -name "*.test.*" -o -name "*_test.go" -o -name "test_*.py" \
   | grep -v node_modules | head -10

# CI/CD
ls .github/workflows/ .gitlab-ci.yml Makefile 2>/dev/null
```

### Phase 2: Architecture Mapping

From reconnaissance, determine:
- Tech stack (language, framework, database, build tools)
- Architecture pattern (monolith/microservices/serverless)
- Key directory purposes
- Request lifecycle (one request traced end-to-end)

### Phase 3: Convention Detection

From actual code (not config):
- File/class/test naming patterns
- Error handling style
- Async patterns (async/await, goroutines, futures)
- Commit message style (`git log --oneline -10`)

### Phase 4: Generate Artifacts

**Onboarding Guide** → `docs/ONBOARDING.md` (or print inline)
**CLAUDE.md** → `CLAUDE.md` (enhance if exists, don't replace)

Both artifacts must be:
- Scannable in 2 minutes
- Generated from code evidence, not assumptions
- Under 150 lines (guide) / 100 lines (CLAUDE.md)

---

## Onboarding Guide Structure

```markdown
# [Project] — Developer Onboarding

## What This Is
## Tech Stack
## Architecture
## Key Entry Points
## Directory Map
## Request Lifecycle
## Conventions
## Common Tasks
## Where to Look for X
```

## CLAUDE.md Structure

```markdown
# CLAUDE.md
## Project Overview
## Commands (install, dev, test, build, lint)
## Code Style
## Project Structure
## Conventions
```

---

## Usage Examples

- `/onboard` — Full onboarding (guide + CLAUDE.md)
- `/onboard --guide` — Only generate onboarding guide
  
- `/onboard --claude-md` — Only generate/update CLAUDE.md
- `/onboard docs/` — Focus analysis on the docs directory

## Notes

- If CLAUDE.md already exists: **enhance it**, preserve existing content
- Flags unknowns rather than guessing: "Pattern unclear — verify with team"
- Focus on the architecturally significant — don't list every dependency
- Guide must be readable in 2 minutes maximum
