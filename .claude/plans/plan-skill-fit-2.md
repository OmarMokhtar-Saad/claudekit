# Implementation Plan: Skill Fit 2 -- derived stack tags, user-level registry, enforced `disabled`

**Slug:** `skill-fit-2` · **Branch:** `feat/skill-profiles` · **Owner-approved goal:** yes (all follow-ups from plan-skill-fit.md "Phase 2 / Deferred")

| Part | Ops config | Tier | Ops | Edits | State |
|------|-----------|------|-----|-------|-------|
| A | `.claude/plans/archive/ops-skill-fit-2-a/ops-skill-fit-2-a.json` | 2 | 5 | 15 | **executed + committed (8ce9ec3)** |
| B | `.claude/plans/ops-skill-fit-2-b.json` | 3 (writes user settings from a repository-controlled profile) | 5 | 18 | **revised 2026-09-13 (skillOverrides); pending review** |

Committed A (8ce9ec3) is byte-identical (`cmp`) to the scratch post-A tree that B's
anchors were generated from; `validate-config-json.py` on B in the live worktree:
APPROVED; `check-plan-artifacts.py --check`: OK.

**File names:** `ops-skill-fit-2-a/-b`, not `2a/2b`, because `check-plan-artifacts.py`
binds a config to its plan by a hyphen-boundary prefix walk of the filename;
`ops-skill-fit-2b` resolved to `plan-skill-fit.md` and the gate went red.

## Overview

The fleet run showed `ck skill match` returning `<none>` for AppiumLens vs 13 projects:
project-owned skills carry no `stack_tags`. Part A (done) derives tags, adds a
user-level card registry and Jaccard matching. Part B makes the profile's `disabled`
list drop always-on tokens with `ck skill apply`, which merges Claude Code's
`skillOverrides` setting into the gitignored `.claude/settings.local.json`. No skill
file is edited, no hook, no prompt injection.

## Scope

- **In scope (B):** `src/claudekit/skill_fit.py`, `src/claudekit/cli/main.py` (`skill
  apply`, `cmd_init`/`cmd_update` re-apply, doctor), new `tests/test_skill_apply.py`,
  `docs/cli.md`, `CHANGELOG.md`.
- **Out of scope:** `fleet-sync.py`; `install.sh` changes; `.gitignore` entry for
  `.claude/skills-applied.json`; `packs`/`roles`/`overlays` semantics; kit frontmatter
  `stack_tags`; installing suggestions.

## Phase 0: Design precheck

**Ownership model (B, revised).** Skill files stay kit- or project-owned exactly as the
install receipt says, and B edits none of them. B's value lives in two project-local,
per-machine files: `.claude/settings.local.json` (Claude Code's local settings, which
this repo already treats as the user's: never in the manifest -- install.sh:669
`NEVER_MANAGED`; ignored by `ck diff` -- main.py:977 `DIFF_IGNORED`; carried across a
reinstall -- install.sh:577-583; skipped by `preserve_assets.py`/`fleet-enhance.py`;
gitignored -- .gitignore:49) and `.claude/skills-applied.json`, apply's own record
of the `skillOverrides` names it manages. Inside `settings.local.json`, apply owns ONLY
the `skillOverrides` entries its record names AND whose value still equals what it
wrote; every other key and every other entry belongs to the user. The record is a
separate file rather than a marker key because JSON has no comments and an unknown
top-level key risks Claude Code's settings validation -- a risk that, in this repo,
could drop the `ECC_HOOK_PROFILE` env entry its own session setup depends on. No value
sits outside this model, so there is no `ck diff` / `_classify_manifest` change.

