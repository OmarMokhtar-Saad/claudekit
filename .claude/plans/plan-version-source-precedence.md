# Implementation Plan: version source precedence (source checkout wins)

## Overview

`_resolve_version()` in `src/claudekit/cli/main.py` prefers
`importlib.metadata.version("claude-kit")` over the version in the source tree. On an
EDITABLE install that metadata is frozen at install time, so after a version bump lands
the CLI keeps reporting the OLD version until somebody re-runs `pip install -e`. Meanwhile
`install.sh` derives the SOURCE version and stamps it into every project's
`.claudekit-manifest.json`, and `ck doctor`'s install-drift check compares those two — so a
freshly installed project is reported as DRIFTED and 7 `tests/test_doctor_gate.py` tests
fail on a source checkout while passing in CI (CI installs fresh, so the two agree).

This plan inverts the precedence on a source checkout only, in ONE shared place
(`src/claudekit/_version.py`), and deletes both hand-bumped version literals.

## Verified reproduction (this worktree, before the change)

```
$ grep -n '^version' pyproject.toml
10:version = "3.2.0"
$ python3 -c "from importlib import metadata; print(metadata.version('claude-kit'))"
3.1.0
$ PYTHONPATH=src python3 -c "import claudekit; print(claudekit.__version__)"
3.1.0
$ ECC_HOOK_PROFILE=minimal python3 -m pytest tests/test_doctor_gate.py -q | tail -1
7 failed, 38 passed in 17.17s
```

The doctor line every one of the 7 failures traces to:

```
[!] Install version drift: this project records v3.2.0, the claudekit package on this
    machine is v3.1.0 — ...
```

`3.2.0` is `install.sh`'s derived source version in the manifest; `3.1.0` is the frozen
editable-install metadata the CLI reports. Same tree, two answers.

## Scope

- **In scope:** where the running version comes from, and in what order; removal of the two
  hardcoded fallback literals; tests that pin the precedence in both directions.
- **Out of scope:** the version NUMBER (no bump), `install.sh` (it already derives, and
  `tests/test_packaging.py::test_single_version_source_of_truth` enforces that), the doctor
  drift check's severity policy, and the 7 `test_doctor_gate` tests — they are **not
  touched**, not re-anchored, not weakened.

## Prerequisites

None. Stdlib only, Python 3.9 target (no `tomllib`, no `importlib.resources.files`).

## Decision 1 — how a source checkout is detected

`src/claudekit/_version.py` accepts the tree only when BOTH hold:

1. **Layout:** the module resolves to `<root>/src/claudekit/_version.py`, i.e.
   `Path(__file__).resolve().parents[1].name == "src"`. A wheel install is
   `site-packages/claudekit/`, which has no `src` parent.
2. **Identity:** `<root>/pyproject.toml` exists and its `[project]` table declares
   `name = "claude-kit"`.

The version is then read from the `[project]` table only, scanned line-wise with the same
anchoring `install.sh` uses (`install.sh:28`); an unanchored `^version` match would take a
`version =` key from any `[tool.*]` table sorted above `[project]` — the same
silent-wrong-value shape this change removes. Any failure returns None, never a guess.

Measured on prototypes of each layout (installed metadata in this env is 3.1.0):

| layout | pyproject next to root | reported |
| --- | --- | --- |
| `<root>/src/claudekit/`, `name = "claude-kit"`, `version = "42.0.1"` | yes | `42.0.1` (source wins) |
| `<root>/src/claudekit/` with the REAL repo pyproject | yes | `3.2.0` (source wins) |
| `<root>/site-packages/claudekit/` (flat, wheel shape), `claude-kit`, `7.7.7` | yes | `3.1.0` (metadata) |
| `<root>/src/claudekit/`, `name = "someone-else"`, `6.6.6` | yes | `3.1.0` (metadata) |

**Named failure modes of this detector:**

- **Wheel / site-packages install** — no `src` parent, so no pyproject is consulted at
  all; falls to metadata. Behaviour unchanged, which is the requirement.
- **A site-packages copy sitting near an unrelated `pyproject.toml`** — rejected twice
  (layout check, then name check); falls to metadata.
