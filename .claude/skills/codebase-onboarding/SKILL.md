---
name: codebase-onboarding
description: "Use when first entering an unfamiliar project — generates structured onboarding guide and a starter CLAUDE.md from code analysis"
disable-model-invocation: true
allowed-tools: Read, Glob, Grep, Bash
---

# Codebase Onboarding

## Purpose

Analyze an unfamiliar codebase in 4 phases and produce two artifacts:
1. **Onboarding Guide** — scannable in 2 minutes
2. **Starter CLAUDE.md** — project-specific Claude Code configuration

**Trigger when:** First time in a project, "help me understand this codebase", "generate CLAUDE.md", "onboard me to this repo"

---

## Phase 1: Reconnaissance (Run All in Parallel)

```bash
# Detect package manager / language manifests
ls package.json go.mod Cargo.toml pyproject.toml pom.xml build.gradle Gemfile mix.exs 2>/dev/null

# Framework fingerprinting
ls next.config* nuxt.config* angular.json remix.config* astro.config* \
   django/ flask/ fastapi/ config/application.rb 2>/dev/null

# Entry point candidates
find . -maxdepth 3 -name "main.*" -o -name "index.*" -o -name "app.*" \
   -o -name "server.*" | grep -v node_modules | grep -v ".git" | head -20

# Top-level structure (2 levels, skip junk)
find . -maxdepth 2 -not -path "*/node_modules/*" -not -path "*/.git/*" \
   -not -path "*/vendor/*" -not -path "*/dist/*" -not -path "*/.cache/*" \
   -not -path "*/build/*" | sort | head -60

# Tooling detection
ls .eslintrc* .prettierrc* tsconfig.json Makefile Dockerfile \
   docker-compose* .github/ .gitlab-ci.yml .env.example 2>/dev/null

# Test structure
find . -maxdepth 4 -name "*.test.*" -o -name "*.spec.*" -o -name "*_test.go" \
   | grep -v node_modules | head -15
find . -maxdepth 3 -name "pytest.ini" -o -name "jest.config*" -o -name "vitest.config*" \
   | grep -v node_modules | head -5
```

---

## Phase 2: Architecture Mapping

From reconnaissance data, determine:

### Tech Stack
- **Language + version:** (from manifest)
- **Framework + key libraries:** (from deps)
- **Database / ORM:** (look for prisma, sqlalchemy, gorm, hibernate patterns)
- **Build tools:** (webpack, vite, cargo, gradle, make)
- **CI/CD:** (.github/workflows, .gitlab-ci.yml, Jenkinsfile)

### Architecture Pattern
- **Monolith / Monorepo / Microservices / Serverless?**
- **Frontend / Backend split?** (same repo or separate?)
- **API style?** (REST, GraphQL, gRPC — look for resolver, handler, route files)

### Directory Map
For each top-level directory, describe its purpose in one line.

### Request Lifecycle (trace one request)
```
[Entry] → [Validation] → [Business Logic] → [Data Layer] → [Response]
    e.g.: router/index.ts → middleware/auth.ts → services/user.ts → models/user.ts → HTTP 200
```

---

## Phase 3: Convention Detection

Identify from actual code (not config):

| Convention | Pattern Found |
|-----------|--------------|
| File naming | `camelCase.ts` / `kebab-case.py` / `snake_case.go` |
| Component naming | `PascalCase` / `snake_case` |
| Test file naming | `*.test.ts` / `*_test.go` / `test_*.py` |
| Error handling | `try/catch` / `Result<T>` / `Either` |
| Async pattern | `async/await` / `goroutines` / `Futures` |
| DI approach | Constructor injection / decorators / manual |
| State management | Redux / Zustand / Context / Vuex |
| Commit style | Conventional commits / freeform |

```bash
# Check commit style
git log --oneline -10 2>/dev/null

# Check branch naming
git branch -a 2>/dev/null | head -10

# Check PR/issue templates
ls .github/PULL_REQUEST_TEMPLATE* .github/ISSUE_TEMPLATE/ 2>/dev/null
```

---

## Phase 4: Generate Artifacts

### Artifact 1: Onboarding Guide

```markdown
# [Project Name] — Developer Onboarding

## What This Is
[1 sentence description from README or package.json description]

## Tech Stack
| Layer | Technology |
|-------|-----------|
| Language | [detected] |
| Framework | [detected] |
| Database | [detected] |
| Testing | [detected] |
| CI/CD | [detected] |

## Architecture
[2-3 sentences describing the overall shape]

```
[ASCII diagram of main layers]
```

## Key Entry Points
| Purpose | File |
|---------|------|
| App start | [path] |
| API routes | [path] |
| Database config | [path] |
| Environment vars | [path] |

## Directory Map
```
[top-level tree with one-line descriptions]
```

## Request Lifecycle
`[entry] → [middleware] → [handler] → [service] → [db] → [response]`

## Conventions
- **File naming:** [pattern]
- **Error handling:** [pattern]
- **Testing:** [run command]
- **Commits:** [style]

## Common Tasks
| Task | Command |
|------|---------|
| Install | [command] |
| Dev server | [command] |
| Run tests | [command] |
| Build | [command] |
| Lint | [command] |

## Where to Look for X
| If you need to... | Look in... |
|-------------------|-----------|
| Add an API endpoint | [path] |
| Add a UI component | [path] |
| Change DB schema | [path] |
| Add a config value | [path] |
| Add a test | [path] |
```

### Artifact 2: Starter CLAUDE.md

```markdown
# CLAUDE.md

## Project Overview
[1 sentence]

## Tech Stack
[bullet list]

## Commands
- **Install:** `[cmd]`
- **Dev:** `[cmd]`
- **Test:** `[cmd]`
- **Build:** `[cmd]`
- **Lint:** `[cmd]`

## Code Style
[2-4 key conventions from Phase 3]

## Project Structure
[key directories, 5-10 entries max]

## Conventions
[3-5 most important project-specific rules]
```

**If CLAUDE.md already exists:** Enhance it — preserve all existing content, add missing sections, flag what's new with a comment.

---

## Quality Rules

- Use Glob/Grep for reconnaissance — don't read every file
- Verify signals from actual code, not just config files
- Keep onboarding guide scannable in 2 minutes (max 150 lines)
- Keep CLAUDE.md under 100 lines
- Flag unknowns rather than guessing: "Pattern unclear — check with team"
- Do NOT list every dependency — only the architecturally significant ones
- Do NOT describe obvious directories like `src/` or `tests/`

---

## Anti-Patterns

| Anti-Pattern | Why Wrong |
|-------------|----------|
| CLAUDE.md over 100 lines | Defeats the purpose — nobody reads it |
| Listing all 47 npm packages | Not actionable — use package.json for that |
| Guessing architecture without evidence | Creates false mental models |
| Copying the README | Redundant — link to it instead |
| Describing `utils/` as "utilities" | Too obvious — what KIND of utilities? |
