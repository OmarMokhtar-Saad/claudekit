---
description: "Diagnose bug via debugger agent (read-only)"
argument-hint: "[error description or file path]"
model: opus
---

# Debugger Command

Invoke the debugger agent to systematically diagnose a bug or issue.

## Agent Reference

See @agents/debugger.md for the full agent specification.

## Task

Diagnose issue: $ARGUMENTS

## Mandatory Skills

You MUST load and apply the following skills before proceeding:

- **using-superpowers** - Core agent capabilities and tool usage
- **systematic-debugging** - Structured diagnosis methodology

## READ-ONLY WARNING

This agent operates in READ-ONLY mode. You may read any file, run any diagnostic command, and execute tests, but you MUST NOT modify any source files, configuration files, or project state. The debugger diagnoses -- it does not fix. Fixes are the responsibility of the planner and implementer agents.

The ONLY exception: you may create temporary scratch files in /tmp for analysis purposes.

## Workflow Phases

### Phase 1: Symptom Collection
- Reproduce the reported issue (if reproduction steps are provided)
- Gather error messages, stack traces, and log output
- Identify the exact failure point (file, line, function)
- Document the expected vs actual behavior

### Phase 2: Context Mapping
- Identify all files involved in the failing code path
- Trace the call chain from entry point to failure
- Map data flow through the affected components
- Identify recent changes to the affected area (git log)

### Phase 3: Hypothesis Generation
- Generate at least 3 possible root causes
- Rank hypotheses by likelihood and testability
- For each hypothesis, define a test to confirm or refute it

### Phase 4: Hypothesis Testing
- Test each hypothesis in order of likelihood
- Use targeted reads, searches, and diagnostic commands
- Eliminate hypotheses that are disproven
- Narrow down to the most likely root cause

### Phase 5: Root Cause Confirmation
- Confirm the root cause with evidence
- Explain the causal chain from root cause to symptom
- Identify any contributing factors

## Pattern Match Table

Use these common patterns to accelerate diagnosis:

| Symptom                          | Common Causes                                |
|----------------------------------|----------------------------------------------|
| Null/undefined reference         | Missing initialization, race condition, bad import |
| Type error                       | Schema mismatch, serialization issue, wrong API version |
| Test failure after refactor      | Broken assumption, missing mock update, import path change |
| Build failure                    | Missing dependency, version conflict, config error |
| Intermittent failure             | Race condition, timing dependency, external service |
| Performance regression           | N+1 query, missing index, unbounded loop, memory leak |
| Import/module error              | Circular dependency, wrong path, missing export |
| Permission/auth error            | Token expiry, scope change, config mismatch |

## Confidence Decision

After diagnosis, rate your confidence:

- **HIGH (>90%)**: Root cause confirmed with direct evidence. Single clear fix path.
- **MEDIUM (60-90%)**: Strong evidence pointing to root cause but some ambiguity. 1-2 possible fix paths.
- **LOW (<60%)**: Multiple possible causes, insufficient evidence to isolate. Recommend further investigation.

## Output Format

```
## Diagnosis Report

### Issue Summary
- **Reported**: [user's description]
- **Reproduced**: YES/NO
- **Severity**: CRITICAL / HIGH / MEDIUM / LOW

### Root Cause
- **Confidence**: HIGH / MEDIUM / LOW (XX%)
- **Cause**: [clear description]
- **Location**: [file:line]
- **Causal Chain**: [A triggered B which caused C]

### Evidence
1. [evidence item with file references]
2. [evidence item with file references]
3. [evidence item with file references]

### Hypotheses Evaluated
| # | Hypothesis          | Status    | Evidence                 |
|---|---------------------|-----------|--------------------------|
| 1 | [description]       | CONFIRMED | [brief evidence]         |
| 2 | [description]       | REFUTED   | [why ruled out]          |
| 3 | [description]       | REFUTED   | [why ruled out]          |

### Recommended Fix
- **Approach**: [description of fix]
- **Files to modify**: [list]
- **Risk**: LOW / MEDIUM / HIGH
- **Suggestion**: Run `/plan [fix description]` to create implementation plan

### Related Issues
- [any related patterns or tech debt noticed]
```

## Usage Examples

- `/debug Tests in auth module failing after user service refactor`
- `/debug Build fails with "Cannot find module" error`
- `/debug API returns 500 on POST /users endpoint`
- `/debug Application hangs when processing large CSV files`
- `/debug Flaky test: UserService.test.ts intermittently fails`

## Notes

- Always check git history for recent changes to affected files
- Look for similar past issues in the codebase (comments, TODOs)
- Consider environmental factors (node version, OS, config differences)
- If reproduction is not possible, state this clearly and proceed with static analysis
