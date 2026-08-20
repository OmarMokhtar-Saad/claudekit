# Implementation Plan: Record two harness findings (2026-08-20)

## Overview

Two findings about the *harness* — not about product behavior — surfaced during the
plan-doctor-gate batch and would otherwise die with the session. Record them in the maintainer
docs: the `reviewer` agent has no execution capability (so plan reviews are structurally static,
and `.ai/REVIEW_GUIDE.md` asks it to do something it cannot), and `ops-enforcement.sh`'s exemption
prefixes silently disable enforcement for *any* tree under them, including a whole repo clone.

Neither finding is fixed here. Both are recorded with evidence; the asset/security decisions they
imply are owner-gated and are written as options with trade-offs, not as recommendations.

## Scope

- **In Scope:** documentation-only edits to `.ai/BACKLOG.md` and `.ai/REVIEW_GUIDE.md`.
- **Out of Scope:** any change to `.claude/agents/reviewer.md`, `.claude/hooks/ops-enforcement.sh`,
  its exemption list, `tests/`, `install.sh`, `templates/`, `docs/`, or `CHANGELOG.md`. Parallel
  workstreams own those files. No CHANGELOG entry: both findings are maintainer-facing only and
  change no user-visible behavior. No new recurrence-class row is invented — Finding 2 is an
  instance of the existing `vacuous-check` class and is written as prose that points at it.

## Prerequisites

- Branch `perf/token-efficiency`, clean tree.
- No prerequisite work; the two target files exist and are edited additively.

## Implementation Steps

### Step 1: Add a hook-review checklist bullet about fixture/clone location

- **File:** `.ai/REVIEW_GUIDE.md`
- **Action:** Modify
- **Description:** Add one bullet to the **Hook changes:** maintainer checklist so a reviewer
  checking a hook test is prompted to confirm the fixture is not under an exempted prefix.
- **Details:** `add_after` the anchor
  `- [ ] settings.json registration matches (dangling-hooks CI).` (line 33). Content begins with a
  leading `\n`. New bullet: verify the fixture location is outside the hook's exemption prefixes
  before trusting a pass; an enforcement test that passes by *allowing* is suspect until located.

### Step 2: Add a prose subsection generalising the exemption-prefix lesson

- **File:** `.ai/REVIEW_GUIDE.md`
- **Action:** Modify
- **Description:** Extend the "What the 2026-08-19/20 batch actually proved about this table"
  section with a third bolded paragraph, matching the two existing ones in tone (claim in bold,
  concrete evidence, heuristic). It carries both findings: the exemption-prefix generalisation with
  its diagnostic signature (exit 2 expected, exit 0 received), and the note that the mutation
  discipline the section prescribes cannot be performed by the read-only `reviewer` agent, so the
  orchestrator owns it until that is resolved (ticketed, not decided).
- **Details:** `add_after` the anchor
  `for one of them. Declare the collateral per mutant and assert set equality.` (line 108).
  Content begins with a leading `\n`.

### Step 3: Add a `P0.75` backlog section with both findings

- **File:** `.ai/BACKLOG.md`
- **Action:** Modify
- **Description:** Insert a new dated section between P0.5 and P1 holding three items: the
  reviewer-cannot-execute item (with options a/b/c and the security tension on (a) stated
  explicitly), and the exemption-list-breadth item (recorded as worth revisiting, with no proposed
  change). Format matches the file: `- [ ] **bold lead** — body`, repo-relative `path:line` refs.
- **Details:** `add_before` the anchor `## P1 — high value, unblocked`. Content ends with a
  trailing blank line so the P1 heading keeps its separation. `add_before` prepends, so the leading
  `\n` rule does not apply to it, but the content still ends with `\n\n` to be safe.

## Testing Strategy

Docs-only; no behavioral surface. Verification is:

- `python3 .claude/operations/scripts/validate-config-json.py .claude/plans/plan-harness-findings.ops.json`
  → APPROVED (run at plan time, must be re-run before execution).
- After execution: `git diff --stat` shows exactly two files changed, both under `.ai/`.
- After execution: `sed -n '30,40p' .ai/REVIEW_GUIDE.md` and `grep -n "P0.75" .ai/BACKLOG.md`
  confirm the inserts landed on their own lines and did not concatenate onto an anchor line
  (the `add_after` leading-`\n` hazard already recorded in BACKLOG P0.5).
- `python3 scripts/gen-docs.py --check` still passes (no counts touched; guards against an
  accidental count-bearing string).
- No pytest impact expected; the full suite is unaffected by `.ai/` content.

## Rollback Plan

`git checkout -- .ai/BACKLOG.md .ai/REVIEW_GUIDE.md`. Both operations are additive inserts with no
deletions, so revert is total and no other file is involved.

## Risk Assessment

- **Low Risk:** both files are maintainer prose with no generated content, no counts, and no
  consumer. Both edits are additive. Neither file is referenced by a test that asserts its content.
- **Low Risk:** anchor uniqueness confirmed (`grep -cF` = 1 for all three anchors).
- **Medium Risk:** the `add_after` newline hazard — mitigated by both `add_after` payloads starting
  with `\n`, and by the post-execution `sed`/`grep` check above.
- **Medium Risk:** wording risk. Finding 1 touches an owner-gated asset decision; the text must not
  read as a decision. Mitigation: options are lettered with trade-offs and no recommendation, and
  the collision with the tool-grant work (`tests/test_agent_tool_grant_drift.py`) is stated inside
  option (a).
- **High Risk:** none. No blast radius outside `.ai/`; no god-node touched.
