# System Overview

## What ClaudeKit is

ClaudeKit is a **multi-agent orchestration system for Claude Code**. It turns an unstructured AI coding assistant into a governed pipeline: every change is planned, the plan is scored by a reviewer agent against a 90/100 threshold, execution happens exclusively through a validated, atomic, rollback-capable JSON operations engine, and the result is verified against an 80/100 quality threshold. Hooks — not instructions — enforce the rules.

Users install it into their own project (`pip install claude-kit && ck init <project> --full`, or `./install.sh`), which copies the `.claude/` asset tree, generates a `CLAUDE.md` and `CONSTITUTION.md` from templates for their language, and wires 19 lifecycle hooks through `.claude/settings.json`.

**What makes it differentiated** (per the 2026-07 external audit): no comparable Claude Code kit has a deterministic transactional execution engine (ops.json + 29 guards + backup/rollback), scored review gates, or the anti-anchoring adversarial-review designs (Santa dual review, GAN evaluator loops with fresh context per iteration).

## The five subsystems

1. **Agent corpus** (`.claude/agents/`, 28 Markdown agents + `_shared/` protocols) — role prompts with frontmatter (name, description, model, tools). Core pipeline: coordinator, planner, reviewer, implementer, verifier, gitOps; plus specialists (debugger, tester, security-scanner, code-reviewer, …). See [AGENTS.md](AGENTS.md).
2. **Command layer** (`.claude/commands/`, 40 slash commands) — user entry points that dispatch agents and workflows (`/plan`, `/review`, `/implement`, `/santa`, `/gan-build`, `/prp-*`, …). See [COMMANDS.md](COMMANDS.md).
3. **Skill library** (`.claude/skills/`, 74 skills + `skills-registry.json`) — reusable procedure modules agents load on demand; the registry maps skills to agents, with `using-superpowers` and `golden-rule` mandatory for all. See [SKILLS.md](SKILLS.md).
4. **Enforcement layer** (`.claude/hooks/`, 19 shell hooks wired in `.claude/settings.json`; `src/claudekit/security/` Python validator) — blocks unsafe edits, bad commits, dangerous commands; profiles via `ECC_HOOK_PROFILE`. See [HOOKS.md](HOOKS.md) and [SECURITY_GUIDE.md](SECURITY_GUIDE.md).
5. **Operations engine** (`.claude/operations/scripts/`) — `validate-config-json.py` (29 guards), `execute-json-ops.py` (backups, atomic writes, rollback), `restore-backup.py`, `operations-schema.json`. The only sanctioned way agents change user code. See [SKILLS.md](SKILLS.md#operations-pipeline) and [DOMAIN.md](DOMAIN.md).

Delivery shell around them: the Python CLI (`src/claudekit/cli/main.py` — init/doctor/diff/update/uninstall/validate/execute/rollback/agents/config/check-command/check-path), `install.sh` (staging + backup + atomic swap), and CI (11 GitHub Actions jobs).

## Repository map

| Path | What it is |
|------|------------|
| `.claude/agents/` | 28 agent prompts + `_shared/` protocol docs + QUICK_START, HANDOFF_PROTOCOL |
| `.claude/commands/` | 40 slash-command prompts |
| `.claude/skills/` | 74 skills (one dir each, `SKILL.md`) + `skills-registry.json` |
| `.claude/hooks/` | 19 hook scripts + `lib.sh` + `config.json` (project cmds) + logs |
| `.claude/operations/scripts/` | ops.json validator/executor/restore + schema |
| `.claude/plans/` | Plan artifacts (`*.md`, `*.ops.json`) incl. `phase-1-HANDOFF.md` |
| `.claude/local/` | `CLAUDE.template.md`, `CONSTITUTION.template.md` (install-time templates) |
| `.claude/settings.json` | Hook wiring (the enforcement truth) |
| `src/claudekit/` | Python package: `cli/main.py`, `security/{command_validator,path_guard,cli}.py` |
| `install.sh` | Bash installer (525 lines) |
| `templates/` | 11 language `CLAUDE.md`+`config.env` sets, 13 extra commands, 7 modes, 4 hooks, 14 skills, MCP configs, `.agentignore` |
| `examples/` | Filled-in python-fastapi and typescript-nextjs projects |
| `docs/` | User docs: ARCHITECTURE, AGENTS, SKILLS, HOOKS, cli, CUSTOMIZATION, CONSTITUTION-GUIDE |
| `review/` | Frozen 2026-07-05 audit: 11 reviews, FINAL-REPORT (49/100), roadmap, tasks/001–014 |
| `tests/` | 16 pytest files, 516 tests |
| `.github/workflows/` | ci.yml (11 jobs), release.yml (PyPI Trusted Publishing), security.yml |
| `scripts/gen-docs.py` | Count generation + docs-drift CI gate |
| `i18n/` | README in ar/es/fr/ja/ko/zh |
| `.ai/` | This AI operating system |

## Key numbers (verify with `gen-docs.py`)

28 agents · 40 commands · 74 skills · 19 hooks · 29 ops guards · 11 language templates · 516 tests · Python ≥3.9 · zero runtime dependencies · version 2.1.0 · PyPI name `claude-kit` · GitHub `OmarMokhtar-Saad/claudekit`.

## Where the project stands

Phase 1 ("v2.1 Fix What's Broken", from the audit roadmap) is **complete and merged to main** (2026-07-06). The package builds, installs, and self-checks; hooks genuinely block; CI is honest. Remaining: tag `v2.1.0` + PyPI publish (user-gated), then the v3.0 roadmap (plugin packaging, eval framework, corpus consolidation). Details: [STATUS.md](STATUS.md), [ROADMAP.md](ROADMAP.md).
