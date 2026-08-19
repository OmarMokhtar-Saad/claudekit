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
- [ ] Every review finding carries a `Class` (see the recurrence table below).
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

## Finding format and the recurrence ratchet

Every review finding — plan review, code review, or a maintainer reviewing ClaudeKit itself —
is one block. A finding that cannot fill `Scenario` and `Evidence` is not confirmed and is not
written.

```
F<n>      <one-line claim>
Verdict:  confirmed | refuted | unproven      (refuted is dropped, not softened)
Blocking: yes | no                            (yes = wrong behavior ships)
Where:    <path>:<line>                       repository-relative
Scenario: <the concrete sequence that produces the wrong result>
Evidence: <what was run or read, and what it returned>
Class:    <recurrence class from the table below, or "new: <name>">
Fix:      patch | ticket | decision_needed | dismiss
```

`Class` is the load-bearing field and the reason the block exists. **When a class reaches three
entries it earns a mechanical check, or an explicit written "cannot be mechanised, and here is
why."** Extend the table; never invent a synonym for a row that already exists. This ratchet is
what task 010 (eval framework) consumes — findings that live only in a transcript die with the
session, and the same class gets re-found instead of accumulating into a check.

| Class | Shape | What catches it now |
|---|---|---|
| `unconfirmed-revision` | a conclusion drawn from a tree never pinned to the reviewed ref | nothing yet — code-reviewer Phase 0 is prose, not a check |
| `vacuous-check` | a test or gate that cannot fail (mock-only, no-throw, or the fixture re-declares what the shipped artifact owns) | `verification-gap-lens` (prose); no mechanical check |
| `hardcoded-count` | a component count typed by hand instead of generated | `scripts/gen-docs.py --check` |
| `registry-drift` | an agent loads a skill the registry does not list | `scripts/gen-registry.py --check` |
| `dangling-hook` | `settings.json` references a hook file that does not exist | dangling-hooks CI check |
| `context-floor-creep` | always-on prompt text grows and nothing fails | `scripts/check-context-floor.py --check` |
| `prose-verified-claim` | a claim resting on reading prose instead of executing something | `_shared/VERIFICATION_PROTOCOL.md` refutation pass (prose) |
| `duplicate-asset` | a new near-duplicate agent/skill instead of extending the existing one | nothing yet — task 008 is manual |

## Review philosophy

Findings need file:line and a suggested fix; severity-ranked; verify claims by running code, not by trusting prose (this repo's history is the cautionary tale — reviews once scored a product whose hooks had never fired). Push back with evidence; accept pushback with evidence. When reviewing consolidation PRs (task 008), demand the migration table: old asset → new home → registry/routing updates → user-facing note.
