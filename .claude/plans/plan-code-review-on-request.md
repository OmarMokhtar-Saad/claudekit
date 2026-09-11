# Implementation Plan: Code review runs only on user request

## Overview
Owner decision (2026-09-11): "make code review run only when i ask no automatic in any phase".
Code review (`code-reviewer`, adversarial diff review, `/code-review`, `/santa`) must never be
launched automatically by any agent, command, skill or policy. Plan review (`reviewer`, the
>=90 gate that authorises ops execution) is not code review and is unchanged. This plan
rewrites the mandatory per-PR "review floor" as an on-request rule and removes the remaining
places that mandate or auto-run code review.

Tier 2 (multi-file, prompt/policy text plus one test; no public API, schema, security or
architecture surface). No `reviewer` pass. Execution uses `--no-approval`, disclosed here; no
review verdict is recorded.

## Design precheck
Ownership model: the policy lives in the `CLAUDEKIT:TOKEN-MODEL-POLICY` region of `CLAUDE.md`,
which the fleet sync copies downstream and skips when the marker is already present
(CHANGELOG, v2 entry). That means a content change needs a marker bump. Correction to the task
brief: `ck adapt` does **not** own this region. `src/claudekit/adapt.py` writes its own
`PROJECT-ADAPT` region (`REGION_ID`, line 66). `tests/test_adapt.py` only uses the real
`TOKEN-MODEL-POLICY` markers as a parser fixture, and it asserts `version == 3` against the
live `CLAUDE.md`. The rule itself is carried by `CLAUDE.md:73`, `.ai/REVIEW_GUIDE.md`, and the
prompt assets that auto-run review: the `subagent-driven-development` skill (both copies) and
`gitOps.md`. Every one of these is covered below.

## Scope
- **In Scope:**
  - The policy line and marker bump in `CLAUDE.md`
  - Test fixtures plus the upgrade test in `tests/test_adapt.py`
  - Rule wording in `.ai/REVIEW_GUIDE.md` and `.claude/agent-memory/README.md`
  - The auto-review triggers in `.claude/agents/gitOps.md`,
    `.claude/skills/subagent-driven-development/SKILL.md` and
    `.agents/skills/subagent-driven-development/SKILL.md`
  - The `CHANGELOG.md` entry
- **Out of Scope:**
  - Running the fleet sync downstream (owner-gated)
  - Historical records (`.ai/CHANGELOG_AI.md`, `.ai/SESSION_STATE.md`, the older CHANGELOG
    entries, and the stale `.ai/BACKLOG.md:25-26` push item)
  - Places where the user invokes or is merely *offered* review: `/code-review`, `/santa`,
    `/audit`, the `/ship` Stage 2 lint check, the `/santa` suggestions in prp-implement,
    prp-pr, gan-build and opensource, the plan review in blueprint Phase 4, and the
    coordinator routing rows triggered by "review this code"

## Prerequisites
- Branch `chore/code-review-on-request` checked out; `ECC_HOOK_PROFILE=minimal` session.

## Implementation Steps

### Step 1: Policy line and marker (op1)
- **File:** `CLAUDE.md`
- **Action:** Modify
- **Details:** Change `TOKEN-MODEL-POLICY v3` START/END to `v4`. Replace the "Review floor
  (all tiers)" bullet with "Code review: only on user request — never auto-run by any agent,
  command, skill or phase (incl. `/santa`)". The round mechanics stay (fresh `code-reviewer`,
  never the author, REFUTE, stop at first zero-blocking round, ceiling 3, rounds 2+ read only
  the diff). The `Review routing` and `Verifier gate` lines are unchanged. The new line is 18
  characters shorter than the old one. This is measured: a first draft that was 26 bytes longer
  failed the context floor at 31040/31000, because CLAUDE.md sits at 30940/31000.

### Step 2: Rebind the fixtures and prove the upgrade (op2)
- **File:** `tests/test_adapt.py`
- **Action:** Modify
- **Details:** Change `REAL_START`/`REAL_END` to v4, `assert region.version == 4`, and
  `render_region(..., version=4)`. Add `test_a_v3_policy_region_is_upgraded_in_place_to_v4`,
  which applies a v4 body over a v3 `TOKEN-MODEL-POLICY` region. It asserts `replaced`,
  `previous == 3`, byte-exact output (one v4 region, no v3 residue, surrounding text kept) and
  that the parsed version is 4.

