# Implementation Plan: review-record resolves records against the ops file's tree; bare approvals refused

## Overview
Two fixes to the approval gate, both taken from one measured qa-agents session. (1) `review-record.py`
resolves `.claude/reports/reviews/` against the cwd (`_records_dir()` -> `_project_root()` walking from
`Path.cwd()`, review-record.py:313-330). A session whose cwd is a main checkout, reviewing an ops.json in
a sibling worktree, writes the verdict under MAIN. `execute-json-ops.py --root <worktree>` chdirs into
the worktree and then refuses with "no review record exists [review-record exit 3]". (2) `write` accepts a
bare `--score 95 --decision APPROVED`, so the session kept asking its owner to type approvals for fixes
no reviewer had seen. After this change an approving verdict needs a parsed `--from-review` block, or
`--owner-approved`, the human owner's path. An agent's Bash call carrying that flag is denied at
PreToolUse by `block-no-verify.sh` under every profile. That deny is a **speed bump against agents, not a
sandbox** (hard rule 6). The residual paths are listed in Risk Assessment.

Revision 2 (review REVISE 87, `.claude/reports/reviews/review-record-ops-root.review.md`) covers five
findings. MAJOR: `--owner-approved` is now bound by a PreToolUse deny (ops 10-11), and the exit-7 text no
longer names the flag. MINOR 1: the plan-toplevel fallback is gone. MINOR 2: edit counts now match the
ops. MINOR 3: the CHANGELOG entry is plain bullets. MINOR 4: `owner` is handled in flow-analyst's
score-trend exclusion (op 12) and documented beside `--verdict-origin`.

## Phase 0: Design Precheck
Ownership model: a review record belongs to the ops file it binds. It is keyed by `ops_slug(ops)`, bound
by `sha256(ops)`, and it should also live in that file's project. "Project" means the git toplevel of the
ops file's directory. If the ops file is outside git, use today's cwd walk. There is **no plan
fallback**. The executor holds only the config, so a plan-rooted answer would put the record where the
executor never looks (review MINOR 1). Five places follow the new root: `record_paths`
(write/check/diff), `author_path`/`load_author`/`load_author_role` (the `*.author.json` sidecar, also
written by validate-config-json.py:1119 via `record_author`), `_rejections_dir` as used by `emit_brief`,
and the executor's pre-lookup `module.record_paths(s)` (execute-json-ops.py:985). `cmd_check` gets
`ops=config_file` (absolute), so it anchors on the same argument. The `plan="plan-<slug>.md"` that
check_approval passes (execute-json-ops.py:997) no longer affects the root. `resolve`, `resolve_ops` and
the `rejections search/stats/classify/backfill` queries do not change.

**Who may approve without a review.** The approval gate (execute-json-ops.py -> `review-record.py
check`) does not depend on the hook profile, so the guard on its escape hatch runs under every profile
too. It lives in `block-no-verify.sh`, an existing blocking PreToolUse Bash handler in
`dispatch-registry.json` (line 53) whose job is already "deny a flag that bypasses a gate". The new check
runs **before** that hook's profile guard. This repo runs its own sessions on the lightest profile, where
a guard that stood down would never bind. `dispatch.sh` does not skip handlers by profile (grep: no
profile logic in dispatch.sh or dispatch_resolve.py), so the hook's own guard line is the only switch.
No new hook, no registry row, no settings change, and no gen-docs hook-count change. The human path
survives because the owner types the flag in a real terminal or a `!` command, and neither goes through
PreToolUse.

**Sharing `_git_toplevel`:** a local 20-line helper in review-record.py, not an import (the reviewer
accepted this in round 1). **Bare-approval rule:** only APPROVED authorises
(`NON_RECORDABLE_DECISIONS`), with new exit code 7 (verified unused), placed after the
`--only-non-approving` exit-5 block.

## Scope
- **In Scope:** review-record.py (root resolution; `--owner-approved`; exit-7 refusal that does not name
  the flag; `owner` documented as a verdict_origin); execute-json-ops.py `check_approval` pre-lookup;
  `.claude/hooks/block-no-verify.sh` (agent deny, every profile); `.claude/agents/flow-analyst.md` (the
  score-trend exclusion gains `owner`); behavioural tests in tests/test_review_record.py and
  tests/test_hooks_behavioral.py; the 7 existing test callers that pass a bare APPROVED; CHANGELOG
  `[Unreleased]`.
