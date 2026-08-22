# Implementation Plan: Installer drops Python hooks — fix every delivery path + add the structural guard

## Overview

Commit `26b26da` added `.claude/hooks/reflection-gate.py` (wired into `.claude/settings.json`
on 7 lifecycle events) and its library `reflection.py`. `install.sh` copies hooks by an
**extension allowlist** (`*.sh`, `*.json`, `*.md`) that was never updated, so a fresh full
install ships `settings.json` referencing a script that does not exist. `python3 <missing>`
exits **2**, and exit 2 on `PreToolUse` is a BLOCK — every Edit, Write and Bash in a freshly
installed project is blocked. This plan fixes the delivery paths that drop `.py`, replaces the
stale extension allowlist with a **structural denylist**, and adds two mechanical guards
(install-time fail-closed check + `ck doctor` check) plus behavioral tests.

## Regression verification (each link executed, not assumed)

| Link | Evidence | Verdict |
|---|---|---|
| Hooks exist | `.claude/hooks/reflection-gate.py`, `.claude/hooks/reflection.py` present | CONFIRMED |
| Wired on 7 events | `grep -n '\.py' .claude/settings.json` -> 7 hits: PreToolUse, PostToolUse, SessionStart, PreCompact, Stop, SubagentStop, PostToolUseFailure | CONFIRMED |
| Installer drops `.py` | `install.sh:245-247` copies only `*.sh`, `*.json`, `*.md` | CONFIRMED |
| settings.json ships | `install.sh:259` copies `settings.json` unconditionally in full mode | CONFIRMED |
| `python3 <missing>` -> 2 | executed: `python3 /tmp/definitely-missing-xyz.py; echo $?` -> `exit=2` | CONFIRMED |
| exit 2 == BLOCK | CLAUDE.md hard rule 2 | CONFIRMED |

**Net effect confirmed end to end.** Scope refinement: the bug affects **full mode only**
(the default). Minimal mode installs neither hooks nor `settings.json` (both are inside the
`if [[ "$MODE" == "full" ]]` block at `install.sh:208`), so minimal installs are unaffected.

## Other delivery paths — audit results

1. **Wheel / sdist — NOT BROKEN.** `MANIFEST.in` uses `recursive-include .claude *` and
   `setup.py::_include` is a **denylist** (`_EXCLUDE_NAMES`, `_EXCLUDE_SUFFIXES`,
   `_EXCLUDE_DIR_PARTS`). Both are structural, so `hooks/*.py` is already bundled into
   `<prefix>/share/claudekit`. This is exactly the pattern `install.sh` failed to use.
   **The manifest test would NOT have caught it**: `tests/test_packaging.py::test_setup_bundles_runtime_assets`
   asserts only `any(f.endswith(".sh") and "hooks" in f ...)` — an extension-specific
   assertion that is blind to `.py`. Tightened in Step 5.
2. **`ck init` / `ck update` — INHERIT THE BUG, no separate fix needed.** Both
   (`main.py:80` and `main.py:576`) shell out to `bash install.sh`; they do not copy assets
   themselves. Fixing `install.sh` fixes both. No code change required in those functions.
3. **`ck doctor` — DOES NOT CATCH IT (confirmed gap).** `main.py:214-236` checks a hardcoded
   list of five `.sh` hooks and then only that `settings.json` is parseable JSON and counts
   its event keys. It never resolves the hook *commands* to files, so it reports a healthy
   install on a fully-blocked project. Step 3 adds that check — the highest-leverage item
   here because it generalises to every future hook.
4. **`templates/hooks/` — SAME STALE ASSUMPTION.** `install.sh:250` copies
   `templates/hooks/*.sh`. All four current files are `.sh`, so no live breakage, but the
   assumption is identical and is fixed by the same structural copy.

## Scope

