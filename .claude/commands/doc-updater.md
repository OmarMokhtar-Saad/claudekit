---
description: "Update existing documentation after code changes — READMEs, docstrings, JSDoc, API references. Distinct from /docs which creates new documentation."
argument-hint: "[<path>|--all] [--api|--readme|--docstrings]"
model: haiku
---

# Doc Updater Command

Invokes the `doc-updater` agent to sync existing documentation with recent code changes. Targets READMEs, inline docstrings, JSDoc, and API reference files. Does NOT create new documentation from scratch — use `/docs` for that.

## Mandatory Skills

- **using-superpowers** - Core capabilities
- **documentation-standards** - Formatting, structure, accuracy rules

## Task

Update documentation: $ARGUMENTS

---

## Execution Steps

### Step 1: Parse Target

```bash
ARGS="$ARGUMENTS"
TARGET="."
SCOPE="all"

echo "$ARGS" | grep -q '\-\-api'        && SCOPE="api"
echo "$ARGS" | grep -q '\-\-readme'     && SCOPE="readme"
echo "$ARGS" | grep -q '\-\-docstrings' && SCOPE="docstrings"

TARGET=$(echo "$ARGS" | sed 's/--[a-z]*//g' | xargs)
[ -z "$TARGET" ] && TARGET="."
echo "Target: $TARGET | Scope: $SCOPE"
```

### Step 2: Detect Recent Changes

```bash
# Find files changed in the last commit (or staged changes)
git diff HEAD~1 --name-only 2>/dev/null | head -20
git diff --cached --name-only 2>/dev/null | head -10
```

### Step 3: Route to doc-updater Agent

Hand off to `doc-updater` with:
- List of recently changed source files
- Scope filter (api / readme / docstrings / all)
- Target directory

The agent:
1. Identifies which doc files are affected by the source changes
2. Updates them to reflect the new code (signatures, examples, descriptions)
3. Verifies all code examples in docs still compile/run
4. Flags any doc sections that reference deleted or renamed symbols

### Step 4: Report

```
DOC UPDATE COMPLETE
====================
Target: <path>
Scope: <all|api|readme|docstrings>

Files updated:
  ~ README.md — updated endpoint list in API section
  ~ src/auth/middleware.ts — updated JSDoc for refreshToken()
  ~ docs/api-reference.md — updated POST /auth/refresh schema

Warnings:
  ! docs/examples/auth.ts:22 — references deleted method validateJWT()
    → Update or remove this example

No new documentation created. Use /docs for new content.
```

---

## Usage Examples

- `/doc-updater` — update all docs affected by recent changes
- `/doc-updater src/auth/` — update docs for the auth module only
- `/doc-updater --api` — update API reference docs only
- `/doc-updater --docstrings src/payments/` — sync docstrings in payments module
- `/doc-updater --readme` — update README only

## Notes

- Use after `/prp-implement` or significant feature work
- Does NOT write new documentation — only updates existing files
- For creating new READMEs, API docs, or guides: use `/docs`
- Automatically flags stale examples that reference deleted symbols
