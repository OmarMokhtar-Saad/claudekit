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
3. **Reference files by path** -- Do not embed file content in the handoff
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
Coordinator → DocUpdater
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
