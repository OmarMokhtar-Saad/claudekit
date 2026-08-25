---
description: "Review actual code — files, directories, or a GitHub PR — for bugs, security issues, and quality problems"
argument-hint: "[<path>|--pr <N>] [--severity critical|high|all]"
model: opus
---

# Code Review Command

Invokes the `code-reviewer` agent to review actual code diffs, files, or pull requests. Produces a ranked findings report with specific file:line references and actionable fix suggestions.

Distinct from `/review` which validates implementation plans. This command reviews working code.

## Mandatory Skills

- **using-superpowers** - Core capabilities
- **security-checklist** - OWASP Top 10 review
- **differential-security-review** - Detect removed security controls

## Task

Review: $ARGUMENTS

---

## Execution Steps

### Step 1: Parse Target

```bash
ARGS="$ARGUMENTS"
SEVERITY="all"
TARGET=""
PR_NUM=""

# Extract severity filter
echo "$ARGS" | grep -q '\-\-severity' && \
    SEVERITY=$(echo "$ARGS" | grep -oE '\-\-severity\s+\S+' | awk '{print $2}')

# Extract PR number
if echo "$ARGS" | grep -q '\-\-pr'; then
    PR_NUM=$(echo "$ARGS" | grep -oE '\-\-pr\s+[0-9]+' | grep -oE '[0-9]+')
    echo "Reviewing PR #$PR_NUM"
else
    TARGET=$(echo "$ARGS" | sed 's/--severity\s\+\S\+//' | xargs)
    [ -z "$TARGET" ] && TARGET="."
    echo "Reviewing: $TARGET"
fi
```

### Step 2: Gather the Artifact

**For a file or directory:**
```bash
# Get all relevant changed files
if [ -n "$TARGET" ]; then
    find "$TARGET" -name "*.ts" -o -name "*.tsx" -o -name "*.py" \
         -o -name "*.go" -o -name "*.rs" -o -name "*.js" 2>/dev/null | \
         grep -v node_modules | grep -v ".git" | head -30
fi
```

**For a PR:**
```bash
if [ -n "$PR_NUM" ]; then
    gh pr view "$PR_NUM" --json title,body,files,commits
    gh pr diff "$PR_NUM"
fi
```

### Step 3: Route to code-reviewer Agent

Hand off to the `code-reviewer` (Opus) agent with:
- Full file contents (not just diff lines — context matters)
- Severity filter: critical-only, high+, or all
- Domain context: auth/payments/api/infra (derived from file paths)

The code-reviewer applies 5 dimensions in priority order:
1. **Correctness** — logic errors, edge cases, race conditions
2. **Security** — OWASP Top 10, removed guards, injection points
3. **Performance** — N+1 queries, blocking I/O, memory leaks
4. **Reliability** — error handling, retry logic, timeouts
5. **Code quality** — dead code, complexity, misleading names

### Step 4: Apply Severity Filter

```
If --severity critical: show only Critical findings
If --severity high:     show Critical + High findings
If --severity all:      show all findings (default)
```

### Step 5: Present Report

```
CODE REVIEW REPORT — Target: <files/PR> | Severity: <all|high|critical> | Files: N
VERDICT: [APPROVE | APPROVE WITH SUGGESTIONS | REQUEST CHANGES | BLOCK]
Summary: Critical: N | High: N | Medium: N | Low: N
CRITICAL / HIGH / MEDIUM / LOW, most severe first:
  [C1] <finding>  File: <path:line>  Fix: <specific fix>
Positive observations: <what the change got right>
```

### Step 5b: Save the report VERBATIM (Step 5c reads this file)

```bash
REVIEW_OUT="${REVIEW_OUT:-.claude/reports/last-code-review.txt}"
mkdir -p "$(dirname "$REVIEW_OUT")"
cat > "$REVIEW_OUT" <<'CODE_REVIEW_REPORT'
REPLACE THIS LINE WITH THE REPORT ABOVE, VERBATIM, INCLUDING ITS VERDICT BLOCK
CODE_REVIEW_REPORT
```
### Step 5c: Record a NON-APPROVING verdict

**Only rejections are recorded**, and `--only-non-approving` enforces it: an APPROVE from a *diff* review must never authorise execution of an ops.json it never scored.
This step derives no verdict of its own — one parser owns that. `REVIEW_OUT` is Step 5b's file; `PLAN_FILE` is the plan whose ops.json produced the code (newest plan by default, as in `/review`). Skip it for a `CANNOT REVIEW` round; skips are announced, never silent.
Contract: `.claude/knowledge/rejections/README.md`.

```bash
REVIEW_OUT="${REVIEW_OUT:-.claude/reports/last-code-review.txt}"
PLAN_FILE="${PLAN_FILE:-$(ls -t .claude/plans/plan-*.md 2>/dev/null | head -1)}"
python3 .claude/operations/scripts/review-record.py record-code-review \
  --report "$REVIEW_OUT" --plan "$PLAN_FILE"
```

---

## Usage Examples

- `/code-review src/auth/` — review all files in the auth module
- `/code-review --pr 42` — review GitHub PR #42
- `/code-review src/api/payments.ts --severity high` — high+ findings only
- `/code-review .` — review all source files (use on small PRs only)

## Notes

- Uses `code-reviewer` agent (Opus model) for thorough analysis
- For high-stakes changes (auth, payments, security), consider `/santa` for dual review
- Does NOT modify any code — read-only analysis only
- Findings are confidence-filtered: only real issues with file:line references
- NEVER reports style nitpicks without functional or security impact
