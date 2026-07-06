# ClaudeKit Architecture

## System Overview

ClaudeKit is a multi-agent orchestration framework for Claude Code. It provides structured workflows, safety guardrails, and reusable knowledge (skills) to coordinate AI-driven software development across planning, implementation, review, and deployment.

```
+------------------------------------------------------------------+
|                          ClaudeKit                                |
|                                                                   |
|  +-----------+   +-----------+   +-----------+   +-------------+ |
|  |  CLI      |   |  Agents   |   |  Skills   |   |  Operations | |
|  |  Layer    |   |  Layer    |   |  Registry |   |  Engine     | |
|  +-----------+   +-----------+   +-----------+   +-------------+ |
|       |               |               |                |          |
|  +-----------+   +-----------+   +-----------+   +-------------+ |
|  |  Config   |   |  Hooks    |   |  Security |   |  Backup     | |
|  |  System   |   |  System   |   |  Layer    |   |  System     | |
|  +-----------+   +-----------+   +-----------+   +-------------+ |
|                                                                   |
|  +-----------+   +-----------+   +-----------+   +-------------+ |
|  |  File     |   |  Handoff  |   |  Scoring  |   |  Templates  | |
|  |  State    |   |  Protocol |   |  Gates    |   |  Engine     | |
|  +-----------+   +-----------+   +-----------+   +-------------+ |
+------------------------------------------------------------------+
```

### Directory Layout

```
claudekit/
├── .claude/
│   ├── agents/           # 28 specialized agent definitions
│   │   ├── _shared/      # Shared agent configuration
│   │   ├── coordinator.md
│   │   ├── planner.md
│   │   ├── reviewer.md
│   │   ├── implementer.md
│   │   ├── verifier.md
│   │   ├── debugger.md
│   │   ├── documenter.md
│   │   ├── gitOps.md
│   │   ├── explore.md
│   │   ├── tester.md
│   │   ├── security-scanner.md
│   │   ├── devops.md
│   │   └── database-architect.md
│   ├── commands/         # 39 slash commands
│   ├── skills/           # 73 skill modules + registry
│   │   ├── skills-registry.json
│   │   └── <skill-name>/SKILL.md
│   ├── hooks/            # Lifecycle hooks
│   │   ├── config.json
│   │   ├── pre-commit.sh
│   │   ├── post-implement.sh
│   │   ├── pre-plan.sh
│   │   ├── pre-push.sh
│   │   └── post-tool-use.sh
│   ├── operations/       # Operations engine
│   │   └── scripts/
│   │       ├── validate-config-json.py
│   │       ├── execute-json-ops.py
│   │       ├── restore-backup.py
│   │       ├── shared.py
│   │       └── operations-schema.json
│   ├── settings.json     # Official Claude Code hooks configuration
│   └── local/            # Templates for CLAUDE.md and CONSTITUTION.md
├── src/
│   ├── cli/              # CLI entry point
│   └── security/         # Command validator, path guard
├── templates/            # Language-specific templates (11 languages)
├── tests/                # Test suite
├── docs/                 # Documentation
└── install.sh            # Installation script
```

---

## Workflow Engine

The workflow engine drives tasks through a defined sequence of agents. Every task follows one of two paths depending on complexity.

### Standard Workflow

```
  User Request
       |
       v
  +------------+
  | Coordinator|  (1) Classify task type
  +-----+------+
        |
        v
  +------------+
  |  Explorer  |  (2) Analyze codebase, discover patterns
  +-----+------+
        |
        v
  +------------+
  |  Planner   |  (3) Create plan + ops.json
  +-----+------+
        |
        v
  +------------+     FAIL (< 90)
  |  Reviewer  |  (4) Score plan --------+
  +-----+------+                         |
        | PASS (>= 90)                   |
        v                                |
  +------------+              +----------v---------+
  |Implementer |  (5)        | Planner (revision)  |
  +-----+------+              +--------------------+
        |                     (max 3 iterations)
        v
  +------------+     FAIL (< 80)
  |  Verifier  |  (6) Quality check -----+
  +-----+------+                          |
        | PASS (>= 80)                    |
        v                     +-----------v--------+
  +------------+              |Implementer (retry)  |
  |   GitOps   |  (7)        +--------------------+
  +------------+              (max 3 iterations)
```

