---
description: "Fix build errors, type errors, and compilation failures with the minimum possible diff — max 7 iterations"
argument-hint: "[--ts|--eslint|--go|--rust|--python] [--max-iter N]"
model: sonnet
---

# Build Fix Command

Invokes the `build-error-resolver` agent to fix build and type errors. Uses the smallest possible diff per error. Never refactors, never redesigns — only fixes the error.

## Mandatory Skills

- **using-superpowers** - Core capabilities
- **systematic-debugging** - Error → source → fix methodology

## Task

Fix build errors: $ARGUMENTS

---

## Execution Steps

### Step 1: Parse Options

```bash
ARGS="$ARGUMENTS"
MAX_ITER=7
BUILD_TYPE="auto"

echo "$ARGS" | grep -q '\-\-ts'     && BUILD_TYPE="typescript"
echo "$ARGS" | grep -q '\-\-eslint' && BUILD_TYPE="eslint"
echo "$ARGS" | grep -q '\-\-go'     && BUILD_TYPE="go"
echo "$ARGS" | grep -q '\-\-rust'   && BUILD_TYPE="rust"
echo "$ARGS" | grep -q '\-\-python' && BUILD_TYPE="python"

if echo "$ARGS" | grep -q '\-\-max-iter'; then
    MAX_ITER=$(echo "$ARGS" | grep -oE '\-\-max-iter\s+[0-9]+' | grep -oE '[0-9]+$')
fi
```

### Step 2: Detect Build Type (if auto)

```bash
if [ "$BUILD_TYPE" = "auto" ]; then
    [ -f "tsconfig.json" ] && BUILD_TYPE="typescript"
    [ -f "go.mod" ] && BUILD_TYPE="go"
    [ -f "Cargo.toml" ] && BUILD_TYPE="rust"
    [ -f "pyproject.toml" ] || [ -f "setup.py" ] && BUILD_TYPE="python"
fi

echo "Build type: $BUILD_TYPE"
```

### Step 3: Run Initial Build + Capture Errors

Run the build command for the detected type:

```bash
case "$BUILD_TYPE" in
  typescript)
    npx tsc --noEmit 2>&1 | tee /tmp/build-errors.txt
    ;;
  eslint)
    npx eslint . --format=compact 2>&1 | tee /tmp/build-errors.txt
    ;;
  go)
    go build ./... 2>&1 | tee /tmp/build-errors.txt
    ;;
  rust)
    cargo build 2>&1 | tee /tmp/build-errors.txt
    ;;
  python)
    python3 -m py_compile $(find . -name "*.py" -not -path "*/.*") 2>&1 | tee /tmp/build-errors.txt
    ;;
esac

ERROR_COUNT=$(wc -l < /tmp/build-errors.txt)
echo "Initial errors: $ERROR_COUNT lines"
```

### Step 4: Invoke Build Error Resolver

Pass all errors to the `build-error-resolver` agent. The agent:
1. Parses each error: file:line:col + error code
2. Groups by file (fix upstream errors first)
3. Applies minimum fix per error
4. Re-runs build after each batch
5. Repeats until clean or max iterations

**The one rule:** Fix the error. Only the error. Nothing else.

Supported fixes (NEVER alternatives):
- Type mismatches → fix the type, not suppress with `@ts-ignore`
- Missing imports → add the correct import, not inline the type
- Undefined variable → fix the reference, not rename everything
- Build failures → minimum patch, not architectural change

### Step 5: Iteration Loop

```
FOR iteration 1..MAX_ITER:
  1. Read current error list
  2. Fix highest-priority errors (upstream first)
  3. Re-run build
  4. IF errors decreased → continue
  5. IF errors unchanged → try different approach for same error
  6. IF errors increased → revert last change + escalate

IF build clean → report success
IF MAX_ITER reached → report remaining errors + escalate
```

### Step 6: Report

```
BUILD FIX COMPLETE
==================
Build type: <type>
Initial errors: <N>
Remaining errors: <N>
Iterations used: <N> / <MAX_ITER>
Status: <CLEAN | PARTIAL | ESCALATE>

Fixes applied:
  1. src/auth/middleware.ts:42 — TS2345 — Added string narrowing
  2. src/api/routes.ts:87 — TS2339 — Fixed property name (userId → user_id)
  ...

Remaining errors (if any):
  1. src/legacy/auth.ts:12 — TS2741 — Requires architectural change (escalate)

Next steps:
  /prp-commit "fix TypeScript errors"
  OR manually review remaining errors
```

---

## Usage Examples

- `/build-fix` — auto-detect build type, fix all errors
- `/build-fix --ts` — TypeScript tsc errors only
- `/build-fix --eslint` — ESLint violations only
- `/build-fix --go` — Go compilation errors
- `/build-fix --max-iter 3` — stop after 3 fix iterations

## Notes

- NEVER suppresses errors with `@ts-ignore`, `eslint-disable`, `#[allow(...)]`
- NEVER adds `any` type as a quick fix
- NEVER changes function signatures (fix the call site instead)
- Architectural errors are escalated — not hacked around
- Works best after `/prp-implement` if the implementation left type errors
