# Verification Protocol

Evidence-based completion protocol for all ClaudeKit agents. No agent may claim a task is complete without verification evidence.

---

## Core Principle

> **No claims without evidence.**
>
> Every completion claim must include concrete, verifiable evidence.
> "I believe it works" is not evidence. "Tests pass (14/14)" is evidence.

---

## Verification Gate

Before reporting completion, every agent MUST pass this gate:

```
VERIFICATION GATE
=================
Agent: <your-agent-name>
Task: <what was done>

Evidence Required:
  [ ] At least one concrete verification step was performed
  [ ] Evidence is included in the output (not just "it works")
  [ ] No unresolved errors or warnings
  [ ] All deliverables exist and are accessible

Evidence Provided:
  1. <verification step> → <result>
  2. <verification step> → <result>
  3. <verification step> → <result>

Gate: PASS | FAIL
```

If the gate FAILS, do not report completion. Either fix the issue or escalate.

---

## Evidence Types by Agent

### Planner
- Plan file exists at specified path
- ops.json exists and is valid JSON
- ops.json operations count matches plan steps
- All file paths in ops.json are valid (existing files exist, new files have valid directories)

### Reviewer
- All scoring criteria were evaluated (no skipped dimensions)
- Score calculation matches the formula
- Pre-validation checklist was completed
- Findings include specific file paths and line references

### Implementer
- Build command succeeds (include exit code)
- Lint command passes (or only pre-existing warnings)
- Test suite passes (include pass/fail counts)
- All plan steps were executed (include checklist)
- Dry run was performed before execution (for ops.json)

### Verifier
- Static analysis tool was run (include tool name and output summary)
- Tests were executed (include framework, pass/fail/skip counts)
- Coverage was measured (include percentage)
- Score calculation shown with weights applied

### GitOps
- Branch exists (include branch name)
- Commit was created (include commit hash)
- No secrets in committed files (scan result)
- Push succeeded (include remote and branch)

### Debugger
- Error was reproduced (include reproduction steps)
- Root cause was identified (include specific file and line)
- At least one code path was traced
- Confidence level is stated with justification

### Documenter
- Documentation file exists at specified path
- All referenced files/functions exist in the codebase
- No placeholder text remains (no TODO, TBD, etc.)
- Links are valid (internal references resolve)

### Explore
- Search queries were executed (include query and result counts)
- Files were read (not assumed from memory)
- Findings reference specific file paths
- All claimed patterns were verified with examples

---

## Verification Shortcuts

For simple tasks, a single verification step may suffice. For complex tasks, use the full gate.

### Quick Verification (simple tasks)
```
Verified: <one-line evidence statement>
```

Example: `Verified: plan.md and ops.json created at .claude/plans/, ops.json has 4 operations matching 4 plan steps.`

### Full Verification (complex tasks)
```
VERIFICATION GATE
=================
Agent: implementer
Task: Implement user authentication feature

Evidence:
  1. Build: PASS (exit code 0)
  2. Lint: PASS (0 errors, 2 pre-existing warnings)
  3. Tests: PASS (47/47, including 5 new auth tests)
  4. Files: 4 modified, 2 created (matches plan)
  5. Dry run: Completed with 0 conflicts

Gate: PASS
```

---

## Unacceptable Evidence

The following are NOT valid evidence and will cause the gate to FAIL:

- "I believe this is correct"
- "This should work"
- "Based on the plan, this is done"
- "The code looks right"
- "No errors were reported" (without actually running a check)
- Quoting from memory instead of reading the actual file
- Referencing a tool output without including the key result

---

## Escalation on Verification Failure

If verification fails and cannot be resolved:

```
VERIFICATION FAILED
===================
Agent: <name>
Task: <description>
Attempted Fixes: <what was tried>
Remaining Issues:
  1. <issue with evidence of failure>
  2. <issue with evidence of failure>
Recommendation: <suggested next step>
Escalating To: coordinator
```