### Task Classification

The Coordinator classifies every incoming request before routing:

| Type | Pipeline | Description |
|------|----------|-------------|
| Feature | Full pipeline | New functionality requiring plan and review |
| Bug | Debugger-first | Diagnosis, then plan, implement, verify |
| Refactor | Planner-first | Structural changes with safety checks |
| Quality | Verifier-first | Test coverage, linting, performance |
| Docs | Documenter | Documentation generation or updates |
| Git | GitOps | Branch management, PRs, releases |
| Explore | Explorer | Read-only codebase analysis |

### Coordinator-Driven Workflow (Complex Tasks)

For tasks requiring 3 or more agents, the Coordinator provides active orchestration:

1. Spawns each agent as a fresh subagent (clean context window)
2. Manages file-based handoffs between agents using the Handoff Protocol
3. Tracks state in `operations/{task-name}/state.json`
4. Handles revision loops with a maximum of 3 iterations per gate
5. Escalates to the user when stuck (after 3 failed iterations)

### Handoff Protocol

Every agent-to-agent transition follows a structured format:

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

## Agent Orchestration

### Agent Architecture

```
+-------------------------------------------------------------------+
|                         COORDINATOR                                |
|  Classifies tasks, selects pipelines, manages handoffs            |
+---+----------+----------+-----------+----------+----------+-------+
    |          |          |           |          |          |
    v          v          v           v          v          v
+-------+ +-------+ +---------+ +--------+ +-------+ +---------+
|EXPLORE| |PLANNER| |REVIEWER | |IMPLMNT | |VERIFY | | GITOPS  |
| read  | | plan  | |validate | |execute | |quality| | version |
+-------+ +-------+ +---------+ +--------+ +-------+ +---------+
                                     |
              +----------------------+----------------------+
              |                      |                      |
          +-------+            +----------+           +----------+
          |TESTER |            | DEBUGGER |           |DOCUMENTER|
          | tests |            | diagnose |           |  docs    |
          +-------+            +----------+           +----------+

+-------------------------------------------------------------------+
|              SPECIALIST AGENTS (domain-specific)                   |
+----------+-------------------+-----------+------------------------+
|SEC-SCAN  |  DATABASE-ARCHT  |  DEVOPS   |                        |
|security  |  schema/migrate  |  CI/CD    |                        |
+----------+-------------------+-----------+------------------------+
```

### The 13 Agents

| Agent | Role | Tools | Key Skills |
|-------|------|-------|------------|
| coordinator | Orchestration hub | Read, Grep, Glob, Bash, Agent | multi-agent-coordination, dispatching-parallel-agents |
| explore | Read-only codebase analysis | Read, Grep, Glob | using-superpowers |
| planner | Implementation planning | Read, Grep, Glob, Bash | writing-plans, generate-operations-config |
| reviewer | Plan and code validation | Read, Grep, Glob | validate-operations-config, clean-architecture |
| implementer | Code execution | Read, Grep, Glob, Bash, Edit, Write | execute-operations-config, test-driven-development |
| verifier | Quality assurance | Read, Grep, Glob, Bash | verification-before-completion, performance-guidelines |
| debugger | Root cause analysis | Read, Grep, Glob, Bash | systematic-debugging |
| tester | Test creation and execution | Read, Grep, Glob, Bash, Edit, Write | test-driven-development, property-based-testing |
| documenter | Documentation generation | Read, Grep, Glob, Edit, Write | documentation-standards |
| gitOps | Version control operations | Read, Grep, Glob, Bash | git-workflow, using-git-worktrees |
| security-scanner | Security auditing | Read, Grep, Glob, Bash | security-checklist, supply-chain-audit |
| devops | CI/CD and infrastructure | Read, Grep, Glob, Bash, Edit, Write | ci-cd-pipeline, containerization-patterns |
| database-architect | Schema and migration design | Read, Grep, Glob, Bash | database-migration-patterns, performance-guidelines |

