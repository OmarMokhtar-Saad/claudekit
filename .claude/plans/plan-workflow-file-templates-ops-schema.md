# Implementation Plan: Fix the legacy ops.json schema in `_shared/WORKFLOW_FILE_TEMPLATES.md`

**Goal:** make the shared agent template teach the exact ops.json schema `validate-config-json.py` / `operations-schema.json` / `execute-json-ops.py` actually accept, instead of a legacy schema they reject (AGENTS_KNOWN_ISSUES.md #9).
**Approach:** replace the template's Operations Config section with the canonical modern schema + an enforced-rules table, then add a behavioral test that materializes every ops-config-shaped JSON fence in `.claude/agents/**` and `.claude/skills/**` into a throwaway project and runs the REAL validator on it, so the class of bug cannot silently return; finish by retiring the issue in the maintainer docs.
**Riskiest step:** the new test is corpus-wide — it also grades the three pre-existing examples in `generate-operations-config/SKILL.md` and the one in `planner.md`; if the materializer's anchor synthesis is wrong for any of them the suite goes red on files this plan did not touch (mitigation and per-example dry-analysis in §Risk Assessment).

> **Artifact location note.** The intended homes are
> `.claude/plans/plan-workflow-file-templates-ops-schema.md` and
> `.claude/plans/ops-workflow-file-templates-ops-schema.json`. Writes into `.claude/**` were
> refused by the platform's sensitive-path gate during planning, so both artifacts were written
> to the repo root instead. Move them before executing:
> `mv plan-workflow-file-templates-ops-schema.md ops-workflow-file-templates-ops-schema.json .claude/plans/`

---

## Overview

`.claude/agents/_shared/WORKFLOW_FILE_TEMPLATES.md` ships an ops.json template using
`version` / `plan_ref` / `id` / `type: "create|modify|delete|move|rename"` / `file` /
`changes[].action` / `changes[].target` / `dependencies` / `rollback` / `validation`.
Every one of those is rejected by the live contract:

- `operations-schema.json` is `oneOf[legacy, modern]`, both with `additionalProperties: false`
  and `required: ["plan", "files"|"operations"]` — so `version`, `plan_ref` and `validation`
  fail at the top level before any guard runs (`validate-config-json.py:303-309`, returns early).
- Modern operation items are `oneOf` three closed objects: `file_create` (`type`,`path`,`content`),
  `file_delete` (`type`,`path`,`reason` minLength 10), `code_edit` (`type`,`path`,`edits`), each
  allowing only optional `id`/`description` (`operations-schema.json:107-167`).
- `validate-config-json.py:414` hard-codes `valid_types = ['file_create','file_delete','code_edit']`
  (GUARD 29) and `execute-json-ops.py:792-796` prints `Unknown operation type` for anything else.
- `edits[]` entries are `required:["find"]` + `oneOf` exactly one of
  `add_after`/`add_before`/`replace`/`delete:true` (`operations-schema.json:158-163`,
  simulated cumulatively in `_validate_edits`, `validate-config-json.py:159-231`).

So an agent that follows the shared template produces a config the validator rejects and the
Reviewer must AUTO-REJECT. This plan makes the template correct and makes correctness mechanical.

## Scope

- **In Scope:**
  - Rewrite the "Operations Config Template" section of `_shared/WORKFLOW_FILE_TEMPLATES.md`
    against the actual schema, with a validator-clean worked example and a rules table.
  - New behavioral regression test `tests/test_agent_doc_ops_examples.py`: runs the real
    `validate-config-json.py` on every ops-config-shaped JSON fence found in
    `.claude/agents/**` and `.claude/skills/**`.
  - Sweep + retire the issue in maintainer docs: `.ai/AGENTS_KNOWN_ISSUES.md` #9,
    `.ai/AGENTS_PROTOCOLS.md` (its explicit "Warning" about this template),
    `.ai/TECH_DEBT.md` row 1, `.ai/BACKLOG.md` P1 item; `CHANGELOG.md [Unreleased] → Fixed`.
- **Out of Scope:**
  - The other 15 issues in AGENTS_KNOWN_ISSUES.md (QUICK_START drift #6, phantom
    `opensource-forker` #8, etc.). Untouched.
  - The Plan/Review/Verification/Explore/Debug/State/Handoff templates in the same file —
    they do not encode the ops schema and are consistent with `planner.md`/`reviewer.md`.
  - Consolidating the three homes of the schema (planner.md summary + skill CANONICAL +
    this template). Task 008/009 owns de-duplication; this plan makes the copies *agree* and
    marks the skill + JSON schema as owners.
  - Stale "516 tests" counts across `.ai/` + `CLAUDE.md` — already a tracked backlog sweep
    (`.ai/BACKLOG.md:45`); adding a test file does not affect `gen-docs.py` (it counts only
    agents/commands/skills/hooks, `scripts/gen-docs.py:41-65`).
  - `templates/**` mirrors: verified by grep to contain **no** ops-config JSON fences
    (`"operations"|"plan_ref"|"files": [` → no matches), so nothing to sweep there.

## Prerequisites

- `.claude/settings.local.json` present with `ECC_HOOK_PROFILE=minimal` (repo's own
  ops-enforcement hooks otherwise block Edit/Write — CLAUDE.md "Session setup gotcha").
- `jsonschema>=4` installed (`pip install -e ".[dev]"`). Without it the validator prints a
  warning and *skips* schema validation (`validate-config-json.py:718-720`), which would make
  the new test weaker but still meaningful (GUARD 29 + field guards still fire). CI installs
  the dev extra, so the schema layer is exercised there.
- Sourced facts (read, not assumed): `validate-config-json.py`, `execute-json-ops.py:720-830`,
  `operations-schema.json`, `shared.py` (`PROTECTED_PATTERNS` includes `*.md` → no example may
  `file_delete` a markdown file), `.ai/AGENTS_KNOWN_ISSUES.md:26`.

---

## Implementation Steps

### Step 1: Replace the legacy Operations Config Template
- **File:** `.claude/agents/_shared/WORKFLOW_FILE_TEMPLATES.md`
- **Action:** Modify
- **Description:** Swap the legacy JSON block (lines 55-84) for the canonical modern schema.
- **Details:**
  - Name the schema owners up front: `generate-operations-config` (CANONICAL SCHEMA) and
    `.claude/operations/scripts/operations-schema.json`; state that this copy defers to them.
  - Worked example is deliberately *validator-clean when materialized*: one `file_create`
    (`src/repositories/user_repository.py`, non-empty `content`), one `code_edit` with two
    non-overlapping, non-ambiguous `find` anchors, one `file_delete` (`.py`, not protected,
    reason well over the 10-char floor).
  - Add a rules table covering: allowed top-level keys; the three operation types; `path`
    (relative, no `file`/`target`); per-type required fields; the four edit actions;
    `additionalProperties: false` (with "rollback/dependency/validation notes belong in
    plan.md"); the `MAX_DELETIONS = 3` cap (GUARD 26).
  - State that array position IS execution order (the schema has no `dependencies` field).
  - End with the validation command so the template closes the loop it previously left open.
- **Verification:** `python3 .claude/operations/scripts/validate-config-json.py` accepts the
  embedded example (proved by Step 2's test case for this file).

### Step 2: Add the corpus-wide regression test
- **File:** `tests/test_agent_doc_ops_examples.py`
- **Action:** Create
- **Description:** Mechanically prove every ops.json example in the agent/skill corpus validates.
- **Details:**
  - Scan `.claude/agents/**/*.md` + `.claude/skills/**/*.md` for `json` fences; parse each.
  - `_is_ops_config()` keys on a non-empty `operations` list **or** a `files` list of dicts —
    deliberately NOT on `plan`, because the bug under guard replaced `plan` with `plan_ref`;
    a `plan`-keyed filter would have skipped exactly the broken example.
  - `_materialize()` builds the on-disk state each example assumes inside `tmp_path`:
    `code_edit`/`file_delete` targets are created (each `find` anchor written once, skipping
    anchors already present so repeated ops on one path stay unambiguous under GUARD 11);
    `file_create` targets are deliberately left absent (GUARD 18).
  - `_validate()` runs the real `validate-config-json.py` via `subprocess` with `cwd` = the
    tmp project and `ECC_HOOK_PROFILE` forced explicitly (repo test convention: never inherit
    the developer session's profile).
  - Four tests: (1) parametrized "example is APPROVED by the real validator";
    (2) `MIN_EXAMPLES` floor per known doc so a rename/fence change cannot silently reduce the
    guard to zero cases; (3) every ops-*shaped* fence must parse as JSON (an unparseable fence
    would otherwise be skipped by (1)); (4) no legacy keys/types anywhere in the parsed
    examples (`version`, `plan_ref`, `file`, `changes`, `action`, `target`, `dependencies`,
    `rollback`, `validation`, `build_command`… and types `create|modify|delete|move|rename`) —
    this one gives the crisp "issue #9 regression" diagnostic.
  - Behavioral over structural: nothing is asserted about the markdown's wording; the assertion
    is the validator's exit code.
- **Verification:** `python3 -m pytest tests/test_agent_doc_ops_examples.py -q` → 5 validator
  cases (WORKFLOW_FILE_TEMPLATES x1, planner x1, generate-operations-config x3) + 3 guard tests,
  all pass. Sanity-check the guard bites: temporarily reintroduce `"plan_ref"` in the template
  and confirm the suite goes red.

### Step 3: Record the fix in the user-facing changelog
- **File:** `CHANGELOG.md`
- **Action:** Modify
- **Description:** Add a `[Unreleased] → Fixed` entry (prompt-corpus change is user-visible).
- **Details:** Insert as the first bullet of the first `### Fixed` block, before the
  `using-git-worktrees` entry. Names the old bad fields, the new schema, and the new test.

### Step 4: Retire issue #9 in the agent-issue catalog
- **File:** `.ai/AGENTS_KNOWN_ISSUES.md`
- **Action:** Modify
- **Description:** Rewrite item 9 as FIXED with the date, the new schema, and the guard test.
- **Details:** Keep the item numbered 9 (items 10-16 reference their own numbers; renumbering
  would break `.ai/TECH_DEBT.md`, `.ai/BACKLOG.md` and `docs/` cross-references).

### Step 5: Drop the stale warning in the protocol digest
- **File:** `.ai/AGENTS_PROTOCOLS.md`
- **Action:** Modify
- **Description:** Replace the "**Warning:** its ops.json template uses a legacy schema …"
  sentence with an accurate description of the corrected section plus the guard test.

### Step 6: Pay off the tech-debt row
- **File:** `.ai/TECH_DEBT.md`
- **Action:** Modify
- **Description:** Delete row 1 ("Legacy ops.json schema in shared template"), per the file's
  own rule "Live register — remove entries when paid". Remaining rows keep their numbers
  (they are stable labels referenced from other docs, not positions).

### Step 7: Remove the completed P1 backlog item
- **File:** `.ai/BACKLOG.md`
- **Action:** Modify
- **Description:** Delete the P1 bullet "Fix `_shared/WORKFLOW_FILE_TEMPLATES.md` legacy ops
  schema"; the backlog lists open work, and CHANGELOG + AGENTS_KNOWN_ISSUES carry the record.

### Step 8 (post-execution, not an ops operation): session bookkeeping
- **Files:** `.ai/SESSION_STATE.md`, `.ai/CHANGELOG_AI.md`
- **Action:** Modify, by the implementing session at the end of the work period
- **Description:** CLAUDE.md requires both to be updated before ending a work period. They are
  deliberately excluded from ops.json: their content depends on the *measured* results of this
  execution (test counts, DoD command output), which do not exist at planning time, and their
  anchors move every session (high drift risk for a `find` pattern authored hours earlier).

---

## Testing Strategy

1. **New behavioral test** (Step 2) — the primary artifact. Executes the real validator against
   every embedded example; failure message points at `<doc>#<block index>`.
2. **Negative control** (manual, once): reintroduce a legacy field in the template and confirm
   both `test_embedded_ops_example_is_approved_by_the_real_validator` and
   `test_ops_examples_use_no_legacy_schema_fields` fail. A guard never observed failing is not
   a guard.
3. **Existing suite unaffected but re-run in full:** `python3 -m pytest tests/ -q` (all must
   pass). Note `tests/test_delivery_contract_smoke.py::test_queued_ops_configs_validate_against_head`
   validates every queued config in `.claude/plans/` — the ops config for this plan must be moved
   to `.claude/plans/archive/` (with a README entry) once executed, or it will fail that test on
   the next run (its `find` anchors are spent).
4. **DoD gate:** `ruff check src/ tests/ scripts/` (line-length 100), `mypy`,
   `python3 scripts/gen-docs.py --check` (counts unchanged — no agent/command/skill/hook added),
   `python3 scripts/gen-registry.py --check`, `shellcheck install.sh .claude/hooks/*.sh`.
5. **End-to-end spot check:** `python3 .claude/operations/scripts/execute-json-ops.py <ops> --dry-run`
   before the real run.

## Rollback Plan

- Every operation is backed up by the executor under `backups/<plan>-<timestamp>/`;
  `python3 .claude/operations/scripts/restore-backup.py <backup-dir>` reverts all six file
  edits, and `--post` restores the post-state checkpoint if a later external change intervenes.
- Manual fallback: `git checkout -- .claude/agents/_shared/WORKFLOW_FILE_TEMPLATES.md CHANGELOG.md .ai/AGENTS_KNOWN_ISSUES.md .ai/AGENTS_PROTOCOLS.md .ai/TECH_DEBT.md .ai/BACKLOG.md`
  and `rm tests/test_agent_doc_ops_examples.py`. No file is deleted by this plan
  (zero `file_delete` operations), so nothing is unrecoverable.
- Stamp the drift gate before executing: `validate-config-json.py <ops> --stamp-baseline`.

## Risk Assessment

- **Low Risk**
  - Steps 3-7: prose-only edits to changelog and maintainer docs; no behavior depends on them.
  - Doc counts: `gen-docs.py` counts only agents/commands/skills/hooks — a new test file and
    edited markdown do not move any count, so `--check` stays green.
  - Deletion cap / protected files: this plan performs **zero** `file_delete` operations.
- **Medium Risk**
  - **Step 1 anchor exactness.** The `find` is the full legacy block including both fences; a
    single whitespace mismatch fails GUARD 10. Mitigated by copying verbatim from the Read
    output and by validating this ops config before handoff (the validator simulates the edit).
  - **Step 2 grading pre-existing examples.** Dry-analysis of each of the 4 non-new examples:
    `planner.md` (create `src/module/new_file.py` absent OK; delete `src/module/deprecated.py`
    reason 39 chars, not protected OK; edit `src/module/file.py` anchor unique OK);
    `SKILL.md` modern (same shape, reason 49 chars OK); `SKILL.md` legacy `files` format
    (routed through `validate_legacy_format` OK); `SKILL.md` rename example (3 files, one anchor
    each, each unique in its materialized file OK). If a future example is written with two
    overlapping anchors in one file, GUARD 11 will flag it — that is a true finding, not a
    false positive, and the fix is to disambiguate the example.
  - **Warnings are not failures.** GUARD 17 (missing parent dir) and GUARD 21 (unsafe chars in
    plan name) only `print`; they do not affect the new test's exit-code assertion. Confirmed in
    `validate-config-json.py:144-151, 546-556`.
- **High Risk**
  - **None identified.** No source code, hook, installer or executor logic changes; the ops
    engine itself is untouched. The blast radius is the prompt corpus (which the new test now
    pins) plus one additive test file.
  - Blast-radius note: `.claude/project-graph.json` does not exist in this tree, so no
    GOD-NODE analysis was possible (`project-graph.py` would exit 3); the manual equivalent —
    grep for every reference to the touched files — found the references handled above plus
    historical audit notes in `review/` that are intentionally left as-is.

## Operations

- **Ops config:** `ops-workflow-file-templates-ops-schema.json` (move to `.claude/plans/`)
- **Operations:** 7 (1 `file_create`, 6 `code_edit`, 0 `file_delete`)
- **Order:** template fix → test → CHANGELOG → AGENTS_KNOWN_ISSUES → AGENTS_PROTOCOLS →
  TECH_DEBT → BACKLOG. The template must be corrected before the test lands, or the suite is
  red between operations.
