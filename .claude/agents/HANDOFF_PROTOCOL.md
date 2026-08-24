# Handoff Protocol

Standardized format for passing work between ClaudeKit agents. Every agent-to-agent transition MUST follow this protocol.

---

## Handoff Block Format

Every handoff uses this exact structure:

```
HANDOFF TO: <target-agent>
---
Task: <concise task description>
Classification: <Feature|Bug|Quality|Git|Docs|Explore|Refactor>
Pipeline Position: Step <N> of <M>
Prior Agent Output: <summary of what was produced>
Files Modified: <list of files touched so far>
Constraints:
  - <constraint 1>
  - <constraint 2>
Expected Output: <what the target agent should produce>
Return To: <agent to return to, usually coordinator>
```

---

## Handoff Rules

1. **Always use the structured format** -- No free-form handoffs
2. **Include all required fields** -- Missing fields cause ambiguity
3. **Reference files by path, never embed file content** -- a handoff, subagent response,
   or echoed Bash output that reprints a plan/ops.json/artifact body pins that payload in
   context for every subsequent turn (see `.claude/agents/_shared/INVOCATION.md`'s
   "Delivery contract" section). Interactive spawns write their own artifacts and return
   only the path; headless spawns' stdout is redirected straight to disk by the invoking
   command's wrapper, never teed or echoed back.
4. **State the expected output** -- The receiving agent must know what to produce
5. **Specify return routing** -- Who gets the result when the target finishes
6. **Include constraints** -- Any limitations the receiving agent must respect

---

## Agent-Specific Handoff Formats

### Coordinator to Any Agent
```
HANDOFF TO: <agent>
---
Task: <description>
Classification: <type>
Pipeline Position: Step <N> of <M>
Prior Agent Output: <summary or "Initial task, no prior output">
Files Modified: <list or "None yet">
Constraints:
  - <from user request>
  - <from pipeline state>
Expected Output: <specific deliverable>
Return To: coordinator
```

### Planner to Reviewer
```
HANDOFF TO: reviewer
---
Plan File: <path to plan.md>
Ops Config: <path to ops.json>
Complexity: <Simple|Medium|Complex>
Files Affected: <count>
Steps: <count>
Risk Level: <Low|Medium|High>
```

### Reviewer to Implementer (Approved)
```
HANDOFF TO: implementer
---
Status: APPROVED
Score: <total>/100
Plan File: <path>
Ops Config: <path>
Notes:
  - <non-blocking suggestions>
```

### Reviewer to Planner (Revision)
```
HANDOFF TO: planner
---
Status: REVISION REQUIRED
Score: <total>/100
Revision Number: <N> of 3
Plan File: <path>
Ops Config: <path>

Critical Issues (must fix):
  1. <issue with specific location and fix suggestion>

Warnings (should fix):
  1. <issue with specific location and fix suggestion>
```

### Implementer to Verifier
```
HANDOFF TO: verifier
---
Status: IMPLEMENTATION COMPLETE
Plan: <path>
Method: <Script|Manual>
Files Modified: <list>
Files Created: <list>
Build Status: PASS
Test Results: <summary>
```

### Verifier to GitOps (Pass)
```
HANDOFF TO: gitOps
---
Status: VERIFICATION PASSED
Score: <total>/100
Files Verified: <list>
Test Results: <N> passed, <M> failed, <K> skipped
Coverage: <N>%
Notes:
  - <informational items>
```

### Verifier to Implementer (Retry)
```
HANDOFF TO: implementer
---
Status: RETRY REQUIRED
Score: <total>/100
Retry: <N> / 2

Issues to Fix:
  1. <file:line> - <description> - Suggested fix: <fix>

Anti-Patterns Found:
  1. <pattern> in <file:line>

Note: Fix ONLY the listed issues. Do not make other changes.
```

### Any Agent to Coordinator (Escalation)
```
HANDOFF TO: coordinator
---
Status: ESCALATION
Agent: <self>
Reason: <why escalation is needed>
Current State: <where in the pipeline>
Context: <what was done so far>
Options: <suggested paths forward>
Recommendation: <best suggestion>
```

### Debugger to Planner
```
HANDOFF TO: planner
---
Status: ROOT CAUSE IDENTIFIED
Confidence: <N>%
Bug: <description>
Root Cause: <file:line> - <description>
Suggested Fix: <approach>
Affected Files: <list>
Report: <path to debug report>
```

---

---

## Reviewer Decision Taxonomy

**One definition, referenced everywhere.** Ten files defined their own before task 008
batch 4, and two of them contradicted: `commands/review.md` mapped a score below 70 to
`REVISE` while `agents/reviewer.md` mapped the same score to `REJECTED`, and
`reviewer.md` declared four decisions in its anchored block but only three in its
summary template and three score bands — leaving `REVISE`, which
`operations/scripts/review-record.py` accepts, with no band at all. That is not
theoretical: batch 2's round-1 verdict came back `REVISE` at 84, which both files' own
tables would have called `CONDITIONAL`.

