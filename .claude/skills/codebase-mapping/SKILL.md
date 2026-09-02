---
name: codebase-mapping
description: "Use when you need machine-readable structure for a project -- scans directories, maps dependencies with confidence tiers, and emits .claude/project-index.md plus the .claude/project-graph.json sidecar that explore, planner and refactor-cleaner query instead of re-grepping."
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
5. Tag every internal edge with a confidence tier: `extracted` (explicit
   import/include statement observed in source), `inferred` (deduced from naming
   conventions, DI wiring, or framework configuration), `ambiguous` (dynamic
   dispatch, reflection, string-built target). Never report an inferred edge as
   extracted.

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

Hubs (god-node candidates, from `project-graph.py hubs`):
  src/services/OrderService.ts   fan_in=18 fan_out=9  total=27  GOD-NODE
  src/utils/helpers.ts           fan_in=14 fan_out=2  total=16
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

## Hubs
<table from `project-graph.py hubs --top 10` (Step 7)>

## Notes
- <any anomalies, warnings, or suggestions>
```

### Step 7: Emit Graph Sidecar

Persist the dependency graph in machine-readable form so other agents can query
it without re-reading the codebase. Write the nodes/edges collected in Steps 3-4
as JSON (do NOT fill `hash`/`loc` — the script computes them):

```json
{
  "version": 1,
  "nodes": [
    {"id": "src/services/order.ts", "kind": "file"},
    {"id": "express", "kind": "external"}
  ],
  "edges": [
    {"from": "src/services/order.ts", "to": "express",
     "type": "import", "confidence": "extracted"}
  ]
}
```

Node `id` is a repo-relative POSIX path (optionally `path#Symbol`); third-party
targets get `kind: external` stubs. Then:

1. `python3 .claude/operations/scripts/project-graph.py build --check --input <file>` — fix any exit-2 validation errors (each names the offending record)
2. `python3 .claude/operations/scripts/project-graph.py build --input <file> --force` — writes `.claude/project-graph.json` with hashes and line counts
3. `python3 .claude/operations/scripts/project-graph.py hubs --top 10` — paste the table into `project-index.md` under the `## Hubs` heading

---

## Refresh Strategy

- Run on first session with a new project
- Re-run after major refactors or new module additions
- Incremental update: diff current structure against saved index, update only changed sections
- Staleness check: `python3 .claude/operations/scripts/project-graph.py stale` —
  exit 0: graph is fresh, skip; exit 1: re-read only the listed files, re-emit
  their nodes/edges, then `build --merge --input <file>`; exit 3: no graph yet,
  do a full Step 1-7 run
- NEVER overwrite user-added notes in the index file

---

## Integration

- The project index is loaded by the **context-keeper** skill when priming a session
- The **coordinator** agent uses it to route tasks to the correct part of the codebase
- The **planner** agent uses it to understand impact scope of planned changes
- The **explore**, **refactor-cleaner** and **planner** agents query the graph
  sidecar (`project-graph.py query/hubs/path`) instead of re-grepping; script
  exit 3 means no graph/no match — fall back to normal search

---

## Trusting, Viewing and Comparing a Graph

A graph is agent-asserted, so treat it as a claim until it is checked.

- **`verify`** gates the claims against disk: nodes must exist, edge endpoints must
  be declared, and an `extracted` edge must leave a textual trace in its own source
  file. Exit 1 lists the violations. Run it before acting on a graph you did not
  just build. The support test is a substring falsifier — it catches invented
  edges, it does not prove real ones, and aliased imports or generated sources can
  false-positive; `--strict` extends the same check to `inferred` edges.
- **`render`** draws the *verified* graph: `--format mermaid` for a diagram to paste
  into a doc, `--format html --out graph.html` for a self-contained interactive page
  (no CDN, no network). Bound large graphs with `--focus <node> --depth 2`. It
  refuses to render a graph that fails `verify` unless you pass `--allow-unverified`.
  The HTML file needs no server and no network, so it travels as one artifact —
  but it embeds every node id, which is the project's internal path layout.
  Self-contained is not the same as safe to publish: check what the ids reveal
  before sharing one outside the team, and bound it with `--focus` if they say
  more than the audience needs.
- **`diff --against <other.json>`** reports the structural delta — added/removed nodes
  and edges — so a review can see the shape of a change instead of its text.
  Exit 1 means "differences found", which is information, not an error.
- **`impact --ops <plan.ops.json>`** reads a plan's operations config and reports the
  blast radius of the files it touches. Exit 1 means a touched node is a hub/god-node,
  the touched set crosses a package boundary, or a path is absent from the graph —
  all of which mean the change earns a reviewer.