- **In Scope:** `install.sh` hook copy/chmod/count + a new install-time wired-hook check;
  `ck doctor` wired-hook resolution check (`src/claudekit/cli/main.py`); new behavioral tests;
  tightening the packaging assertion.
- **Out of Scope (owned by others / explicitly not touched):** `.claude/settings.json`,
  `.claude/hooks/**` (including both reflection hooks), `scripts/gen-docs.py` (sibling
  workstream owns the documented hook count), `CLAUDE.md`, `CHANGELOG.md`, `.ai/**`, agents,
  skills. No changes needed to `MANIFEST.in`, `setup.py` or `pyproject.toml` — verified
  already correct.

## Prerequisites

None. No new dependencies (stdlib only). `.claude/settings.local.json` with
`ECC_HOOK_PROFILE=minimal` must exist for the implementer to edit files in this repo.

## Design principle: structural rule, not extension list

The failure mode was an allowlist that silently went stale. Every replacement is structural:

- **Copy:** ship *every* file in the hooks source dir, denying only runtime state
  (`*.log`, `*.pyc`, `compact-counter.txt`, `settings.local.json`). Mirrors `setup.py`.
  Note `.claude/hooks/` really does contain runtime state in-tree (`hooks.log`,
  `cost-tracker.log`, `edited-files.log`, `compact-counter.txt`) — the denylist covers all four.
- **chmod:** executability follows the file's own **shebang**, not its extension.
- **Count:** `HOOK_COUNT` counts shebang-bearing installed files, so it can never go stale
  against a new language again.
- **Guard:** derive the expected hook set from `settings.json` itself (the wiring is the
  source of truth) instead of from any hardcoded list.

## Implementation Steps

### Step 1: Structural hook copy, shebang-based chmod, non-stale count
- **File:** `install.sh` (replaces lines 244-255)
- **Action:** Modify
- **Details:** Replace the three `cp ... *.sh/*.json/*.md` lines, the `templates/hooks/*.sh`
  copy, the `chmod +x *.sh` and the `ls *.sh | wc -l` count with a `_copy_hook_assets()`
  helper (denylist-filtered, called for both `$CLAUDE_SRC/hooks` and
  `$SCRIPT_DIR/templates/hooks`) plus a shebang-driven chmod/count loop.
- **bash 3.2 / `set -Eeuo pipefail` notes:** `_hook_line` is initialised to `""` before each
  `read` so an empty file cannot trip `set -u`; `read` is guarded with `|| true` for the
  no-trailing-newline case; `for f in dir/*` is guarded by `[[ -f ]]` so an empty glob is a
  no-op; `${_hook_src##*/}` avoids a `basename` subprocess. No arrays, no `mapfile`.

### Step 2: Install-time fail-closed check that every wired hook resolves
- **File:** `install.sh` (inserted after the `settings.json` copy, ~line 261)
- **Action:** Modify
- **Details:** After `settings.json` is installed, a stdlib `python3` heredoc regexes
  `\.claude/hooks/([A-Za-z0-9._-]+)` out of the installed `settings.json` and reports any
  name with no corresponding file in `$DEST/hooks/`. If any is missing, print the list via
  `print_err` and `exit 1`. This runs **before** `trap - ERR` at line 440, so the existing
  cleanup trap removes the staging dir and preserves any pre-existing `.claude/` — the
  installer fails closed rather than leaving a project where every tool call is blocked.
  Uses `print_err` (the actual function name; there is no `print_error`).

### Step 3: `ck doctor` resolves every hook command in settings.json
- **File:** `src/claudekit/cli/main.py`
- **Action:** Modify (2 edits: add `import re`; add the check after the settings.json block)
- **Details:** Same regex extraction against `.claude/settings.json`, resolved against
  `.claude/hooks/`. Missing files -> `check(..., False, ...)` -> `doctor` returns 1. Zero
  references -> `"warn"`. All resolve -> pass with the reference count. Import is placed
  between `os` and `shutil` to satisfy ruff's isort (`I`) rule.

