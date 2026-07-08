# Domain Model

The concepts ClaudeKit is *about*, independent of implementation. Terms: [GLOSSARY.md](GLOSSARY.md); relationships: [KNOWLEDGE_GRAPH.md](KNOWLEDGE_GRAPH.md).

## Entities

- **Agent** — a role with one responsibility, a model tier, and a tool set that *is* its permission grant. Identified by frontmatter `name`; discovered by Claude Code from `description` examples.
- **Command** — a user-invocable workflow entry point (`/plan`, `/santa`, …) that dispatches agents.
- **Skill** — a loadable procedure module; the registry (`skills-registry.json`) is the authoritative agent↔skill mapping.
- **Hook** — a lifecycle interceptor (PreToolUse/PostToolUse/UserPromptSubmit/SessionStart/Stop/…) that enforces or observes.
- **Plan** — a Markdown implementation plan plus its **ops.json** (operations config): the declarative list of `file_create` / `file_delete` / `code_edit` operations that fully specify a change.
- **Operations engine** — validator (29 guards) + executor (backup, atomic, rollback) + restorer. The only sanctioned mutation path.
- **Constitution** — per-project governance document (8 articles: architecture, code quality, testing, security, operations, performance, documentation, review) that agents enforce; violations carry penalties up to AUTO-REJECT.
- **Handoff** — the structured block that moves work between agents (task, classification, pipeline position, artifacts, constraints, return-to).
- **Pipeline** — an ordered agent sequence selected by task classification (Feature/Bug/Refactor/Security Audit/Docs/EPIC/…).
- **Profile** — `ECC_HOOK_PROFILE` enforcement level (minimal/standard/strict).
- **Manifest** — `.claudekit-manifest.json`, the installed-file inventory (version + sha256) enabling diff/update/uninstall.
- **Mode** — a behavioral overlay (brainstorm, token-efficient, …).
- **Template** — per-language `CLAUDE.md` + `config.env` rendered at install time.

## Business rules (the "laws")

1. **Golden Rule:** no code changes without explicit user approval, ever.
2. **Iron Law:** approved plan + ops.json required before implementation; no manual-edit fallback.
3. **Gates:** plans ship at ≥90/100; implementations pass at ≥80/100; plans without ops.json score 0.
4. **Ops safety:** protected files are undeletable; ≤3 deletions/plan; every execution backed up and atomic; rollback always available.
5. **Permission floor:** agents run with scoped tools under Claude Code's permission system; nothing may bypass it.
6. **Hard stage gates:** multi-stage pipelines (opensource) may not proceed past a FAILed stage.
7. **Loop containment:** every autonomous loop has iteration caps and a supervising operator with an intervention ladder.
8. **Only GitOps commits** (division of labor rule; one cataloged violator — refactor-cleaner — is a known bug, AGENTS.md issue #13).
9. **Evidence rule:** no agent claims success without command output proving it.
10. **Config over code:** project-specific commands live in config, not in prompts or scripts.

## Lifecycle of a change (canonical story)

User asks → coordinator classifies → planner explores and emits plan + ops.json → reviewer scores (reject → refine loop) → implementer validates + executes via engine (backup → apply → verify build/lint/test) → verifier scores → gitOps commits/PRs → hooks observed everything and telemetry landed in logs. Rollback available at every point after execution.

## Actors

**End user** (developer using ClaudeKit in their project) · **Owner/maintainer** (develops the kit) · **Agents** (the 28 roles) · **Claude Code** (the runtime that interprets everything) · **CI** (the impartial enforcer of kit quality).
