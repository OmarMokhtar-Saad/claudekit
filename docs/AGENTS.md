# Agents

ClaudeKit ships 28 specialized agents, each with a single responsibility. The
core orchestration agents are documented in detail below; run `ck agents` (or
`claudekit agents`) to list every installed agent, including the extended suite.

## Agent Summary

| Agent | File | Color | Model | Permissions |
|-------|------|-------|-------|-------------|
| Coordinator | `coordinator.md` | Gray | Sonnet | READ, SPAWN |
| Planner | `planner.md` | Cyan | Sonnet | READ, WRITE (plans only) |
| Reviewer | `reviewer.md` | Blue | Opus | READ |
| Implementer | `implementer.md` | Green | Sonnet | READ, WRITE, EXECUTE |
| Verifier | `verifier.md` | Purple | Haiku | READ, EXECUTE |
| Debugger | `debugger.md` | Red | Opus | READ |
| Documenter | `documenter.md` | Teal | Haiku | READ, WRITE (docs only) |
| GitOps | `gitOps.md` | Orange | Haiku | READ, WRITE, EXECUTE (git) |
| Explore | `explore.md` | Yellow | Sonnet | READ |
| Tester | `tester.md` | Lime | Sonnet | READ, WRITE, EXECUTE |
| Security Scanner | `security-scanner.md` | Crimson | Opus | READ, EXECUTE |
| DevOps | `devops.md` | Bronze | Sonnet | READ, WRITE, EXECUTE |
| Database Architect | `database-architect.md` | Indigo | Sonnet | READ, WRITE |

## Coordinator

**Purpose**: Orchestrate complex multi-agent workflows.

**When to use**: Tasks requiring 3+ agents, parallel execution, failure recovery.

**Capabilities**:
- Routes tasks to appropriate agents based on classification
- Manages revision loops (plan ↔ review, max 3 iterations)
- Tracks workflow state via file system
- Handles implementation failure recovery
- Detects deadlocks and escalates

**Cannot**: Edit code, write files, execute build commands.

## Planner

**Purpose**: Create implementation plans with operations configs.

**Workflow**:
1. Explore codebase for target files
2. Create plan with approach, affected files, risk assessment
3. Generate `ops.json` operations config
4. Auto-trigger Reviewer

**Output**: `operations/{task-name}/plan.md` + `ops.json`

**Key rule**: ALL plans MUST include ops.json. No exceptions.

## Reviewer

**Purpose**: Validate plans against quality, architecture, and security.

**Scoring** (90/100 threshold):
- Plan Quality: 40% — Config valid, paths correct, patterns accurate
- Architecture: 30% — Layer compliance, dependency direction
- Security: 30% — No secrets, input validation, safe operations

**Auto-reject triggers**: Missing ops.json, architecture violations.

## Implementer

**Purpose**: Execute approved plans.

**Iron Law**: When `ops.json` exists, MUST use the execution script. Manual edits FORBIDDEN.

```bash
python3 .claude/operations/scripts/execute-json-ops.py operations/{plan}/ops.json
```

**Fallback**: Manual implementation only when no ops.json exists.

## Verifier

**Purpose**: Quality validation after implementation.

**Scoring** (80/100 threshold):
- Static Analysis: 30%
- Test Results: 40%
- Coverage: 30%

**Actions by score**:
- ≥80%: PASS → proceed to GitOps
- 60-79%: RETRY → return to Implementer (max 2x)
- <60%: FAIL → escalate to user

## Debugger

**Purpose**: Read-only bug diagnosis.

**Cannot**: Edit code, write files, apply fixes.

**Workflow**:
1. Gather context (error, stack trace, logs)
2. Pattern match against known categories
3. Analyze logs
4. Identify root cause
5. Handoff to Planner (≥70% confidence) or request more context

## Documenter

**Purpose**: Create and update technical documentation.

**Can write**: README files, API docs, guides, changelogs, architecture docs.

**Cannot**: Edit source code, run builds.

## GitOps

**Purpose**: Safe version control operations.

**Safety rules** (non-negotiable):
- Never force-push to main/master
- Never delete remote branches without approval
- Always check for secrets before commit
- Always verify current branch

**Operations**: Branch creation, commits, pushes, PRs, releases.

## Explore

**Purpose**: Fast codebase exploration and pattern discovery.

**Read-only**. Three thoroughness levels:
- `quick`: 1-2 searches, <5K tokens
- `medium`: 3-5 searches, <10K tokens (default)
- `very thorough`: 6+ searches, <20K tokens

## Tester

**Purpose**: Dedicated test writer — generates unit, integration, and E2E tests, coverage gap analysis.

**Capabilities**:
- Generates unit, integration, and end-to-end tests
- Identifies coverage gaps and suggests tests to fill them
- Works with any test framework the project uses

**Cannot**: Modify production source code.

## Security Scanner

**Purpose**: Active SAST scanning, CVE detection, secret scanning, and config hardening.

**Capabilities**:
- Static application security testing (SAST)
- CVE detection in dependencies
- Secret scanning across codebase
- Configuration hardening recommendations

**Cannot**: Modify source code, deploy changes.

## DevOps

**Purpose**: CI/CD pipelines, Docker, Kubernetes, and environment management.

**Capabilities**:
- CI/CD pipeline design and configuration
- Docker and container orchestration
- Kubernetes manifests and Helm charts
- Environment provisioning and management

**Cannot**: Access production systems directly.

## Database Architect

**Purpose**: Schema design, migration planning, query optimization, and data modeling.

**Capabilities**:
- Database schema design and normalization
- Migration planning with zero-downtime strategies
- Query optimization and indexing recommendations
- Data modeling and relationship design

**Cannot**: Execute migrations on production databases.

## Shared Templates

Located in `agents/_shared/`:

| Template | Purpose |
|----------|---------|
| AGENT_TEMPLATE.md | Standard initialization and safety rules |
| VERIFICATION_PROTOCOL.md | Evidence-based completion claims |
| OUTPUT_TEMPLATE.md | Silent mode output standards |
| CONTEXT_CLEANUP_PROTOCOL.md | Context clearing between phases |
| TASK_TOOL_SPECIFICATION.md | Task tool patterns |
| VALIDATION_CHECKLIST.md | Pre-flight validation |
| WORKFLOW_FILE_TEMPLATES.md | Workflow file structure |

## Adding a Custom Agent

1. Create `agents/my-agent.md` using the template:

```markdown
---
name: my-agent
description: What this agent does
color: magenta
model: sonnet
---

## Agent Identity
**Permissions**: READ, WRITE
**Single Responsibility**: [one thing]

## Workflow
[steps]

## Output Format
[format]

## Handoff
[when and to whom]
```

2. Create a matching command in `commands/my-agent.md`
3. Update skills registry if the agent uses specific skills
