---
name: Santa Method
description: Adversarial dual-review pattern — two independent model reviewers (Opus + Sonnet) both must approve before code or plans ship. Neither reviewer sees the other's output, preventing anchoring. Both must approve; one rejection triggers revision; both reject triggers escalation.
trigger: Use when reviewing high-stakes code, security-sensitive changes, or any change where a missed bug would be expensive to fix.
---

# Santa Method

An adversarial dual-review pattern where two independent reviewers evaluate the same artifact with no shared context. Both must approve before the work proceeds. This eliminates the anchoring bias of sequential review (Reviewer B is influenced by Reviewer A's findings).

## When to Use

- Security-sensitive code changes
- Public API changes
- Database migrations or schema changes
- Authentication / authorization changes
- Any change the team has flagged as high-stakes
- When a single reviewer returned marginal approval (score 90-95)

## When NOT to Use

- Routine documentation updates (overkill)
- Internal refactors with no behavioral change
- Trivial bug fixes (< 5 lines, no edge cases)
- Use `/review` (single reviewer) for standard plan validation

---

## The Two Reviewers

### Reviewer A — The Skeptic (Opus)
**Focus:** Correctness and long-term consequences  
**Mindset:** Assume the code is wrong until proven otherwise  
**Checks:** Logic errors, edge cases, error handling, race conditions, security holes  
**Bias:** Prefers rejection when uncertain

### Reviewer B — The Pragmatist (Sonnet)
**Focus:** Real-world risk and shipping speed  
**Mindset:** Is this good enough to ship? What's the actual blast radius if it's wrong?  
**Checks:** Is the logic sound for the happy path? Are the dangerous cases handled? Is this reversible if wrong?  
**Bias:** Prefers approval when risk is low and change is reversible

---

## Anti-Anchoring Protocol (CRITICAL)

Both reviewers MUST be spawned:
1. **In parallel** (not sequentially)
2. **With no shared context** (each gets only the artifact, not the other's output)
3. **With no prior conversation history** (fresh agent spawn per reviewer)

Violating this protocol invalidates the review — a reviewer who sees the other's findings will anchor on them, defeating the purpose.

---

## Execution Protocol

### Step 1: Prepare Review Package
```
Compile a self-contained review package:
  - The artifact (code diff, plan file, or PR description)
  - Specific questions to answer (e.g. "Is the auth check sufficient?")
  - Context brief (what this change does, what it replaces)
  - Risk context (what breaks if this is wrong)

Do NOT include:
  - Prior review feedback
  - Author's explanation of their choices
  - Team's opinion on the change
```

### Step 2: Spawn Both Reviewers in Parallel
```
Spawn Reviewer A (Opus, Skeptic):
  - Full review package
  - Instruction: "You are the Skeptic. Assume the code is wrong.
    Find every issue. Only approve if you cannot find a flaw."
  - Must produce: APPROVE or REJECT + ranked findings

Spawn Reviewer B (Sonnet, Pragmatist):
  - Same full review package (identical content)
  - Instruction: "You are the Pragmatist. Assess real-world risk.
    Would you ship this? What's the blast radius if you're wrong?"
  - Must produce: APPROVE or REJECT + ranked findings

Both spawns happen simultaneously. Neither sees the other.
```

### Step 3: Collect and Synthesize
```
Collect both verdicts. Then:

IF both APPROVE:
  → Proceed. Note any overlapping findings as "worth addressing but not blocking."

IF one APPROVE, one REJECT:
  → Send rejection findings to the author for revision
  → Re-run Santa Method after revision (counts as revision cycle)
  → Max 3 revision cycles before escalation

IF both REJECT:
  → ESCALATE immediately to human
  → Both reviewers found critical issues — do not attempt to fix without guidance
  → Present both finding sets to the human
```

### Step 4: Synthesis Report
Present to user:

```
SANTA METHOD REVIEW
====================
Artifact: <name>

Reviewer A (Skeptic/Opus):   [APPROVE | REJECT]
Reviewer B (Pragmatist/Sonnet): [APPROVE | REJECT]

VERDICT: [APPROVED | REVISION REQUIRED | ESCALATE]

─── Reviewer A Findings ───
[findings list with severity]

─── Reviewer B Findings ───
[findings list with severity]

─── Agreement Analysis ───
Both flagged:    <issues both found — highest confidence>
Only A flagged:  <issues Skeptic found that Pragmatist considered acceptable>
Only B flagged:  <issues Pragmatist found that Skeptic missed>

─── Action Items ───
[if REVISION]: Fix these before re-review:
  1. <item>
[if APPROVED]: Optional improvements:
  1. <item>
```

---

## Scoring Guidance (per reviewer)

Each reviewer scores independently:

| Dimension | Weight | Skeptic focus | Pragmatist focus |
|-----------|--------|---------------|------------------|
| Correctness | 40% | Edge cases, logic errors | Happy path, blast radius |
| Security | 30% | Every injection point, authz gap | Real exploitability |
| Architecture | 30% | Long-term technical debt | Fits existing patterns |

**Approval threshold:** Each reviewer must score ≥ 90/100 independently.

---

## Usage in Commands

```
/santa <file-or-diff>           — dual review a file or diff
/santa plans/my-plan.md         — dual review a plan
/santa --pr 42                  — dual review a GitHub PR
/santa --strict <file>          — strict mode: threshold raised to 95/100
```

---

## Integration with Reviewer Agent

The `reviewer.md` agent supports `--dual` flag:
```
When invoked with --dual:
  1. Load santa-method skill
  2. Spawn two independent sub-reviewers per this protocol
  3. Synthesize and return combined verdict
  4. Threshold: 90/100 each for normal, 95/100 each for --strict
```
