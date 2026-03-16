---
name: database-migration-patterns
description: "Use when planning or reviewing database schema changes - zero-downtime migrations and rollback safety"
user-invocable: false
---

# Database Migration Patterns

## Core Principle

**Every migration must be reversible and deployable without downtime.** A migration that requires taking the application offline is a migration that was not planned correctly.

---

## The Expand-Contract Pattern

The fundamental pattern for zero-downtime schema changes:

```
Phase 1: EXPAND    - Add new structure alongside old
Phase 2: MIGRATE   - Backfill data, update application code
Phase 3: CONTRACT  - Remove old structure once fully migrated
```

### Example: Renaming a Column

```
Step 1: Add new column (old column still active)
Step 2: Deploy code that writes to BOTH columns
Step 3: Backfill new column from old column data
Step 4: Deploy code that reads from new column only
Step 5: Deploy code that writes to new column only
Step 6: Drop old column (separate migration, separate deploy)
```

**NEVER** rename a column directly in production. The application will fail between the migration running and the new code deploying.

---

## Zero-Downtime Migration Rules

### Safe Operations (No Lock, No Downtime)

| Operation | Safety |
|---|---|
| Add nullable column | Safe |
| Add column with default (modern DBs) | Safe (Postgres 11+, MySQL 8.0+) |
| Add index concurrently | Safe (use CONCURRENTLY in Postgres) |
| Add new table | Safe |
| Add new enum value | Safe |

### Dangerous Operations (Require Expand-Contract)

| Operation | Risk | Mitigation |
|---|---|---|
| Rename column | App reads fail | Use expand-contract |
| Change column type | Data conversion lock | Add new column, migrate, drop old |
| Add NOT NULL constraint | Existing nulls fail | Backfill first, then add constraint |
| Drop column | App writes fail | Remove code references first |
| Drop table | Data loss | Ensure no references, backup first |
| Add index on large table | Table lock | Use concurrent/online index creation |

---

## Rollback Strategies

### Every Migration Needs a Rollback Plan

```
Forward Migration:
  ALTER TABLE users ADD COLUMN display_name VARCHAR(255);

Rollback Migration:
  ALTER TABLE users DROP COLUMN display_name;
```

### Rollback Decision Matrix

| Situation | Action |
|---|---|
| Migration failed mid-execution | Run rollback migration immediately |
| Migration succeeded but app fails | Assess data impact, then rollback if safe |
| Data backfill is incomplete | Pause backfill, app uses old column |
| New column has data, need to revert | Backup new column data, then drop |

### Rules

- Write rollback migrations at the same time as forward migrations
- Test rollback migrations in staging before production
- NEVER deploy a migration without a tested rollback
- Keep migrations small -- one logical change per migration file
- Rollbacks MUST NOT lose user data created after the forward migration

---

## Data Transformation Safety

### Large Table Backfills

- Process in batches (1000-10000 rows at a time)
- Add rate limiting between batches to avoid overwhelming the database
- Use background jobs, not migration scripts, for large backfills
- Monitor database load during backfill
- Make backfills idempotent (safe to re-run)

### Data Validation

```
Before migration:
  1. Count rows that will be affected
  2. Sample and verify transformation logic
  3. Check for edge cases (nulls, empty strings, invalid data)

After migration:
  1. Verify row counts match expectations
  2. Sample and verify transformed data
  3. Run application-level validation
  4. Monitor error rates for 24 hours
```

---

## Migration Ordering

### Dependencies Between Migrations

- Migrations MUST be ordered by dependency (table before foreign key)
- NEVER create circular dependencies between migrations
- If two migrations are independent, they can run in any order
- Number migrations sequentially or use timestamps

### Multi-Service Migrations

When multiple services share a database:

1. Expand: Add new schema (backward compatible)
2. Deploy all services to use new schema
3. Contract: Remove old schema
4. NEVER contract before all services are updated

---

## Anti-Patterns

| Anti-Pattern | Why It Is Bad | Alternative |
|---|---|---|
| Direct column rename | Breaks running application code | Expand-contract pattern |
| Large migration in one transaction | Locks table, causes downtime | Break into smaller migrations |
| No rollback plan | Stuck if something goes wrong | Always write rollback with forward |
| Backfill in migration file | Blocks deployment pipeline | Use background job for large backfills |
| Skipping staging test | Discover problems in production | Always test migrations in staging first |
| NOT NULL without default | Breaks existing inserts | Add nullable first, backfill, then constrain |

---

## Migration Checklist

- [ ] Migration has a corresponding rollback migration
- [ ] Schema change is backward compatible with current application code
- [ ] Large data changes use batched background processing
- [ ] Index creation uses concurrent/online mode
- [ ] Migration tested in staging with production-like data volume
- [ ] Monitoring is in place for error rates post-deploy
- [ ] No direct renames or type changes on active columns