### Step 4: Behavioral regression tests (new file)
- **File:** `tests/test_hook_delivery.py`
- **Action:** Create
- **Details:** Every test runs the real installer into a `tempfile.TemporaryDirectory()` with
  `ECC_HOOK_PROFILE` forced explicitly in `env`; nothing mutates the real tree.
  1. `test_every_wired_hook_resolves_after_install` — the load-bearing guard. Full install,
     parse the **installed** `settings.json`, assert every referenced `.claude/hooks/<name>`
     exists on disk. Asserts on the installed result, never on the text of `install.sh`.
  2. `test_python_hooks_installed_and_executable` — `reflection-gate.py` and `reflection.py`
     present and `os.access(..., X_OK)`.
  3. `test_all_source_hook_assets_installed` — structural: every non-runtime file in
     `.claude/hooks/` in the source tree is present in the install. Catches the *next* stale
     extension, not just this one.
  4. `test_installer_rejects_wired_but_missing_hook` — copies the repo to a temp dir, deletes
     `reflection-gate.py` from the **copy**, runs the installer from the copy, asserts a
     non-zero exit and the missing hook named in the output. Proves Step 2 is fail-closed
     without touching the real tree.
  5. `test_doctor_flags_wired_but_missing_hook` — builds a minimal installed tree in a temp
     dir, writes a `settings.json` wiring a nonexistent hook, runs
     `python3 -m claudekit.cli.main doctor` with `cwd=tmpdir`, asserts returncode 1 and the
     hook name in stdout.
  6. `test_doctor_passes_on_clean_install` — doctor on a real full install does not fail on
     the new check (guards against a false positive breaking `ck doctor --strict`).
- **Boundedness: MEASURED, not asserted** (see the Dry-Run Evidence section below).
  In `test_doctor_flags_wired_but_missing_hook`, only the `"ghost-hook.py" in output`
  assertion BINDS the fix; the `returncode == 1` assertion does NOT bind it (the minimal
  fixture already fails several pre-existing doctor checks, so it returns 1 either way).
  Both are kept, and the test is commented to say which is which.

