---
description: "PRP Phase 2 — Execute a PRP plan with rigorous validation loops. Stops only when all checks pass."
argument-hint: "<prp-plan-file>"
model: sonnet
---

# PRP Implement Command

Phase 2 of the Product Requirements Process. Loads a PRP plan and implements it step by step, following the patterns documented in the plan exactly. Runs validation after each file and a full gate at the end. Does NOT stop until all checks pass or max iterations is reached.

## Mandatory Skills

- **using-superpowers** - Core capabilities
- **executing-plans** - Batch execution with checkpoints
- **verification-loop** - 6-phase quality gate
- **verification-before-completion** - Never claim done without evidence

## Task

Implement PRP plan: $ARGUMENTS

---

## Execution Steps

### Step 1: Load and Validate Plan

```bash
PLAN_FILE="$ARGUMENTS"

if [ ! -f "$PLAN_FILE" ]; then
    echo "ERROR: Plan file not found: $PLAN_FILE"
    echo "Run /prp-plan first to create the plan."
    exit 1
fi

# Verify plan has required sections
for section in "Affected Files" "Implementation Steps" "Test Requirements" "Verification Commands"; do
    grep -q "$section" "$PLAN_FILE" || echo "WARNING: Missing section: $section"
done

echo "Plan loaded: $PLAN_FILE"
grep "^# PRP:" "$PLAN_FILE" | head -1
grep "^**Goal:**" "$PLAN_FILE" | head -1
```

### Step 2: Pre-Implementation Baseline

```bash
# Capture baseline state
git stash list | head -3
git status --short
tsc --noEmit 2>&1 | tail -5  # baseline type errors (if any)
```

### Step 3: Implement Each Step

For each implementation step in the plan:
1. Read the step description carefully
2. Read the target file (if it exists) before modifying
3. Apply ONLY the change described — follow the exact pattern shown in the plan
4. After each file: verify the change is syntactically correct
5. Do NOT refactor unrelated code while implementing

**Hard constraints:**
- Follow every pattern documented in the plan — no improvisation
- If the plan says "ADD", do not also MODIFY other things
- If unsure about a pattern, re-read the plan's pattern section — do not guess

### Step 4: Per-Step Verification

After each file modified:
```bash
# Syntax check (language-appropriate)
tsc --noEmit 2>&1 | grep "error TS" | wc -l   # TypeScript
# OR
python3 -m py_compile <file>                    # Python
# OR
go build ./...                                  # Go
```

If a syntax error appears, fix it immediately before moving to the next step.

### Step 5: Full Validation Gate

After all steps complete, run the plan's verification commands:

```bash
# Run commands from plan's "Verification Commands" section
<commands from plan>
```

Then run the 6-phase verification-loop gate:
1. Build — no errors
2. Types — tsc clean
3. Lint — no new violations
4. Tests — all pass, coverage ≥ threshold
5. Security — no new issues
6. Diff review — only expected files changed

### Step 6: Validation Loop

```
IF all checks pass:
  → Report success, list all files modified

IF checks fail:
  → Fix only the failing checks (do not re-implement everything)
  → Re-run validation
  → Max 3 fix iterations before escalating

IF max iterations reached:
  → Report what passed and what is still failing
  → Escalate to human with specific remaining issues
```

### Step 7: Completion Report

```
PRP IMPLEMENTATION COMPLETE
============================
Plan: <plan file>
Feature: <feature name>

Files created (N):
  + path/to/new-file.ts
  + ...

Files modified (N):
  ~ path/to/modified-file.ts
  ~ ...

Validation results:
  Build:    PASS ✓
  Types:    PASS ✓ (0 errors)
  Lint:     PASS ✓
  Tests:    PASS ✓ (N passed, 0 failed)
  Coverage: PASS ✓ (N%)
  Security: PASS ✓

Next steps:
  /prp-commit "add <feature name>"   — commit these changes
  /prp-pr                            — create PR
  /santa <file>                      — dual review (recommended for auth/security changes)
```

---

## Usage Examples

- `/prp-implement .claude/plans/prp-jwt-refresh.md` — implement a specific PRP plan
- `/prp-implement .claude/plans/prp-rate-limiting.md` — implement rate limiting plan

## Notes

- NEVER implement beyond what the plan specifies
- NEVER skip the validation gate at the end
- If a step in the plan is ambiguous, stop and ask rather than guessing
- The plan's "Decisions Already Made" section is authoritative — do not re-decide
