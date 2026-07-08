# Review Guide

## Two review systems — don't conflate

| | Plan review | Code review |
|---|------------|-------------|
| Agent | `reviewer` (opus, read-only) | `code-reviewer` (opus, read-only) |
| Command | `/review` | `/code-review` |
| Object | `plan-*.md` + ops.json | diffs, files, PRs |
| Gate | ≥90/100: Plan Quality 40% + Architecture 30% + Security 30% | findings ranked by severity; APPROVE/REQUEST_CHANGES/BLOCK |
| Auto-reject | plan without ops.json → score 0 | — |

High-stakes escalation: `/santa` (dual independent reviewers, both must approve). Language-specific: python-reviewer / typescript-reviewer (merge candidates into code-reviewer, task 008).

## Reviewing changes to ClaudeKit itself (maintainer checklist)

**Any PR:**
- [ ] Full DoD gate green (pytest 516, ruff, mypy, gen-docs --check, shellcheck).
- [ ] CHANGELOG `[Unreleased]` entry for user-visible changes.
- [ ] No hardcoded counts introduced; no new near-duplicate assets.
- [ ] Conventional commit format; co-author line for AI commits.

**Prompt changes (agents/commands/skills):**
- [ ] Registry, coordinator routing, QUICK_START, INVOCATION rows updated for renames/merges.
- [ ] No schema/rule duplication — reference the single source (generate-operations-config, INVOCATION.md).
- [ ] Frontmatter examples intact; tools list still minimal.
- [ ] Doesn't contradict HANDOFF_PROTOCOL / VERIFICATION_PROTOCOL / the Iron Law.

**Hook changes:**
- [ ] Blocking = exit 2 + stderr, fail closed; profile-gated correctly.
- [ ] bash-3.2/macOS-safe; shellcheck clean; behavioral test proves block AND allow paths.
- [ ] settings.json registration matches (dangling-hooks CI).

**Security-layer changes:**
- [ ] Bypass corpus extended for the new surface; coverage ≥85% holds.
- [ ] No allowlist additions of shell interpreters/launchers (bash/sh/env/xargs stay off).
- [ ] SECURITY.md still honest ("speed bump" framing).

**Installer changes:**
- [ ] Staging/backup/atomic-swap preserved; mid-failure test passes; manifest correctness; `settings.local.json` survival.

## Review philosophy

Findings need file:line and a suggested fix; severity-ranked; verify claims by running code, not by trusting prose (this repo's history is the cautionary tale — reviews once scored a product whose hooks had never fired). Push back with evidence; accept pushback with evidence. When reviewing consolidation PRs (task 008), demand the migration table: old asset → new home → registry/routing updates → user-facing note.