### Step 5: Tighten the packaging assertion that missed this
- **File:** `tests/test_hook_delivery.py` (same new file, `test_setup_bundles_python_hooks`)
- **Action:** Create (part of Step 4's file)
- **Details:** Load `setup.py::_asset_data_files()` the same way `test_packaging.py` does and
  assert `hooks/*.py` is in the bundle. Lives in the new file rather than editing
  `test_packaging.py` to keep file ownership clean for parallel workstreams.

## Testing Strategy

```bash
python3 -m pytest tests/test_hook_delivery.py -v      # new guards
python3 -m pytest tests/test_install.py tests/test_cli.py tests/test_packaging.py -q
python3 -m pytest tests/ -q                            # full suite, zero failures
ruff check src/ tests/ scripts/
mypy
shellcheck install.sh
python3 scripts/gen-docs.py --check                    # confirm no docs-count drift
```

Manual end-to-end confirmation of the fix:

```bash
T=$(mktemp -d) && bash install.sh "$T" --full --force --yes && \
  python3 - "$T" <<'EOF'
import os, re, sys
d = sys.argv[1] + "/.claude"
t = open(d + "/settings.json").read()
missing = [n for n in set(re.findall(r"\.claude/hooks/([A-Za-z0-9._-]+)", t))
           if not os.path.exists(os.path.join(d, "hooks", n))]
print("MISSING:", missing or "none")
EOF
```

## Rollback Plan

- `git revert` / `git checkout -- install.sh src/claudekit/cli/main.py` and delete
  `tests/test_hook_delivery.py`. All three changes are additive or self-contained; no data
  migration, no schema change, no asset renames.
- The operations engine writes `.claude/backups/` entries for both edited files.
- Partial rollback is safe: Step 3 (doctor) and Step 1 (installer) are independent.

## Risk Assessment

- **Low Risk**
  - `import re` addition; `ck init`/`ck update` need no change (they delegate to `install.sh`).
  - `MANIFEST.in` / `setup.py` / `pyproject.toml` untouched — audited as already correct.
  - New test file: no collision with any sibling workstream's files.
- **Medium Risk**
  - **`HOOK_COUNT` semantics change** (`*.sh` count -> shebang-bearing file count). The
    number in the installer's runtime message will change. Verified no test, doc or script
    asserts on `HOOK_COUNT` or the string "hooks installed" (`grep -rn` over `tests/`,
    `scripts/`, `docs/` -> zero hits). Message reworded to "hook scripts installed" to keep
    it honest. This is the installer's own runtime message only; **`scripts/gen-docs.py` is
    untouched** — the sibling workstream owns the documented count. Note the two counts will
    legitimately differ: `reflection.py` is a shebang-bearing library imported by
    `reflection-gate.py` (like `lib.sh`), so it is installed and counted here but is not
    *wired*. Flagged for the owner rather than decided unilaterally.
  - **New `exit 1` path in `install.sh`.** It fires only when `settings.json` wires a hook
    that is not installed — i.e. exactly the broken state. It sits before `trap - ERR`, so
    the cleanup path is the already-tested one
    (`test_install.py::test_mid_failure_preserves_existing_claude`). A regex false positive
    would break all installs; the character class `[A-Za-z0-9._-]+` is deliberately narrow
    and test 6 guards the clean-install case.
  - **`ck doctor --strict` sensitivity**: existing installs predating this fix will now
    correctly FAIL doctor. That is the intent (it surfaces the live regression), but it is a
    user-visible behavior change worth a CHANGELOG line — **CHANGELOG.md is not mine to
    edit**, raised below.
- **High Risk**
  - None. No security surface, no schema change, no protected-file or deletion operations
    (0 `file_delete` ops).

## Raised for the owner (outside my ownership)

1. **CHANGELOG.md `[Unreleased]`** needs an entry (release-blocking bug fix + the
   `ck doctor` behavior change). Not mine to edit — needs an owner or the docs workstream.
2. **Hook count reconciliation** with the sibling `scripts/gen-docs.py` workstream: this plan
   deliberately does not touch `gen-docs.py`. If that workstream lands "wired hooks only",
   the installer's shebang-based count and the documented count will differ by exactly
   `reflection.py`. Owner decision, not mine.
3. **Fleet impact**: per project memory, 16 kitted projects were synced. Any that received
   `settings.json` from commit `26b26da` without the `.py` hooks are currently blocked and
   need `ck update` after this lands. Worth an explicit owner check.

## Note on ops.json `run_command` operations

The operations engine's `run_command` allowlist is `black, gofmt, goimports, isort,
pip-compile, prettier, ruff, rustfmt`. Only `ruff check src/ tests/ scripts/` is therefore
encoded as an op. **`shellcheck install.sh` and the pytest runs must be executed manually**
after the implementer applies the config — they are listed in Testing Strategy above and are
required before this is considered done.


---

# Addendum: review round 1 (89/100 CONDITIONAL) — all findings addressed

## MAJOR — the guard could have blocked installation for everyone. FIXED.

The reviewer was right, and this was the most important finding in the review: my original
extractor took *every* `\.claude/hooks/([A-Za-z0-9._-]+)` token and demanded it exist. My own
copy step deliberately DENIES `*.log` — so the first hook command that logs to
`$ROOT/.claude/hooks/hooks.log` (an idiom already used in this repo) would have made the
installer `exit 1` and nobody could install. That is strictly worse than the bug being fixed,
and it contradicted my own stated principle of failing open when unsure.

Both extractors (`install.sh` heredoc and `main.py::_required_hook_scripts`) now require a
token to be **provably a script** before demanding it exist:

1. **Denylist subtraction** — `*.log`, `*.pyc`, `*.orig`, `*.rej`, `*.swp`, `~`,
   `compact-counter.txt`, `settings.local.json` are never required. Identical to the copy
   denylist, so the two can never disagree about what is runtime state.
2. **Plausibility rule** — a token qualifies only if it carries a known script extension
   (`.sh .bash .zsh .py .js .mjs .ts .rb .pl`) **or** is directly preceded by an interpreter
   invocation (`python3|python|bash|sh|zsh|node|ruby|perl`, optional flags, optional quoting
   and `$VAR/` path prefix, within 80 chars).
3. **Everything else is IGNORED, never required.** "Cannot determine" now fails open.

The logic is duplicated (a shell heredoc cannot import from `main.py`); the denylists and
suffix tuples are kept textually identical and both are covered by tests.

## MINOR — existence is not resolvability. FIXED.

Both extractors now use `os.path.isfile` / `Path.is_file()` instead of `exists()`, so a
*directory* named `foo.py` no longer satisfies the gate. New test
`test_doctor_flags_hook_that_is_a_directory` covers it.

**Documented blind spot (Risk, as requested):** hooks wired by an absolute path
(`/Users/x/.claude/hooks/h.sh`) or a home-relative path (`~/.claude/hooks/h.sh`) are matched
by the regex only in their `.claude/hooks/<name>` tail, and are then resolved against the
*project* hooks dir. A user-level hook living outside the project would therefore be reported
as unresolved. No such wiring exists in the shipped `settings.json` today (all 25 references
are project-relative), and the failure mode is a loud, named, actionable message rather than
silent breakage — but this guard is **not** a complete model of Claude Code hook resolution
and must not be described as one.

## MINOR — `exit 1` does not fire the ERR trap. FIXED.

Confirmed: bash does not run an ERR trap for the `exit` builtin, so `_cleanup_on_failure`
(`install.sh:117`) would not have run and `.claude.staging.$$` would have been left in the
user's project. The check now calls `_cleanup_on_failure` explicitly before `exit 1`. The
data-safety claim was and remains correct (the atomic swap at `install.sh:439` is *after* this
check, so the user's real `.claude` is never touched); it was the no-litter claim that was
wrong. `test_installer_fails_closed_on_wired_but_missing_hook` now also asserts
`not list(target.glob(".claude.staging.*"))`.

## MINOR — denylist insurance. FIXED.

`*.orig`, `*.rej`, `*~`, `*.swp` added to the copy `case` so merge and editor debris cannot
ship into user projects. (Dotfiles remain naturally excluded: `for f in "$dir"/*` does not
glob them.)

## MINOR — say what the count means. FIXED.

The installer now prints:
`"$HOOK_COUNT hook scripts installed (executables, including shared libraries)"`
with an inline comment stating that this count legitimately differs from the docs' "wired"
count because shared libraries (`reflection.py`, `lib.sh`) and template hooks are executable
but not themselves wired. `scripts/gen-docs.py` remains untouched.

## Dry-Run Evidence (everything below was executed, not reasoned about)

The ops config was applied with the real operations engine to a `copytree` of the repo in the
scratch dir, and the suites were run there. **The real tree was never modified**
(`git status` clean, verified after). The engine's approval gate correctly refused the run
until `--no-approval` was passed, which is legitimate only because this was a throwaway copy.

- `validate-config-json.py` -> **APPROVED** (7 operations, all find patterns located).
- Engine apply -> **7/7 successful, 0 errors**; the `ruff` op reported "All checks passed!".
- `shellcheck install.sh` -> **clean** (see the SC2001 fix below).
- `pytest tests/test_hook_delivery.py` -> **11 passed**.
- Full suite -> 991 passed / 15 failed, against a pristine-copy baseline of 983 passed /
  12 failed. Attribution of the delta is in "Findings for the implementer" below; **zero**
  failures are caused by the code change itself.

### Two defects the dry run caught in my own plan (both fixed before re-validation)

1. **`shellcheck` SC2001** on `echo "$MISSING_HOOKS" | sed 's/^/        - /'`. Replaced with a
   `while IFS= read -r ... done <<< "$MISSING_HOOKS"` loop (bash 3.2 safe). This would have
   failed the repo's own DoD gate.
2. **`cli.main.err()` writes to STDERR**, not stdout — so my doctor assertions on
   `result.stdout` could never have seen a *failed* check. Two tests failed for this reason.
   Tests now assert on `result.stdout + result.stderr` via a `_doctor_output()` helper that
   documents why. The fix itself was correct; my assertions were wrong.

### Boundedness, measured by reverting each fix in an applied copy

| Revert | Result |
|---|---|
| Step 1 (structural copy) | **6 failed**, incl. `test_every_wired_hook_resolves_after_install`, `test_python_hooks_installed_and_executable`, `test_all_source_hook_assets_installed` |
| Step 2 (installer check only) | **exactly 1 failed**: `test_installer_fails_closed_on_wired_but_missing_hook` |
| Step 3 (doctor check only) | **exactly 3 failed**: the two `test_doctor_flags_*` tests and `test_doctor_passes_wired_hook_check_on_clean_install` |

Every guard is bound to its own fix, and Steps 2 and 3 are independently bound.

### Explicit confirmation of the MAJOR fix

`test_log_and_unprovable_references_do_not_block_install` patches a copy's `settings.json` to
reference `$ROOT/.claude/hooks/hooks.log` (both bare and interpreter-prefixed) plus an
unprovable `.claude/hooks/mystery-token`, then runs the installer: **exit 0, install
succeeds**, and `hooks.log` is confirmed absent from the installed tree. Under the pre-review
design this install would have been refused.

## Findings for the implementer / coordinator (NOT plan defects)

1. **The operations engine strips the executable bit.** After `code_edit` on `install.sh`, the
   mode went `0755 -> 0600`, failing `test_structure.py::TestRootFiles::test_install_script`
   and `test_install.py::TestInstallScript::test_script_executable`. This is generic engine
   behavior for any `code_edit`, not something my ops config controls, and
   `.claude/operations/scripts/` is outside my ownership. **The implementer MUST run
   `chmod +x install.sh` after applying this config**; `chmod` is not on the `run_command`
   allowlist so it cannot be encoded as an op. Worth filing separately — it silently breaks
   the executable bit on every shell asset the engine touches.
2. **Archive the ops config after execution.**
   `test_delivery_contract_smoke.py::test_queued_ops_configs_validate_against_head` requires
   every *queued* config in `.claude/plans/` to validate against the current tree; once
   applied, this one no longer does. Moving it to `.claude/plans/archive/` restores the suite
   (verified: 148 passed across the four affected test files afterwards).
3. **Pre-existing order-dependent flake**, not mine:
   `test_reflection_ledger.py::TestCli::test_receipt_via_cli_clears_the_checkpoint` fails in a
   full-suite run but **passes in isolation in both the baseline and the modified copy**.
   Adding a test file perturbed collection order and exposed it. Owned by the reflection
   workstream.
4. The remaining 12 full-suite failures (mostly `test_ops_enforcement_scope.py`) are present
   identically in the pristine baseline copy and are artifacts of running outside a git
   checkout. Unrelated to this change.

## Confirmed unchanged from round 1

Ownership boundaries held: `.claude/settings.json`, `.claude/hooks/**`, `scripts/gen-docs.py`,
`CLAUDE.md`, `CHANGELOG.md`, `.ai/**` and all agents/skills are untouched. `MANIFEST.in`,
`setup.py` and `pyproject.toml` remain audited-correct and unedited. The CHANGELOG entry —
including that pre-fix installs will newly FAIL `ck doctor --strict`, in CI too — is owned by
the coordinator.