- **A vendored copy** at `<other-project>/src/claudekit/` — the neighbouring pyproject
  describes the HOST project, so the name check rejects it; falls to metadata.
- **A vendored copy of a claude-kit FORK** that keeps `name = "claude-kit"` — reports the
  fork's pyproject version. Accepted residual: that is the tree `install.sh` would stamp
  from, so installer/CLI agreement (the property being defended) still holds.
- **Zipapp / frozen / no real file behind the module** — `__file__` missing or
  unresolvable, or `pyproject.toml` unreadable inside the archive; every access is guarded
  and returns None; falls to metadata.
- **Malformed or version-less `[project]` table** — no version parsed, so None; falls to
  metadata. A half-written pyproject can never make the CLI report garbage.
- **Neither source nor metadata** (a stray copied package directory) — returns
  `"unknown"`, the word `install.sh` already records for an unpinnable value.
  `_parse_semver("unknown")` is None, which doctor renders as a **skip**, never a false
  "Install matches kit v…".
- **Cost:** one small file read at import. Accepted; `__version__` is computed once per
  process.

## Decision 2 — which version sites are affected

| site | today | after |
| --- | --- | --- |
| `pyproject.toml` | the truth | unchanged, still the truth |
| `install.sh` | derives from `[project]` (never hardcodes) | unchanged |
| `src/claudekit/__init__.py` | metadata, else hardcoded `"3.2.0"` | `resolve_version()` — **no literal** |
| `src/claudekit/cli/main.py` | metadata, else hardcoded `"3.2.0"` | `resolve_version()` — **no literal** |

So the change **reduces the hand-maintained sites from three to one**: `pyproject.toml`.
Both duplicated literals become derived, which retires a recurring release defect —
`cli/main.py`'s literal sat at `2.1.0` through the whole of the 3.0.0 release
(`.ai/KNOWLEDGE_BASE.md:3`), i.e. it was missed for two releases and nothing failed.
`tests/test_packaging.py::test_single_version_source_of_truth` keeps passing: its literal
regex simply finds nothing left to compare. It is left unchanged and remains the guard
against a literal being re-introduced.

## Decision 3 — do the 7 `test_doctor_gate` failures go away, unweakened?

**Yes, all 7, with zero changes to the test file.** Verified by applying this plan's exact
edits to a scratch copy of the worktree and running the suite there:

```
$ ECC_HOOK_PROFILE=minimal python3 -m pytest tests/test_doctor_gate.py -q | tail -1
45 passed in 17.78s
```

Why they were failing is the disagreement itself, not the fixtures. Three shapes:

- `test_a_freshly_installed_tree_reports_no_version_drift` — positive control: manifest
  3.2.0 vs CLI 3.1.0, so the drift line fired on a fresh install. A TRUE signal; it stops
  firing because the two sides now agree.
- `test_a_minor_version_behind…` / `test_a_patch_gap…` — these derive their fixture version
  from the manifest (`_recorded_version` → `_bumped`), i.e. from install.sh's 3.2.0. "One
  minor behind" was therefore 3.1.0 — exactly the version the CLI reported — so the
  expected gap collapsed to equality and the expected line never appeared.
- the two strict-green tests — reddened by the spurious drift warning.

The previous attempt re-anchored those fixtures to `__version__` and was WITHDRAWN for good
reason. Nothing here re-anchors or weakens them.

Also re-run against the scratch copy: `tests/test_packaging.py`, `tests/test_cli.py`,
`tests/test_doctor_score.py`, `tests/test_install.py`, `tests/test_structure.py` — all
pass; `ruff check src/ tests/ scripts/ .claude/operations/scripts/` and `mypy` clean.
(`tests/test_install_receipts.py` failed 3 tests **in the scratch copy only**, because the
copy has no `.git` and the receipt records no commit; the same file is 37/37 green in the
real worktree, before and independent of this change.)

## Implementation Steps

### Step 1: create the shared resolver