The four values are exhaustive and mutually exclusive. **Findings decide first, score
second** — a score cannot approve past an open blocker:

| Decision | Condition | What happens next |
|---|---|---|
| `APPROVED` | score >= 90 **and** zero open CRITICAL or MAJOR | Proceed. Open MINORs are suggestions; record them, do not gate on them. |
| `CONDITIONAL` | score >= 70, only MINOR findings open | Proceed **after** fixing the named MINORs. No new review round — the fixes are mechanical and need no re-verification. |
| `REVISE` | >= 1 open CRITICAL or MAJOR that is fixable in place, **at any score** | Fix, then a new round reads **only the diff** since this verdict. This is the verdict for "the approach is right, the execution has a hole". |
| `REJECTED` | score < 70, **or** a finding that invalidates the approach itself, **or** any AUTO-REJECT trigger: no `ops.json`, invalid `ops.json`, or destructive operations with no rollback | Re-plan. Not a fix-and-resubmit; the artifact goes back to the planner. |

`review-record.py` enforces exactly these four spellings (`VALID_DECISIONS`), and only
`APPROVED` authorises `execute-json-ops.py` to run. A verdict the parser cannot read
cannot gate execution, so the anchored block is mandatory:

```
=== REVIEW ===
SCORE: <integer 0-100>
DECISION: APPROVED | CONDITIONAL | REVISE | REJECTED
- [CRITICAL|MAJOR|MINOR] <one finding per line, file:line + what is wrong>
=== END REVIEW ===
```

**Round ceiling is 3.** Stop at the first round with zero blocking findings. If you
reach the ceiling with something still open, report that to the owner rather than
opening a fourth round.

## Pipeline Flow Reference

### Feature Pipeline
```
Coordinator → Planner → Reviewer → Implementer → Verifier → GitOps
                  ↑          |
                  └──────────┘  (revision loop, max 3)
```

### Bug Pipeline
```
Coordinator → Debugger → Planner → Reviewer → Implementer → Verifier → GitOps
```

### Quality Pipeline
```
Coordinator → Verifier
```

### Git Pipeline
```
Coordinator → GitOps
```

### Docs Pipeline (New Documentation)
```
Coordinator → Documenter
```

### Docs Pipeline (Update Existing Documentation)
```
Coordinator → docs (mode: update)
```

### Explore Pipeline
```
Coordinator → Explore
```

### TDD Pipeline
```
Coordinator → TDDGuide → Verifier → GitOps
```

### Dead Code Pipeline
```
Coordinator → RefactorCleaner → Verifier → GitOps
```

### Performance Pipeline
```
Coordinator → [Explore + PerformanceOptimizer] (parallel analysis) → Planner → Implementer → Verifier
```

### Security Audit Pipeline
```
Coordinator → [SilentFailureHunter + SecurityScanner] (parallel, read-only) → Planner → Implementer → Verifier
```

### Code Quality Audit Pipeline
```
Coordinator → [TypeScriptReviewer | PythonReviewer] → Implementer (if fixes needed) → Verifier
```

### EPIC / Blueprint Pipeline
```
Coordinator → Blueprint skill → Plan review → per-step execution pipelines
```

### TDDGuide to Implementer (Tests Written)
```
HANDOFF TO: implementer
---
Status: TESTS WRITTEN — RED PHASE COMPLETE
Test Files: <list of test files>
Failing Tests: <count>
Test Scope: <what is being tested>
Next Step: Write ONLY the minimum code to make these tests pass
Constraint: Do NOT modify test files
```

### SilentFailureHunter + SecurityScanner to Planner (Audit Complete)
```
HANDOFF TO: planner
---
Status: AUDIT COMPLETE
Critical Issues: <count>
High Issues: <count>
Report: .claude/reports/audit-<timestamp>.md
Next Step: Create remediation plan for Critical + High issues only
Constraint: Do not redesign; fix the specific issues identified
```

### RefactorCleaner to Verifier (Batch Removed)
```
HANDOFF TO: verifier
---
Status: DEAD CODE BATCH REMOVED
Batch: <category> (e.g., unused imports, dead exports)
Files Modified: <list>
Detection Tool: <knip|depcheck|ts-prune|eslint>
Tests Must Pass: Yes — any failures mean rollback this batch
```

---

## Handoff Validation

Before sending a handoff, verify:

```
HANDOFF VALIDATION:
  [ ] Target agent name is correct
  [ ] All required fields are present
  [ ] File paths are valid and accessible
  [ ] Status accurately reflects the current state
  [ ] Expected output is clearly defined
  [ ] Return routing is specified
  [ ] No sensitive data in the handoff block
```

---

## Failed Handoff Recovery

If a handoff fails (target agent not available, invalid format, etc.):

1. Log the failure with full context
2. Retry once with the same handoff
3. If retry fails, escalate to the Coordinator
4. The Coordinator decides whether to:
   - Retry with a different approach
   - Skip the agent (if non-critical)
   - Escalate to human
