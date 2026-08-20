# Implementation Plan: Gate Scope — point three existing gates at the code they should already cover

**Workstream:** 17 · **Branch:** `perf/token-efficiency` · **Ops config:** `.claude/plans/plan-gate-scope.ops.json`
**Source:** `review/code-review-triage.md` — the 13 findings that need nothing built, only an existing gate re-scoped.

## Overview

Three shipped gates are scoped past the code they are supposed to guard: `mypy` never
sees the operations engine, `gen-docs --check` never sees the CLI's count floors, and
`config.schema.json` is applied by nothing at all. This plan widens all three and proves
each one can now fail on real drift.

## Scope

- **In scope:** `pyproject.toml` (mypy `files` only), `scripts/gen-docs.py`,
  `src/claudekit/cli/main.py`, `config.schema.json`, type-annotation-only fixes in four
  files under `.claude/operations/scripts/`, and a new `tests/test_gate_scope.py`.
- **Out of scope:** any hook, `.claude/settings.json`, agents, skills, `CLAUDE.md`,
  `CHANGELOG.md`, `.ai/**`, `review/**`, `install.sh`, existing test modules. No behavior
  change in the operations engine.

---

## Phase 0 — measurements (taken before any planning; all reproduced below)

### Gate 1 — `mypy`

Baseline (`files = ["src/claudekit"]`): `Success: no issues found in 8 source files`.

Widened (`files = ["src/claudekit", ".claude/operations/scripts"]`) against the untouched
tree: **26 errors in 4 files, 18 source files checked.**

| File | Errors |
|---|---:|
| `.claude/operations/scripts/project-graph.py` | 12 |
| `.claude/operations/scripts/xpipe.py` | 8 |
| `.claude/operations/scripts/validate-config-json.py` | 4 |
| `.claude/operations/scripts/execute-json-ops.py` | 2 |

| Error class | Count |
|---|---:|
| `attr-defined` | 7 |
| `index` | 6 |
| `var-annotated` | 4 |
| `arg-type` | 3 |
| `return-value` | 2 |
| `str-format`, `operator`, `call-overload`, `assignment` | 1 each |

Six of the ten ops scripts (`shared.py`, `review-record.py`, `knowledge-ledger.py`,
`restore-backup.py`, `worktree-manager.py`, `extract-json-from-plan.py`) were already clean.

### Gate 2 — `gen-docs.py --check`

With `src/claudekit/cli/main.py` appended to `DRIFT_FILES`: **3 stale counts**, all in the
`ck doctor` floors.

| Site | Says | Real |
|---|---:|---:|
| `src/claudekit/cli/main.py:203` | 9 agents | 29 |
| `src/claudekit/cli/main.py:209` | 8 commands | 42 |
| `src/claudekit/cli/main.py:216` | 27 skills | 76 |

The floors were roughly a third of reality, so `ck doctor` passed on trees missing 20
agents, 34 commands or 49 skills — a `vacuous-check`.

### Gate 3 — `config.schema.json`

`jsonschema.Draft7Validator(schema).iter_errors(config)` on the shipped pair:
**1 violation** — `<root>: Additional properties are not allowed ('_note' was unexpected)`.
Nothing else. The schema lives at repo root (`./config.schema.json`), not in `.claude/hooks/`.

