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
- [ ] Fixture location checked against the hook's exemption prefixes. A gate test that passes by ALLOWING is unverified until you know where its fixture lives (`tests/test_ops_enforcement_scope.py:42` places fixtures beside the repo for exactly this reason).

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
| `fix-introduces-larger-hole` | the fix for a finding opens a worse one than it closed | **nothing mechanical, and probably nothing can be** — the only thing that caught all four was a FRESH reviewer told to attack the fix, not to confirm the finding was addressed. Make that the delta-review contract instead. |
| `guard-cannot-express-guarded-case` | a rule is added in one place while the artifact the model actually fills cannot express it | nothing yet — candidate check: assert every verdict/status token a prompt instructs also appears in that prompt's output template |
| `count-asserted-not-derived` | a total is restated in prose/metadata instead of re-derived from the thing it counts | `gen-docs.py --check` covers component counts only; in-document totals are ungated |
| `denylist-inside-an-allowlist` | the outer set is allowlisted but an inner dimension (flags, subcommands, arguments) is denylisted, so the security property collapses to "we thought of the bad ones" | nothing yet — the tell is a review round that finds new members of a class a previous round claimed to have swept |
| `silent-failure` | an error is swallowed (`\|\| true`, bare `except`, `2>/dev/null`) and the caller reports success | nothing yet — 12 LIVE instances in `review/code-review-triage.md`; the largest class in the repo |
| `unanchored-pattern` | a pattern matched without anchoring, so it fires on substrings | nothing yet — 6 LIVE |
| `unwired-artifact` | a file ships that nothing executable references | nothing yet — 4 LIVE; `config.schema.json` went 46 days unapplied |
| `type-contract-drift` | an annotation disagrees with what the function returns | `mypy` — but `pyproject.toml:57` scopes it to `src/claudekit`, so the operations engine is unchecked |
| `validator-executor-divergence` | the validator and the thing it gates disagree about what is valid | nothing yet — 2 seams: unknown edit fields (validator rejects, executor ignores) and sequential-edit anchors (validator checks the original file, executor applies in order) |

### What the 2026-08-19/20 batch actually proved about this table

Four classes above crossed the threshold inside a single batch, which is worth reading as a
result rather than a coincidence.

**`fix-introduces-larger-hole` is the one to design around.** Four instances in two days: a
reviewer that went from refusing every review to reporting clean while blind to new files; a
hook-conflict fix that opened an arbitrary source write through a symlinked inbox; an installer
fail-closed check that would have blocked every installation; and a `PreToolUse` control
bypassed by dispatch order. Every one was caught by a FRESH reviewer instance told to attack the
fix. A reviewer asked "did they address the finding? yes" passes all four. That is the delta-review
contract, and it is worth more than any check we could write.

**Writing a mutant finds defects before the mutant runs.** Three times in this batch, the act of
trying to disable a rule exposed that the rule did not live where the table implied: `X = () or
(...)` neutered nothing (it evaluates to the non-empty tuple), `_GIT_OUTPUT_FLAGS` could not be
disabled because the attached `--output=` form was hardcoded at the call site, and `git remote
add` turned out to mutate through positionals that no flag rule touched. Heuristic:
**a guard you cannot disable in one place is a guard whose enforcement you do not understand.**

**Mutants must assert the exact flipped set.** An earlier revision claimed each of eight mutants
flipped only its own case; the test asserted only that the target flipped, and the claim was false
for one of them. Declare the collateral per mutant and assert set equality.

**An exempted prefix disables enforcement for everything under it — including a whole clone.**
The standing warning was narrow: don't put hook fixtures under `$TMPDIR`. The rule is wider.
`.claude/hooks/ops-enforcement.sh:43` exempts `/private/tmp/claude-*`, `/tmp/claude-*` and
`/{private/,}var/folders/*`, and the exemption tests the *target path*, so any tree placed there
loses enforcement wholesale. Hit from the other direction on 2026-08-20: a fresh clone made inside
the session scratchpad (under `/private/tmp/claude-*`) produced 15 failures in
`tests/test_ops_enforcement_scope.py`, because its fixtures live in `REPO.parent`, which for that
clone was the exempt prefix. Re-cloning to a non-exempt parent: 1227 passed, 0 failed. There was no
regression and no CI gap (CI clones to `/home/runner/work/...`). **Diagnostic signature: assertions
expecting exit 2 receive exit 0** — a `vacuous-check` produced by location, not by code. So verify
where the clone and the fixtures sit before trusting ANY ops-enforcement result, and treat a gate
test that passes by allowing as suspect until its location is checked.

One caveat on everything above: the `reviewer` agent holds Read, Grep and Glob and cannot execute,
so it cannot write a mutant, apply an ops.json, or run the DoD commands. Until that is resolved
(BACKLOG P0.75) the mutation discipline in this section is the ORCHESTRATOR's to run, and a plan
review should be read as a static read-through, not as evidence that anything was executed.

## Review philosophy

Findings need file:line and a suggested fix; severity-ranked; verify claims by running code, not by trusting prose (this repo's history is the cautionary tale — reviews once scored a product whose hooks had never fired). Push back with evidence; accept pushback with evidence. When reviewing consolidation PRs (task 008), demand the migration table: old asset → new home → registry/routing updates → user-facing note.