### Step 3: Review guide (op3)
- **File:** `.ai/REVIEW_GUIDE.md`
- **Action:** Modify
- **Details:** Insert "Code review runs only when the user asks …" directly before the round
  mechanics paragraph.

### Step 4: Agent memory README (op4)
- **File:** `.claude/agent-memory/README.md`
- **Action:** Modify
- **Details:** "the same adversarial review floor" becomes "the same review". The floor no
  longer exists.

### Step 5: gitOps foreign-branch review (op5)
- **File:** `.claude/agents/gitOps.md`
- **Action:** Modify
- **Details:** Branches from non-Claude tools still need review before merging. The agent now
  asks the user to run it and never launches it itself.

### Step 6: subagent-driven-development, both copies (op6, op7)
- **Files:** `.claude/skills/subagent-driven-development/SKILL.md`,
  `.agents/skills/subagent-driven-development/SKILL.md`
- **Action:** Modify
- **Details:** Stage 3 (code quality review) runs only if the user asked for code review.
  Otherwise the task is accepted after spec review. Three edits per copy: the flow diagram,
  the PASS outcome, and the Stage 3 intro.

### Step 7: CHANGELOG (op8)
- **File:** `CHANGELOG.md`
- **Action:** Modify
- **Details:** An `[Unreleased]` bullet covering the on-request rule, unchanged plan review,
  and the v3 -> v4 marker bump.

## Testing Strategy
All ops were run with `--no-approval` on a scratchpad copy of the tree before handoff.
```bash
python3 .claude/operations/scripts/validate-config-json.py .claude/plans/plan-code-review-on-request.ops.json
python3 .claude/operations/scripts/execute-json-ops.py .claude/plans/plan-code-review-on-request.ops.json --no-approval
ECC_HOOK_PROFILE=minimal python3 -m pytest tests/test_adapt.py -q
ECC_HOOK_PROFILE=minimal python3 -m pytest tests/ -q
ruff check src/ tests/ scripts/ .claude/operations/scripts/
python3 scripts/gen-docs.py --check
python3 scripts/gen-registry.py --check
python3 scripts/gen-model-policy.py --check
python3 scripts/check-context-floor.py --check
python3 scripts/gen-agents-mirror.py --check
python3 scripts/check-plan-artifacts.py --check .claude/plans/plan-code-review-on-request.ops.json
```
Behavioral proof: the new upgrade test fails on the pre-change fixture (a v3 constant cannot
produce a v4 region). `test_the_real_repo_markers_are_still_the_dialect_we_parse` fails if
`CLAUDE.md` and the fixtures disagree on the version.

## Rollback Plan
- `python3 .claude/operations/scripts/restore-backup.py` with the manifest the executor writes,
  or `git checkout -- <the 8 files>` (nothing is committed by this plan).

## Risk Assessment
- **Low:** The prompt and doc wording changes, and the CHANGELOG entry.
- **Medium:**
  - The marker bump means every fleet project receives the replaced block on its next sync.
    That is intended, but the sync is owner-run.
  - `CLAUDE.md` sits at 30940/31000 on the context floor, so the net change must not grow
    (the new line is shorter).
- **Judgment-dependent (flag to owner):**
  - (a) The `subagent-driven-development` Stage 3 review is an in-skill checklist, not a
    `code-reviewer` spawn. It is gated because it is an automatic code review phase. Stage 2
    "spec review" is left as is (verification against spec). The "two-stage review"
    description is also left alone.
  - (b) gitOps foreign-branch review is a security-flavoured control. It becomes ask-the-user
    rather than being dropped.
  - (c) Left unchanged as self-checks rather than code review: `autonomous-loop` Phase 5
    self-scorecard and `verification-before-completion` Phase 6 diff sanity check.
  - (d) `requesting-code-review` ("New feature: Yes, always") is left unchanged, because it
    carries `disable-model-invocation: true` and is therefore user-invoked only.
- **Rejection-brief search** ("code review automatic policy") found 7 matches, all keyword
  collisions on "review" (agent-memory-learning, retro2-*). None concerns review policy. No
  validated match.
- **Project graph:** not consulted for hubs. Every target is prose or a test, and `CLAUDE.md`
  is the only widely referenced file; its region change is covered by Step 2.
