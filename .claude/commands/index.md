---
description: "Generate a comprehensive project index mapping structure, components, and dependencies"
argument-hint: "[scope]"
---

# Index Command

Generate a comprehensive project index that maps the codebase structure, identifies key files, lists components, and traces dependencies.

## Usage

```
/index              -- Index the entire project
/index src/auth     -- Index a specific directory
```

## Task

Generate a project index for: $ARGUMENTS

If no argument is provided, index the entire project.

## Workflow

### Phase 1: Directory Structure

Map the full directory tree, noting:

- Top-level organization pattern (monorepo, single-app, library, etc.)
- Key directories and their purpose
- Configuration files and their roles
- Ignore patterns from `.gitignore`

### Phase 2: Key File Identification

Identify and categorize:

- **Entry points:** Main files, index files, CLI entry points
- **Configuration:** Build configs, environment files, CI/CD definitions
- **Core modules:** The files that contain the primary business logic
- **Data layer:** Models, schemas, migrations, repositories
- **API surface:** Routes, controllers, handlers, GraphQL resolvers
- **Tests:** Test files and their coverage targets
- **Documentation:** READMEs, docs, API specs

### Phase 3: Component Inventory

List every distinct component or module with:

- Name
- Location (directory path)
- Responsibility (one-line description)
- Public interface (key exports or endpoints)
- Test coverage status (has tests / no tests)

### Phase 4: Dependency Mapping

Trace and record:

- **Internal dependencies:** Which modules import from which other modules
- **External dependencies:** Third-party packages and their versions
- **Circular dependencies:** Flag any circular import chains
- **Dependency direction:** Verify dependencies flow in the expected direction (e.g., controllers depend on services, not the reverse)

## Output Format

Save the index to `.claude/project-index.md` with the following structure:

```markdown
# Project Index

Generated: [timestamp]
Scope: [full project or specified path]

## Overview

- **Project type:** [monorepo / single-app / library / CLI / etc.]
- **Primary language:** [language]
- **Framework:** [framework, if any]
- **Package manager:** [npm / pip / cargo / etc.]

## Directory Structure

[tree-style representation with annotations]

## Key Files

| File | Role | Description |
|------|------|-------------|
| ... | ... | ... |

## Components

| Component | Location | Responsibility | Has Tests |
|-----------|----------|----------------|-----------|
| ... | ... | ... | Yes/No |

## Internal Dependencies

[dependency graph or table showing module relationships]

## External Dependencies

| Package | Version | Used By | Purpose |
|---------|---------|---------|---------|
| ... | ... | ... | ... |

## Observations

- [notable patterns]
- [potential issues]
- [architectural notes]
```

## Notes

- This command is read-only -- it does not modify any project files except writing the index output
- For large projects, the index focuses on the most important files rather than listing every file
- Re-run `/index` after major structural changes to keep the index current
- The generated index can be referenced by other commands and agents for context