- **Out of Scope:** the rejection-query subcommands; fleet sync (owner-gated, `--exclude qa-agents`);
  historical `.ai/` logs that quote a bare `write --decision APPROVED`; closing the residual self-approval
  paths listed in Risk Assessment.

## Prerequisites
- Prior-art searches (round 1): `rejections search` gave 14 keyword hits and `knowledge-ledger search`
  gave 3. None concerns record-root resolution or bare approvals. reflection-4e2c41055d84 (subprocess
  env inheritance) applies to the new tests: they build an explicit env with no inherited GIT_* and
  set `ECC_HOOK_PROFILE` explicitly.

## Implementation Steps

### Step 1: Root resolution + bare-approval refusal in review-record.py
- **File:** `.claude/operations/scripts/review-record.py`
- **Action:** Modify (op 1, **27 edits**, file order)
- **Details:**
  - Add `EXIT_UNATTESTED_APPROVAL = 7` after `RECORDS_DIR`.
  - Replace `_records_dir()` with `_git_toplevel(start)`, `_records_root(ops=None)` (toplevel of the
    ops file, else `_project_root()`, with no plan fallback, and a docstring that says why) and
    `_records_dir(root=None)`.
  - Add an optional `root=None` to `record_paths`, `_rejections_dir`, `emit_brief`, `author_path`,
    `load_author` and `load_author_role`. The default keeps the cwd walk.
  - `write_verdict`: new `owner_approved=False`. It refuses a bare APPROVED with exit 7. The stderr names
    code-reviewer and the `--from-review <file>` bind command, says never to ask the user to type a score
    or run an approval, and **does not name `--owner-approved`**. `--owner-approved` without
    `--from-review` sets `verdict_origin = "owner"`. Compute `root = _records_root(ops_path)` once.
  - The record comment (review-record.py:807-810) documents `"owner"`. A comment above `--verdict-origin`
    (1771) says `owner` is set only by `--owner-approved` and is deliberately not a choice.
  - `record_author`, `cmd_check` and `cmd_diff` call `root = _records_root(ops_path)`.
  - `cmd_write` forwards `owner_approved`. The help text for `--owner-approved` marks it HUMAN OWNER ONLY
    and says a PreToolUse speed bump denies it to agents.
- **Done when:** `write --help` lists the flag and Step 3's tests pass (~15 min).

### Step 2: Executor pre-lookup anchors on the config
- **File:** `.claude/operations/scripts/execute-json-ops.py`
- **Action:** Modify (op 2, 2 edits)
- **Details:** Add `_records_root` to the required-attrs tuple (fail closed when it is missing). Replace
  `module.record_paths(s)` with `root = module._records_root(config_file)` +
  `module.record_paths(s, root)`. This is the same call, with the same single argument, that write makes.
- **Done when:** the Step 3 executor tests pass (~5 min).

### Step 3: Behavioural tests for record roots and the refusal
- **File:** `tests/test_review_record.py`
- **Action:** Modify (op 3, 5 edits)
- **Details:** `_approve` and `_record_round` pass `--owner-approved` only for APPROVED. Both TestWriteSafety
  calls pass it too. Two classes are appended. `TestRecordsFollowTheOpsTree` (a)-(f) is unchanged from
  round 1. `TestApprovalNeedsAReview` is also unchanged, except that (a) now asserts
  `'owner-approved' not in res.stderr` too (MAJOR: the refusal must not advertise the flag).
- **Done when:** `python3 -m pytest tests/test_review_record.py -q` is green (~20 min).

### Step 4: Existing callers that pass a bare APPROVED
Caller inventory (the reviewer confirmed it complete in round 1):
- `.claude/commands/review.md` and `refine.md` bind with `--from-review`, and `record-code-review` uses the
  parsed path, so none of them change. Nothing under `.claude/agents` or `.claude/skills` calls `write`,
  so they do not change either.
