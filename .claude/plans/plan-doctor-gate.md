# Implementation Plan: Make `ck doctor --strict` a Gate That Means Something

*Revision 4 — r3 review APPROVED at 92.5/100 with one MAJOR (fact 11 was false for
`jsonschema`); this revision lands it. r3 markers kept, r4 changes marked **[r4]**.*

## Overview

Three defects keep the repo's own DoD command red and let a push gate lie. This plan (1)
populates `.claude/hooks/config.json` with real, non-mutating project commands, (2) gives
`ck doctor` the missing `skip` result state and uses it — gated on the install manifest's own
*file record*, not on its word — so a `--minimal` install passes `--strict` while a full or
half-delivered install still fails, and (3) removes the placeholder command defaults so an
unconfigured command stays empty and the hooks' honest skip path runs instead of reporting
`Tests: PASSED` having tested nothing.

## Scope

- **In Scope:** `.claude/hooks/config.json`, `src/claudekit/cli/main.py` (`skip()` helper +
  `cmd_doctor`), `install.sh` (command defaults, the config-rewrite failure path, the closing
  output), `templates/generic/config.env`, a new `tests/test_doctor_gate.py`, `CHANGELOG.md`,
  and a factual correction to `.claude/plans/plan-gate-scope.md`.
- **Out of Scope:** `EXPECTED_SKILLS`/`EXPECTED_AGENTS`; the `.codex/hooks/*` mirrors;
  `ck update`/`ck diff`; the empty `.claude/skills/` and `.claude/hooks/` directories a
  `--minimal` install creates; **[r3]** the nine non-generic `templates/*/config.env` files
  (see Follow-ups — pre-existing, not worsened here).

## Prerequisites

None. No new dependencies. `jsonschema` and `shellcheck` stay optional — **[r3]** and the
tests no longer depend on either being present (Decision D9).

## Measured facts this plan depends on

| # | Fact | Evidence |
|---|---|---|
| 1 | `ck doctor --strict` exits 1 here solely because three `project.*_cmd` values are empty (`main.py:344-349` warns, `:369-370` fails `--strict` on any warning). | FINDING A. |
| 2 | `install.sh:482-501` overwrites the whole `project` section from language detection on `--full`, so committed values do not reach users **on the success path**. | FINDING A. |
| 3 | A legitimate `--minimal` install exits 1 under `--strict`: 13 passed, 6 warnings, 2 failed. | Re-measured. |
| 4 | The manifest records `mode` **and** a `files` map; a `--minimal` manifest records **no** `skills/`, `hooks/` or `settings.json` entries. **[r3]** | Re-measured on a real `--minimal` install. |
| 5 | `templates/generic/config.env:1-4` carries the same placeholders. | `cat`. |
| 6 | `pip install -e .` is rejected by CommandValidator (rc=2, `pip` not allowlisted); `python3 -m compileall -q src/claudekit` is accepted (rc=0). | `check-command` on each. |
| 7 | `pre-commit.sh:199-243` and `pre-push.sh:207` **execute** `build_cmd` (after screening) whenever a non-doc source file is staged. | Read. |
| 8 | `install.sh:501` ended `… && print_ok || print_warn`, so a rewrite failure left the shipped section in the user's tree. | Read. |
| 9 | **[r3]** `install.sh:113-117` defines `_cleanup_on_failure`; `:335-338` documents that "Bash does NOT run the ERR trap for the `exit` builtin" and calls it before its own `exit 1`, and `trap - ERR` is only reached at `:520`, after the atomic swap. | Read. |
| 10 | **[r3]** `CK_CONFIG_PATH` is exported for exactly the config-writing `python3` invocations and nothing else in `install.sh`; template rendering uses `CK_TPL_IN`, the manifest uses a heredoc. | `grep -n CK_CONFIG_PATH install.sh`. |
| 11 | **[r4 corrected]** CI's test job **does** install `jsonschema` (`ci.yml:30` runs `pip install --require-hashes -r tests/requirements.txt`; `tests/requirements.txt:131` pins `jsonschema==4.25.1`, declared at `tests/requirements.in:7`). It does **not** install `shellcheck` — that exists only in the separate job at `ci.yml:101-113`. The r3 version of this row claimed neither was installed and was wrong about `jsonschema`. | Executed: `sed -n '26,31p' .github/workflows/ci.yml`, `grep -n jsonschema tests/requirements.*`. |

