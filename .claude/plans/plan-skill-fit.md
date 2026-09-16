# Implementation Plan: Skill Fit (MVP) -- audit, project profile, cards, match

**Slug:** `skill-fit` · **Ops config:** `.claude/plans/ops-skill-fit.json` (7 operations, one phase)
**Branch:** `feat/skill-profiles` · **Tier:** 2 (see Classification) · **Owner-approved goal:** yes

## Overview

Make ClaudeKit skills fit each project, cut token cost, and share proven skills across
the fleet -- as read-only analysis plus one project-owned settings file. Four `ck skill`
verbs (`audit`, `profile init`, `card`, `match`), one `ck doctor` check, preservation of
the new file across install/update/fleet sync, behavioural tests, user docs and a
CHANGELOG entry. No new hook, no prompt-injection path.

## Phase 0: Design precheck

**Ownership model.** The kit owns what the install manifest (`.claude/.claudekit-manifest.json`)
records; the project owns everything else. The new value lives in exactly two places:
(1) `src/claudekit/skill_fit.py`, which *derives* everything (stacks, tokens, buckets,
cards, suggestions) from files already on disk and persists nothing by default; and
(2) `.claude/skills-profile.json`, a PROJECT-owned file the kit never ships. Preservation
of (2) is carried by the existing machinery: install.sh records the manifest from the
staging tree *before* `preserve_assets.py` runs, so the profile is never listed and is
restored as custom. The one hole in that model is the known transition class (a manifest
that wrongly claims a project file -- the agent-memory MEMORY.md incident, fac44bc); the
plan closes it by name in `preserve_assets.py`, exactly as MEMORY.md is. Fleet sync
(`fleet-sync.py`) touches only named skill directories, `code-reviewer.md` and
`skills-registry.json`, so it cannot reach the profile -- proven by a test that runs it.
`fleet-enhance.py` copies kit files only; the kit tree ships no profile (test-pinned).
No value sits outside this model.

**Rejection-brief search** (`review-record.py rejections search "skill profile audit doctor"`,
exit 0, 9 matches). Validated priors and what this plan does differently:
- `fleet-skill-phaseA` [CRITICAL]: *a test asserted registry rows no operation produces.*
  Here no test asserts generated state: the registry is not edited, no skill is added,
  and `gen-docs --check` / `gen-registry --check` were run green on the executed post-state.
- `agent-memory-learning` [CRITICAL]: *tests called a fixture as a module (never ran).*
  Every test here was executed on a scratch copy of this worktree (below), and the
  preservation test was mutation-checked (fails when the `preserve_assets.py` edit is reverted).
- `retro2-*` (stale pinned hashes after a concurrent move): no hash is pinned; ops use
  no `baseline` stamp (stamp it only right before recording a verdict, per the
  stamp-before-verdict lesson).

## Classification (CLAUDE.md blast-radius tiering)

**Tier 2.** Multi-file (7 ops, 7 paths), no DB migration, <15 ops, one phase. Not Tier 3:
no enforcement hook, security module or ops-engine schema changes. It does add **public
CLI surface** (four `ck skill` actions, new flags) and touches `preserve_assets.py`
(installer data-preservation path), so per the Tier 2 rule "reviewer ONLY if
architecture is touched (public API)" this plan **routes to `reviewer`**.

**Project graph:** `.claude/project-graph.json` is absent in this worktree -> graph step
skipped (unknown blast radius stated rather than assumed). `cli/main.py` is the
de-facto hub of the CLI (every verb lives there); edits are additive and anchored.

## Scope

- **In scope:** `ck skill audit [--json] [--save] [--max-lines N] [--max-tokens N]`;
  `ck skill profile init`; `ck skill card`; `ck skill match --registry DIR [--json]`;
  doctor check for `.claude/skills-profile.json`; preservation by name in
  `preserve_assets.py`; tests; `docs/cli.md`; `CHANGELOG.md` `[Unreleased]`.
