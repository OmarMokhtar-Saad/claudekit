---
name: context-first-workflow
description: "Use when starting ANY request involving code changes - ensures exploration happens before modifications"
user-invocable: false
---

# Context-First Workflow

## Core Principle

**Understand before you act. Explore before you modify. Read before you write.**

Every failed implementation shares a root cause: insufficient understanding of the existing system. This skill ensures you gather enough context before making any changes.

---

## The Decision Tree

```
User Request Arrives
    |
    v
[CLASSIFY] What type of request is this?
    |
    +---> Bug fix ---------> Explore: error context, logs, related code
    +---> New feature ------> Explore: existing patterns, integration points
    +---> Refactor ---------> Explore: all usages, dependencies, tests
    +---> Configuration ----> Explore: current config, environment, docs
    |
    v
[ASSESS] How much context do I need?
    |
    +---> Quick (1-2 files) ---------> Thoroughness: QUICK
    +---> Medium (3-10 files) -------> Thoroughness: MEDIUM
    +---> Large (10+ files) ---------> Thoroughness: VERY THOROUGH
    |
    v
[EXPLORE] Gather context at the assessed level
    |
    v
[QUALITY GATE] Do I have enough understanding?
    |
    +---> No -----> Go back to EXPLORE
    +---> Yes ----> PROCEED to planning/implementation
```

---

## Thoroughness Levels

### QUICK (Small, isolated changes)

**When:** Single file edit, well-understood area, clear requirements.

**Minimum exploration:**
- Read the target file
- Read the most relevant test file
- Check for recent changes to the target (`git log -5 <file>`)

**Time budget:** 1-2 minutes of exploration

### MEDIUM (Cross-cutting changes)

**When:** Multiple files affected, touches shared code, new integration.

**Minimum exploration:**
- Read all target files
- Read related test files
- Search for all usages of modified interfaces/functions
- Check the dependency graph (what imports/uses the target?)
- Review recent commits in the area (`git log -10 --oneline <directory>`)
- Check for configuration files that might be affected

**Time budget:** 3-5 minutes of exploration

### VERY THOROUGH (Architectural changes)

**When:** New subsystem, refactoring, anything touching core abstractions.

**Minimum exploration:**
- Everything in MEDIUM, plus:
- Map the full module/package structure
- Read architectural documentation if it exists
- Trace the request/data flow end-to-end
- Identify all integration points
- Check for feature flags or conditional behavior
- Review related pull requests or issues
- Understand the testing strategy for the area

**Time budget:** 5-15 minutes of exploration

---

## Quality Gates Before Implementation

Before proceeding to make changes, verify you can answer these questions:

### Gate 1: Understanding
- [ ] Can I explain what the current code does in plain language?
- [ ] Do I know WHY it was written this way (not just WHAT it does)?
- [ ] Have I identified any non-obvious constraints or invariants?

### Gate 2: Impact Analysis
- [ ] Do I know every file that will need to change?
- [ ] Have I identified all callers/consumers of the code I will modify?
- [ ] Do I understand the test coverage for this area?

### Gate 3: Risk Assessment
- [ ] What could go wrong with my planned change?
- [ ] Are there edge cases I need to handle?
- [ ] Could my change break something in a non-obvious way?

### Gate 4: Pattern Conformance
- [ ] Does my planned change follow existing patterns in the codebase?
- [ ] Am I introducing any new patterns? If so, is that justified?
- [ ] Will my change be consistent with the surrounding code style?

---

## Exploration Techniques

### Finding Related Code

```
# Find all files in a module/package
Glob: src/modulename/**/*

# Find all usages of a function or class
Grep: "functionName" across the codebase

# Find all implementations of an interface
Grep: "implements InterfaceName" or language-appropriate pattern

# Find test files for a module
Glob: **/test*/**/ModuleName* or **/ModuleName*.test.*
```

### Understanding Dependencies

```
# What does this file import/depend on?
Read the file, examine import statements

# What depends on this file?
Grep for the filename or its exports across the codebase

# What is the dependency direction?
Map out: A imports B, B imports C, etc.
```

### Understanding History

```
# Recent changes to a file
git log -10 --oneline <file>

# What changed and why
git log -5 --format="%h %s" <file>

# Who has been working in this area
git log -20 --format="%an" <directory> | sort | uniq -c | sort -rn
```

---

## Anti-Patterns

### The Eager Editor
**Problem:** Jumping to Edit/Write before reading enough code.
**Fix:** Force yourself to use Read/Grep/Glob at least 3 times before any edit.

### The Tunnel Vision
**Problem:** Reading only the file you plan to change.
**Fix:** Always read at least one level of dependencies in each direction.

### The Assumption Maker
**Problem:** Assuming code works a certain way based on naming.
**Fix:** Read the actual implementation. Names lie. Code does not.

### The History Ignorer
**Problem:** Not checking git history for context on why code exists.
**Fix:** Always run `git log` on files you plan to change.

---

## When to Skip Deep Exploration

You may use QUICK thoroughness even for larger changes when:
- You have already explored this area in the current conversation
- The user has provided comprehensive context in their message
- You are executing a pre-approved plan that already includes context
- The change is purely additive (new file, no existing code modified)

Even in these cases, verify your assumptions with at least one Read operation.