### Agent Skill Loading

Every agent loads skills on startup in a defined order:

1. **Mandatory skills first**: `using-superpowers` (skill discovery), `golden-rule` (no code changes without approval)
2. **Agent-specific skills**: Loaded from `skills-registry.json` agentMapping
3. **On-demand skills**: Discovered and loaded via the `using-superpowers` protocol during execution

The skills registry (`skills-registry.json`) maps each agent to its skill set:

```
agentMapping:
  coordinator -> [using-superpowers, golden-rule, multi-agent-coordination, ...]
  planner     -> [using-superpowers, golden-rule, writing-plans, brainstorming, ...]
  reviewer    -> [using-superpowers, golden-rule, validate-operations-config, ...]
  ...
```

---

## Hook Lifecycle

ClaudeKit hooks into Claude Code's official hook system via `.claude/settings.json`. Hooks execute at specific lifecycle boundaries to enforce safety and track state.

### Hook Execution Points

```
  Session Start
       |
       v
  +------------------+
  | SessionStart     |  Log session metadata
  +--------+---------+
           |
           v
  +------------------+
  | UserPromptSubmit |  Detect plan creation -> run pre-plan.sh
  +--------+---------+
           |
           v
  +------------------+
  | PreToolUse       |  Before Bash: intercept git commit / git push
  |  (Bash matcher)  |  Run pre-commit.sh or pre-push.sh
  +--------+---------+
           |
           v
  +------------------+
  | [Tool Executes]  |
  +--------+---------+
           |
           v
  +------------------+
  | PostToolUse      |  After Edit/Write/Bash: track modifications
  |  (Edit|Write|    |  Run post-tool-use.sh
  |   Bash matcher)  |
  +--------+---------+
           |
           v
  +------------------+
  | Stop             |  Log session end, summarize modifications
  +--------+---------+
           |
           v
  +------------------+
  | SubagentStop     |  Log subagent completion
  +------------------+
```

### Hook Details

| Hook Point | Matcher | Script | Purpose |
|------------|---------|--------|---------|
| PreToolUse | Bash (git commit) | pre-commit.sh | Validate ops configs, check for secrets before commit |
| PreToolUse | Bash (git push) | pre-push.sh | Full validation suite before pushing to remote |
| PostToolUse | Edit\|Write\|Bash | post-tool-use.sh | Track file modifications, validate tool output |
| UserPromptSubmit | (all) | pre-plan.sh | Detect plan-related prompts, check for duplicate plans |
| SessionStart | (all) | inline logging | Record session metadata to hooks.log |
| Stop | (all) | inline logging | Log session completion |
| SubagentStop | (all) | inline logging | Log subagent task completion |

### Hook Configuration

Hooks are configured in two locations:

1. **`.claude/settings.json`** (primary): Official Claude Code hook format with matchers, used at runtime
2. **`.claude/hooks/config.json`** (legacy): Retained for backward compatibility; project command configuration read by scripts

Hook scripts read project-specific commands (build, test, lint, coverage) from `config.json` so they never hardcode build tools.

---

## Operations Pipeline

The operations engine provides safe, auditable, and reversible code modifications through a structured pipeline.

### Pipeline Flow

