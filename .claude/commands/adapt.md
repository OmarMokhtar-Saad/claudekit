---
description: "Adapt ClaudeKit to the current project — any language, any stack: detect state, configure commands/CLAUDE.md/CONSTITUTION/hooks, verify with evidence, record decisions"
argument-hint: "[--verify-only|--reconfigure]"
model: sonnet
---

# Adapt Command

Fit ClaudeKit to this project. Works for any language — including stacks with no dedicated template (the kit is language-agnostic; only a small configuration surface is project-specific).

## Mandatory Skills

- **using-superpowers** - Core capabilities
- **golden-rule** - Propose changes, get approval before writing
- **project-adaptation** - The full adaptation methodology

**On demand:** load **codebase-onboarding** when project-adaptation directs reconnaissance (it loads this itself).

## Task

Adapt ClaudeKit to this project: $ARGUMENTS

## Modes

| Flag | Behavior |
|------|----------|
| (default) | Full run: Phases 0–3 of project-adaptation, then report |
| `--verify-only` | Phase 3 only — prove the current configuration works (hook block test, four commands, ops round-trip, doctor) |
| `--reconfigure` | Re-run Phases 1–2 against the current stack (after CI/stack changes), preserving existing CLAUDE.md content |

## Execution

1. **Detect** installation state (manual copy / installed-unconfigured / drifted).
2. **Learn** the project via codebase-onboarding reconnaissance.
3. **Propose** the configuration set (config.json commands, CLAUDE.md render-or-enhance, CONSTITUTION tuning, hook profile, .agentignore) — wait for approval.
4. **Apply** approved changes.
5. **Verify** with evidence (Phase 3 of the skill) — paste command output; no unverified "it works".
6. **Report**: what changed, what was skipped and why, recommended profile, suggested next enhancements (`/hookify`, `/learn`).

## Usage Examples

- `/adapt` — first session after adding `.claude/` to any project
- `/adapt --verify-only` — health-check an existing configuration
- `/adapt --reconfigure` — stack changed (e.g., migrated Jest→Vitest); refresh commands and docs

## Related

`/onboard` learns the codebase and writes CLAUDE.md content; `/adapt` configures **the kit itself** and proves it works. Run `/adapt` first in a fresh install; it delegates recon to the same skill `/onboard` uses.
