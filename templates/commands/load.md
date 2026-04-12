---
name: load
description: Load and summarize project context components
usage: /load [component] [--depth=N] [--format=fmt]
args:
  component:
    description: "Component to load: all, src, tests, docs, skills, agents, config"
    required: false
    default: all
---

# /load - Context Loader Command

Load project components into context and provide a structured summary. This helps the agent understand the project layout, key files, and available resources before starting work.

## Components

### `all` (default)

Load a summary of every component below. Provides a high-level project overview.

**Algorithm:**
1. Read `package.json`, `pyproject.toml`, `Cargo.toml`, or equivalent for project metadata.
2. List top-level directory structure.
3. Identify the primary language and framework.
4. Summarize each component below at depth=1.
5. Output a unified project overview.

### `src`

Load source code structure and key entry points.

**Algorithm:**
1. Identify the source root (`src/`, `lib/`, `app/`, or project root).
2. Map the directory tree (respecting `.gitignore` and `.agentignore`).
3. Identify entry points: `main.*`, `index.*`, `app.*`, `server.*`.
4. List modules/packages with file counts and line counts.
5. Identify key patterns: routers, controllers, models, services, utilities.
6. At depth >= 3: read and summarize each entry point file.
7. At depth >= 4: map import graphs and dependency chains.

### `tests`

Load test structure, coverage data, and test configuration.

**Algorithm:**
1. Identify the test root (`tests/`, `test/`, `__tests__/`, `spec/`).
2. List test files grouped by type: unit, integration, e2e.
3. Read test configuration (`jest.config.*`, `pytest.ini`, `vitest.config.*`, etc.).
4. If coverage reports exist, summarize coverage percentages.
5. At depth >= 3: list test names and describe coverage gaps.

### `docs`

Load documentation files and structure.

**Algorithm:**
1. Find documentation: `docs/`, `doc/`, `README*`, `CONTRIBUTING*`, `CHANGELOG*`.
2. List documentation files with titles and sizes.
3. Read and summarize the main README.
4. At depth >= 3: summarize each doc file in one sentence.

### `skills`

Load available Claude Code skills from `.claude/skills/`.

**Algorithm:**
1. Scan `.claude/skills/` for `SKILL.md` files.
2. For each skill, extract: name, description, trigger patterns.
3. List skills in a summary table.
4. At depth >= 3: include full skill descriptions.

### `agents`

Load agent configurations from `.claude/agents/`.

**Algorithm:**
1. Scan `.claude/agents/` for agent definition files.
2. For each agent, extract: name, role, capabilities, constraints.
3. List agents in a summary table.
4. At depth >= 3: include full agent specifications.

### `config`

Load project configuration and tool settings.

**Algorithm:**
1. Read Claude configuration: `.claude/settings.json`, `.claude/hooks/config.json`.
2. Read project config: `package.json`, `tsconfig.json`, `pyproject.toml`, etc.
3. Read linter/formatter config: `.eslintrc*`, `.prettierrc*`, `ruff.toml`, etc.
4. Read CI/CD config: `.github/workflows/`, `.gitlab-ci.yml`, etc.
5. Summarize key settings: build commands, test commands, lint rules, deploy targets.

## Output Format

For each loaded component, output a structured summary:

```
## [Component Name]

**Root:** <path>
**Files:** <count> | **Lines:** <count>

### Key Files
- <file>: <one-line description>
- <file>: <one-line description>

### Structure
<tree or list>

### Notes
- <relevant observation>
```

When `--format=json` is used, output conforms to the universal JSON schema defined in the command-flags skill, with each component as a separate item in the `result.items` array.

## Behavior

1. Parse the requested component (default: `all`).
2. Apply `--depth` to control how deep into each component to read (default: 2).
3. Respect `.agentignore` and `.gitignore` when listing files.
4. Skip components that do not exist (e.g., no `tests/` directory) with a note.
5. For `all`, provide a brief summary of each component; use per-component commands for details.
6. Format output according to `--format` flag.
