---
name: codebase-mapping
description: "Use when you need to auto-generate a project structure map -- scans directories, identifies patterns, maps dependencies, and creates an annotated project index."
---

# Codebase Mapping

## Purpose

Automatically generate a comprehensive project structure map that documents directory layout, dependency relationships, architectural patterns, and module purposes. Outputs a reusable `.claude/project-index.md` that accelerates onboarding and context loading.

---

## Mapping Process

### Step 1: Scan Directory Structure

1. Walk the project tree, respecting `.gitignore` and common exclusions:
   - `node_modules/`, `venv/`, `.venv/`, `__pycache__/`, `target/`, `build/`, `dist/`
   - `.git/`, `.idea/`, `.vscode/` (IDE directories)
   - Binary files, media assets (log path only)
2. Record every file with: path, extension, size, last modified date
3. Generate a visual tree with depth annotations

**Output format:**

```
project-root/
  src/                    # Application source code
    api/                  # REST API endpoints (12 files)
      routes/             # Express route handlers
      middleware/          # Auth, validation, rate-limiting
    services/             # Business logic layer (8 files)
    models/               # Data models / ORM entities (6 files)
    utils/                # Shared utility functions (4 files)
  tests/                  # Test suites
    unit/                 # Unit tests (mirrors src/ structure)
    integration/          # Integration tests
    e2e/                  # End-to-end tests
  docs/                   # Documentation
  scripts/                # Build, deploy, migration scripts
  config/                 # Environment-specific configuration
```

### Step 2: Identify Patterns

Detect and document:

| Pattern | Detection Method |
|---------|-----------------|
| **Monorepo** | Multiple `package.json` / `go.mod` at different levels |
| **Microservices** | Multiple service directories with independent configs |
| **MVC** | `models/`, `views/`, `controllers/` directories |
| **Clean Architecture** | `domain/`, `usecases/`, `adapters/`, `infrastructure/` |
| **Hexagonal** | `ports/`, `adapters/` directories |
| **Feature-based** | Directories grouped by feature rather than type |
| **Layer-based** | Directories grouped by technical layer |
| **Framework conventions** | Rails (`app/`), Django (`apps/`), Next.js (`pages/`), Spring (`src/main/java/`) |

### Step 3: Map Dependencies

1. Parse dependency manifests:
   - `package.json` / `yarn.lock` / `pnpm-lock.yaml`
   - `requirements.txt` / `pyproject.toml` / `Pipfile`
   - `go.mod` / `go.sum`
   - `Cargo.toml` / `Cargo.lock`
   - `build.gradle` / `pom.xml`
   - `Gemfile` / `Gemfile.lock`
2. Identify internal module dependencies (import/require graph)
3. Flag circular dependencies
4. Classify dependencies: runtime, dev, peer, optional

### Step 4: Generate Visual Tree

Create a dependency graph in text format:

```
Entry Points:
  src/index.ts -> src/app.ts -> src/api/routes/index.ts
                              -> src/services/index.ts
                              -> src/config/index.ts

Dependency Flow:
  routes/ -> middleware/ -> services/ -> models/ -> database
                                      -> utils/

Circular Dependencies: NONE (or list them)
```

### Step 5: Annotate Purpose

For each top-level directory and key files, document:

- **What it does** (one line)
- **Key files** (the 3-5 most important files)
- **Dependencies** (what it imports)
- **Dependents** (what imports it)
- **Test coverage** (if detectable)

### Step 6: Create Project Index

Write the final output to `.claude/project-index.md`:

```markdown
# Project Index

Generated: <timestamp>
Root: <project-root>

## Tech Stack
- Language: TypeScript 5.3
- Framework: Express 4.18
- Database: PostgreSQL 15 via Prisma 5.7
- Testing: Jest 29 + Supertest
- CI: GitHub Actions

## Architecture
Pattern: Layer-based MVC
Entry point: src/index.ts

## Directory Map
<visual tree from Step 1>

## Key Files
<annotated list from Step 5>

## Dependency Graph
<from Step 4>

## Patterns Detected
<from Step 2>

## Notes
- <any anomalies, warnings, or suggestions>
```

---

## Refresh Strategy

- Run on first session with a new project
- Re-run after major refactors or new module additions
- Incremental update: diff current structure against saved index, update only changed sections
- NEVER overwrite user-added notes in the index file

---

## Integration

- The project index is loaded by the **context-priming** skill on session start
- The **coordinator** agent uses it to route tasks to the correct part of the codebase
- The **planner** agent uses it to understand impact scope of planned changes
