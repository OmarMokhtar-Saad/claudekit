# Plan: `request-shaping` skill + `/ask` command

**Status:** REVISED after review round 1 (REJECTED, 62/100) — awaiting owner approval (hard rule 5)
**Tier:** 2 (multi-file, no security/schema surface; no new module boundary → reviewer optional)
**Origin:** evaluation of https://github.com/nidhinjs/prompt-master (MIT). No code vendored — idea only.

## Overview

`/ask` + `request-shaping` add input-side request normalization: a raw request is
turned into a fixed Shaped Request block naming the six dimensions the pipeline routes
on, before any tier is chosen or agent spawned. Two new assets, one new test file, one
CHANGELOG entry, then a registry regeneration. No existing behaviour changes.

## Problem

Every prompt-quality asset in this repo is **output-side**: `writing-skills`, `writing-plans`,
`prompt-evaluation`, `token-optimization` all improve text *we* emit. Nothing normalizes the
**incoming user request** before routing. Result: the blast-radius tier in CLAUDE.md is chosen
from an unstructured sentence, and `planner` re-derives scope every time.

prompt-master solves an adjacent problem (write a prompt for a *foreign* tool) with a 13-framework
router and 30+ tool profiles. Both are dead weight here: our only target is this repo's own
pipeline. We take the *input-normalization* idea and drop the rest.

## Non-goals

- No framework router (RTF / CO-STAR / RISEN / CRISPE). Ceremony the planner does not consume.
- No foreign-tool profiles (Midjourney, Zapier, Cursor…).
- No model-spec verification step — `claude-api` skill already owns model facts; a second
  model table is a staleness liability.
- No always-on behaviour. `/ask` is invoked, never auto-triggered.

## Design

### 1. `.claude/skills/request-shaping/SKILL.md`

Frontmatter MUST carry `disable-model-invocation: true`.
Evidence: `src/claudekit/context_floor.py:model_invisible()` — invisible skills are
excluded from the `skill descriptions` category, which is at **8817 / 9000** (183 chars
headroom). A model-visible description would very likely breach the gate.

Body: the six dimensions we actually route on — deliberately *not* prompt-master's nine.

| # | Dimension | Feeds |
|---|---|---|
| 1 | Task verb (add / fix / refactor / explain / audit) | agent selection |
| 2 | Scope — concrete files, dirs, globs | ops.json `files` |
| 3 | Constraints — stdlib-only, bash 3.2, no new deps | planner guardrails |
| 4 | Success criteria — the command that proves it | DoD / verifier |
| 5 | Blast-radius tier (1/2/3) per CLAUDE.md | pipeline routing |
| 6 | Evidence needed — files to read before writing | context-first-workflow |

Missing-dimension protocol: **max 3 questions**, asked via `AskUserQuestion`.
Reuse `clarify`'s existing Blocking / Risky / Minor severity ladder verbatim — do not
invent a fourth question style (hard rule: no near-duplicate assets, task 008).
Only **Blocking** dimensions earn a question; Risky/Minor are stated as assumptions.

Output: a **Shaped Request block** — the artifact, in a fixed shape a planner can consume:

```
TASK: <verb> <object>
SCOPE: <paths>
TIER: <1|2|3>  (reason)
CONSTRAINTS: <list>
DONE WHEN: <command that must pass>
READ FIRST: <paths>
ASSUMED: <Risky/Minor calls made without asking>
```

### 2. `.claude/commands/ask.md`

- `description:` ≤ 90 chars. Budget: command descriptions 4851 / 6000 → 1149 free. Safe.
- `argument-hint: "<raw request>"`
- Mandatory skills: `request-shaping`, `clarify`, `context-first-workflow`.
- Workflow: extract 6 dimensions → ask ≤3 blocking questions → emit Shaped Request block →
  name the next command (`/plan` for Tier 2-3, direct ops.json for Tier 1) but **do not run it**.
  Stopping there keeps hard rule 5 intact: `/ask` never causes a code change.
- Honour `command-flags` (`--depth`, `--format`) rather than inventing flags.

## Steps

