# Implementation Plan: pipeline-session-hygiene

## Overview

Three measured failures from 2026-09-16 — a main session that grew 51k -> 301k tokens over 317
turns with zero compactions, four follow-on defects inside 93/100-approved plans (the `reviewer`
agent has no Bash and cannot execute anything), and an implementer that declared COMPLETE while
the suite was still running and once ran `ck lint --update-baseline` to turn a red gate green —
get three prompt-level rules: a stage-handoff/compaction rule in the pipeline commands, a Tier 3
"static-only verdict cannot be the last review" routing rule, and an implementer prohibition on
premature completion and baseline mutation. Two phrase-pinned structure tests and a CHANGELOG
entry lock them in.

## Phase 0: Design precheck

The ownership model: every rule lands in the file whose reader actually performs the behaviour —
`/implement` and `/plan` and `/review` and `/refine` are read by the MAIN agent (the dominant cost
and the one that must compact), `implementer.md` is read by the implementer subagent (the one that
reports COMPLETE and mutates baselines), `.ai/REVIEW_GUIDE.md` is read by the maintainer routing
the review. The value of the change sits in exactly those files; no generated or downstream
artifact carries it. CLAUDE.md is deliberately NOT touched (see Risk Assessment).

Prior-art searches: `review-record.py rejections search` and `knowledge-ledger.py search` were not
run in this spawn — the caller supplied the measured findings and a hard 20-call discovery budget
which was spent on the line/char-budget measurements that actually gate this change.
`UNVERIFIED:` no prior rejection record was consulted.

## Scope

- **In Scope:** `.claude/commands/{implement,plan,review,refine}.md`, `.claude/agents/implementer.md`,
  `.ai/REVIEW_GUIDE.md`, `tests/test_pipeline_hygiene.py` (new), `CHANGELOG.md`.
- **Out of Scope:** CLAUDE.md (no char headroom — see below); `.claude/settings.json` and
  `.claude/hooks/*` (owned by the concurrent `plan-hook-stdin-and-reflection`);
  `.claude/agents/{planner,reviewer}.md` and `.claude/agents/_shared/*` (owned by the concurrent
  `plan-agent-token-caps`); any change to `suggest-compact` itself; any change that would make the
  reviewer executable (a tool-grant change is a separate, security-relevant decision).

## Prerequisites

None. All edits are prompt/doc/test text.

## Measured budgets (the constraint that shapes every edit)

`ck lint` command-line ratchet (`.claude/lint-baseline.json`, rule: count <= recorded):

| file | actual | baseline | headroom |
|---|---|---|---|
| `.claude/commands/implement.md` | 148 | 148 | **0 lines** |
| `.claude/commands/plan.md` | 105 | 105 | **0 lines** |
| `.claude/commands/review.md` | 125 | 125 | **0 lines** |
| `.claude/commands/refine.md` | 463 | 466 | 3 lines |

`tests/test_rejection_briefs.py::TestTheCallSitesPassItExplicitly` independently asserts
`review.md <= 125`, `refine.md <= 466`, `code-review.md <= 140`.

`scripts/check-context-floor.py --check`: CLAUDE.md 30996 / 31000 chars (**4 chars**, x4 weighted);
pipeline agent bodies (`planner.md` + `reviewer.md` + `implementer.md`) 42955 / 43000 (**45 chars**).

Consequences, and they are absolute:
1. Every command-file edit is **line-neutral** — text is folded onto lines that already exist.
2. The CLAUDE.md "Review routing" line is **not touched**; the routing rule goes to
   `.ai/REVIEW_GUIDE.md` (maintainer-facing, unbudgeted) and the agent-facing wording to
   `.claude/commands/review.md` (line-neutral). This is the smaller change *and* the only one
   that fits.
3. The `implementer.md` edit must pay for itself: the two new rules cost +59 and +127 chars, and
   two verbatim-duplicate passages (the "never read target files upfront" rationale appears in
   both Safety Rules and Anti-Patterns) are compressed for -72 and -75. **Measured net: +39 chars
   against 45 of headroom.**

## Implementation Steps

