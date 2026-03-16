# Architecture

## Overview

ClaudeKit is a multi-agent system where each agent has a single responsibility. Agents communicate through file-based handoffs and follow a structured workflow.

## Agent Interaction Model

```
                    ┌─────────────────┐
                    │   COORDINATOR   │  Orchestrates complex workflows
                    └────────┬────────┘
                             │ routes to
         ┌───────────────────┼───────────────────┐
         │                   │                   │
    ┌────▼────┐        ┌────▼────┐        ┌────▼────┐
    │ EXPLORE │        │ PLANNER │        │ DEBUGGER│
    │(read)   │        │(plan)   │        │(read)   │
    └────┬────┘        └────┬────┘        └────┬────┘
         │                  │                   │
         │            ┌─────▼─────┐             │
         └───────────►│ REVIEWER  │◄────────────┘
                      │(validate) │
                      └─────┬─────┘
                            │ ≥90%
                      ┌─────▼──────┐
                      │IMPLEMENTER │
                      │(execute)   │
                      └─────┬──────┘
                            │
                      ┌─────▼─────┐
                      │ VERIFIER  │
                      │(quality)  │
                      └─────┬─────┘
                            │ ≥80%
                      ┌─────▼─────┐
                      │  GITOPS   │     ┌──────────┐
                      │(version)  │     │DOCUMENTER│
                      └───────────┘     │(docs)    │
                                        └──────────┘
```

## Workflow Phases

### Standard Workflow (Plan → Review → Implement → Verify)

1. **Explore**: Codebase analysis, pattern discovery
2. **Plan**: Create implementation plan with ops.json
3. **Review**: Validate plan (90/100 threshold)
4. **Implement**: Execute ops.json via Python scripts
5. **Verify**: Quality checks (80/100 threshold)
6. **GitOps**: Commit, branch, PR

### Coordinator-Driven Workflow (Complex Tasks)

For tasks requiring 3+ agents, the Coordinator:
- Spawns agents with fresh context (token savings)
- Manages revision loops (max 3 iterations)
- Handles failure recovery
- Escalates to user when stuck

## File-Based State Management

```
operations/{task-name}/
├── explore.md          # Phase 1: Exploration findings
├── plan.md             # Phase 2: Implementation plan
├── ops.json            # Phase 2: Operations config
├── reviewer.md         # Phase 2: Review feedback + score
├── implementation.md   # Phase 3: Results (on success)
├── issues.md           # Phase 3: Error details (on failure)
├── verification.md     # Phase 4: Quality results
└── state.json          # Coordinator state (optional)
```

Each agent writes to its designated file. The next agent reads from the previous agent's file. This provides:
- 85% token reduction vs passing full context
- Crash recovery via file state
- Audit trail of all decisions

## Operations System

The operations system provides safe, auditable code modifications:

```
ops.json → validate-config-json.py → execute-json-ops.py → backups/
                (29 guards)           (atomic + rollback)   (manifest)
```

**Safety guarantees**:
- Every file backed up before modification
- Atomic writes (temp file + rename)
- Automatic rollback on any failure
- Execution lock prevents concurrent runs
- Path traversal protection
- Protected file patterns

## Skill System

Skills are markdown documents loaded on-demand by agents:

```
skills/
├── skill-name/
│   └── SKILL.md       # Frontmatter + content
└── skills-registry.json  # Index mapping skills to agents
```

Skills provide:
- Domain expertise (testing, security, debugging)
- Workflow patterns (TDD, code review, branch management)
- Decision frameworks (when to plan vs. direct implement)

## Hook System

Hooks execute at workflow boundaries:

| Hook | Trigger | Purpose |
|------|---------|---------|
| pre-commit | Before git commit | Validate ops configs, check secrets |
| post-implement | After implementation | Run tests, check coverage |
| pre-plan | Before plan creation | Detect duplicate plans |
| pre-push | Before git push | Full validation suite |
| post-tool-use | After Edit/Write/Bash | Track modifications |

Hooks read project commands from `config.json` — no hardcoded build tools.

## Scoring and Gates

### Plan Review (Reviewer Agent)
```
Score = Plan_Quality (40%) + Architecture (30%) + Security (30%)
Gate: ≥ 90/100 → Approved
```

### Quality Verification (Verifier Agent)
```
Score = Static_Analysis (30%) + Tests (40%) + Coverage (30%)
Gate: ≥ 80/100 → Passed
```

### Escalation
- 3 plan/review iterations → escalate to user
- 3 implementation attempts → escalate to user
- User can: proceed anyway, revise manually, or abort

## Design Principles

1. **Copy, not symlink** — Project is self-contained after install
2. **Config-driven** — No hardcoded build commands
3. **File-based handoffs** — Agents don't share context
4. **Fail-safe** — Backup before every modification
5. **Governance as code** — Constitution enforced by agents