- **Out of scope:** any hook; any prompt injection; enforcing `disabled` (Phase 2);
  interpreting `packs` / `roles` beyond shape validation; installing suggested skills;
  editing kit skills (e.g. adding `stack_tags` to their frontmatter); registry schema
  changes; fleet-wide rollout (owner-gated, fleet HELD per memory).

## Design decisions (and why)

1. **One new module, not a new tree.** `src/claudekit/skill_fit.py` extends existing code:
   `adapt.detect()` (stack), `adapt.fenced_lines()` and `adapt.write_atomic()`,
   `context_floor.frontmatter/description_span/model_invisible` (same description
   accounting as the context floor), `skills.skills_dir/load_registry/renamed_map/NAME_RE/
   MAX_DESCRIPTION`, and `memory.rejections()` (the existing secret/credential/private-path
   sanitizer). `cmd_skill` gains a dispatch; `ck skill new` is unchanged except that its
   `--description` requirement moves from argparse into `cmd_skill` (refused exit 1, not 2,
   before anything is written).
2. **Stack detection** = `adapt.detect(root).stack` UNION a bounded source-file count
   (>=20 files per extension, the same threshold `fleet-sync.py` STACKS was measured with;
   skips dot-dirs, `node_modules`, `build`, `dist`, `target`, `venv`; cap 20k files; no
   symlinks). Needed because adapt's `_STACK_BY_MARKER` maps no Java/Kotlin marker.
   `ck adapt` behaviour is untouched. Vocabulary matches fleet-sync: python, typescript,
   java, kotlin, rust, go.
3. **Stack tags.** Kit skills carry none today. A small table `KIT_STACK_TAGS` tags the
   four per-language review checklists; everything else is stack-neutral. Project skills
   declare `stack_tags: [..]` in frontmatter, which wins. **An undetected stack never
   makes a skill irrelevant** (so `profile init` cannot disable capability on a guess).
4. **Budget defaults 300 lines / 2000 tokens, not 150.** Measured on this worktree's 81
   skills: `>150 lines` flags 73 (noise); 300/2000 flags 22. CLI-overridable.
5. **Broken** = unreadable SKILL.md, no frontmatter block, no `name`, no `description`,
   or a relative markdown link to a missing file. Links in code fences / inline code are
   excluded -- measured: without the exclusion the kit corpus shows 3 false positives,
   with it 0 (pinned by `test_the_kit_corpus_audits_with_zero_broken_skills`). Title-case
   `name:` values (context-keeper, hookify, prp-plan, santa-method) are NOT broken.
6. **Ownership for cards** comes from the manifest; no manifest -> `card` refuses (exit 1)
   rather than publish kit skills as the project's. Cards carry only `card_version,
   name, stack_tags, description, tokens`. Withheld reasons never quote content.
7. **Match** re-validates every foreign card (name regex, tags regex, int tokens,
   description length/printable/sanitizer); invalid cards are skipped with a reason,
   never repaired. Score = |overlap| / |card tags|; untagged or non-overlapping cards
   and already-installed names are not suggested. Nothing is written.
8. **Doctor check only when the profile exists** -- an install without one keeps the
   exact check count and readiness score (no `test_doctor_score` drift). Malformed file
   or an overlay path that is absolute / escapes the project = FAIL; a disabled/overlay
   skill that is not installed or an overlay file that is missing = WARN (names the
   `renamed` alias when the registry has one), so a kit update removing a skill does not
   redden every downstream doctor.

## Implementation Steps

### Step 1: Skill-fit module
- **File:** `src/claudekit/skill_fit.py` -- **Create** (op 1)
- `detect_stacks`, `manifest_files`, `parse_stack_tags`, `missing_references`,
  `inspect_skill`, `audit`, `save_audit` (-> `.claude/reports/skills/audit.json`),
  `load_profile`, `profile_findings`, `init_profile` (open mode `"x"`: never overwrites),
  `cards`, `load_cards`, `match`, `SkillFitError`. Stdlib only, py3.9-typed.

### Step 2: CLI wiring
- **File:** `src/claudekit/cli/main.py` -- **Modify** (op 2, five anchored edits)
  1. `cmd_skill`: dispatch non-`new` actions to `_cmd_skill_fit`; refuse `new` without a
     name or `--description` (exit 1).
  2. Add `_cmd_skill_fit(args)` and `_print_skill_audit(report)` immediately before `def cmd_mcp(args):`.
  3. `skill` parser: `action` choices `new, audit, profile, card, match`; `name` optional;
     `--description` no longer argparse-required.
  4. New flags after `--allowed-tools`: `--json`, `--save`, `--max-lines`, `--max-tokens`, `--registry`.
  5. `cmd_doctor`: skills-profile check inserted before `    # Summary`.

