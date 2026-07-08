# Memory — Durable Facts an AI Must Retain

Short, hard facts. If your context is tight, load this file plus [SESSION_STATE.md](SESSION_STATE.md) and nothing else.

## Identity
- ClaudeKit = multi-agent orchestration system for Claude Code. Not a library; a copied-in asset corpus + delivery shell.
- PyPI: `claude-kit` (name `claudekit` taken). CLI: `claudekit` / `ck`. Import: `claudekit`. GitHub: `OmarMokhtar-Saad/claudekit`. MIT.
- Version 2.1.0, `[Unreleased]`; tag/publish is user-gated.

## Counts (regenerate via `python3 scripts/gen-docs.py`)
28 agents · 40 commands · 74 skills · 19 hooks · 29 ops guards · 11 language templates · 516 tests · py ≥3.9 · 0 runtime deps.

## Invariants (never violate — full list in [KNOWLEDGE_BASE.md](KNOWLEDGE_BASE.md))
Iron Law (ops.json only; implementer can't Edit) · hooks block via exit 2+stderr, fail closed · no `--dangerously-skip-permissions` (CI-gated) · protected files + MAX_DELETIONS=3 · golden rule (no changes without approval) · "speed bump, not a sandbox" framing · 3 synced version locations (pyproject, `src/claudekit/__init__.py`, `operations/scripts/shared.py`) · counts generated, never typed · bash-3.2/macOS compatible · conventional commits + AI Co-Authored-By line.

## Quality gates (Definition of Done)
`pytest -q` (516 pass) · `ruff check src/ tests/ scripts/` · `mypy` · `gen-docs.py --check` · `shellcheck install.sh .claude/hooks/*.sh` · CHANGELOG entry for user-visible changes.

## Session mechanics
- This repo enforces its own hooks; dev override = `ECC_HOOK_PROFILE=minimal` in gitignored `.claude/settings.local.json`.
- Ops filenames: both `*.ops.json` and `ops-*.json` (lib.sh OPS_FIND_EXPR).
- Thresholds: plan review ≥90/100 (40/30/30), verification ≥80/100 (30/40/30) — prompt-enforced until task 010.
- Plan of record: `review/roadmap.md` + `review/tasks/007-010,012-014` (001-006, 011 done).

## People & preferences
- Owner: Omar Mokhtar (omar.mokhtarsaad92@gmail.com). Decides: releases, asset deletions/renames, plugin-packaging bet.
- Style: concise, evidence-first, honest claims; behavioral tests; fix root causes.
