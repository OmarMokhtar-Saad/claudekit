---
name: performance
description: "Profile, analyze, and optimize application performance"
argument-hint: "<target> [--profile|--bundle|--queries|--memory]"
disable-model-invocation: true
context: fork
agent: explore
allowed-tools: Read, Bash, Grep, Glob
---

# Performance Command

Profile, analyze, and identify optimization opportunities in the target code.

## Task

Performance analysis: $ARGUMENTS

## Mandatory Skills

You MUST load and apply the following skills before proceeding:

- **using-superpowers** - Core agent capabilities and tool usage
- **golden-rule** - No code changes without explicit approval
- **performance-guidelines** - Response times and resource management

## READ-ONLY WARNING

This agent operates in READ-ONLY mode. You may read files, run profiling commands, and execute benchmarks, but you MUST NOT modify source files. Performance fixes are the responsibility of the planner and implementer agents.

## Workflow

### Phase 1: Target Identification
- Parse $ARGUMENTS to identify the analysis target and mode
- Detect the project language, framework, and build system
- Identify available profiling tools in the environment
- Establish baseline metrics if measurable

### Phase 2: Bundle Size Analysis (--bundle)
- Detect bundler (webpack, vite, esbuild, rollup, parcel)
- Run bundle analysis: `npx webpack-bundle-analyzer` or equivalent
- Identify the largest modules and dependencies
- Flag tree-shaking failures (unused exports still in bundle)
- Report code splitting opportunities
- Compare against size budgets if configured

### Phase 3: Database Query Optimization (--queries)
- Scan for ORM usage patterns (Prisma, TypeORM, SQLAlchemy, ActiveRecord, etc.)
- Detect N+1 query patterns: loops containing database calls
- Identify missing eager loading / joins
- Flag queries without index hints on large tables
- Detect unbounded queries (missing LIMIT/pagination)
- Check for sequential queries that could be batched

### Phase 4: Memory Leak Detection (--memory)
- Identify common leak patterns:
  - Event listeners never removed
  - Closures capturing large objects
  - Growing caches without eviction
  - Circular references preventing GC
  - Global state accumulation
- Check for resource cleanup (file handles, connections, streams)
- Flag long-lived references to short-lived objects

### Phase 5: Hot Path Identification (--profile)
- Identify CPU-intensive code paths via static analysis
- Flag nested loops with high complexity (O(n^2) or worse)
- Detect synchronous blocking operations in async contexts
- Identify repeated computation that could be memoized
- Check for unnecessary serialization/deserialization cycles
- Flag expensive operations inside render loops or request handlers

## Output Format

```
## Performance Analysis Report

### Target: [file, module, or feature]
### Mode: profile | bundle | queries | memory | full

### Bundle Analysis (if applicable)
- Total bundle size: X KB (gzipped: Y KB)
- Largest modules:
  1. [module]: X KB (Y% of total)
  2. [module]: X KB (Y% of total)
- Tree-shaking issues: N
- Code splitting opportunities: [list]

### Query Analysis (if applicable)
- N+1 patterns found: N
  1. [file:line] - [description]
- Missing indexes: N
- Unbounded queries: N
- Optimization suggestions: [list]

### Memory Analysis (if applicable)
- Potential leaks found: N
  1. [file:line] - [pattern] - [severity]
- Unclosed resources: N
- Growing caches: N

### Hot Paths (if applicable)
- High complexity paths: N
  1. [file:line] - O(n^X) - [description]
- Blocking operations: N
- Memoization candidates: N

### Priority Recommendations
1. [HIGH] [description] - Expected impact: [estimate]
2. [MEDIUM] [description] - Expected impact: [estimate]
3. [LOW] [description] - Expected impact: [estimate]

### Next Steps
- Run `/plan [optimization]` to create an implementation plan
```

## Usage Examples

- `/performance src/api/` -- Full performance analysis of the API layer
- `/performance src/api/ --queries` -- Database query optimization only
- `/performance src/components/ --bundle` -- Bundle size analysis only
- `/performance src/workers/ --memory` -- Memory leak detection only
- `/performance src/services/payment.ts --profile` -- Hot path profiling

## Notes

- If no flag is provided, run all applicable analyses
- Bundle analysis only applies to frontend/bundled projects
- Query analysis requires an ORM or database client to be detected
- This is a read-only analysis; use `/plan` to act on recommendations
- For runtime profiling, suggest appropriate tools rather than running long benchmarks
