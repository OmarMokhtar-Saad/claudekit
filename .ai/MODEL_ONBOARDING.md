# Model Onboarding — Start Here

You are an AI model taking over development of **ClaudeKit**, a production-grade multi-agent orchestration system for Claude Code. This document gets you productive in one session without any prior chat history.

## 1. What to read first (mandatory, in order)

1. This file, fully.
2. [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md) — what the product is.
3. [CONTEXT.md](CONTEXT.md) — the non-obvious facts (naming, versioning, session gotchas). **Do not skip.**
4. [SESSION_STATE.md](SESSION_STATE.md) — current state and suggested next tasks.
5. Root `CLAUDE.md` — the operating rules you must follow while working here.

Read on demand: [ARCHITECTURE.md](ARCHITECTURE.md) before structural changes; the catalog docs ([AGENTS.md](AGENTS.md), [COMMANDS.md](COMMANDS.md), [SKILLS.md](SKILLS.md), [HOOKS.md](HOOKS.md)) before touching those asset classes; [SECURITY_GUIDE.md](SECURITY_GUIDE.md) before touching anything in `src/claudekit/security/` or `.claude/hooks/`.

## 2. The 60-second mental model

ClaudeKit is **not a library you import** — it is a corpus of Markdown prompts (28 agents, 40 commands, 74 skills), shell hooks (19), and Python safety tooling that gets **copied into a user's project** (`ck init` / `install.sh`). Its core promise: every AI code change flows through **plan → scored review (≥90/100) → validated ops.json execution (29 guards, atomic, rollback) → verification (≥80/100)**, enforced by hooks, not politeness.

Two codebases live here:

- **The product assets**: `.claude/` (agents/commands/skills/hooks/operations), `templates/`, `examples/` — Markdown + Bash + JSON. These double as the dev environment: the repo eats its own dog food.
- **The delivery shell**: `src/claudekit/` (CLI + security layer, Python), `install.sh`, `.github/workflows/`, `tests/`.

## 3. Mandatory conventions

- **Bump versions in three places together**: `pyproject.toml`, the fallback in `src/claudekit/__init__.py`, and `.claude/operations/scripts/shared.py`. Tests guard this.
- **Never hard-code component counts** in docs. `scripts/gen-docs.py --check` is a CI gate (`docs-drift`); run it after adding/removing any agent/command/skill/hook.
- **Bash must be macOS/bash-3.2 compatible** (no `${VAR,,}`, no GNU-only `date -r`). CI runs shellcheck on `install.sh` and all hooks.
- **Blocking hooks fail closed**: `exit 2` + message on **stderr**. `exit 0` = allow, `exit 2` = block. Never revert to `exit 1`/stdout — that was the historic "enforcement never enforced" bug.
- **Never reintroduce `--dangerously-skip-permissions`** anywhere in shipped assets. CI's `permission-gate` job blocks it; `.claude/agents/_shared/INVOCATION.md` is the single source of truth for spawning agents.
- **Python**: ruff (line-length 100, E/F/W/I) + mypy clean, py3.9-compatible. Zero runtime dependencies is a product feature — do not add any.
- **Conventional commits** (`feat:`, `fix:`, `docs:`, `ci:`, `test:`, `build:`); the repo's own `commit-quality.sh` hook enforces format.

## 4. Working in this repo without fighting its own hooks

This repo ships enforcement hooks *and runs them on itself*. `ops-enforcement.sh` blocks direct Edit/Write to source files outside `.claude/` and docs unless an approved ops.json exists.

- `.claude/settings.local.json` (gitignored) sets `ECC_HOOK_PROFILE=minimal` to disable enforcement for kit development. If your session is being blocked, that override is missing — see `CONTRIBUTING.md` "Working on ClaudeKit itself".
- Profiles: `minimal` = enforcement off · `standard` = default (command-guard warns) · `strict` = everything blocks.
- Tests that prove blocking behavior set `ECC_HOOK_PROFILE=standard` per-subprocess — don't weaken them.

## 5. How to verify your work (Definition of Done)

```bash
python3 -m pytest tests/ -q        # 516 tests; all must pass
ruff check src/ tests/ scripts/    # clean
mypy                               # clean (config in pyproject.toml)
python3 scripts/gen-docs.py --check  # no docs drift
shellcheck install.sh .claude/hooks/*.sh  # clean (see .shellcheckrc)
```

A task is done only when all of the above pass **and** the change is documented (CHANGELOG.md entry for user-visible changes; relevant `.ai/` docs updated). Claim nothing without running the command and seeing the output — this project's own `verification-before-completion` skill applies to you.

## 6. How to implement a new feature

1. Check [BACKLOG.md](BACKLOG.md) / [ROADMAP.md](ROADMAP.md) — most work is already specified in `review/tasks/0XX-*.md` with file-level detail.
2. Read the relevant task file and the source files it names. The 2026-07-05 audit is unusually precise (file:line references).
3. Write or update tests first where practical — the suite favors **behavioral** tests (e.g., `test_hooks_behavioral.py` actually runs hooks in a subprocess and asserts exit codes) over existence checks.
4. Implement, run the full DoD gate above, update docs, commit conventionally.

## 7. How to debug

Start with [DEBUGGING_GUIDE.md](DEBUGGING_GUIDE.md). Key entry points: `.claude/hooks/hooks.log` (hook activity), `ck doctor --strict` (install health, 19 checks), `bash -x` on hooks with a crafted stdin JSON payload, `python3 -m pytest tests/test_hooks_behavioral.py -q` (the enforcement truth suite).

## 8. How to update documentation

- User-visible behavior → `README.md` + relevant `docs/*.md` + `CHANGELOG.md` under `[Unreleased]`.
- Counts → never manual; verify with `gen-docs.py --check`.
- Maintainer knowledge → the relevant `.ai/` file, and append a session entry to [CHANGELOG_AI.md](CHANGELOG_AI.md).

## 9. How to hand over again

Before ending a significant work period: update [SESSION_STATE.md](SESSION_STATE.md) (state, pending work, blockers, next tasks), append to [CHANGELOG_AI.md](CHANGELOG_AI.md), update [STATUS.md](STATUS.md) if the snapshot changed, and record any new decisions in [DECISIONS.md](DECISIONS.md). The bar: a different model must be able to resume from these four files alone.

## 10. Mistakes to avoid (all have happened before)

- Publishing without checking the package actually installs (the v2.0 wheel **never** built — wrong build backend).
- "Blocking" hooks that don't block (`exit 1`/stdout instead of `exit 2`/stderr).
- Docs drifting from reality (13-vs-28 agent gap, three different skill counts, four version values at once).
- Non-monotonic versioning (1.3.0 published after 2.0.0; renumbered to 2.1.0).
- GNU-only shell constructs breaking macOS users.
- Duplicating instead of consolidating (`autonomous-loop` vs `autonomous-loops` skills still exist — task 008).
- Trusting summaries (including this folder) over the tree. Verify.
