# Knowledge Graph

How everything relates. Node detail lives in the catalogs: [AGENTS.md](AGENTS.md), [COMMANDS.md](COMMANDS.md), [SKILLS.md](SKILLS.md), [HOOKS.md](HOOKS.md).

## Core relationships

```mermaid
graph LR
    USER((User)) -->|types| CMD[Commands /39/]
    CMD -->|dispatch per INVOCATION.md| AGENTS[Agents /28/]
    AGENTS -->|load via registry| SKILLS[Skills /73/]
    REG[skills-registry.json] -.maps.- SKILLS
    REG -.maps.- AGENTS
    AGENTS -->|write| PLANS[plans/*.md + ops.json]
    PLANS -->|validated by 29 guards| OPS[Operations engine]
    OPS -->|atomic + backup| CODE[(User codebase)]
    OPS -->|rollback| BACKUPS[(Backups)]
    HOOKS[Hooks /19/] -->|PreToolUse block| AGENTS
    SETTINGS[settings.json] -->|wires| HOOKS
    HOOKS -->|command-guard| SEC[claudekit.security<br/>CommandValidator·PathGuard]
    CONST[CLAUDE.md + CONSTITUTION.md] -->|standing context| AGENTS
    TPL[templates/ 11 languages] -->|rendered by| INST[install.sh / ck init]
    INST -->|copies+manifest| SETTINGS
    INST --> CONST
    CLI[ck CLI] --> INST
    CLI -->|doctor·diff·update·uninstall| MANIFEST[.claudekit-manifest.json]
    CLI -->|validate·execute·rollback| OPS
    TESTS[tests/ 516] -->|prove| HOOKS & SEC & OPS & INST & CLI
    CI[ci.yml 11 jobs] -->|gates| TESTS & DOCS[docs/ + README] & REG & HOOKS
    GEN[gen-docs.py] -->|counts| DOCS
    AUDIT[review/ audit+tasks] -->|work queue| BACKLOG[.ai planning docs]
```

## Pipeline / concept relationships

```mermaid
graph TD
    subgraph Gates
        R90[Plan gate ≥90] --> I[implement]
        V80[Verify gate ≥80] --> G[gitOps commit/PR]
    end
    PLANNER[planner] --> R90
    I --> V80
    SANTA[/santa dual review/] -.escalation.-> G
    GAN[/gan-build loop/] -.alternative.-> PLANNER
    PRP[/prp-* 4-phase/] -.alternative pipeline.-> G
    LOOP[/loop-start/] --> LO[loop-operator<br/>Warn→Pause→Stop]
    OSSP[/opensource/] --> S1[sanitizer PASS/FAIL] -->|hard gate| S3[packager]
    GOLDEN[Golden Rule] -.governs.-> PLANNER & I & G
    IRON[Iron Law: ops.json only] -.governs.-> I
```

## Traceability spine

Feature promise (README) → enforcing mechanism (hook/guard/CI job) → proving test (tests/) → documenting page (docs/ + .ai/). When adding anything, complete all four links — the audit's core finding was promises with missing mechanism/test links.

| Promise | Mechanism | Test | Doc |
|---------|-----------|------|-----|
| "Plans before code" | ops-enforcement.sh + Iron Law | test_hooks_behavioral | HOOKS/DOMAIN |
| "29 safety guards" | validate-config-json.py | test_validator | SKILLS §ops |
| "Safe execution, rollback" | execute-json-ops / restore-backup | test_validator, behavioral | SKILLS §ops |
| "Hooks block" | exit-2 contract + settings.json | test_hooks_behavioral | HOOKS |
| "Command safety" | CommandValidator + command-guard | test_security(+hooks) | SECURITY_GUIDE |
| "Self-contained install" | wheel share/claudekit + manifest | test_packaging, test_install | ARCHITECTURE §8 |
| "Counts are true" | gen-docs.py + docs-drift CI | (CI job) | everywhere |
| "No permission bypass" | INVOCATION.md + permission-gate CI | (CI job) | AGENTS/SECURITY |
