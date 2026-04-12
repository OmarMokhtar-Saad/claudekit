---
name: context-priming
description: "Use when starting a new session or switching tasks -- loads CLAUDE.md, project structure, key configs, tech stack, and active conventions to prime Claude with comprehensive project context."
---

# Context Priming

## Purpose

Prime Claude Code with comprehensive project context at the start of a session or when switching to a new task area. Reduces the need for repeated exploration and ensures consistent, project-aware responses from the first interaction.

---

## Priming Sequence

Execute these steps in order on session start or when `/prime` is invoked.

### Step 1: Load Project Identity

Read these files (if they exist):
1. `CLAUDE.md` -- primary project instructions and conventions
2. `CONSTITUTION.md` -- behavioral rules and constraints
3. `.claude/session-state.json` -- previous session context (via session-continuity skill)
4. `.claude/project-index.md` -- project structure map (via codebase-mapping skill)

### Step 2: Scan Project Structure

If no project index exists, perform a lightweight scan:
1. List top-level directory contents
2. Identify the primary language from file extensions
3. Read the main entry point file (first 50 lines)
4. Read the primary config file (`package.json`, `pyproject.toml`, `Cargo.toml`, etc.)

### Step 3: Read Key Config Files

Parse and internalize:
| File | Purpose |
|------|---------|
| `package.json` / `pyproject.toml` / `Cargo.toml` | Dependencies, scripts, project metadata |
| `tsconfig.json` / `setup.cfg` / `rustfmt.toml` | Language/compiler configuration |
| `.eslintrc` / `.prettierrc` / `ruff.toml` | Linting and formatting rules |
| `Dockerfile` / `docker-compose.yml` | Container configuration |
| `.github/workflows/*.yml` | CI/CD pipeline definition |
| `.env.example` | Environment variable structure (NEVER read `.env`) |

### Step 4: Identify Tech Stack

Build a tech stack profile:
```
Language:    TypeScript 5.3
Runtime:     Node.js 20
Framework:   Express 4.18
Database:    PostgreSQL 15 (via Prisma 5.7)
Testing:     Jest 29 + Supertest 6
Linting:     ESLint 8 + Prettier 3
CI:          GitHub Actions
Deployment:  Docker + AWS ECS
```

### Step 5: Load Active Conventions

Extract coding conventions from:
1. `CLAUDE.md` explicit rules
2. Linter/formatter configuration
3. Existing code patterns (naming, structure, error handling)
4. Test patterns (framework, assertion style, file organization)
5. Git conventions (commit message format from recent history)

---

## Priming Template

After loading, internalize this context summary:

```
=== Project Context ===

Project: <name> (<language>)
Stack: <framework> + <database> + <testing>
Architecture: <pattern detected>

Conventions:
- Naming: <camelCase/snake_case/PascalCase>
- File structure: <by feature/by type/by layer>
- Error handling: <pattern observed>
- Testing: <framework, assertion style, coverage expectations>
- Git: <commit format, branch naming>

Active Task: <from session state, or "none">
Key Files: <list of files central to current work>
Gotchas: <from session state warnings>

Constraints:
- <from CLAUDE.md and CONSTITUTION.md>
=== End Context ===
```

---

## Selective Priming

For large projects, prime only the relevant context:

### By Task Type

| Task Type | Prime These |
|-----------|------------|
| Feature development | Target module + its tests + related services |
| Bug fix | Error location + related code paths + test files |
| Refactoring | Target module + all dependents + all dependencies |
| Documentation | Module being documented + existing docs + API surface |
| Testing | Target module + existing tests + test utilities |
| DevOps | CI configs + Dockerfile + deploy scripts + infrastructure |

### By Scope

| Scope | Depth |
|-------|-------|
| Single file | File + direct imports + corresponding test |
| Module | All files in module + shared dependencies + module tests |
| Cross-cutting | All affected modules + shared infrastructure + integration tests |
| Full project | Complete priming sequence |

---

## Refresh Triggers

Re-prime when:
- User switches to a different area of the codebase
- 30+ minutes have passed since last priming
- User reports Claude is "forgetting" project conventions
- After a `git pull` or `git merge` that changes project structure
- User explicitly invokes `/prime`

---

## Performance

- Full priming should complete in under 10 seconds
- Selective priming should complete in under 3 seconds
- Cache parsed config data in memory for the duration of the session
- NEVER re-read files that haven't changed since last read

---

## Integration

- Invoked automatically by **coordinator** at session start
- Uses **codebase-mapping** output if available
- Uses **session-continuity** state if available
- Feeds context to all downstream agents