- **File:** `src/claudekit/_version.py`
- **Action:** Create
- **Description:** `DIST_NAME`, `UNKNOWN`, `_project_field()` (`[project]`-scoped key read),
  `source_version()` (the detector above, returning None on every rejection),
  `resolve_version()` (source, then metadata, then `"unknown"`). The module docstring
  carries the precedence rule and the failure-mode list, so the next reader does not have to
  re-derive them.

### Step 2: derive `claudekit.__version__`

- **File:** `src/claudekit/__init__.py`
- **Action:** Modify
- **Details:** replace the `try: metadata.version(...) / except: "3.2.0"` block with
  `from ._version import resolve_version` and `__version__ = resolve_version()`.

### Step 3: derive the CLI's version

- **File:** `src/claudekit/cli/main.py`
- **Action:** Modify
- **Details:** `_resolve_version()` delegates to `claudekit._version.resolve_version()`.
  The import is FUNCTION-LOCAL on purpose: the `sys.path` repair at the top of the file must
  run first for raw-script mode (`python3 src/claudekit/cli/main.py`, which
  `tests/test_cli.py` exercises), and a module-level import after that block would trip
  ruff `E402`. An `ImportError` falls back to metadata, then `"unknown"` — the existing
  `from importlib import metadata` import stays used.

### Step 4: pin the precedence with tests

- **File:** `tests/test_version_precedence.py`
- **Action:** Create
- **Details:** see Tests below.

### Step 5: record it

- **File:** `CHANGELOG.md`
- **Action:** Modify — a `[Unreleased]` entry (user-visible: `ck --version` and `ck doctor`
  change what they report on a source checkout).

### Step 6: correct the maintainer note

- **File:** `.ai/KNOWLEDGE_BASE.md`
- **Action:** Modify — the "Hard rule 7 names four version sites" entry now ends with the
  outcome: the two `src/` literals are gone and `pyproject.toml` is the only hand-bumped
  site. `CLAUDE.md` is NOT touched (it already points at the test rather than listing
  sites, and it is the x4-weighted file with four characters of headroom).

## Files this plan's ops.json writes (exhaustive)

1. `src/claudekit/_version.py` (create)
2. `src/claudekit/__init__.py` (edit)
3. `src/claudekit/cli/main.py` (edit)
4. `tests/test_version_precedence.py` (create)
5. `CHANGELOG.md` (edit)
6. `.ai/KNOWLEDGE_BASE.md` (edit)

No `file_delete`, no `run_command`.

## Tests

New file `tests/test_version_precedence.py`. Every case runs a subprocess against a
SYNTHETIC package tree in `tmp_path` — the two real modules are COPIED into
`<tmp>/<layout>/claudekit/`, so the code under test is the shipped code and no `pip` run is
needed. The environment's own installed metadata (3.1.0 here) is the control, and the
sentinel source version `42.0.1` is one no environment will ever have installed (asserted,
so the test cannot pass for the wrong reason).

| test | pins |
| --- | --- |
| `test_a_source_checkout_reports_the_source_version` | src layout + `claude-kit` pyproject `42.0.1` → reports `42.0.1`, not metadata |
| `test_the_source_version_is_read_from_the_project_table_only` | synthetic pyproject carries `[tool.poetry] version = "0.0.9"` above `[project]`; the answer is never `0.0.9` |
| `test_the_cli_and_the_package_both_report_the_pyproject_version` | REAL checkout: `ck --version` and `claudekit.__version__` both equal the pyproject version |
| `test_no_hand_bumped_version_literal_remains` | no semver literal left in `__init__.py`, `_version.py`, `cli/main.py` (comments excluded) |
| `test_a_wheel_style_layout_still_prefers_installed_metadata` | flat layout + a `claude-kit` pyproject one level up → metadata, NOT `7.7.7` |
| `test_an_unrelated_neighbouring_pyproject_is_not_a_kit_source` | src layout, `name = "someone-else"` → metadata, NOT `6.6.6` |
| `test_a_src_layout_without_a_pyproject_falls_back_without_raising` | tarball/copied tree → metadata or `"unknown"`, exit 0, no traceback |
| `test_the_installer_and_the_cli_cannot_disagree` | real `install.sh --minimal` into `tmp_path`: manifest version == pyproject version, and `ck doctor` prints `Install matches kit v<pyproject>` with no drift line |

