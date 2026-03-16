# Validation Checklist

Pre-flight validation checklist for all ClaudeKit agents. Run this before starting any work.

---

## Universal Pre-Flight Checklist

Every agent runs this before beginning its task:

```
PRE-FLIGHT VALIDATION
=====================
Agent: <name>
Task: <description>

Environment:
  [ ] Working directory is the project root
  [ ] Required tools are available (python3, git, build tools)
  [ ] Agent definition file exists at .claude/agents/<name>.md

Input:
  [ ] Handoff block is present and structured
  [ ] Referenced files exist and are readable
  [ ] Task description is clear and actionable
  [ ] No conflicting instructions

Safety:
  [ ] Task is within this agent's permissions
  [ ] No destructive operations without approval
  [ ] No secrets or credentials in the input
  [ ] Target files are within the project directory

Dependencies:
  [ ] Previous pipeline steps completed successfully
  [ ] Required deliverables from prior agents exist
  [ ] No unresolved blockers from prior steps

Status: READY | BLOCKED (<reason>)
```

If any check fails, report it and do not proceed.

---

## Agent-Specific Checklists

### Planner Pre-Flight
```
  [ ] Codebase is accessible (can read files)
  [ ] No existing plan with the same name (pre-plan hook)
  [ ] Task scope is clear (in-scope and out-of-scope defined)
  [ ] Tech stack is identifiable
```

### Reviewer Pre-Flight
```
  [ ] plan.md exists at the specified path
  [ ] ops.json exists at the specified path
  [ ] ops.json is valid JSON
  [ ] Both files are complete (not truncated)
  [ ] Scoring criteria are loaded
```

### Implementer Pre-Flight
```
  [ ] Plan was APPROVED by Reviewer (check status)
  [ ] ops.json path is correct (if using script execution)
  [ ] execute-json-ops.py script is available (if using ops.json)
  [ ] Target files exist (for modify operations)
  [ ] Target directories exist (for create operations)
  [ ] Build tools are available
  [ ] Backup strategy is in place (git or script backups)
```

### Verifier Pre-Flight
```
  [ ] Test framework is available and configured
  [ ] Linter is available and configured
  [ ] Coverage tool is available and configured
  [ ] List of modified files is provided
  [ ] Baseline metrics are available (or noted as unavailable)
```

### GitOps Pre-Flight
```
  [ ] Git repository is initialized
  [ ] Current branch is identified
  [ ] Remote is configured
  [ ] No merge conflicts exist
  [ ] Working tree state is known (clean or dirty)
  [ ] Files to commit are identified
```

### Debugger Pre-Flight
```
  [ ] Error description or stack trace is provided
  [ ] Relevant source files are accessible
  [ ] Log files are accessible (if referenced)
  [ ] Reproduction steps are provided (or noted as missing)
```

### Documenter Pre-Flight
```
  [ ] Source files to document are accessible
  [ ] Existing documentation is identified
  [ ] Documentation format is known (README, API docs, etc.)
  [ ] Target output path is clear
```

### Explore Pre-Flight
```
  [ ] Search query or question is clear
  [ ] Thoroughness level is determined (quick/medium/thorough)
  [ ] Codebase is accessible (can read and search)
  [ ] Output format is known
```

---

## Post-Completion Checklist

After completing the task, before producing the handoff:

```
POST-COMPLETION VALIDATION
===========================

Deliverables:
  [ ] All expected outputs were produced
  [ ] Output files exist at the specified paths
  [ ] Output files are not empty
  [ ] Output files are well-formed (valid JSON, valid Markdown, etc.)

Verification:
  [ ] Verification gate was run (see VERIFICATION_PROTOCOL.md)
  [ ] Evidence is included in the output
  [ ] No unresolved errors or warnings

Handoff:
  [ ] Handoff block is structured correctly
  [ ] All referenced files are listed
  [ ] Status is accurately reported
  [ ] Next agent is correctly identified

Cleanup:
  [ ] No temporary files left behind
  [ ] No debug output in production code
  [ ] No TODO items that should have been resolved
  [ ] State files updated (if using file-based state)
```

---

## Quick Validation (Simple Tasks)

For simple, well-defined tasks, a condensed validation is acceptable:

```
Pre-flight: Input present, files accessible, permissions OK
Post-flight: Output written, verified, handoff ready
```

Use the full checklists for:
- Tasks involving more than 3 files
- Tasks with pipeline dependencies
- Tasks involving code execution
- Tasks with security implications