### Step 3: Preservation by name
- **File:** `.claude/operations/scripts/preserve_assets.py` -- **Modify** (op 3)
- `ALWAYS_CUSTOM_FILES = frozenset({"skills-profile.json"})`; `_is_custom` returns True
  for it regardless of manifest. No `install.sh` change is needed (install copies named
  kit dirs + `settings.json` only; the manifest is written from staging before
  preservation), and `SKIP_NAMES` must NOT gain the name (that would stop preservation).

### Step 4: Behavioural tests
- **File:** `tests/test_skill_fit.py` -- **Create** (op 4). tmp_path project trees, real CLI
  (`python -m claudekit.cli.main`, `ECC_HOOK_PROFILE=minimal` forced): buckets, fenced-link
  exclusion, token formula, budget override, write-nothing (whole-tree hash), `--save`
  writes only the report, Java threshold 19 vs 20 files, undetected stack, real kit corpus
  has zero broken, `profile init` + never-overwrite, unknown sub-action, doctor
  absent/pass/warn-with-rename/escape-fail/malformed-fail, card local-only + exact keys +
  no body/path, secret description withheld unquoted, no-manifest refusal, match
  overlap/skip/sanitizer/installs-nothing, `--registry` required, `skill new` guard.
- **File:** `tests/test_skills_profile_preserved.py` -- **Create** (op 5). Real `install.sh`
  twice (byte-identical profile), manifest-claims-it transition case (mutation-checked),
  kit ships no profile, real `fleet-sync.py` `main()` against a temp fleet via
  monkeypatched `ROOT` / `KIT_SKILLS` / `STACKS` (asserts the sync actually copied a skill, so
  it cannot pass vacuously).

### Step 5: User docs + CHANGELOG
- **File:** `docs/cli.md` -- **Modify** (op 6): new section before the `mcp add` section; doctor
  "Checks:" line mentions the profile. States the honest limit (nothing enforces `disabled`).
- **File:** `CHANGELOG.md` -- **Modify** (op 7): `[Unreleased]` entry.
- No hand-edited counts: no skill/agent/command/hook is added, so `gen-docs.py` output is unchanged.

## Pre-handoff evidence (executed, not asserted)

The ops config was executed with the real engine on a scratch rsync copy of this worktree
(`execute-json-ops.py ... --no-approval` in the COPY only -- nothing executed in the worktree):
- `validate-config-json.py .claude/plans/ops-skill-fit.json` -> APPROVED (worktree and copy)
- executor: 7/7 operations successful
- `pytest tests/test_skill_fit.py tests/test_skills_profile_preserved.py tests/test_skill_new.py tests/test_preserve_assets.py` -> 56 passed
- `ruff check src/ tests/ scripts/ .claude/operations/scripts/` -> clean; `mypy` -> no issues (39 files)
- `gen-docs.py --check`, `gen-registry.py --check`, `check-context-floor.py --check`, `gen-model-policy.py --check` -> OK
- mutation: removing the `ALWAYS_CUSTOM_FILES` check makes `test_it_survives_even_when_the_manifest_claims_it` fail
- all 13 live secret-scanner patterns: no hit in any new/edited file
- full suite, differential (both copies are non-git, so git-index/hook tests fail
  environmentally in both): pristine copy 36 failed / 11126 passed; changed copy 37 failed /
  11151 passed (+25 new tests). The ONE extra failure is
  `test_delivery_contract_smoke.py::test_queued_ops_configs_validate_against_head`, which is
  expected for an already-EXECUTED config still sitting in `.claude/plans/` (queued-ops gate).
  In the real worktree, pre-execution, that test passes (2 passed).