### Step 1: implementer.md — completion requires an exit code
- **File:** `.claude/agents/implementer.md` — **Action:** Modify
- **Details:** extend the existing Step 4 sentence about quoting actual output so it also forbids
  reporting before the command has exited.
- **Done when:** `grep -c "a running suite is not a PASS" .claude/agents/implementer.md` = 1. (~2 min)

### Step 2: implementer.md — baseline mutation is forbidden
- **File:** `.claude/agents/implementer.md` — **Action:** Modify
- **Details:** new Anti-Pattern bullet after the suppression-comments bullet: never run
  `ck lint --update-baseline` or `--no-verify`; a red gate is reported, never repaired.
- **Done when:** `grep -c -- "--update-baseline" .claude/agents/implementer.md` = 1. (~2 min)

### Step 3 + 4: implementer.md — pay for the additions
- **File:** `.claude/agents/implementer.md` — **Action:** Modify
- **Details:** compress the two duplicated "do not read target files upfront" rationales (Safety
  Rules keeps the full reason, Anti-Patterns keeps only the rule). Behaviour-preserving; the
  prohibition itself is untouched in both places, which is what
  `tests/test_agent_tool_grant_drift.py` pins.
- **Done when:** `python3 scripts/check-context-floor.py --check` still exits 0. (~3 min)

### Step 5: review.md — Tier 3 gets an execution-capable review
- **File:** `.claude/commands/review.md` — **Action:** Modify (line-neutral: extends line 18)
- **Details:** a Tier 3 plan, or any plan whose ops touch hooks, tests, or executable scripts,
  makes the `reviewer` verdict STATIC-ONLY; it may not be the last review before execution —
  follow with `/code-review` on plan + ops (`code-reviewer` has Bash) running the plan's own
  Validation commands against a dry-run/scratch copy.
- **Done when:** `wc -l` still 125 and `grep -c STATIC-ONLY` = 1. (~5 min)

### Step 6: review.md — stage handoff on APPROVED
- **File:** `.claude/commands/review.md` — **Action:** Modify (line-neutral: extends the
  "If APPROVED" suggestion line)
- **Done when:** `wc -l` still 125. (~2 min)

### Step 7: implement.md — start from a compacted context
- **File:** `.claude/commands/implement.md` — **Action:** Modify (line-neutral: extends the
  Phase 1 "Note the validation commands" bullet)
- **Details:** STAGE HANDOFF — implementation starts from a compacted or fresh context whose only
  input is the plan path; if `suggest-compact` has fired, `/compact` first.
- **Done when:** `wc -l` still 148. (~3 min)

### Step 8: implement.md — Phase 3 completion discipline
- **File:** `.claude/commands/implement.md` — **Action:** Modify (line-neutral: extends the
  existing "never estimate" bullet) — a not-yet-exited command is not a PASS; a red gate is
  reported, never repaired with `--update-baseline`/`--no-verify`.
- **Done when:** `wc -l` still 148. (~3 min)

### Step 9: plan.md — hand off to a fresh context
- **File:** `.claude/commands/plan.md` — **Action:** Modify (line-neutral: extends the final
  `/review` suggestion line). **Done when:** `wc -l` still 105. (~2 min)

