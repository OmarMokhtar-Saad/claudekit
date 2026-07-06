---
description: "PRP Phase 1 — Deep codebase analysis then produce a context-rich implementation plan a fresh agent can execute without re-exploration"
argument-hint: "<feature-description>"
model: sonnet
---

# PRP Plan Command

Phase 1 of the Product Requirements Process. Explores the codebase deeply before writing the plan — extracts existing patterns, maps affected files, traces data flow. The output plan is a complete contract for `/prp-implement`.

## Mandatory Skills

- **using-superpowers** - Core capabilities
- **prp-plan** - 5-phase codebase-first planning protocol
- **context-first-workflow** - Explore before modifying
- **search-first** - Check what already exists

## Task

Create PRP plan for: $ARGUMENTS

---

## Execution Steps

### Phase 1: Goal Clarification

Restate the requirement clearly:
- What does "done" look like? What's the acceptance test?
- What is explicitly OUT of scope?
- Any ambiguities that need resolution before planning?

### Phase 2: Codebase Reconnaissance (run in parallel)

```bash
# Find the tech stack
find . -maxdepth 2 \( -name "package.json" -o -name "pyproject.toml" \
  -o -name "go.mod" -o -name "Cargo.toml" \) \
  -not -path "*/node_modules/*" | head -5

# Find similar existing features
KEYWORD=$(echo "$ARGUMENTS" | awk '{print $NF}')
grep -r "$KEYWORD" src/ --include="*.ts" --include="*.py" --include="*.go" -l 2>/dev/null | head -10

# Map the affected module
ls -la src/ 2>/dev/null || ls -la app/ 2>/dev/null || ls -la lib/ 2>/dev/null

# Find existing tests
find . -name "*.test.*" -o -name "*_test.go" -o -name "test_*.py" | grep -v node_modules | head -15

# Recent git history for context
git log --oneline -10
```

### Phase 3: Deep Pattern Extraction

Read 3–5 files most similar to what you're building. Document:
- Error handling style (with file:line example)
- Module/file structure (with directory listing)
- Test structure (with example test block)
- Naming conventions (variables, functions, files)
- Import patterns (relative vs absolute, barrel files)
- Async patterns (if applicable)

### Phase 4: Map Every Affected File

List files in implementation order. For each:
- Path (NEW or existing)
- Change type: CREATE / ADD / MODIFY / RENAME / DELETE
- Specific change description (not vague)

### Phase 5: Write PRP Document

Save to `.claude/plans/prp-<slug>.md`

Apply prp-plan quality gate — reject and revise if any section is missing.

```bash
# Verify plan was created
ls -la .claude/plans/prp-*.md | tail -1

# Count implementation steps
grep -c "^### Step" .claude/plans/prp-*.md | tail -1
```

### Step 6: Confirm

```
PRP PLAN CREATED
================
File: .claude/plans/prp-<slug>.md
Feature: <feature name>
Affected files: <N>
Implementation steps: <N>
Test requirements: <N edge cases>

Quality gate: PASS ✓

To implement: /prp-implement .claude/plans/prp-<slug>.md
```

---

## Usage Examples

- `/prp-plan "Add JWT refresh token rotation"` — full PRP plan
- `/prp-plan "Fix the race condition in the order processor"` — bug PRP plan
- `/prp-plan "Add rate limiting to the public API"` — feature PRP plan

## Notes

- Unlike `/plan`, PRP includes deep pattern extraction from actual code
- The plan is the contract — implement ONLY follows what the plan specifies
- Plan must pass quality gate before `/prp-implement` can run
- Decisions section prevents re-debating resolved questions next session