```
                    +------------------+
                    |   ops.json       |  Declarative operations config
                    +--------+---------+
                             |
                             v
                    +------------------+
                    | validate-config  |  29 validation guards
                    | -json.py         |  Schema, paths, conflicts,
                    +--------+---------+  protected files, sizes
                             |
                        PASS | FAIL -> abort with detailed errors
                             v
                    +------------------+
                    | execute-json     |  Atomic execution engine
                    | -ops.py          |
                    +--------+---------+
                             |
                    +--------+---------+
                    |                  |
                    v                  v
           +---------------+  +---------------+
           | Backup every  |  | Execute ops   |
           | target file   |  | (temp + rename)|
           +-------+-------+  +-------+-------+
                   |                   |
                   v                   v
           +---------------+  +---------------+
           | backups/      |  | Success       |
           | {plan}-{ts}/  |  | report        |
           | manifest.json |  +---------------+
           +---------------+          |
                                 FAIL | -> automatic rollback
                                      v
                              +---------------+
                              | restore-      |
                              | backup.py     |
                              +---------------+
```

### Validation Guards (29 checks)

The validator (`validate-config-json.py`) enforces:

- **Schema compliance**: JSON structure matches `operations-schema.json`
- **Path safety**: No traversal (`../`), no null bytes, no absolute paths outside project
- **Protected files**: Blocks modification of `.git/`, `node_modules/`, lock files
- **File size limits**: Prevents creation of excessively large files
- **Conflict detection**: No duplicate targets across operations
- **Operation type validation**: Only allowed operation types (create, modify, delete, rename)
- **Content validation**: Required fields present for each operation type
- **Backup feasibility**: Target files exist for modify/delete operations

### Execution Safety

The executor (`execute-json-ops.py`) guarantees:

- **Pre-execution backup**: Every target file copied to `backups/{plan}-{timestamp}/`
- **Manifest tracking**: `manifest.json` records original paths, checksums, and timestamps
- **Atomic writes**: Operations use temp file + rename to prevent partial writes
- **Execution lock**: Prevents concurrent execution of operations
- **Automatic rollback**: On any failure mid-execution, all changes are reverted from backup
- **Dry-run mode**: Preview all changes without applying them

### Rollback

The restore script (`restore-backup.py`) can:

- List all available backups with timestamps and metadata
- Restore from any specific backup directory
- Preview restore operations in dry-run mode
- Verify backup integrity before restoration

---

## CLI Execution Flow

The CLI (`src/cli/main.py`) provides the `claudekit` (and `ck` shorthand) command.

```
  claudekit <command> [args]
       |
       v
  +------------------+
  | Argument Parser  |  Parse command and flags
  +--------+---------+
           |
           +-- init     -> Copy .claude/ to target, apply templates
           +-- doctor   -> Run 9+ health checks, report status
           +-- validate -> Invoke validate-config-json.py
           +-- execute  -> Invoke execute-json-ops.py with backup
           +-- rollback -> Invoke restore-backup.py
           +-- agents   -> Read agents/*.md, display metadata
           +-- config   -> Read hooks/config.json, query keys
```

### Doctor Checks

The `doctor` command runs these health checks:

1. Python version (>= 3.8)
2. Bash availability
3. Git availability
4. Agent count and validity (13 expected)
5. Command count and validity (17 expected)
6. Skills registry integrity (all agentMapping IDs exist in skills array)
7. Hook scripts present and executable
8. Operations scripts present
9. Config file validity (JSON parse)

---

## Configuration Loading Order

ClaudeKit supports three tiers of configuration, loaded in precedence order:

```
  +----------------------------+
  |  Enterprise Config         |  Highest priority
  |  (organization-wide)       |  ~/.claude/enterprise-settings.json
  +-------------+--------------+
                |
  +-------------v--------------+
  |  Personal Config           |  User-level overrides
  |  (user preferences)        |  ~/.claude/settings.json
  +-------------+--------------+
                |
  +-------------v--------------+
  |  Project Config            |  Lowest priority (most specific)
  |  (repo-specific)           |  .claude/settings.json
  +----------------------------+  .claude/hooks/config.json
```

**Resolution rules:**
- Higher tiers override lower tiers for the same key
- Project config is the most commonly edited
- Enterprise config can enforce policies that projects cannot override
- Hook scripts read project commands from `.claude/hooks/config.json`