**Verdict: the schema is wrong, the config is right.** `_note` carries the live deprecation
notice for the file ("superseded by `.claude/settings.json` … retained for the `project`
section"). JSON has no comments, so an underscore-prefixed key is the conventional carrier.
Deleting it to satisfy a schema that nothing had executed in 46 days would destroy
information to preserve an assumption. The schema simply predates `_note` and, never having
been run, never learned about it. Fix: admit `_note` as a `string` property.

---

## Decision: the mypy scope option

**Chosen: fix all 26 outright. No `ignore_errors`, no per-path strictness reduction.**

Justification: 26 is small, concentrated in 4 files, and every error is annotation-level —
missing `Dict`/`Deque` annotations, an implicit-`Optional` default, a return type that
contradicts its own docstring, and eight pre-existing `# type: ignore[...]` suppressions
whose error codes no longer match what mypy emits. None requires touching control flow, so
"behavior changes are out of scope" is satisfied literally: the applied diff changes only
annotations, ignore codes, and two guard conditions that the surrounding code already
enforced but mypy could not see (`if error or data is None`, `if src is None or dst is None`
— both unreachable branches under existing invariants). A burn-down list or
`ignore_errors` would have been the honest answer at several hundred errors; at 26 it would
be the `vacuous-check` this workstream exists to close.

### Real bugs found and NOT fixed here (report only, per the brief)

None of the 26 is a live bug. The closest calls, all currently unreachable:

1. `project-graph.py:271` — `cmd_build` checks `if error:` but not `data is None`.
   `read_input` always returns them paired, so the `None` path is unreachable today; the
   plan adds the explicit guard rather than an `assert`, so a future `read_input` that
   returns `(None, None)` degrades to exit 2 instead of `TypeError`.
2. `execute-json-ops.py:288,291` — `normalize_config` is annotated `-> dict` while its
   docstring and body both return `None` on a malformed legacy config. Callers already
   handle `None`; only the annotation was wrong.
3. `xpipe.py` (8 sites) — `state`/`stage` are `Dict[str, object]`, which forces a
   suppression at every use. **Recommended follow-up (not this plan): convert both to
   `TypedDict` and delete all eight `# type: ignore` comments.** Correcting the codes here
   keeps the diff minimal and the intent intact.

---

## Implementation Steps

### Step 1 — widen the mypy gate
- **File:** `pyproject.toml` · **Action:** Modify
- `files = ["src/claudekit"]` → `files = ["src/claudekit", ".claude/operations/scripts"]`.
- Verified: mypy resolves the dash-named scripts (`execute-json-ops.py` etc.) as standalone
  modules; checked-file count goes 8 → 18.
- **What this does and does not buy.** The ops scripts are now *in scope* at the project's
  existing strictness — which is default: `check_untyped_defs` is off, so mypy still skips
  the **bodies of unannotated functions**, and the eight retained `# type: ignore[...]` in
  `xpipe.py` still suppress. An unannotated `def` in the operations engine can hold a type
  error and the widened gate stays green. This closes the "never looked at all" gap, not the
  "fully type-checked" one; `check_untyped_defs = true` is a recorded residual-gap follow-up
  and is deliberately out of this plan, whose measured cost was 26 errors, not the unmeasured
  cost of that flag.

### Step 2 — teach `gen-docs.py` to own the CLI's count floors
- **File:** `scripts/gen-docs.py` · **Action:** Modify (6 edits)
- Add `src/claudekit/cli/main.py` to `DRIFT_FILES` (prose scan).
- Add `PY_BEGIN` / `PY_END` / `PY_BLOCK_FILE` and `render_py_block()`, generating
  `EXPECTED_AGENTS` / `EXPECTED_COMMANDS` / `EXPECTED_SKILLS` constants. Hooks are
  deliberately excluded: `install.sh --minimal` legitimately ships a hook subset.
- Generalise `_replace_block(text, block, begin=BEGIN, end=END)` so one function serves both
  the README table and the Python block.
- `main()` regenerates the Python block on a plain run and fails `--check` when it is stale.
- Treat a **missing marker as an error**, not a pass. `_replace_block` returns the text
  unchanged when it finds no markers, so without this the entire count gate could be
  disabled — silently, and green — by deleting the very block it keys on. `--check` and the
  plain run both exit 1 when `PY_BEGIN` is absent from `PY_BLOCK_FILE`. Guarded with
  `py_path.exists()` so an invocation from outside a repo reports that cleanly instead of
  dying on a raw `FileNotFoundError`.
- Add `NO_AUTOFIX = {PY_BLOCK_FILE}` so `fix_drift` never rewrites numbers inside Python
  source. A bare literal in a comparison (`>= 9`) has no noun beside it, so auto-fix would
  update only its message twin and leave the check silently disagreeing with what it prints.
  On code drift, gen-docs reports "could not auto-fix" and exits 1 instead.

### Step 3 — make the CLI floors generated, and apply the schema
- **File:** `src/claudekit/cli/main.py` · **Action:** Modify (6 edits)
- Insert the `# BEGIN GENERATED:counts` … `# END GENERATED:counts` block after
  `__version__`, seeded with the generator's current output (29 / 42 / 76).
- Replace the three hardcoded floors and their message literals with the constants — after
  this, no component-count digit remains hand-written in the file (hard rule 8).
- Add `_check_config_schema(data, check)` and call it from the `config.json` block of
  `cmd_doctor`. The schema is located via `find_claudekit_root() / "config.schema.json"`
  (`setup.py` already ships it as a root data file). `jsonschema` is imported lazily: it is
  an **optional extra** (`[project.optional-dependencies] validation`), so the zero-runtime-
  dependency rule holds, and when it is absent the check degrades to a `warn`, never to a
  silent pass. Reports up to three violations with their JSON paths.

### Step 4 — fix the schema, not the config
- **File:** `config.schema.json` · **Action:** Modify (1 edit)
- Add a `_note` string property. The root `additionalProperties: false` is retained, so any
  other unknown **top-level** key still fails. **Nested objects are not constrained:**
  `hooks`, each per-hook object, `global`, `project` and `security` omit
  `additionalProperties`, so a typo like `hooks.pre-commit.enabeld`, or an entirely unknown
  hook name, still passes. Closing them is a follow-up, not this plan.

### Step 5 — annotations for the widened mypy scope (no behavior change)
- `.claude/operations/scripts/project-graph.py` (4 edits): import `Any`/`Deque`; guard
  `data is None` in `cmd_build`; annotate `rows: List[Dict[str, Any]]`; guard
  `src`/`dst` `None` and annotate `queue: Deque[Tuple[str, List[dict]]]` in `cmd_path`.
- `.claude/operations/scripts/validate-config-json.py` (5 edits): widen the `typing` import;
  annotate `legacy_sim`, `sim_files`, `filename_map`; make the implicit-`Optional` default on
  `validate_backup_compatibility` explicit.
- `.claude/operations/scripts/execute-json-ops.py` (1 edit): `normalize_config` →
  `Optional[dict]`.
- `.claude/operations/scripts/xpipe.py` (8 edits): correct the error code on eight existing
  suppressions (7 → `attr-defined`, 1 → `call-overload`). Anchors include the preceding line
  where a 4-space-indented line is a substring of an 8-space one.

### Step 6 — behavioral red/green tests
- **File:** `tests/test_gate_scope.py` · **Action:** Create (12 tests)
- Filename chosen to avoid collision with the sibling task-015 Lane A test modules; no
  existing test file is touched.
- `ECC_HOOK_PROFILE=minimal` is forced into every subprocess env.
- The real tree is never mutated: gen-docs cases run against a `tmp_path` mirror whose
  asset directories are symlinks back to the repo, and the doctor cases build a throwaway
  project plus a fake install root wired via `CLAUDEKIT_HOME`.

---

## Proof that each widened gate now fails on real drift

Measured, not asserted. Every number below was produced by running the command.

| Gate | Red arm | Result | Green arm | Result |
|---|---|---|---|---|
| mypy | widened `files`, untouched ops scripts | **26 errors in 4 files** (rc≠0) | after Step 5 | `Success: no issues found in 18 source files` (rc=0) |
| mypy (synthetic) | `planted.py` with `def f() -> int: return 'x'` under the widened path | rc≠0, names `planted.py` | — | — |
| gen-docs (block) | `EXPECTED_AGENTS = 1` in the mirror | rc=**1**, `ERROR: generated counts block in src/claudekit/cli/main.py is out of date` | `python3 scripts/gen-docs.py` then `--check` | rc=**0** |
| gen-docs (prose) | append `# drift probe: 5 agents` to the mirror's `main.py` | rc=**1**, `main.py:896: says 5, should be 29` | remove the line | rc=**0** |
| gen-docs (no-autofix) | same probe, plain run | rc=**1**, `could not auto-fix`, file left unmodified | — | — |
| gen-docs (missing marker) | delete the whole `BEGIN/END GENERATED:counts` block | `--check` rc=**1**, `has no '# BEGIN GENERATED:counts' block - the generated count gate is not bound to anything`; plain run rc=**1**, `nothing to regenerate` | block restored + regenerated | rc=**0** |
| gen-docs (absent file) | `main.py` moved away entirely | rc=**1**, same clean message, no `FileNotFoundError` traceback | — | — |
| doctor schema | shipped config + shipped schema, before Step 4 | `[✗] … 1 schema violation(s): <root>: Additional properties are not allowed ('_note' was unexpected)`, 23/27 pass, 1 fail | after Step 4 | `[✓] Hooks config.json matches config.schema.json`, 24/27 |
| doctor schema | inject `global.logLevel = "verbose"` + an unknown top-level section | `[✗] Hooks config.json matches config.schema.json — 2 schema violation(s)` | same skeleton project, valid config | `[✓] Hooks config.json matches config.schema.json` |

No existing gate was weakened: `additionalProperties: false` is retained, README drift
checking is untouched, and mypy's strictness settings are unchanged — only its `files` list grew.

## End-to-end verification (fresh clone, ops config applied by the engine)

`git clone --local` of `perf/token-efficiency` → `execute-json-ops.py` → 9/9 operations
succeeded, 0 errors. Then, in that clone:

| DoD command | Result |
|---|---|
| `ruff check src/ tests/ scripts/` | rc=0 |
| `mypy` | `Success: no issues found in 18 source files` |
| `python3 scripts/gen-docs.py --check` | `OK: docs counts are current.` |
| `python3 scripts/gen-registry.py --check` | rc=0 |
| `shellcheck install.sh .claude/hooks/*.sh` | rc=0 |
| `ck doctor` | Agents 29 ✓ · Commands 42 ✓ · Skills 76 ✓ · schema ✓ · 24/27 passed |
| `python3 -m pytest tests/ -q` | 1203 passed, 12 failed |

**The 12 failures are clone artifacts, not regressions — and this was executed, not
reasoned.** I made a second, *unpatched* `git clone --local` of the same commit
(`$SCRATCH/clone0`) and ran the same modules there: the failing node-id set is byte-identical
(`diff` of the sorted `FAILED` lines returns empty). Both control runs were mine; nothing here
rests on inference. The 12:

- `tests/test_ops_enforcement_scope.py` — 11 node ids, including
  `TestOptedInProjectTreatsClaudeAsSource::test_ordinary_source_still_blocked`,
  `::test_over_broad_glob_still_enforces_real_source[.claude/*]`, `…[*]`,
  `TestPlainUserProjectIsUnchanged::test_source_is_still_blocked`,
  `::test_env_var_can_opt_in_without_the_file` (full set reproducible with
  `pytest tests/test_ops_enforcement_scope.py` in any fresh clone).
- `tests/test_hooks_behavioral.py::TestOpsEnforcement::test_direct_source_edit_blocked`.

They depend on the gitignored `.claude/settings.local.json` that no clone carries — **including
CI's**, so the suite cannot pass in a fresh clone today. Pre-existing, orthogonal, recorded as
a follow-up. The real working tree's baseline is **1204 passed, 0 failed**, so the expected
post-merge total there is **1216 passed**. `tests/test_gate_scope.py` alone: **12 passed**.

### The one DoD command expected to fail — and why it already does

`ck doctor --strict` exits **1 both before and after this change**. Cause: three warnings for
empty `project.build_cmd` / `test_cmd` / `lint_cmd` in `.claude/hooks/config.json`, and
`--strict` fails on warnings. This is **pre-existing** (measured on the untouched tree) and
this plan neither causes nor fixes it. **CORRECTION (see `plan-doctor-gate.md`):** the reason
given below for not fixing it is FALSE and the fix has since landed. `install.sh` does *not*
copy this file verbatim - `install.sh:482-501` overwrites the whole `project` section with
language-detected commands on a `--full` install (measured), and that rewrite's failure path
now blanks the section - or aborts the install - rather than leaving this repo's commands
behind. Original, incorrect rationale, kept for the record:
~~`install.sh`
copies `.claude/hooks/config.json` verbatim into user projects, so populating it with
ClaudeKit's own `pytest`/`ruff` commands would ship this repo's build commands to every
user.~~ **Unblocked by:** giving `ck init` a project-local config template, or exempting
"unconfigured project commands" from `--strict`. Neither is in this workstream's ownership.
The non-strict `ck doctor` exits 0, and check counts improve from 23/26 to 24/27.

---

## Testing Strategy

`tests/test_gate_scope.py`, 12 behavioral tests in three classes:

- `TestMypyScope` — the config lists both paths; the gate runs green and reports ≥18 checked
  files (so it demonstrably reaches the ops scripts); a planted type error under the widened
  path turns it red. `pytest.importorskip("mypy")`.
- `TestGenDocsCoversTheCli` — no hand-written count literal survives in `main.py`; `--check`
  is green on the real tree; a stale generated block goes red then green after regeneration;
  a hardcoded prose count goes red; a code count is reported, never auto-rewritten; and
  **deleting the generated block turns the gate red rather than disabling it**.
- `TestDoctorAppliesConfigSchema` — the shipped config satisfies the shipped schema (the
  direct regression test for the 46-day drift); doctor prints `[✓] Hooks config.json matches
  config.schema.json` for a good config and `[✗] … 2 schema violation(s)` for a bad one.
  The assertions key on that verdict line, **not** on the exit code: the skeleton project
  built by `_fake_install` has no agents/commands/skills, so doctor returns 1 there for
  unrelated reasons and an exit-code assertion would prove nothing. The good-config case is
  the explicit GREEN control for the bad-config case, same skeleton.
  `pytest.importorskip("jsonschema")`.

## Rollback Plan

Every operation is a `code_edit` or a `file_create`; the engine writes a timestamped backup
directory (`backups/gate-scope-<ts>/`) and `restore-backup.py` reverts the set. Manually:
`git checkout -- pyproject.toml scripts/gen-docs.py src/claudekit/cli/main.py
config.schema.json .claude/operations/scripts/` and `rm tests/test_gate_scope.py`. No
deletions, no `run_command`, no schema-breaking data migration.

## Risk Assessment

- **Low** — mypy scope widening (annotations only; 26→0 measured). Schema `_note` addition
  (strictly additive). New test module (net-new file, collision-safe name).
- **Low** — `gen-docs.py` change: the README path is untouched and the existing
  `TestHookCountIsTrue` tests continue to pass.
- **Medium** — raising the `ck doctor` floors to the exact shipped inventory. A tree with a
  deliberately trimmed asset set now fails where it previously passed. Note this is already
  true today for `install.sh --minimal`, which installs **zero** skills and therefore already
  fails the old `>= 27` floor; the class of breakage is pre-existing and unchanged in kind.
  Reported, not fixed here (the minimal-profile doctor contract is not this workstream's).
- **Medium** — `main.py` now carries a generator-owned block. If a sibling workstream lands
  a new skill or command before merge, `gen-docs --check` goes red; the fix is one command,
  `python3 scripts/gen-docs.py`. The seeded values (29/42/76) are the generator's own output,
  transcribed verbatim, and the generator owns them from then on.
- **Low** — `jsonschema` absence: the doctor check warns rather than passing or crashing.

## Follow-ups for the owner (out of scope, reported not fixed)

1. **`check_untyped_defs = true`** for the ops-scripts path. Without it the widened mypy gate
   still skips the bodies of unannotated functions there, and the eight `xpipe.py`
   suppressions still hold. This is the residual gap behind Step 1; its cost is unmeasured.
2. **Close `additionalProperties` on the schema's nested objects.** `hooks`, each per-hook
   object, `global`, `project` and `security` accept any key today, so `pre-commit.enabeld`
   or an unknown hook name passes `ck doctor`. Only the root is constrained.
3. **`install.sh` never copies `config.schema.json`** (zero matches for "schema" in the
   script); only `setup.py:54` ships it as a root data file. A tree installed by `install.sh`
   alone therefore gets a permanent `warn` from the new doctor check and so can never pass
   `ck doctor --strict`. Note the degrade is a **visible WARN counted in `checks_warned`**,
   not the validator's cosmetic-warning-with-green-exit pattern — the check announces its own
   absence rather than faking a pass, which is the behaviour we want; the packaging gap is
   the thing to fix.
4. **The suite cannot pass in a fresh clone**, CI's included: 12 tests need the gitignored
   `.claude/settings.local.json` (node ids listed above).
5. `xpipe.py` `state`/`stage` should become `TypedDict`s, retiring all eight suppressions.
6. `install.sh --minimal` installs no skills, so `ck doctor` cannot pass on a minimal tree —
   pre-existing, orthogonal to this plan.
7. `ck doctor --strict` cannot pass in this repo until the empty `project.*_cmd` warnings are
   resolved (see above). Independently confirmed by the reviewer from the exit code.
8. **`DRIFT_FILES` still covers only 5 docs + `main.py`.** A stale component count in any
   other Python source, agent, skill, command or template remains ungated. Scope-correct per
   the triage finding, but not a general solution.
9. `CHANGELOG.md` `[Unreleased]` needs an entry for the three re-scoped gates — that file is
   outside this workstream's ownership.