### Mutation proofs (each one executed against the scratch copy)

| mutation | result |
| --- | --- |
| revert precedence to metadata-first (`return metadata.version(...)` before `source_version()`) | `10 failed` — the 3 new source-side tests **and** the same 7 `test_doctor_gate` tests come back |
| drop the `src`-layout guard (`if len(here.parents) < 3:` only) | `test_a_wheel_style_layout_still_prefers_installed_metadata` FAILS (reports `7.7.7`) |
| drop the `name = "claude-kit"` guard | `test_an_unrelated_neighbouring_pyproject_is_not_a_kit_source` FAILS (reports `6.6.6`) |
| unanchor the table scan (`in_project = True`) | `test_a_source_checkout_reports_the_source_version` and `…project_table_only` FAIL (report `0.0.9`) |
| unmutated | `8 passed` |

Both directions are therefore mutation-sensitive: nothing here passes if the precedence is
reversed, and nothing passes if the wheel path is broken to satisfy the source path.

### Full-gate commands to run after execution

```bash
ECC_HOOK_PROFILE=minimal python3 -m pytest tests/ -q
ruff check src/ tests/ scripts/ .claude/operations/scripts/
mypy
python3 scripts/gen-docs.py --check
python3 scripts/check-plan-artifacts.py --check
shellcheck install.sh .claude/hooks/*.sh
```

## Rollback

Nothing is deleted and no data is migrated, so rollback is a revert:

1. `git revert <commit>` (or `git checkout HEAD~1 -- src/claudekit/_version.py
   src/claudekit/__init__.py src/claudekit/cli/main.py tests/test_version_precedence.py
   CHANGELOG.md .ai/KNOWLEDGE_BASE.md`), then delete `src/claudekit/_version.py` and
   `tests/test_version_precedence.py`, which are new files a checkout will not remove.
2. Restoring the old code restores the old literals, so re-check that
   `src/claudekit/__init__.py` and `src/claudekit/cli/main.py` name the CURRENT
   `pyproject.toml` version before committing the revert —
   `tests/test_packaging.py::test_single_version_source_of_truth` enforces it.
3. Expect the 7 `tests/test_doctor_gate.py` failures to return on any editable checkout
   whose metadata is stale; that is the pre-existing defect, not a new one.
4. Per-operation backups are written by the operations engine, so
   `.claude/operations/scripts/restore-backup.py --list` also covers steps 2, 3, 5 and 6.

## Risk Assessment

- **Low:** `CHANGELOG.md` and `.ai/KNOWLEDGE_BASE.md` (prose); the new test file (additive);
  `src/claudekit/__init__.py` (six lines, one import).
- **Medium:** `src/claudekit/cli/main.py` — every `ck` command imports it, and a
  module-level import there would break raw-script mode; mitigated by the function-local
  import and by `tests/test_cli.py::test_version_flag`, which runs the file as a script.
  `src/claudekit/_version.py` is new but is imported at package init, so a syntax or typing
  error there breaks the whole CLI — covered by `ruff`/`mypy` and by the 8 new tests.
- **High:** none identified. The one behaviour that CHANGES is what a source checkout
  reports; wheel installs take the same metadata path they take today, pinned by
  `test_a_wheel_style_layout_still_prefers_installed_metadata`.
- **Blast radius note:** `cli/main.py` is a hub (every command, `ck doctor`, `ck update`).
  The change is confined to one function whose only output is a string, and the value it now
  produces is the same one `install.sh` already stamps.

## Open / not settled

- **Editable install vs a released wheel built FROM a source tree.** A wheel never ships
  `pyproject.toml` next to `src/claudekit/`, so the source path is unreachable there — but
  this is asserted from the layout, not from an installed-wheel run; the wheel-install test
  in `tests/test_packaging.py` builds and installs in CI and would surface a surprise.
- **Pre-release / build-suffixed versions** (`3.2.0rc1`) would now flow from pyproject into
  `_parse_semver`, which returns None for them and makes doctor skip the drift check. This
  kit has never shipped one; unchanged from today's behaviour and deliberately not
  designed for here.
