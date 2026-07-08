# Prompt Library & Prompt Engineering

ClaudeKit **is** a prompt library — the production prompts are the product. This doc maps where they live, the conventions they follow, and their lifecycle. Per-prompt detail: [AGENTS.md](AGENTS.md), [COMMANDS.md](COMMANDS.md), [SKILLS.md](SKILLS.md).

## Where prompts live

| Layer | Location | Role |
|-------|----------|------|
| Agent prompts | `.claude/agents/*.md` | Role/system prompts. Frontmatter: `name`, `description` (with 1–2 `<example>` blocks showing Context/user/assistant), `model` (haiku/sonnet/opus), `tools` (the permission model), `color`. Body: role, mandatory skill loading, workflow phases, output contract, handoff formats. |
| Command prompts | `.claude/commands/*.md` | Entry-point prompts. Frontmatter: `description`, optionally `allowed-tools`. Body: argument parsing, workflow, agent dispatch per `_shared/INVOCATION.md`. |
| Skill prompts | `.claude/skills/*/SKILL.md` | Procedure modules loaded on demand; trigger-rich descriptions drive discovery. |
| Shared protocol includes | `.claude/agents/_shared/*.md` | Cross-cutting contracts (INVOCATION, HANDOFF_PROTOCOL, VERIFICATION_PROTOCOL, OUTPUT_TEMPLATE, …) referenced by agents/commands instead of duplicating text. |
| Generated-context templates | `.claude/local/CLAUDE.template.md`, `CONSTITUTION.template.md`, `templates/*/CLAUDE.md` | Rendered by the installer (`{{PROJECT_NAME}}`, `{{LANGUAGE}}`, build commands…) into the user project's standing context. |
| Mode overlays | `templates/modes/*.md` | Behavioral variants (brainstorm, token-efficient, …). |

## Conventions (follow when authoring)

1. **Frontmatter examples are load-bearing.** The `<example>` blocks teach Claude Code when to auto-select the agent. Two per agent is the standard (some newer ones have one — flagged in AGENTS.md Known Issues #14).
2. **Imperative, checklist-driven bodies.** Numbered phases, explicit STOP conditions ("no ops.json → STOP"), hard constraints stated as IRON LAW / NEVER / ALWAYS.
3. **Single source of truth over duplication.** Schemas and invocation rules are *referenced* (e.g., planner → `generate-operations-config` skill), never embedded — embedded copies drift (the planner schema once failed the kit's own validator).
4. **Tools = permissions.** Read-only agents omit Write/Edit from `tools`; implementer deliberately lacks Edit/Write to force the ops engine.
5. **Model choice by task shape.** Opus for judgment (reviewer, debugger, code-reviewer, security-scanner); Sonnet for generation/execution; Haiku for mechanical steps (verifier, gitOps, documenter, model-router). model-router codifies the scoring.
6. **Output contracts.** Agents end with a defined report format (OUTPUT_TEMPLATE.md) and handoff block (HANDOFF_PROTOCOL.md) so downstream agents can parse deterministically.
7. **Scoring gates are explicit** (90/100 plan, 80/100 verify, weights spelled out) — but note the audit's criticism: thresholds are currently uncalibrated "precision theater" until the eval framework (task 010) grounds them.

## Prompt lifecycle

```
user types /command → command body expands → classifies/parses args
  → dispatches agent (scoped --allowedTools per INVOCATION.md)
  → agent loads using-superpowers → golden-rule → task skills (registry)
  → agent works in phases, writes artifacts to .claude/plans/
  → emits OUTPUT_TEMPLATE report + HANDOFF block → next agent or user
```

Versioning: prompts are versioned only through git + CHANGELOG (no per-prompt version fields). Renames/merges must update: registry `usedBy`, coordinator routing tables, QUICK_START tables, `gen-docs.py` counts, and docs.

## Strongest exemplars (read these before writing a new prompt)

`build-error-resolver.md` (crisp constraints, iteration cap), `loop-operator.md` (intervention ladder), `reviewer.md` (explicit scoring rubric), `coordinator.md` (routing + handoff discipline), `_shared/INVOCATION.md` (rule writing done right).

## Improvement queue

- Add few-shot *output* exemplars to reviewer/verifier (audit: gates lack output validation).
- Machine-parseable verdicts (`review.json` schema) so hooks can mechanically gate `/implement` (roadmap §2.3).
- Fix the 16 prompt-layer inconsistencies cataloged in [AGENTS.md](AGENTS.md#known-issues) — especially the legacy ops schema in `WORKFLOW_FILE_TEMPLATES.md` (issue #9, actively harmful) and QUICK_START table drift (#6).
- Generate "Mandatory Skill Loading" sections from the registry instead of hand-writing (roadmap §2.4).