### Step 10: refine.md — the success banner names the handoff
- **File:** `.claude/commands/refine.md` — **Action:** Modify (line-neutral: extends the banner's
  "Next step" line; this extends yesterday's ceiling edit rather than duplicating it).
- **Done when:** `wc -l` <= 466. (~2 min)

### Step 11: REVIEW_GUIDE.md — the routing rule, in full
- **File:** `.ai/REVIEW_GUIDE.md` — **Action:** Modify (add_after the routing section's last line)
- **Details:** new subsection "Tier 3 plans need a review that can execute", stating the
  static-only rule and why (four of seven follow-on fixes on 2026-09-16 were defects inside
  93/100-approved plans).
- **Done when:** `grep -c "static-only" .ai/REVIEW_GUIDE.md` >= 1. (~5 min)

### Step 12: behavioural/structure tests
- **File:** `tests/test_pipeline_hygiene.py` — **Action:** Create
- **Details:** two phrase-pinned **structure** tests, named and docstringed as such (they assert
  prompt text, not runtime behaviour — an honest name is the point): implementer.md forbids
  baseline mutation; review.md names the execution-capable Tier 3 route.
- **Done when:** `python3 -m pytest tests/test_pipeline_hygiene.py -q` green, and each test fails
  when its pinned phrase is removed (prove the check can fail before trusting it). (~8 min)

### Step 13: CHANGELOG
- **File:** `CHANGELOG.md` — **Action:** Modify (add_after `## [Unreleased]`). (~3 min)

## Testing Strategy

- New `tests/test_pipeline_hygiene.py` — 2 structure tests, each proved falsifiable by temporarily
  deleting its pinned phrase in a scratch copy.
- Existing gates that this change can break, all of which must be run:
  `python3 -m pytest tests/ -q` · `ck lint` (command ratchet) ·
  `python3 scripts/check-context-floor.py --check` · `python3 scripts/gen-model-policy.py --check`
  (implementer.md frontmatter untouched, so this should stay green — run it anyway) ·
  `python3 scripts/gen-docs.py --check` · `python3 scripts/check-plan-artifacts.py --check` ·
  `ruff check src/ tests/ scripts/ .claude/operations/scripts/` · `mypy`.
- Line-budget spot check: `wc -l .claude/commands/{implement,plan,review,refine}.md` must print
  148 / 105 / 125 / <=466.

## Rollback Plan

All 13 operations are text edits plus one new file. `execute-json-ops.py` backs up every target
and rolls the whole batch back on failure. Manual rollback: `git checkout --` the six modified
files and `rm tests/test_pipeline_hygiene.py`.

## Risk Assessment

- **High Risk:** the 45-char pipeline-agent-body headroom is **shared** with the concurrent
  `plan-agent-token-caps` plan, which owns `planner.md` and `reviewer.md` — the same budget line.
  If that plan lands first and spends any of the 45 chars, `check-context-floor.py --check` fails
  after this plan executes even though this plan's own net is +39. Mitigation: run
  `check-context-floor.py --check` immediately before execution; if headroom is gone, shorten
  Step 2's bullet to a single line (`- NEVER run a baseline-mutating command (\`ck lint
  --update-baseline\`, \`--no-verify\`)`) which saves a further ~55 chars, or defer until the other
  plan has landed and re-measure. **Do not** resolve it by touching planner.md/reviewer.md.
- **Medium Risk:** three command files sit at exactly their `ck lint` baseline; any accidental
  newline in an edit payload breaks a currently-green gate and
  `tests/test_rejection_briefs.py::test_the_flag_was_added_line_neutrally`. Every command edit here
  is a `replace` on an existing line with no `\n` introduced.
- **Medium Risk:** CLAUDE.md has 4 chars of headroom, so the "Review routing" line keeps pointing
  at `.ai/REVIEW_GUIDE.md` while the guide's content changes — the single source moves, the
  pointer does not. Intentional; documented here so a reviewer does not read it as an omission.
- **Low Risk:** the two new tests are structure tests. They prove the text exists, not that any
  agent obeys it — stated in the file's docstring rather than implied away.
- **UNVERIFIED:** no project-graph impact query and no rejection-store search were run (discovery
  budget); the touched set is prompts/docs/tests with no importers.

## Validation commands

```bash
python3 .claude/operations/scripts/validate-config-json.py .claude/plans/plan-pipeline-session-hygiene.ops.json
python3 scripts/check-context-floor.py --check
python3 -m pytest tests/test_pipeline_hygiene.py tests/test_rejection_briefs.py tests/test_behavior_spec.py tests/test_agent_tool_grant_drift.py tests/test_lint.py -q
python3 -m pytest tests/ -q
python3 scripts/gen-model-policy.py --check
python3 scripts/gen-docs.py --check
python3 scripts/check-plan-artifacts.py --check
ruff check src/ tests/ scripts/ .claude/operations/scripts/
wc -l .claude/commands/implement.md .claude/commands/plan.md .claude/commands/review.md .claude/commands/refine.md
```