- Tests (add `--owner-approved` to APPROVED calls only):
  - `tests/test_rejection_briefs.py` (op 4, 3 edits)
  - `tests/test_ops_approval_gate.py` (op 5, 1 edit)
  - `tests/test_review_identity_roles.py` (op 6, 1 edit)
  - `tests/test_approval_machinery.py` (op 7, 1 edit)
  - `tests/test_plan_index.py` (op 8, 1 edit)
  - `tests/test_pipeline_e2e.py` (op 9, 2 edits; line 322 is CONDITIONAL and stays)
- These are test subprocesses, not agent Bash calls, so the Step 5 hook never sees them.
- **Done when:** the full suite is green (~10 min).

### Step 5: Bind `--owner-approved` at PreToolUse (MAJOR)
- **File:** `.claude/hooks/block-no-verify.sh`
- **Action:** Modify (op 10, 2 edits)
- **Details:** A header line names the second duty. `TOOL_INPUT=$(cat)` moves above the profile guard,
  and the new block goes between them. It works in five steps:
  1. Scan the parsed `command`, or the raw payload when parsing fails (fail closed).
  2. Delete quote and backslash characters from the scan text.
  3. Extract every `--ow[a-z-]*` token.
  4. Deny (exit 2 + stderr via `deny`) when a token equals the full flag anywhere, which covers a renamed
     copy of the script. A token that is only an argparse prefix of the flag (`--ow`, `--owner`, ...)
     denies only when the command also names `review-record`, so `tar --owner=root` still passes.
  5. The whole command is scanned, so `bash -c`, heredocs and `F=--owner-approved; ... $F` are covered.
  - The stderr points to code-reviewer + `--from-review <file>` and says not to ask the user to run an
    approval.
  - No new line references the profile variable, so `profiles.scan_hook_guards` still reads one guard,
    and `test_minimal_declaration_equals_the_minimal_guard` stays green.
  - The code is bash 3.2-safe: `for` over `grep -o`, and `case` on a variable, so shellcheck SC2194
    does not fire.
- **Done when:** Step 6's tests pass and `shellcheck .claude/hooks/block-no-verify.sh` is clean (~15 min).

### Step 6: Behavioural hook tests
- **File:** `tests/test_hooks_behavioral.py`
- **Action:** Modify (op 11, 1 edit: new class `TestOwnerApprovedIsHumanOnly` inserted before
  `class TestOpsEnforcement:`)
- **Details:** Each test runs the real hook with an explicit `ECC_HOOK_PROFILE`:
  - The flag is blocked under minimal, standard and strict, and the stderr names code-reviewer and
    `--from-review`.
  - Quoted, prefixed (`--owner`, `--ow`), `bash -c`-wrapped, variable-indirected and renamed-script
    forms are blocked under minimal.
  - A truncated JSON payload carrying the flag is blocked under minimal (fail closed).
  - These pass under minimal and standard: `--from-review`, bare REVISE, `tar --owner=root`,
    `grep -n owner-approved ...` and `ls`.
  - Under minimal, a malformed payload without the flag still exits 0. This is the pre-existing minimal
    behaviour.
- **Done when:** `python3 -m pytest tests/test_hooks_behavioral.py tests/test_profiles.py -q` is green.

### Step 7: verdict_origin readers (MINOR 4)
- **File:** `.claude/agents/flow-analyst.md`
- **Action:** Modify (op 12, 1 edit)
- **Details:** I grepped `verdict_origin` over .claude/agents, commands, skills, hooks, operations/scripts,
  scripts/ and src/. It has two consumers:
  - flow-analyst.md:73 excludes `gate-token` and `reconstructed` from score trends. Owner rows gain the
    same exclusion, because the integer was typed, not judged.
  - review-record.py itself: line 701 copies the field into a brief row, and line 1544 sets
    `reconstructed`. `rejections stats` never filters by origin, so an owner approval counts like any
    other decision. That is correct, because stats count outcomes, not scores. No change there.
- **Done when:** the paragraph lists `owner`.

### Step 8: CHANGELOG (MINOR 3)
- **File:** `CHANGELOG.md`, **Action:** Modify (op 13). Two plain bullets go directly under
  `## [Unreleased]`, wrapped at ~95 columns with a two-space continuation like their neighbours. There is
  **no `### Changed` heading**.
- **Done when:** the bullets are the first two entries under `[Unreleased]` and no new `###` heading
  exists.