1. `file_create` `.claude/skills/request-shaping/SKILL.md` (model-invisible).
2. `file_create` `.claude/commands/ask.md`.
3. `file_create` `tests/test_request_shaping.py`.
4. `code_edit` `CHANGELOG.md` -- `[Unreleased]` gains an `### Added` entry.
5. **Regenerate the skills registry:** `python3 scripts/gen-registry.py`.

   Step 5 is mandatory and cannot be an ops operation. `gen-registry.py:246-249` fails
   `--check` for any `.claude/skills/<id>/SKILL.md` with no `skills-registry.json`
   entry, and a bare `file_create` adds no entry. It cannot be a `run_command` op
   either: `shared.py:ALLOWED_RUN_COMMANDS` is
   `{black, gofmt, goimports, isort, pip-compile, prettier, ruff, rustfmt}` -- `python3`
   is absent, and widening that allowlist is a security-surface change that this plan
   will not smuggle in as a side effect. Hand-editing the registry is forbidden by hard
   rule 8 (generated files are generator-owned), so running the generator is the only
   sanctioned path -- and it is the exact remedy the failing gate itself prints.

## Testing

See the Tests section below. `tests/test_request_shaping.py` asserts the registry and
docs gates directly, so step 5 being skipped fails pytest rather than surfacing later
at the commit gate.

## Rollback

Every operation is additive or a single appended hunk; there is no migration, no schema
change and no deletion, so rollback is exact and total:

1. `python3 .claude/operations/scripts/restore-backup.py` restores the pre-execution
   snapshot the executor writes for ops 1-4 (the engine's own transaction rollback).
2. If restoring by hand instead: `rm -rf .claude/skills/request-shaping`,
   `rm .claude/commands/ask.md`, `rm tests/test_request_shaping.py`, and revert the
   `### Added` hunk in `CHANGELOG.md`.
3. Re-run `python3 scripts/gen-registry.py` to drop the registry entry, which the
   generator removes once the skill directory is gone.
4. Confirm with `python3 scripts/gen-registry.py --check` and
   `python3 scripts/check-context-floor.py` -- both must exit 0.

Fleet rollback: the distribution script is additive and skips existing paths, so
undoing it is `rm -rf <project>/.claude/skills/request-shaping` and
`rm <project>/.claude/commands/ask.md` per project. Nothing is committed downstream,
so no downstream history is touched.

## Files

| File | Action |
|---|---|
| `.claude/skills/request-shaping/SKILL.md` | create |
| `.claude/commands/ask.md` | create |
| `tests/test_request_shaping.py` | create |
| `CHANGELOG.md` `[Unreleased]` | edit |
| `docs/SKILLS.md`, `docs/COMMANDS.md` | via `gen-docs.py` (counts are generator-owned, rule 8) |

## Tests (behavioural, not structural)

1. `SKILL.md` frontmatter parses and `model_invisible()` returns True for it.
2. `check_new_skill()` admits it without charge → floor gate still green.
3. `check-context-floor.py` exits 0 after both files exist.
4. `gen-registry.py --check` exits 0 -- this is the assertion that catches a skipped
   step 5, and it is the finding that rejected review round 1.
5. `gen-docs.py --check` exits 0.
6. The Shaped Request block template contains all six labelled fields (guards silent drift
   between the skill body and the command that consumes it).

## Gates before commit

`pytest -q` · `ruff check` · `mypy` · `gen-docs.py --check` · `gen-registry.py --check` ·
`gen-model-policy.py --check` · `check-context-floor.py` · `shellcheck` · `ck doctor --strict`

**Ordering:** step 5 (`python3 scripts/gen-registry.py`) must run *before*
`gen-registry.py --check` is invoked here. The generator run is outside the operations
engine's transaction, so nothing fails at execution time if it is skipped -- the
registry gate and `test_skill_is_registered` are what catch it.
Plus one adversarial `code-reviewer` round (review floor, all tiers).

## Risks

- **Overlap with `/clarify`.** Mitigation: `/clarify` analyses an existing *spec file*;
  `/ask` shapes a *raw request* with no artifact yet. If review finds the split thin,
  the fallback is to fold shaping into `/clarify` as a second mode rather than ship both.
- **Skill-description floor.** Neutralized by `disable-model-invocation: true`; test 2 proves it.

## Open decisions for the owner

1. Ship as `/ask`, or fold into `/clarify --mode=request`?
2. Should `/ask` be allowed to chain straight into `/plan`, or always stop and hand back?

## Review history

**Round 1 — REJECTED, 62/100.** Three findings, all reproduced before acting:
- *No Rollback section* (mandatory-rejection item). Fixed above.
- *`gen-registry.py --check` would fail* — `file_create` registers nothing. Fixed by
  explicit step 5 plus a test that asserts the gate, rather than by trusting the step
  to be remembered.
- *Tests narrower than the plan claimed* — registry/docs gates were promised but not
  asserted. Fixed in the Tests section.

Verified independently: the context-floor mechanism claim (`context_floor.py:59-97`)
and the judgement that the `clarify` split is composition rather than duplication.
