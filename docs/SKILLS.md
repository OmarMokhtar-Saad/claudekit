# Skills

Skills are markdown documents that provide domain expertise, workflow patterns, and decision frameworks to agents.

## Skill Catalog

### Foundational
| Skill | Description | Used By |
|-------|-------------|---------|
| using-superpowers | Skill discovery protocol — ensures agents load relevant skills | All |
| golden-rule | Never modify code without explicit approval | All |
| context-first-workflow | Explore codebase before making changes | Planner, Implementer |

### Planning & Execution
| Skill | Description | Used By |
|-------|-------------|---------|
| writing-plans | Plan structure, bite-sized tasks, ops.json | Planner |
| executing-plans | Batch execution with review checkpoints | Implementer |
| brainstorming | Creative design exploration before planning | Planner |
| generate-operations-config | Create ops.json for code changes | Planner, Implementer |
| validate-operations-config | Run validator + dry-run on ops.json | Reviewer |
| execute-operations-config | Execute ops.json with backup | Implementer |

### Quality & Testing
| Skill | Description | Used By |
|-------|-------------|---------|
| verification-before-completion | Evidence before claims, always | Verifier, All |
| test-driven-development | RED/GREEN/REFACTOR workflow | Implementer |
| clean-architecture | Layer boundaries and dependency rules | Reviewer, Planner |
| security-checklist | OWASP Top 10 validation | Reviewer, GitOps |
| performance-guidelines | Response times, resource management | Verifier |

### Debugging
| Skill | Description | Used By |
|-------|-------------|---------|
| systematic-debugging | 4-phase root cause investigation | Debugger |
| clarify | Reverse-question protocol for ambiguity | All |

### Code Review
| Skill | Description | Used By |
|-------|-------------|---------|
| requesting-code-review | Prepare and dispatch code reviews | GitOps |
| receiving-code-review | Technical evaluation of feedback | Implementer |

### Refactoring & Patterns
| Skill | Description | Used By |
|-------|-------------|---------|
| refactoring-patterns | Proven refactoring patterns catalog | Planner |
| error-handling | Exception hierarchy, logging, recovery | Implementer |
| documentation-standards | Doc formatting and knowledge base | Documenter |

### Git & Collaboration
| Skill | Description | Used By |
|-------|-------------|---------|
| git-workflow | Git conventions and workflow patterns | GitOps |
| using-git-worktrees | Isolated workspace patterns | GitOps |
| finishing-a-development-branch | Branch completion and cleanup | GitOps |

### Multi-Agent
| Skill | Description | Used By |
|-------|-------------|---------|
| multi-agent-coordination | Safe parallel execution patterns | Coordinator |
| dispatching-parallel-agents | Parallel task investigation | Coordinator |
| subagent-driven-development | Fresh subagent per task pattern | Coordinator |

### Governance
| Skill | Description | Used By |
|-------|-------------|---------|
| constitution | Constitutional governance creation | All |
| writing-skills | TDD approach to skill creation | All |

### Security
| Skill | Description | Used By |
|-------|-------------|---------|
| supply-chain-audit | Dependency tree threat analysis, typosquatting detection, CVE cross-referencing | Reviewer, Verifier, Security Scanner |
| differential-security-review | Security-focused diff analysis, removed controls detection, regression patterns | Reviewer, GitOps, Security Scanner |
| insecure-defaults | Hardcoded credentials, fail-open patterns, dangerous default configurations | Reviewer, Verifier, Security Scanner |
| static-analysis-integration | Semgrep, Bandit, ESLint security, SARIF parsing, severity classification | Verifier, Reviewer, Security Scanner |

### API & Data
| Skill | Description | Used By |
|-------|-------------|---------|
| api-design-patterns | REST, GraphQL, gRPC design guidance, versioning, pagination, error responses | Planner, Reviewer |
| database-migration-patterns | Zero-downtime migrations, expand-contract pattern, rollback strategies | Planner, Reviewer, Database Architect |

### Testing
| Skill | Description | Used By |
|-------|-------------|---------|
| property-based-testing | Hypothesis, fast-check, proptest, QuickCheck - property-driven test generation | Tester, Implementer |

### DevOps
| Skill | Description | Used By |
|-------|-------------|---------|
| ci-cd-pipeline | Pipeline stage design, artifact promotion, environment gating | Planner, GitOps, DevOps |
| monitoring-observability | Structured logging, distributed tracing, metric naming, SLO/SLA | Planner, Debugger, DevOps |
| containerization-patterns | Docker multi-stage builds, security hardening, compose and K8s patterns | DevOps |
| dependency-audit | CVE assessment, semver compatibility, safe incremental upgrades | Verifier, Reviewer, Security Scanner |

### Accessibility & i18n
| Skill | Description | Used By |
|-------|-------------|---------|
| accessibility-standards | WCAG 2.1 AA compliance, ARIA patterns, keyboard navigation | Reviewer, Verifier |
| i18n-patterns | Locale-aware formatting, translation keys, RTL layout, pluralization | Planner, Implementer |

### Advanced Patterns
| Skill | Description | Used By |
|-------|-------------|---------|
| spec-driven-development | Specification-first workflow where specs are the single source of truth | Planner, Implementer |
| code-explanation | Analogy-first code explanation with visual diagrams and gotcha highlights | Explore, Debugger |
| incident-response | Triage, war room coordination, post-mortem writing, runbook patterns | Debugger, Coordinator |

## Skill Structure

Each skill lives in `skills/{skill-name}/SKILL.md`:

```markdown
---
name: skill-name
description: Use when [triggering condition] — [what it does]
---

# Skill Title

## Overview
[What and why]

## When to Use
[Triggering conditions]

## The Process
[Steps, checklists, decision trees]

## Common Mistakes
[What goes wrong and how to fix]
```

### Frontmatter Rules
- `name`: kebab-case, matches directory name
- `description`: Starts with "Use when..." — this is what agents read to decide whether to load the skill

## Skills Registry

`skills/skills-registry.json` maps skills to agents:

```json
{
  "version": "1.1",
  "skills": [
    {
      "id": "golden-rule",
      "name": "Golden Rule",
      "path": "skills/golden-rule/SKILL.md",
      "mandatory": true,
      "usedBy": ["all"]
    }
  ]
}
```

## Creating a New Skill

Follow the `writing-skills` skill's TDD approach:

1. **RED**: Observe agent failing without the skill (pressure scenario)
2. **GREEN**: Write minimal SKILL.md that addresses the failure
3. **REFACTOR**: Close loopholes found in testing

### Quick Start

```bash
mkdir -p .claude/skills/my-skill
cat > .claude/skills/my-skill/SKILL.md << 'EOF'
---
name: my-skill
description: Use when [situation] — ensures [outcome]
---

# My Skill

## Overview
[Core principle in 1-2 sentences]

## When to Use
- [Trigger 1]
- [Trigger 2]

## The Process
1. [Step 1]
2. [Step 2]
3. [Step 3]

## Common Mistakes
| Mistake | Fix |
|---------|-----|
| [X] | [Y] |
EOF
```

Then update `skills-registry.json` to include the new skill.

## Skill Types

**Rigid** (TDD, debugging, verification): Follow exactly. Don't adapt.

**Flexible** (patterns, architecture): Adapt principles to context.

The skill content tells you which type it is.