## Testing Strategy
Named mutants (PREDICTED by trace; code-reviewer must run them):
1. `_records_root` returns `_project_root()`: `test_write_lands_in_the_ops_files_worktree` and
   `test_executor_run_in_the_sibling_is_authorised` go red.
2. `check_approval` uses `module.record_paths(s)` with no root:
   `test_executor_looks_where_write_wrote_not_at_its_cwd` goes red. This is the only killer, because in
   the `--root <sibling>` test the chdir makes this mutant equivalent.
3. Delete the exit-7 block: `test_bare_approval_is_refused_and_writes_nothing` goes red.
4. Put `--owner-approved` back in the exit-7 text: the same test goes red on `'owner-approved' not in`.
5. Delete the hook's owner block: every blocked-case test in `TestOwnerApprovedIsHumanOnly` goes red.
6. Move the owner block below the profile guard: the minimal cases go red. This proves the check binds
   in this repo's own profile.
7. Drop the `review-record` condition on prefix tokens: `tar --owner=root` goes red (over-blocking).

Commands: `python3 -m pytest tests/ -q`, `ruff check .claude/operations/scripts/ tests/`, `mypy`,
`shellcheck .claude/hooks/block-no-verify.sh`, `python3 scripts/check-plan-artifacts.py --check`,
`python3 scripts/check-context-floor.py --check` (flow-analyst.md grows by ~2 lines).

## Rollback Plan
`git revert` the implementing commit. No data migration is needed. Records already written stay where
they are. Rows that carry `verdict_origin: owner` stay readable, because the field is free text to every
reader.

## Risk Assessment
- **Tier 3** (approval gate, and now a blocking hook): `reviewer` before execution.
- **HIGH, residual and stated plainly (MAJOR, hard rule 6):** the PreToolUse deny is a speed bump
  against agents, not a sandbox. An agent can still self-approve by:
  - writing a script file that carries the flag and running it in a second call;
  - `python3 -c` importing the module and calling `write_verdict(owner_approved=True)`;
  - hand-writing a record JSON under `.claude/reports/reviews/`;
  - composing the flag from pieces (`--$F`);
  - piping its own `=== REVIEW ===` block through `--from-review -`.
  This plan does not claim "an agent can never self-issue an approval". It claims that the direct,
  typed path is denied and that the refusal no longer advertises it. The last path above (a
  self-authored review block) stays open because the author != reviewer gate can only attest role, not
  session identity (planner memory `session-is-not-an-identity-axis`).
- **Medium:** the owner block runs under the minimal profile. `profiles.py`'s declaration still says
  `block-no-verify` is `off` under minimal, which stays true for its `--no-verify` duty. The header and
  the in-hook comment state the exception. UNVERIFIED: whether any doc table (docs/, `ck profile`
  output) presents minimal as "no blocking hook at all"; if one does, it needs a one-line note.
- **Medium, false positives:**
  - An agent command that names the full flag with its dashes is denied, for example
    `grep -- --owner-approved`, or a commit message that quotes it. The deny text tells the agent to
    drop the dashes.
  - **The commit for this very change must not put the literal flag in `-m`**. Use `-F <file>` or
    reword it.
- **Medium:** the bare-approval refusal is user-visible. Downstream scripts and fleet projects that
  record bare APPROVED get exit 7 after the fleet sync, which is owner-gated.
- **Medium:** a hook-exported `GIT_DIR` overrides `git rev-parse` cwd. The executor has the same
  exposure, and the tests strip GIT_*.
- **Medium:** an ops file in git whose toplevel has no `.claude/` records at the git toplevel.
- **Low:** 1-2 extra `git` subprocesses per record command. One extra JSON parse per Bash call under
  minimal (the hook previously exited before reading stdin).
- Verified in round 1 by the reviewer and no longer UNVERIFIED: exit 7 is unused, `## [Unreleased]` is
  unique, the executor's code-4 text, the caller inventory, and no test asserts `rubric` on a bare
  approval. New anchors checked this round with `grep -cF` (all = 1): the block-no-verify header line,
  its profile-guard line, `class TestOpsEnforcement:`, the flow-analyst paragraph, the record comment,
  and the `--verdict-origin` line.
- Validator: see the ops file. Baseline re-stamped after this revision.