---

## Plugin and Skill System

### Skill Architecture

Skills are markdown documents with YAML frontmatter, organized as self-contained modules:

```
.claude/skills/
├── skills-registry.json          # Central index
├── using-superpowers/SKILL.md    # Mandatory: skill discovery protocol
├── golden-rule/SKILL.md          # Mandatory: no code changes without approval
├── writing-plans/SKILL.md        # Planner: plan structure and ops.json
├── systematic-debugging/SKILL.md # Debugger: 4-phase investigation
├── ...                           # 73 skills total
```

### Registry Structure

The `skills-registry.json` contains:

- **skills array**: Every skill with id, name, path, mandatory flag, usedBy agents, description
- **agentMapping**: Maps each of the 28 agents to its ordered list of skill IDs
- **version**: Registry format version for compatibility checks

### Skill Loading Protocol

```
  Agent Startup
       |
       v
  Load using-superpowers  (mandatory, always first)
       |
       v
  Load golden-rule        (mandatory, always second)
       |
       v
  Load agent-specific     (from agentMapping in registry)
  skills in order
       |
       v
  On-demand discovery     (using-superpowers protocol queries
       |                   registry for additional skills
       v                   when domain expertise is needed)
  Agent Ready
```

### Skill Categories

| Category | Skills | Used By |
|----------|--------|---------|
| Governance | using-superpowers, golden-rule, constitution, clarify | All agents |
| Planning | writing-plans, brainstorming, refactoring-patterns, spec-driven-development | Planner |
| Operations | generate-operations-config, validate-operations-config, execute-operations-config | Planner, Reviewer, Implementer |
| Quality | test-driven-development, verification-before-completion, property-based-testing | Implementer, Verifier, Tester |
| Security | security-checklist, dependency-audit, supply-chain-audit, insecure-defaults, differential-security-review, static-analysis-integration | Reviewer, Verifier, Security-Scanner |
| Architecture | clean-architecture, api-design-patterns, database-migration-patterns, performance-guidelines | Planner, Reviewer, Database-Architect |
| DevOps | git-workflow, using-git-worktrees, finishing-a-development-branch, ci-cd-pipeline, containerization-patterns, monitoring-observability | GitOps, DevOps |
| Domain | error-handling, documentation-standards, accessibility-standards, i18n-patterns, incident-response, code-explanation | Various specialists |
| Meta | writing-skills, multi-agent-coordination, dispatching-parallel-agents, subagent-driven-development | Coordinator, All |

---

## Security Architecture

ClaudeKit implements defense-in-depth security across multiple layers.

> **Speed bump, not a sandbox.** The command and path validators are a
> *denylist speed bump*: they raise the cost of an accidental or low-effort
> destructive operation. They are **not** a security boundary and will not
> contain a determined adversary (obfuscation, novel interpreters, and
> environment-dependent shell expansion can evade a static check). For real
> isolation, run Claude Code under OS-level sandboxing (containers, seccomp,
> restricted users). See `SECURITY.md`.

### Layer 1: Command Validation

The `CommandValidator` (`src/claudekit/security/command_validator.py`) is wired
into a **`PreToolUse` Bash hook** (`.claude/hooks/command-guard.sh`) and exposed
as `claudekit check-command "<cmd>"`. It inspects **every** segment of a chained
command (`a && b`, `a | b`, `a; b`) plus the contents of command substitutions
(`$(...)`, backticks) — not just the first word.

Rollout is gated by `ECC_HOOK_PROFILE`:

| Profile    | Behavior                                              |
|------------|-------------------------------------------------------|
| `strict`   | **Blocks** (exit 2 + reason on stderr); fail-closed   |
| `standard` | **Warns** only (default) — logs what it would block   |
| `minimal`  | Off                                                   |

Validation pipeline:

```
  Command Input
       |
       v
  +------------------+
  | Empty check      |  Reject blank/whitespace commands
  +--------+---------+
           |
  +--------v---------+
  | Pattern check    |  Block: eval/exec, IFS evasion, redirect to
  |                  |  /etc /dev /sys, find -delete/-exec, python
  |                  |  os.system()/subprocess smuggling, fork bombs
  +--------+---------+
           |
  +--------v---------+
  | Substitution     |  Validate $(...) / backtick payloads
  | check            |  (blocklist-only, so $(date) passes)
  +--------+---------+
           |
  +--------v---------+
  | Segment split    |  Split on ; && || | & and validate EACH
  |                  |  segment's base command (rm, sudo, curl…)
  +--------+---------+
           |
  +--------v---------+
  | Blocklist +      |  Block: rm, sudo, curl, dd, chmod…
  | Allowlist (safe) |  Safe mode: base must be allowlisted.
  |                  |  bash/sh/env/xargs are NOT allowlisted.
  +--------+---------+
           |
           v
  (allowed, reason) or (blocked, reason)
```

### Layer 2: Path Guarding

The `PathGuard` (`src/claudekit/security/path_guard.py`) is exposed as
`claudekit check-path <path>` and validates file paths at **component**
granularity (so `my.envelope.txt` is not mistaken for `.env`):

