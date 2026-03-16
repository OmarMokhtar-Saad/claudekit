---
name: migrate
description: "Plan and execute database migrations, API version bumps, and framework upgrades"
argument-hint: "<type> [schema|api|framework|data]"
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# Migrate Command

Plan and execute migrations for database schemas, APIs, frameworks, and data transformations.

## Task

Migration: $ARGUMENTS

## Mandatory Skills

You MUST load and apply the following skills before proceeding:

- **using-superpowers** - Core agent capabilities and tool usage
- **golden-rule** - No code changes without explicit approval
- **database-migration-patterns** - Zero-downtime migrations and rollback strategies

## Workflow

### Type: schema
Plan a zero-downtime database schema migration.

1. Read existing schema files and migration history
2. Detect the migration framework (Prisma, Alembic, Flyway, Knex, ActiveRecord, etc.)
3. Analyze the requested change for backward compatibility
4. Apply the **expand-contract pattern** for breaking changes:
   - **Expand**: Add new columns/tables alongside old ones
   - **Migrate**: Backfill data from old to new structures
   - **Contract**: Remove old columns/tables after all consumers updated
5. Generate migration files with both UP and DOWN procedures
6. Validate rollback safety: DOWN must fully reverse UP
7. Estimate migration duration for large tables

### Type: api
Plan a backward-compatible API version bump.

1. Scan existing API routes, controllers, and schemas
2. Identify breaking changes in the proposed update
3. Generate a versioned API structure (URL prefix, header, or content negotiation)
4. Create adapter layers between old and new versions
5. Generate deprecation notices for old endpoints
6. Plan client migration timeline:
   - Dual-run period (both versions live)
   - Deprecation warnings in responses
   - Sunset date and removal
7. Update API documentation and OpenAPI specs

### Type: framework
Plan a framework or library major version upgrade.

1. Identify the framework and current/target versions
2. Read the official migration guide (if available locally)
3. Scan codebase for deprecated API usage patterns
4. Generate a codemod plan for automated transformations
5. Identify manual migration steps that cannot be automated
6. Create a phased upgrade plan:
   - Phase 1: Update dependencies, fix compilation errors
   - Phase 2: Replace deprecated APIs with new equivalents
   - Phase 3: Adopt new features and patterns
   - Phase 4: Remove compatibility shims
7. Estimate effort and risk per phase

### Type: data
Plan a safe data transformation or migration.

1. Identify source and target data formats/locations
2. Analyze data volume and estimate processing time
3. Design the transformation pipeline:
   - Extract from source
   - Validate and transform
   - Load to target
   - Verify integrity
4. Build safety mechanisms:
   - Dry run mode (transform without writing)
   - Checkpointing (resume from last successful batch)
   - Rollback procedure (restore from backup)
5. Generate validation queries to confirm data integrity post-migration

## Output Format

```
## Migration Plan

### Type: [schema|api|framework|data]
### Risk Level: LOW / MEDIUM / HIGH
### Estimated Downtime: [zero / X minutes / requires maintenance window]

### Current State
- [description of current state]

### Target State
- [description of desired end state]

### Migration Steps
1. [step] - Reversible: YES/NO
2. [step] - Reversible: YES/NO
3. [step] - Reversible: YES/NO

### Rollback Plan
1. [rollback step for each migration step]

### Breaking Changes
- [list of breaking changes, or "none"]

### Pre-Migration Checklist
- [ ] Backup created
- [ ] Rollback procedure tested
- [ ] Stakeholders notified
- [ ] Monitoring in place
- [ ] Dry run completed

### Files to Generate
- [migration files, adapters, codemods]

### Next Steps
- Run `/plan` to generate ops.json for execution
- Run `/verify` after migration completes
```

## Usage Examples

- `/migrate schema add-user-roles-table` -- Plan a new table migration
- `/migrate schema rename-column users.name to users.full_name` -- Rename with zero downtime
- `/migrate api v2` -- Plan API v1 to v2 transition
- `/migrate framework react@19` -- Plan React major version upgrade
- `/migrate data csv-to-postgres` -- Plan a data import pipeline

## Notes

- Schema migrations must always include a rollback procedure
- API migrations must maintain backward compatibility during transition
- Framework upgrades should be done incrementally, not all at once
- Data migrations must include integrity verification steps
- Never run destructive migrations without an explicit backup confirmation