**Rejection-brief search** (`review-record.py rejections search "skill profile disabled
frontmatter registry"`, exit 0, 10 matches). Validated: `fleet-skill-phaseA` ("asserts
registry rows no operation produces") -- B changes no skill, agent or registry file, and
gen-docs/gen-registry `--check` pass on the post-state. `agent-memory-learning` (helper
classification, fixture misuse) -- no hook or helper added; tests use only `tmp_path`.
Others matched on keywords only.

## Discovery notes (evidence)

- Coordinator-supplied (code.claude.com/docs/en/skills.md): settings support
  `"skillOverrides": {"<skill>": "on"|"name-only"|"user-invocable-only"|"off"}`, and
  `disable-model-invocation: true` prevents preloading into subagents. **Not
  independently fetched by the planner** (see Uncertainties 1).
- This repo's `.claude/settings.local.json` holds `env.ECC_HOOK_PROFILE` and
  `permissions.allow`; `tests/test_doctor_gate.py:35` pins the hook profile so results
  never depend on it. No test asserts on settings.local.json contents beyond
  preservation (`test_preserve_assets.py:192`), and no source module writes it today.
- `tests/test_skill_loading_contract.py`: a model-invisible skill an agent names as a
  mandatory load is dead prose -- so agent-mandatory loads stay protected alongside
  `skills:` preloads. No shipped agent uses `skills:` frontmatter today.
- Registry ids with `mandatory: true` today: `using-superpowers`, `golden-rule`.

## Part A -- executed (8ce9ec3)

Derived tags (frontmatter > kit table > local keyword scan UNION detected stacks; kit
skills never derived), `ck skill card --publish` to `~/.claudekit/registry/cards/` or an
absolute `$CLAUDEKIT_REGISTRY`, `match` defaulting to it, skipping its own card, Jaccard
score with `--min-score` (0.1). Tests incl. the fleet-miss regression. See the archived
config and its README for details.

## Part B -- Steps (ops-skill-fit-2-b.json)

### Mechanism choice
1. **Chosen: `skillOverrides` in `.claude/settings.local.json`.** Claude Code's own
   visibility control; no kit file changes, so the receipt, `ck diff`, `update`,
   `uninstall` and `adapt` are untouched; project-local and gitignored, so one
   developer's choice does not leak into the repository; installer already preserves it.
2. Flip `disable-model-invocation` in installed SKILL.md (previous revision): edits kit
   files, needs a content-proof drift exception in `_classify_manifest`, and blocks
   subagent preloading. Dropped.
3. A hook: no hook can remove descriptions from the listing; adds an always-on
   fail-closed surface. Rejected; hard rule 2 therefore does not apply.
4. `settings.json` (committed): would impose one project's choice on every clone and
   is kit-shipped/receipted. Rejected.

### B1: `apply` core
- **File:** `src/claudekit/skill_fit.py` · **Action:** Modify
- Profile schema: new optional key `disabled_mode` in `PROFILE_KEYS`, one of
  `off` (default) / `user-invocable-only`; anything else is a load error.
- `PROTECTED_SKILLS` = golden-rule, prompt-injection-defense, security-checklist,
  using-superpowers, verification-before-completion. `protected_skills(root)` adds
  registry `mandatory: true` ids, every skill in an installed agent's `skills:`
  frontmatter (inline `[a, b]` or block `- a` list; `agent_preloaded_skills`), and every
  skill under an agent's **Mandatory** Skill Loading header. The static five never
  depend on a repository file.
- `apply(root, restore=False)`, fail closed BEFORE any write on: no `.claude/`; missing
  (unless restoring) or malformed profile; a `disabled` entry that is not a skill id; any
  protected name (whole profile refused, reasons listed); `settings.local.json` or the
  record unparseable, not an object, `skillOverrides` not an object, or a symlink.
- Converge: for each recorded name no longer wanted, delete the override only if its
  value still equals the recorded one (else report `kept_user_set`). For each wanted
  installed skill: an existing override not written by apply is left alone
  (`kept_user_set`); otherwise set to the mode and record it. Not-installed names are
  reported, not written. An emptied `skillOverrides` block is dropped.
- Writes (all `adapt.write_atomic`): record first as the UNION of old+new names (a crash
  between writes can then only leave a record naming an absent override, which the next
  run drops -- never an override apply wrote but forgot); `settings.local.json` only if
  its parsed content changed; then the final record, or the record deleted when empty.
- `enforcement_status(root)`: effective overrides (settings.json then
  settings.local.json, local wins); `protected_hidden` = protected with any value other
  than `on`; `hidden` + `tokens_saved` (description tokens, chars/4, 0 for already
  model-invisible skills) for `off`/`user-invocable-only`; `diverged` = disabled but not
  at the mode, or recorded-and-still-hidden but no longer disabled.
- `profile_findings`: a protected name in `disabled` is an **error**.

### B2: CLI, reinstall, doctor
- **File:** `src/claudekit/cli/main.py` · **Action:** Modify
- `skill apply [--restore] [--json]`; `profile init` now points at `apply`.
- `_reapply_skill_profile(target)` after a successful install in `cmd_init` and
  `cmd_update`; a refusal warns and never fails the install.
- Doctor "Skill visibility" (runs when a profile OR any `skillOverrides` exists): FAIL
  when any settings file hides a protected skill (profile or not); WARN on divergence;
  PASS "N skill(s) hidden via skillOverrides, ~T always-on tokens saved". Projects with
  neither get no new check, so their readiness score is unchanged.

### B3: Tests, docs, CHANGELOG
- **File:** `tests/test_skill_apply.py` · **Action:** Create (28 test cases):
  merge preserves `env.ECC_HOOK_PROFILE` + `permissions` + a user override and edits no
  skill file; `user-invocable-only` mode; invalid mode refused; restore removes exactly
  apply's entries (settings equal the original object); user-set override never taken
  over or removed; value changed by the user after apply survives restore; convergence
  and a no-op re-run (settings mtime unchanged); file created when absent and empty
  block dropped; not-installed reported; unparseable settings x3 never overwritten;
  symlinked settings not written through; `ck diff` silent with a real receipt; hostile
  profile x5 (static, registry-mandatory, agent-mandatory, inline `skills:`, block
  `skills:`) refused whole with tree unchanged and doctor failing; on-demand not
  protected; path-shaped name refused; doctor fails when settings.json or
  settings.local.json already hides a protected skill (no profile); forged record cannot
  remove a non-matching user value; doctor divergence both directions and tokens saved;
  no profile + no overrides = no check; **real install.sh + `ck update`**: overrides,
  record and `ECC_HOOK_PROFILE` survive, update re-applies, restore returns to the
  original settings.
- **File:** `docs/cli.md` · **Action:** Modify (new `skill apply` section; removes
  "nothing enforces disabled"; documents `disabled_mode`).
- **File:** `CHANGELOG.md` · **Action:** Modify (new entry; MVP entry now points at apply).

## Threat notes (Part B)

| Threat | Control | Test |
|---|---|---|
| PR edits the profile to hide safety skills | static five + registry mandatory + agent `skills:` preloads + agent mandatory loads; whole profile refused before any write; doctor error | `test_a_protected_skill_refuses_the_whole_profile` x5 |
| Committed `settings.json` (or a local edit) hides a protected skill directly | doctor FAIL regardless of profile | `test_doctor_fails_when_settings_already_hide_a_protected_skill` x2 |
| apply clobbers user settings / hook profile | parse-merge, only managed entries, unparseable = refuse, write only on change | `test_merges_off_and_preserves_every_other_key`, `test_an_unparseable_settings_file_is_never_overwritten`, real-install test |
| Forged `skills-applied.json` removes user overrides | removal only when current value equals recorded value; record values limited to the two hiding modes | `test_a_forged_record_cannot_remove_a_user_value_it_does_not_match` |
| Write through a symlinked settings/record file | symlink refusal | `test_a_symlinked_settings_file_is_not_written_through` |
| Path-shaped names | `NAME_RE`, whole profile refused | `test_a_path_shaped_name_is_refused_before_any_write` |
| Registry poisoning (A) | user-level dir; cards re-validated + sanitized on read | Part A tests |

Residual (hard rule 6): the dynamic protected set comes from agent/registry files, so a
PR editing those too can shrink it (the static five remain). A forged record whose
values match the user's own `off` entries could make `--restore` remove them -- the
worst case is a skill becoming visible again, never hidden. `off` is a visibility
setting; the skill stays on disk.

## Testing Strategy (measured on scratch copies, 2026-09-13)

- B built on the scratch post-A tree; ops generated from that diff and replayed through
  the real executor on a copy of post-A (`validate` APPROVED, execute success); all six
  touched files byte-identical (`cmp`) to the verified scratch tree.
- `pytest tests/test_skill_apply.py tests/test_skill_fit.py`: 63 passed. ruff, mypy,
  gen-docs, gen-registry, gen-model-policy, check-context-floor: all OK.
- Mutation proofs, each reverted after: drop the protected refusal (5 failed); remove
  overrides regardless of recorded value (2); take over user-set overrides (1); ignore
  agent `skills:` preloads (2); follow symlinks (1); doctor ignores protected-hidden (2);
  write settings without preserving other keys (6); drop re-apply in `cmd_update` (1) --
  **8/8 killed**.
- Full suite: see "Full-suite result" below.
- Post-execution in the worktree: the whole CLAUDE.md DoD list, incl.
  `check-plan-artifacts.py --check` and `ck doctor --strict`.

### Full-suite result

PENDING_SUITE_RESULT

## Rollback Plan

- Executor backup `backups/skill-fit-2-b-*` or `git checkout -- <files>` before commit;
  `tests/test_skill_apply.py` is new (delete). A is independent and stays.
- User side: `ck skill apply --restore` removes exactly the managed overrides and the
  record; settings.local.json otherwise untouched.

## Risk Assessment

- **Low:** docs/CHANGELOG; no kit file is written, no manifest/diff logic changes.
- **Medium:** `main.py` is a hub (every `ck` verb): the doctor check is new code on
  every doctor run (it no-ops without profile/overrides); `cmd_init`/`cmd_update` gain a
  post-install call that cannot change their exit code. Settings JSON is rewritten with
  2-space indentation when it changes (values preserved, formatting not).
- **High:** writing a user settings file from repository-controlled input -- mitigated
  per Threat notes; Tier 3, reviewer before execution.
- `project-graph.json` hub query not run (planner Bash scoped); treat `main.py` as a
  GOD-NODE.

## Uncertainties / open decisions for the owner

1. `skillOverrides` semantics — VERIFIED 2026-09-13 via context7 against
   code.claude.com/docs/en/settings-reference and /docs/en/skills: scope is "Any file",
   and the `/skills` menu itself writes `.claude/settings.local.json`; `user-invocable-only`
   = "Claude doesn't see the skill, but you can still type /name"; `off` = hidden from
   Claude and autocomplete; absent = `on`; plugin skills are not affected. Unknown
   top-level keys remain untested, which is why the record stays a separate file.
2. Record location `.claude/skills-applied.json` is not gitignored by install.sh. If
   committed, another clone gets a record with no matching overrides -- harmless
   (nothing is removed), but noise. A `.gitignore` entry is out of scope.
3. `name-only` in a settings file counts as "hiding" a protected skill (doctor FAIL):
   deliberately strict.
4. Refusing the WHOLE profile for one protected name (fail closed) vs skipping it.
5. A kit update that adds an agent preloading a disabled skill makes `update`'s re-apply
   refuse (warned) and doctor fail until the profile is edited; the existing override
   stays in place meanwhile.
6. Part A uncertainties unchanged: union tagging noise; project id = directory name
   (collisions; `--project`); Jaccard floor 0.1.