- **Project boundary**: Paths must resolve within the project root
- **Traversal detection**: Blocks `../` sequences after path resolution
- **Symlink escapes**: Follows symlinks (relative targets resolved against the
  link's own directory) and blocks any that point outside the project root
- **Protected files**: `.env`, `.git/config`, `.ssh/`, `.aws/credentials`, etc.,
  matched per path component (not substring)
- **Null byte injection**: Rejects paths containing `\x00`
- **System path protection**: Blocks `/etc`, `/usr`, `/dev`, and other system directories
- **Directory depth limits**: Prevents excessively deep directory creation (> 20 levels)
- **Empty path rejection**: Blank paths are rejected

### Layer 3: Operations Safety

The operations engine provides:

- 29 validation guards before any code modification
- Atomic writes preventing partial file corruption
- Automatic backup before every modification
- Execution locks preventing concurrent operations
- Automatic rollback on any failure

### Layer 4: Hook-Based Enforcement

- **Pre-commit hook**: Validates operations configs, scans for secrets
- **Pre-push hook**: Full validation suite before remote push
- **Post-tool-use hook**: Tracks all file modifications for audit
- **Pre-plan hook**: Detects and prevents duplicate plans

### Layer 5: Agent Governance

- **Golden Rule**: No code changes without explicit user approval (mandatory skill)
- **Constitution**: Project-specific governance rules enforced by all agents
- **Scoring gates**: Plan review (>= 90/100) and quality verification (>= 80/100)
- **Escalation protocol**: 3 failed iterations triggers user escalation

---

## File-Based State Management

Agents communicate exclusively through files, not shared memory or context windows.

### Operations Directory Structure

```
operations/{task-name}/
├── explore.md          # Phase 1: Codebase analysis and pattern discovery
├── plan.md             # Phase 2: Implementation plan (human-readable)
├── ops.json            # Phase 2: Machine-executable operations config
├── reviewer.md         # Phase 2: Review feedback with score
├── implementation.md   # Phase 3: Execution results (on success)
├── issues.md           # Phase 3: Error details (on failure)
├── verification.md     # Phase 4: Quality check results with score
└── state.json          # Coordinator workflow state (optional)
```

### Information Flow

```
  Explorer writes    explore.md
       |
       v
  Planner reads      explore.md
  Planner writes     plan.md + ops.json
       |
       v
  Reviewer reads     plan.md + ops.json
  Reviewer writes    reviewer.md (score + feedback)
       |
       v
  [score >= 90?]
       |
  YES: Implementer reads    ops.json + plan.md
       Implementer writes   implementation.md (or issues.md)
       |
       v
  Verifier reads     implementation.md
  Verifier writes    verification.md (score + findings)
       |
       v
  [score >= 80?]
       |
  YES: GitOps reads  implementation.md + verification.md
       GitOps executes commit/branch/PR
```

### Benefits of File-Based State

| Benefit | Description |
|---------|-------------|
| Token efficiency | 85% reduction vs. passing full context between agents |
| Crash recovery | Work persists on disk; agents can resume from last file |
| Audit trail | Complete record of every decision and artifact |
| Parallel execution | Multiple agents can read shared files concurrently |
| Debuggability | Humans can inspect any intermediate state |

---

## Token Efficiency

ClaudeKit achieves approximately 85% token reduction compared to single-context approaches through several mechanisms:

### Fresh Subagent Spawning

Each agent starts with a clean context window containing only:
- Its agent definition (system prompt)
- Loaded skills (compact markdown)
- The specific input file(s) it needs to read

This avoids accumulating the full conversation history across the entire pipeline.

### File Handoffs vs. Context Passing

```
  Traditional approach:
  [User prompt + Explorer output + Planner output + Reviewer output]
  = ~50,000 tokens in Implementer's context

  ClaudeKit approach:
  [Implementer prompt + skills + ops.json content]
  = ~8,000 tokens in Implementer's context
```

### Compact Skill Format

Skills are terse markdown documents focused on actionable rules, not explanations. The `using-superpowers` skill teaches agents to load additional skills on demand rather than preloading everything.

---

## Scoring and Quality Gates

### Plan Review Gate (Reviewer Agent)

```
Score = Plan_Quality (40%) + Architecture (30%) + Security (30%)

Plan_Quality:  Completeness, clarity, ops.json validity
Architecture:  Layer boundaries, dependency direction, patterns
Security:      Input validation, auth, data protection

Gate: score >= 90 -> Approved
      score <  90 -> Return to Planner with feedback (max 3 iterations)
```

### Quality Verification Gate (Verifier Agent)

```
Score = Static_Analysis (30%) + Tests (40%) + Coverage (30%)

Static_Analysis:  Linting, type checks, code smells
Tests:            All tests pass, new tests for new code
Coverage:         Meets project threshold (configurable)

Gate: score >= 80 -> Passed
      score <  80 -> Return to Implementer with issues (max 3 iterations)
```

### Escalation Protocol

```
  Iteration 1: Agent attempts task
       |
  FAIL v
  Iteration 2: Agent retries with feedback
       |
  FAIL v
  Iteration 3: Agent retries with accumulated feedback
       |
  FAIL v
  ESCALATE: Coordinator notifies user with:
    - Summary of all 3 attempts
    - Specific blockers identified
    - Options: proceed anyway, revise manually, or abort
```

---

## Design Principles

1. **Copy, not symlink** -- After installation, the project is fully self-contained with no external dependencies on the ClaudeKit source.

2. **Config-driven** -- No hardcoded build commands. All project-specific commands (build, test, lint, coverage) are read from configuration.

3. **File-based handoffs** -- Agents never share context windows. All communication flows through files on disk.

4. **Fail-safe** -- Every file modification is backed up first. Failures trigger automatic rollback.

5. **Governance as code** -- The Constitution and Golden Rule are enforced by agents as mandatory skills, not by convention.

6. **Defense in depth** -- Security operates at five layers: command validation, path guarding, operations safety, hook enforcement, and agent governance.

7. **Token efficiency** -- Fresh subagents with file-based handoffs reduce context window usage by approximately 85%.

8. **Audit everything** -- File state, hook logs, backup manifests, and scoring reports provide a complete audit trail.

9. **Escalate, never guess** -- After 3 failed iterations at any gate, the system escalates to the human rather than making increasingly uncertain attempts.

10. **Language agnostic** -- Templates for 11 languages (Python, TypeScript, Java, Go, Kotlin, Swift, Rust, C#, Ruby, PHP, generic) with project-specific configuration.