## Testing Strategy (implementer, in the worktree)

```bash
python3 .claude/operations/scripts/validate-config-json.py .claude/plans/ops-skill-fit.json
python3 .claude/operations/scripts/execute-json-ops.py .claude/plans/ops-skill-fit.json
python3 -m pytest tests/test_skill_fit.py tests/test_skills_profile_preserved.py -q
python3 -m pytest tests/ -q
ruff check src/ tests/ scripts/ .claude/operations/scripts/ && mypy
python3 scripts/gen-docs.py --check && python3 scripts/gen-registry.py --check
python3 scripts/gen-model-policy.py --check && python3 scripts/check-context-floor.py --check
python3 scripts/check-plan-artifacts.py --check .claude/plans/ops-skill-fit.json
shellcheck install.sh .claude/hooks/*.sh    # unchanged files; sanity only
```
After execution, archive the executed config (`.claude/plans/archive/` with its README row)
or `test_queued_ops_configs_validate_against_head` goes red. Then commit, THEN re-run the
self-scan test (tracked-file trap: new files are scanned only once tracked).

## Rollback Plan

- Engine backup: `execute-json-ops.py` writes `backups/skill-fit-<ts>/`; `rollback` restores
  the three edited files and removes the three created ones.
- Git: the change is one conventional commit on `feat/skill-profiles`; `git revert <sha>`.
- Data: nothing in any project is written except on explicit `--save` / `profile init`;
  deleting `.claude/skills-profile.json` / `.claude/reports/skills/` fully reverts a project.

## Risk Assessment

- **Low:** new module is additive; verbs are read-only; doctor check invisible without a profile.
- **Medium:**
  - `ck skill new` without `--description` now exits 1 (was argparse exit 2). No existing
    test depends on exit 2 (grepped); scripts relying on 2 would see 1.
  - `cli/main.py` is the CLI hub (every verb) -- anchored additive edits, full suite required.
  - Stack detection walks the project tree (bounded to 20k files, no symlinks, dot-dirs
    skipped); a huge monorepo pays a one-off walk per audit.
  - `memory.rejections()` is a shape heuristic (hard rule 6): cards are "sanitized", not
    proven secret-free. Docs say withheld-on-shape, never "guaranteed".
- **High:** none identified. Touches `preserve_assets.py` (installer data path) but only
  widens what is preserved; it can never cause a file to be dropped.

## Phase 2 / Deferred (explicitly NOT in this plan)

- **Role-resolver hook** that reads `roles` / `disabled` / `overlays` and shapes what each
  agent loads (the only thing that actually cuts per-session tokens). Needs its own plan,
  Tier 3 (hook + prompt-injection surface), fail-closed design and review.
- `packs` semantics (named skill bundles) and a shipped pack catalogue.
- `stack_tags` in kit skill frontmatter (would replace `KIT_STACK_TAGS`; touches 81
  skills and the registry generator).
- Fleet card registry location/distribution and an owner-gated `install` path for
  suggestions; wiring `fleet-sync.py` STACKS to `detect_stacks` instead of a hand table.

## Open questions for the owner (not blocking this MVP)

1. Budget defaults: 300 lines / 2000 tokens chosen from measurement vs the suggested 150;
   confirm.
2. Should `ck skill audit` exit non-zero when a skill is broken (CI use), or stay report-only (as planned)?
3. Where should fleet cards live (a directory in this repo vs per-project `.claude/reports/`)?
