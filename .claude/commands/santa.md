---
description: "Adversarial dual review — two independent model reviewers (Opus + Sonnet) both must approve before code ships"
argument-hint: "<file|plan|--pr N> [--strict]"
model: opus
---

# Santa Command

Run the Santa Method: two independent reviewers evaluate the same artifact with no shared context. Both must approve. One rejection triggers revision. Both reject triggers escalation.

## Mandatory Skills

- **using-superpowers** - Core capabilities
- **santa-method** - Dual-review protocol with anti-anchoring guarantee

## Task

Run Santa Method dual review on: $ARGUMENTS

---

## Execution Steps

### Step 1: Identify Target

```bash
# Parse arguments
TARGET="$ARGUMENTS"
STRICT_MODE=false

if echo "$TARGET" | grep -q '\-\-strict'; then
    STRICT_MODE=true
    TARGET=$(echo "$TARGET" | sed 's/--strict//' | xargs)
fi

# Determine target type
if echo "$TARGET" | grep -q '\-\-pr'; then
    PR_NUM=$(echo "$TARGET" | grep -oE '[0-9]+')
    echo "Reviewing PR #$PR_NUM"
elif [ -f "$TARGET" ]; then
    echo "Reviewing file: $TARGET"
else
    echo "Reviewing: $TARGET (treating as description)"
fi
```

### Step 2: Build Review Package

Compile a self-contained package containing:
- The artifact (file content or PR diff)
- What the change does (one paragraph)
- What breaks if the change is wrong (blast radius)
- Specific questions to answer (security, correctness, edge cases)

Do NOT include: prior review feedback, author's explanation of choices, team opinions.

### Step 3: Spawn Both Reviewers in Parallel (CRITICAL — no shared context)

Spawn both reviewers in ONE message (two spawns, single response — spawning one per turn
serializes them and breaks the isolation guarantee). Neither sees the other's output.
Spawn per `.claude/agents/_shared/INVOCATION.md` with `--allowedTools "Read,Grep,Glob"` —
reviewers verify claims against the actual repo, not just the packaged text.

**Reviewer A — The Skeptic (Opus)** — spawn with `--model opus`
- Prompt: "You are reviewing this code change as a skeptic. Assume something is wrong. Find every bug, security issue, and edge case. Verify suspicious claims against the repository (Read/Grep) — confirm at least one CRITICAL finding by inspection before REJECT. Score each dimension 0-40/0-30/0-30. Only APPROVE if you cannot find a flaw. Return: APPROVE or REJECT, score, findings — each with file:line, why it's wrong, and the fix."
- Threshold: 90/100 normal, 95/100 with --strict

**Reviewer B — The Pragmatist (Sonnet)** — spawn with `--model sonnet`
- Prompt: "You are reviewing this code change as a pragmatist. Assess real-world risk. Would you ship this? What breaks if it's wrong? Check the surrounding code (Read/Grep) before judging integration risk. Score each dimension. APPROVE if risk is acceptable and change is sound. Return: APPROVE or REJECT, score, findings — each with file:line, why it matters, and the fix."
- Threshold: 90/100 normal, 95/100 with --strict

### Step 4: Synthesize Verdicts

```
Collect both verdicts:

BOTH APPROVE  → Proceed. List overlapping findings as optional improvements.
ONE REJECT    → Send rejection findings to author for revision (max 3 cycles).
BOTH REJECT   → Escalate immediately to human with both finding sets.
```

### Step 5: Present Results

```
SANTA METHOD REVIEW
====================
Target: <name>
Mode: <normal|strict> (threshold: <90|95>/100)

Reviewer A (Skeptic/Opus):      [APPROVE ✓ | REJECT ✗] — Score: N/100
Reviewer B (Pragmatist/Sonnet): [APPROVE ✓ | REJECT ✗] — Score: N/100

VERDICT: [APPROVED ✓ | REVISION REQUIRED | ESCALATE TO HUMAN]

── Reviewer A Findings ──
[ranked list]

── Reviewer B Findings ──
[ranked list]

── Agreement Analysis ──
Both flagged (highest confidence): ...
Only Skeptic flagged: ...
Only Pragmatist flagged: ...

── Next Steps ──
[action items or approval confirmation]
```

---

## Usage Examples

- `/santa src/auth/middleware.ts` — dual review a source file
- `/santa .claude/plans/plan-add-billing.md` — dual review a plan
- `/santa --pr 42` — dual review a GitHub PR
- `/santa --strict src/payments/` — raised threshold (95/100 required)

## Notes

- Both reviewers run in parallel with NO shared context (anti-anchoring)
- Opus acts as Skeptic (correctness focus), Sonnet as Pragmatist (risk focus)
- Use for: security changes, public API changes, DB migrations, auth changes
- Do NOT use for: docs updates, trivial refactors, < 5 line fixes (use `/review`)
