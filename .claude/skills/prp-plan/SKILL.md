---
name: PRP Plan
description: Product Requirements Process — plan phase. Deep codebase analysis before writing a single line of implementation. Extracts existing patterns, maps affected files, traces data flow, and produces a context-rich plan that a fresh agent can execute without re-exploration.
trigger: Use when starting a non-trivial feature or bug fix. Run before /prp-implement. The plan produced by this skill is the contract between planning and implementation.
---

# PRP Plan

The first phase of the Product Requirements Process (PRP). Unlike a standard plan that describes *what* to build, a PRP plan documents *how the existing codebase works* so that the implementation phase never needs to re-explore.

## Core Principle

> A fresh agent with this plan should be able to implement the feature correctly without reading a single file beyond what the plan references.

If the plan requires the implementer to "figure out" anything, the plan is incomplete.

---

## When to Use

- Any feature requiring changes to 3+ files
- Any bug fix where the root cause spans multiple modules
- Any change to a public API, auth system, or data model
- Any task where "following existing patterns" is important

**Do NOT use for:** single-file changes, doc updates, config tweaks.

---

## 5-Phase Protocol

### Phase 1: Understand the Goal
```
1. Restate the requirement in your own words (1 sentence)
2. Identify: what does "done" look like? What's the acceptance test?
3. Identify what NOT to change (scope boundaries)
4. Flag any ambiguities — resolve them before Phase 2
```

### Phase 2: Codebase Reconnaissance (parallel reads)

Run these explorations simultaneously:

```bash
# Stack and entry points
find . -maxdepth 3 -name "package.json" -o -name "pyproject.toml" \
   -o -name "go.mod" -o -name "Cargo.toml" | grep -v node_modules | head -5

# Existing similar patterns (the feature you're adding probably exists nearby)
grep -r "<feature-keyword>" src/ --include="*.ts" -l | head -10

# Affected module structure
find src/<affected-module>/ -type f | sort

# Existing tests for the area
find . -name "*.test.*" -path "*<feature-keyword>*" | head -10

# Recent changes to the affected area
git log --oneline -10 -- src/<affected-module>/
```

### Phase 3: Pattern Extraction

For EACH pattern relevant to the feature, document:

```
PATTERN: <name>
File: <path:line>
Example:
  <3-5 lines of actual code showing the pattern>
Apply when: <condition — when should the implementer follow this pattern>
```

Extract patterns for:
- **Module structure** — how are files organized in this directory?
- **Error handling** — how does this codebase handle errors?
- **Testing style** — what does a test look like here (describe/it, class-based, etc.)?
- **Imports** — absolute vs relative, barrel files, aliased paths?
- **Naming** — camelCase, snake_case, PascalCase per context?
- **Async style** — async/await, callbacks, Promises, goroutines?
- **Type definitions** — interfaces, types, where are they defined?

### Phase 4: Affected File Map

List EVERY file that must change, in implementation order:

```
AFFECTED FILES (in order):
1. src/types/user.ts           — ADD: UserRefreshToken interface
2. src/db/schema.ts            — ADD: refresh_tokens table definition
3. src/auth/tokens.ts (NEW)    — CREATE: token generation + validation
4. src/auth/middleware.ts      — MODIFY: validate refresh token in existing flow
5. src/api/routes/auth.ts      — ADD: POST /auth/refresh endpoint
6. tests/auth/tokens.test.ts (NEW) — CREATE: unit tests for token module
7. tests/auth/routes.test.ts   — ADD: integration test for /auth/refresh

Files to NOT touch:
- src/legacy/auth.ts           — intentionally not migrated (see decisions)
- src/api/routes/user.ts       — unrelated, don't drift
```

### Phase 5: Write the PRP Document

Output to `.claude/plans/prp-<feature>.md`:

```markdown
# PRP: <Feature Name>
**Created:** <date>
**Goal:** <one-sentence goal>
**Acceptance:** <how to verify "done">

## Scope
In scope: <what to build>
Out of scope: <explicit boundaries>

## Existing Patterns (implementer must follow these)

### Error Handling
File: src/utils/errors.ts:23
\`\`\`typescript
// Always use Result<T, AppError> not throw
return err(new AppError('AUTH_FAILED', 'Invalid token', 401))
\`\`\`

### [Other patterns...]

## Implementation Steps (in order)

### Step 1: <title>
File: `src/types/user.ts`
Change: ADD interface
\`\`\`typescript
export interface UserRefreshToken {
  id: string
  userId: string
  token: string
  expiresAt: Date
  createdAt: Date
}
\`\`\`
Why: All entity types live in src/types/ — follow existing UserSession pattern.

### Step 2: <title>
[...]

## Test Requirements
- Unit: <what to test at unit level>
- Integration: <what to test at integration level>
- Edge cases that MUST be covered:
  1. Expired token → 401
  2. Token reuse after rotation → 401 + revoke all tokens for user
  3. Concurrent requests with same token → only first succeeds

## Decisions Already Made
- Using RS256 (not HS256) — auth server controls private key
- Refresh tokens in httpOnly cookies (not localStorage) — XSS mitigation
- TTL: 7 days (product confirmed 2026-04-10)

## Files NOT to Touch
- src/legacy/auth.ts — intentional, not in scope

## Verification Commands
\`\`\`bash
npm test -- --testPathPattern=auth
tsc --noEmit
\`\`\`
```

---

## Quality Gate

A PRP plan PASSES quality gate if:
- [ ] Every affected file is listed with the specific change type
- [ ] Every relevant existing pattern is documented with a file:line example
- [ ] Implementation steps are in dependency order (no forward references)
- [ ] Test requirements specify edge cases explicitly
- [ ] Decisions section explains WHY, not just what
- [ ] Verification commands are runnable (not hypothetical)

A plan that fails any of these is sent back for revision before `/prp-implement` runs.

---

## Anti-Patterns

- NEVER write "follow existing patterns" without showing the actual pattern
- NEVER write "add tests" without specifying which edge cases
- NEVER leave ambiguities for the implementer to resolve
- NEVER list files without specifying the exact change type
- NEVER include files that don't need to change (scope creep)
