---
description: "3-stage open-source pipeline: Sanitizer scans for secrets/PII → Forker transforms safely → Packager generates README/CLAUDE.md/LICENSE/CI. Hard gate: Stage 2 only runs if Stage 1 PASSES."
argument-hint: "[<target-dir>] [--sanitize-only|--package-only|--full] [--license MIT|Apache|GPL]"
model: sonnet
---

# Open-Source Pipeline Command

Runs the 3-stage pipeline for safely publishing private/internal code as open source. Each stage is gated — no stage runs until the previous stage has explicitly passed.

**The rule:** If the Sanitizer finds BLOCKERs (secrets, internal infra, PII), the pipeline stops. Full stop.

## Mandatory Skills

- **using-superpowers** - Core capabilities
- **opensource-pipeline** - 3-stage pipeline protocol, hard gate, blocker categories
- **security-checklist** - Secret pattern detection
- **differential-security-review** - Regression detection in transformed output

## Task

Open-source pipeline: $ARGUMENTS

---

## Execution Steps

### Step 1: Parse Options

```bash
ARGS="$ARGUMENTS"
TARGET="."
MODE="full"
LICENSE="MIT"

# Target directory
TARGET=$(echo "$ARGS" | sed 's/--[a-z-]*\s*[a-z]*//g' | xargs)
[ -z "$TARGET" ] && TARGET="."

# Mode flags
echo "$ARGS" | grep -q '\-\-sanitize-only' && MODE="sanitize-only"
echo "$ARGS" | grep -q '\-\-package-only'  && MODE="package-only"
echo "$ARGS" | grep -q '\-\-full'          && MODE="full"

# License
if echo "$ARGS" | grep -q '\-\-license'; then
    LICENSE=$(echo "$ARGS" | grep -oE '\-\-license\s+\S+' | awk '{print $2}')
fi

echo "Target: $TARGET | Mode: $MODE | License: $LICENSE"
```

### Step 2: Staging Check (for --package-only)

```bash
if [ "$MODE" = "package-only" ]; then
    if [ ! -d ".claude/opensource-staging" ]; then
        echo "ERROR: No staging directory found at .claude/opensource-staging/"
        echo "Run without --package-only first to generate staging."
        exit 1
    fi
    echo "Using existing staging at .claude/opensource-staging/"
fi
```

### Step 3: Stage 1 — Sanitizer (always runs unless --package-only)

Invoke the `opensource-sanitizer` agent with:

```
Target: $TARGET
Task: Scan for secrets, internal infrastructure, PII, and other open-source blockers.
Return PASS or FAIL with structured findings.
```

**Parse the verdict:**

```
IF verdict == "FAIL":
  Display blocker findings with file:line references
  Print: "PIPELINE STOPPED — Fix all BLOCKER findings and re-run /opensource"
  Print: "WARNING findings: N (review before publishing but do not block)"
  EXIT — do not proceed to Stage 2
```

If `--sanitize-only`: display full report and exit here.

### Step 4: Stage 2 — Forker (only if Stage 1 PASS)

Prepare staging directory:

```bash
mkdir -p .claude/opensource-staging
rm -rf .claude/opensource-staging/*
```

Invoke the `opensource-sanitizer` in Forker mode (or a dedicated forker):

```
Source: $TARGET
Staging: .claude/opensource-staging/
Task: Transform source into a safe open-source version.
Apply: secret externalization, internal URL scrubbing, comment sanitization.
Do NOT modify business logic, public APIs, or test structure.
Write all output to .claude/opensource-staging/
```

**Post-fork verification — re-run Sanitizer on staging:**

```bash
# Sanitizer re-scans the staging directory
IF staging_scan.verdict == "FAIL":
  echo "ERROR: Forker introduced new issues or missed existing blockers"
  echo "Review .claude/opensource-staging/ manually"
  EXIT
```

### Step 5: Stage 3 — Packager (only if Stage 2 complete)

Invoke the `opensource-packager` agent:

```
Source: .claude/opensource-staging/
License: $LICENSE
Task: Generate full open-source scaffolding.
Generate: CLAUDE.md, README.md, LICENSE, .env.example, CONTRIBUTING.md,
          .github/pull_request_template.md, .github/ISSUE_TEMPLATE/*.md,
          .github/workflows/ci.yml
Write output to: .claude/opensource-output/
Rules:
  - Read actual code — no generic placeholders
  - CLAUDE.md must describe THIS project specifically
  - README usage examples must use real module/function names from the code
  - LICENSE year: current year
```

### Step 6: Final Verification

```bash
# Count what was generated
ls .claude/opensource-output/ 2>/dev/null | wc -l

# Check required files exist
for f in README.md LICENSE CLAUDE.md .env.example CONTRIBUTING.md; do
    [ -f ".claude/opensource-output/$f" ] && echo "✓ $f" || echo "✗ MISSING: $f"
done

[ -d ".claude/opensource-output/.github" ] && echo "✓ .github/" || echo "✗ MISSING: .github/"
```

### Step 7: Report

**Success:**
```
OPEN-SOURCE PIPELINE COMPLETE
================================
Target: <dir>
License: <type>

Stage 1 — Sanitizer: PASS (0 BLOCKERs, N WARNINGs)
Stage 2 — Forker:    COMPLETE (N files transformed)
Stage 3 — Packager:  COMPLETE (N files generated)

Output: .claude/opensource-output/

Generated files:
  + README.md
  + CLAUDE.md
  + LICENSE (MIT, 2026)
  + .env.example (N variables)
  + CONTRIBUTING.md
  + .github/pull_request_template.md
  + .github/ISSUE_TEMPLATE/bug_report.md
  + .github/ISSUE_TEMPLATE/feature_request.md
  + .github/workflows/ci.yml

Warnings to review before publishing:
  [W1] <warning 1>
  [W2] <warning 2>

Next steps:
  1. Review .claude/opensource-output/ carefully
  2. Address any WARNING findings above
  3. git init in output dir + push to new GitHub repo
  4. Consider /santa CLAUDE.md README.md for dual review
```

**Failure (BLOCKERs found):**
```
PIPELINE STOPPED — STAGE 1 FAILED
====================================
Target: <dir>
BLOCKERs found: N

[B1] <file>:<line> — <description>
     Pattern: <matched content>
     Fix: <specific fix>

[B2] ...

Fix all BLOCKERs and re-run:
  /opensource <target>
```

---

## Usage Examples

- `/opensource .` — full pipeline on current directory
- `/opensource src/ --sanitize-only` — audit only, no transformation
- `/opensource --package-only` — package existing staging directory
- `/opensource . --license Apache` — full pipeline with Apache 2.0 license
- `/opensource ./my-service --full` — explicit full mode

## Notes

- Original source is NEVER modified — all transformations write to `.claude/opensource-staging/`
- If pipeline fails at Stage 2, re-run from Stage 1 (no `--package-only` shortcut)
- `.claude/opensource-output/` is overwritten on each successful run
- WARNING findings do not block the pipeline but should be reviewed before publishing
- For high-risk repos (payments, auth, infra), run `/santa .claude/opensource-output/CLAUDE.md` after pipeline completes