## Decisions

- **D1 — `build_cmd` is `python3 -m compileall -q src/claudekit`.** Not `pip install -e .`
  (rejected by the screen, fact 6) and not `python3 -m pip install -e .` (accepted by the
  screen but **executed** on every source commit, fact 7: mutates site-packages, may hit the
  network, hard-fails under PEP 668 and blocks the commit). `compileall` is non-mutating apart
  from `__pycache__`, offline, deterministic, and catches what a pre-commit build gate is for.
- **D2 — the installer's config rewrite must not fail open, and must not litter. [r3
  revised]** Fact 8 meant a failed rewrite handed the user a config running *this repo's*
  gates in *their* project. The `||` branch now blanks all four values; if that write fails
  too, it aborts. **[r3]** The abort sits at `:501`, *before* the atomic swap and before
  `trap - ERR`, with `$STAGING` fully populated — and Bash does not run the ERR trap for
  `exit` (fact 9). It therefore mirrors `:335-338` exactly: `_cleanup_on_failure` (which
  removes only the staging dir and prints "Installation failed. Your existing .claude (if any)
  was left untouched.") and then `exit 1`. Without that, a failed install leaves a permanent
  `.claude.staging.<pid>` copy of the kit in the user's project root.
- **D3 — the blanking script reads the pristine SOURCE, never the destination. [r3]** The
  write that just failed opened the destination with `'w'`, which truncates before
  `json.dump`, so a mid-write failure (ENOSPC, signal) leaves invalid JSON. Re-reading it
  would raise, `2>/dev/null` would swallow the traceback, and a recoverable install would go
  straight to abort. It now loads `$CLAUDE_SRC/hooks/config.json` — a known-good document —
  blanks the four values, and writes that.
- **D4 — `check()` gets a fourth state.** `main.py:195-205` had pass/warn/fail only, so a
  mode-aware check had to fake a PASS, inflating `checks_passed` and printing the same "All
  checks passed!" as a full install. `"skip"` is printed `[-]`, counted as `Skipped:`,
  excluded from `Passed`, and — unlike `warn` — not a `--strict` failure. **[r3]** *Both*
  terminal verdicts are updated, so a run with warnings **and** skips no longer drops the
  skips from its wording while a skip-only run mentions them.
- **D5 — the manifest is never trusted alone, and completeness is read from the RECORD, not
  the tree. [r3 revised]** `mode == "minimal"` is an excuse only when the manifest's own
  `files` map lists no `skills/`, no `hooks/` and no `settings.json`. This cuts both ways and
  that is the point: flipping `mode` from full to minimal leaves `files` still listing every
  skill and hook the full install recorded, so a half-delivered full install stays red (the
  `CHANGELOG.md:52` bug class); while a user's **own** skill or hook dropped into a minimal
  install is not kit-managed, is not in `files`, and does not revoke the excuse.
  **This replaces r2's working-tree predicate, which was self-refuting**: it would have
  hard-failed the customised-minimal tree that `test_install.py::test_reinstall_preserves_custom_skill`
  creates ("Expected ≥76 skills, found 1"). Both directions now have a test.
- **D6 — the `--strict` regression for undetected-language projects is accepted and
  announced.** Owner-settled: empty is the honest state, and a project whose gates run nothing
  should be told so. The warning is **not** silenced. It is disclosed in the Risk section, the
  CHANGELOG bullet, and `install.sh`'s closing output. **[r3]** That NOTE is gated on
  `CK_CONFIG_REWRITE_FAILED` as well as on the shell variables, because the blanked-on-failure
  path leaves the variables populated while the on-disk config is empty — the user would
  otherwise get an empty config and no explanation.
- **D7 — `coverage_cmd` stays populated.** It needs `pytest-cov` (only in
  `tests/requirements.txt`), so a contributor without test deps sees `Coverage: FAILED` from a
  non-blocking hook. That is loud and true; blanking it would silently skip a gate CI enforces
  at 85% (`ci.yml:47-51`) — the exact class this plan removes. Documented in the CHANGELOG.
- **D8 — the empty `skills/` directory a minimal install creates is kept.** `install.sh:183`
  creates it unconditionally and a supported workflow uses it. **[r3]** With D5 keyed on the
  manifest record, directory contents no longer affect the verdict at all, so the r2
  justification ("doctor keys on contents") is gone along with the flaw it papered over.
- **D9 — the tests shim `shellcheck`, and nothing else. [r4 revised]**
  Corrected fact 11: CI's test job installs `jsonschema` but not `shellcheck`, so only the
  `shellcheck` half of r3's reasoning survives. A session fixture prepends a shim
  (`#!/bin/sh\nexit 0`) to `PATH`; doctor only calls `shutil.which("shellcheck")`
  (`main.py:222`), so the shim satisfies the check honestly — the check asks "is the tool
  available", not "does it pass". Without it the headline `--strict` assertion would skip on
  the one machine that gates a merge.
  **The r3 `jsonschema` stub is deleted, and it was worse than useless.** It was inert on CI
  (where the real library is installed) and live only on a machine lacking `jsonschema` —
  which is precisely where `tests/test_gate_scope.py:191,198,208` `importorskip` and skip
  their schema assertions. So on exactly the machines where it ran, it could have let
  `test_doctor_strict_exits_zero_on_this_repo` report PASS while `.claude/hooks/config.json`
  violated `config.schema.json`, with nothing counter-asserting: a vacuous green manufactured
  by a fix whose premise did not survive a `grep`. Where `jsonschema` is genuinely absent,
  doctor warns for a true reason and `--strict` is right to fail. `ci.yml` is left alone.
- **D10 — docs vs shell placeholder split** (reviewer-confirmed, unchanged): `*_CMD_DOC`
  variables feed only the two `render_template` call sites; the config writer keeps the raw,
  possibly empty, value.

## Implementation Steps

### Step 1: Populate this repo's project commands
- **File:** `.claude/hooks/config.json` — **Modify.** `build_cmd` per D1; `test_cmd`
  `python3 -m pytest tests/ -q`; `lint_cmd` `ruff check src/ tests/ scripts/`; `coverage_cmd`
  mirroring `ci.yml:47-51` (D7). All four screen clean; all stay plain strings so
  `config.schema.json` still validates.

### Step 2: The `skip` state, and manifest-record-gated mode awareness
- **File:** `src/claudekit/cli/main.py` — **Modify (9 edits).**
- 2a: `skip()` beside `ok/warn/err`; `checks_skipped` + the `"skip"` branch in `check()`;
  `Skipped:` in the summary; **both** terminal verdict lines updated (D4).
- 2b: `minimal_install = manifest["mode"] == "minimal" and no recorded skills/hooks/settings`
  (D5).
- 2c: the four by-design absences report `"skip"` under `minimal_install` and are otherwise
  byte-for-byte unchanged. The skills branch also requires `len(skill_dirs) < EXPECTED_SKILLS`,
  so a minimal tree that somehow has a full skill set is still reported normally.

### Step 3: Placeholders out, leak-proof + litter-free failure path, disclosure in
- **File:** `install.sh` — **Modify (5 edits).**
- 3a: defaults become `${VAR:-}`; four `*_CMD_DOC` carry the readable placeholder.
- 3b/3c: the two `render_template` call sites use `*_CMD_DOC`.
- 3d: the `||` branch blanks from the pristine source (D3); on failure `print_err` →
  `_cleanup_on_failure` → `exit 1` (D2).
- 3e: closing NOTE, gated on the rewrite-failed flag too (D6).

### Step 4: Fix the generic template
- **File:** `templates/generic/config.env` — **Modify.** The four values become `""`; the
  comment is worded so it cannot trip Step 5's assertion, and that assertion *parses the four
  values* rather than scanning for a substring.

### Step 5: Behavioral tests
- **File:** `tests/test_doctor_gate.py` — **Create — 18 test cases, three classes, no skips.**
- **[r4]** `test_command_survives_the_hook_command_screen` and
  `test_build_cmd_does_not_mutate_the_environment` each assert the command is **non-empty**
  before screening it. CommandValidator accepts `""` (nothing to screen) and
  `"pip install" not in ""` is trivially true, so against the pre-fix tree both guards
  passed vacuously — they bound only in conjunction with `test_no_project_command_is_empty`.
  The dependency is now enforced in each test and stated in its docstring.
- Failure-path coverage **[r3]**: fact 10 makes a surgical injection possible — a `python3`
  PATH shim that fails only when `CK_CONFIG_PATH` is in its environment and otherwise `exec`s
  the real interpreter, with a counter file so the two config writes can be failed
  independently. Fail #1 only → assert install rc 0 and all four values `""`; fail both →
  assert rc 1, the `print_err` text, the "left untouched" reassurance, and that **no**
  `.claude.staging.*` survives. This deletes r2's "known untested branch" disclosure, which
  was wrong: breaking `python3` selectively does *not* break the rest of the installer.

### Step 6: Correct the superseded rationale
- **File:** `.claude/plans/plan-gate-scope.md` — **Modify.** Replace the false "copies
  verbatim" paragraph with the measured correction; keep the original struck through.

### Step 7: Changelog
- **File:** `CHANGELOG.md` — **Modify.** Two bullets at the top of `[Unreleased] → ### Fixed`.

## Mutant reasoning (which branch to disable, and exactly what must flip)

| Disable this | Tests that MUST fail |
|---|---|
| `check()`'s `"skip"` branch (fall through to `warn`) | `test_minimal_install_is_green_under_strict`, `test_by_design_absences_are_skipped_not_counted_as_passes` |
| The `Skipped:` summary line | `test_by_design_absences_are_skipped_not_counted_as_passes` |
| The `and not _kit_optional` conjunct (trust `mode` alone) | all three `test_a_manifest_recording_kit_assets_cannot_claim_minimal[...]` |
| Re-key `_kit_optional` on the working tree instead of the manifest record | `test_a_customised_minimal_install_stays_green` |
| The `mode == "minimal"` conjunct (excuse everything) | `test_a_full_install_missing_skills_still_fails`, `test_an_install_without_a_manifest_still_fails` |
| The `"skip"` on the skills-count check only | `test_minimal_install_has_no_failed_check`, `test_minimal_install_is_green_under_strict` |
| Step 1's config values (revert to `""`) | `test_no_project_command_is_empty`, `test_doctor_emits_no_unconfigured_command_warning`, `test_doctor_strict_exits_zero_on_this_repo` |
| `build_cmd` → `python3 -m pip install -e .` | `test_build_cmd_does_not_mutate_the_environment` (the screen test still passes — that is why both exist) |
| 3a (restore placeholder defaults) | `test_installed_config_leaves_the_command_empty[*]`, `test_pre_push_skips_honestly_instead_of_reporting_a_pass`, `test_install_discloses_that_the_gates_run_nothing` |
| `templates/generic/config.env` values only | `test_generic_template_configures_no_command`, `test_installed_config_leaves_the_command_empty[*]`, `test_pre_push_skips_honestly_instead_of_reporting_a_pass` |
| 3e (the closing NOTE) | `test_install_discloses_that_the_gates_run_nothing` |
| The `*_CMD_DOC` substitution | `test_rendered_docs_get_a_readable_placeholder_not_a_shell_command` |
| 3d's happy path (per-project rewrite) | `test_install_never_leaves_claudekits_own_commands_behind` |
| 3d's blanking branch (restore `\|\| print_warn`) | `test_a_failed_rewrite_blanks_the_commands_rather_than_leaking` |
| 3d's `_cleanup_on_failure` call only | `test_a_config_that_cannot_be_written_aborts_without_littering` (the staging-dir assertion; rc and text still pass) |
| 3d's `exit 1` (warn and continue) | `test_a_config_that_cannot_be_written_aborts_without_littering` (rc assertion) |
| `strict_env`'s `shellcheck` shim (revert to a skip guard) | nothing fails — but both `--strict` tests report SKIPPED on any machine without `shellcheck`, including CI, which is the failure mode D9 exists to prevent. Read skip counts, not just failures: this module must show **0 skipped** in CI. |
| **[r4]** Op 1's config values, with the two non-empty assertions removed | `test_command_survives_the_hook_command_screen[*]` and `test_build_cmd_does_not_mutate_the_environment` would both still PASS — that is the vacuity MINOR-1 caught, and why the assertions are there |

## Testing Strategy

```bash
python3 -m pytest tests/test_doctor_gate.py -v     # new, 18 test cases, expect 0 skipped
python3 -m pytest tests/ -q                        # full suite, zero failures
ruff check src/ tests/ scripts/ ; mypy
shellcheck install.sh .claude/hooks/*.sh
python3 scripts/gen-docs.py --check ; python3 scripts/gen-registry.py --check
ck doctor --strict                                 # exit 0
```

Pre-verified during planning (patch simulated in memory, nothing written): patched `main.py`,
the new test file and the embedded `jsonschema` stub all parse; `ruff` clean with 0 new long
lines; patched `install.sh` passes `bash -n` and `shellcheck` (rc=0 with the repo's
`.shellcheckrc`); ops config APPROVED with every `find` pattern unique.

Blast radius to re-run explicitly: `tests/test_gate_scope.py` (asserts on `[✓]`/`[✗]` marks —
the new `[-]` must not collide), `tests/test_install.py`, `tests/test_cli.py::test_doctor_runs`,
`tests/test_structure.py`.

## Rollback Plan

One commit, seven files, no data migration; `git revert` restores everything. Per-file:
restore the four empty strings in `config.json`; drop `skip()`, `checks_skipped`,
`minimal_install` and the four `"skip"` branches in `main.py`; restore the placeholder
defaults, the non-`_DOC` `CK_VAR_*`, the one-line `|| print_warn`, and drop the closing NOTE
in `install.sh`; restore `templates/generic/config.env`; delete `tests/test_doctor_gate.py`.
Installed trees are unaffected until a user re-runs `install.sh`.

## Risk Assessment

- **Low:** `config.json` values; `templates/generic`; CHANGELOG; the plan-gate-scope
  correction; the new test file.
- **Medium:** `main.py` `cmd_doctor` — a new result state plus five branches in the repo's own
  health gate. Six negative controls (full-mode manifest, no manifest, three recorded-asset
  manifests, customised-minimal) prove it can still go red and does not over-fire.
- **Medium — accepted regression (D6):** undetected-language projects go from `--strict`
  exit 0 to exit 1 until commands are configured, and their gates now skip visibly instead of
  printing a false PASS. Disclosed in the CHANGELOG and the installer's own output.
- **Medium — this repo's own pushes get slower:** `pre-push` now runs the full suite, and a
  genuinely failing suite blocks a push. That is the intent.
- **Medium — `install.sh`:** highest blast radius touched, and 3d can now *abort* an install
  that previously only warned. It requires two consecutive config-write failures, cleans up
  after itself (D2), and is covered by two behavioral tests.
- **Low — the `shellcheck` shim (D9)** makes doctor's "shellcheck available" check pass on a
  machine without the tool. That check is a availability probe, not a lint run, and the real
  shell lint is a separate DoD command plus its own CI job (`ci.yml:101-113`), so nothing is
  masked. **[r4]** No other tooling is faked; the `jsonschema` stub that r3 proposed is gone
  (D9), so there is no machine on which these tests can go green past a schema violation.
- **High:** none. No security surface, no schema change, no protected file, no deletions.

## Follow-ups (out of scope here — pre-existing, not worsened by this plan)

1. **`templates/python/config.env:1` ships `BUILD_CMD="pip install -e ."`, and `pip` is not in
   `DEFAULT_ALLOWLIST`.** `pre-commit.sh:225-230` therefore refuses it and returns 1 from a
   **blocking** hook, so every Python user's source commit is blocked today. **Stated plainly
   because it undercuts an easy misreading of this plan:**
   `test_build_cmd_does_not_mutate_the_environment` asserts D1's rule against
   `.claude/hooks/config.json` only — *not* against the templates, which is where build
   commands actually ship to users. It gives no assurance about the property D1 argues for
   beyond this repo's own config.
2. **The other nine `templates/*/config.env`** carry the same class of unscreened and/or
   mutating build commands (`dotnet build`, `./gradlew build`, `go build ./...`, …). Each
   needs the same screen-and-execute audit: is it allowlisted, and is it safe to run on every
   commit that touches source?
3. **[r4] `tests/test_gate_scope.py:191,198,208` use `pytest.importorskip("jsonschema")`**, so
   schema conformance — the shipped config against the shipped schema — is asserted on no
   machine that lacks the library, and the module reports SKIPPED rather than red. Since
   `jsonschema` is already a pinned test dependency (`tests/requirements.txt:131`), that
   module should hard-require it instead. Independent of this plan; surfaced by MAJOR-1.
