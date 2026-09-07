# Implementation Plan: One File Identity For The Parse Gate, Proved By Invariance

## Overview

The ops parse gate has now been fixed three times for one defect class — a plan that names one
file two ways passes the gate and leaves unparseable Python on disk — and each fix closed the
spelling that had been demonstrated and left the next one open. This plan stops patching
spellings. It writes the INVARIANT first, shows it red on the current code for eleven distinct
folds, and only then replaces the identity function with one that satisfies it: the nearest
EXISTING ancestor's `(st_dev, st_ino)` plus the remaining components folded by that device's own
measured rules. Four example-shaped tests that the invariant subsumes are deleted rather than
left beside it.

### Why the fourth round exists (the record)

| Round | Spelling that broke it | Identity it forced |
|---|---|---|
| 1 | `./x.py` vs `x.py` | `os.path.relpath` (`_canon`) |
| 1 | a symlink vs its target | group by `os.path.realpath`, refuse the pair |
| 2 | `x.py` vs `X.py` on a case-insensitive FS | group by `(st_dev, st_ino)` |
| 3 | ANY not-yet-existing path | **this plan** |

Round 3's CRITICAL: an inode can only be read for a path already on disk, so a `file_create`
target falls to a lexical `os.path.realpath` fallback (`ops_precompile.py:162`) — and lexical
identity is exactly what rounds 1 and 2 disproved. Reproduced end to end three ways
(`file_create new.py` + `code_edit New.py`; create through a symlinked directory and edit
through the real one; `file_create sub/n.py` + `code_edit SUB/n.py`): the gate said `ok=True`
"still parses", the executor exited 0 with `Errors: 0`, and the file on disk was left
unparseable. A fourth fold, NFC vs NFD, escaped every round.

## Phase 0: design precheck

The ownership model is TWO KEYS, not one, and every previous round confused them:

* **`_canon` = `os.path.relpath`** is the *writer's* key. It must equal what
  `execute_code_edit` keys its `sim_state` and its backup set on
  (`execute-json-ops.py:684`), because a checker that models a different file identity than
  the writer is the divergence that key exists to close. It is load-bearing and pinned by
  `test_the_canonical_key_is_the_executors_own_function`. **This plan does not touch it.**
* **`_identity` (new)** is the *alias* key. It answers a different question — "do two of this
  plan's keys name ONE file?" — and it must be filesystem truth, which `relpath` is not.

The value of the change sits in `.claude/operations/scripts/ops_precompile.py` (the identity and
the set it is computed over) and in `tests/test_ops_parse_gate.py` (the invariant that keeps it
closed). Both are covered by the ops config. Rejection-brief search:
`review-record.py rejections search "parse gate path identity alias"` — no brief recorded for
this identity class (exit 3); the three prior rounds are recorded in
`.claude/plans/archive/ops-parse-gate-inode-identity/` and in the CHANGELOG `[Unreleased]`
entry this plan amends. Silence is not evidence, so the reproductions were re-run rather than
cited: see the matrix below.

## Scope

* **In scope.** A property test for path-identity invariance; one identity function that
  satisfies it; widening the alias check to every path the config NAMES; deleting the three
  example tests the property subsumes; a CHANGELOG entry.
* **Out of scope.** The 3.9 host-grammar limit (see Follow-up). `_canon`. The executor. The
  `--no-parse-check` flag's blast radius (Follow-up). Any behaviour of the gate other than
  file identity.

## Prerequisites

None. Python 3.9, stdlib only (`unicodedata` is stdlib). Baseline: `tests/test_ops_parse_gate.py`
is 72 passed at `6a7c2fa`.

---

## Step 1 — THE INVARIANT FIRST (and it is red before the fix)

* **File:** `tests/test_ops_parse_gate.py` — Modify (append a section; add `import unicodedata`).
* **What.** `_fold_tree()` builds ONE tree holding every alias shape and returns
  `{fold: (spelling_a, spelling_b, skip_reason_or_None)}`. Two parametrised tests run over the
  same 17 folds: `test_the_identity_is_invariant_under_every_alias_spelling` asserts
  `gate._identity(a) == gate._identity(b)`, and
  `test_every_alias_spelling_is_refused_by_the_gate_not_half_checked` carries the invariant
  through to the verdict the executor consumes. Every fold is covered for BOTH an existing
  path and a not-yet-existing one.
* **A fold the filesystem does not perform SKIPS with its reason.** On a case-sensitive
  filesystem `x.py` and `X.py` really are two files and collapsing them would be the bug; on a
  platform without symlinks the link rows have nothing to assert. A row that went green on
  every filesystem would not be testing identity at all.

### Failing-first evidence, measured on this machine (APFS: case-folding, NFC-normalising, symlinks and hardlinks available)

Each column is the identity that round's fix shipped. `RED` = the two spellings got two
identities, which is the hole.

| fold | r1 `relpath` | r2 `realpath` | r3 inode-or-realpath (**current code**) | this plan |
|---|---|---|---|---|
| case-existing-file | RED | RED | same | same |
| case-existing-dir | RED | RED | same | same |
| **case-new-file** | RED | RED | **RED** | same |
| **case-new-dir** | RED | RED | **RED** | same |
| nfc-nfd-existing | RED | RED | same | same |
| **nfc-nfd-new** | RED | RED | **RED** | same |
| symlink-file | RED | same | same | same |
| symlink-dir-existing | RED | same | same | same |
| symlink-dir-new | RED | same | same | same |
| dangling-link-vs-target | RED | same | same | same |
| hardlink | RED | RED | same | same |
| lexical-dot-slash / double-slash / dotdot / trailing-slash / new-dot-slash | same | same | same | same |
| lexical-abs-vs-rel (under a symlinked cwd) | RED | same | same | same |

**Which folds fired vs skipped on this machine:** all 17 fired at identity level — nothing
skipped, because APFS folds case AND normalises unicode, and both symlinks and hardlinks are
available. At gate level one row skips by design (`lexical-trailing-slash`, whose pair is a
DIRECTORY and so is not an ops target); it remains an identity-level row. Post-state run:
**107 passed, 1 skipped**.

The three `RED` rows in the current column are the round-3 hole. The lexical rows are green in
every column because `_canon` collapses them before `_aliases` is reached — which is why the
gate-level test asserts, for exactly those rows, that the plan was modelled ONCE rather than
refused. Demanding a refusal there would be demanding a false positive.

## Step 2 — one identity function that satisfies the invariant

* **File:** `.claude/operations/scripts/ops_precompile.py` — Modify.
* **What.** Add `_CASE_FOLD`, `_case_insensitive`, `_fold`, `_identity`; rewrite `_aliases` to
  group on `_identity`. `_identity` resolves symlinks (`realpath`), walks up to the nearest
  ancestor that stats, keys it `('ino', st_dev, st_ino)`, and appends each not-yet-existing
  component through `_fold`.

### Verdict on the reviewer's prescription: adopt, with two corrections

The prescription is right and it is the only shape that can work — an inode is the only
identity the kernel will vouch for, and the components below it must be compared the way that
device compares them. Two corrections, both measured:

1. **`os.path.realpath` FIRST, not instead.** The prescription's ancestor walk alone regresses
   a pair the current code gets right: a DANGLING symlink `sym.py` plus a `file_create` of the
   `pkg/m.py` it points at. Round 3's code catches that via realpath; a bare ancestor walk keys
   `sym.py` under its parent inode and `pkg/m.py` under `pkg`'s, and they diverge. Resolving
   first keeps it (row `dangling-link-vs-target` above), and realpath also resolves a symlinked
   directory *in the middle* of the path.
2. **The probe must not write.** See below.

**How case-insensitivity is probed without leaving a stray file.** Take an ancestor that already
exists, swap the case of *that ancestor's own name*, and stat it: the same `(st_dev, st_ino)`
back means the kernel folded the two spellings. Nothing is created, so nothing has to be
cleaned up, and the directory does not need to be writable — a `mkstemp` probe answers the same
question but drops a file into the author's checkout in the middle of a read-only check, where
this repo's own secret self-scan and queued-ops gate read the working tree. Pinned by
`test_the_case_probe_writes_nothing_into_the_tree`.

**Probe-failure direction: fail toward COLLAPSING.** When no ancestor name carries a cased
letter (`/`, a numeric-only path) or the walk cannot stat, the answer given is `True`
(case-insensitive). The two errors are not symmetric. Collapsing wrongly costs a **false
refusal** — loud, printed as `ALIAS`, and fixed by naming the file once by one path. Staying
distinct wrongly reopens **exactly the hole this function exists to close**: gate exit 0,
`Errors: 0`, unparseable Python on disk, which is the silent failure the whole module exists to
prevent. The quiet error is the unsafe one, so the probe fails toward the loud one. The
over-refusal cost of that choice is not asserted, it is measured — see Evidence.

The same argument fixes NFC: `unicodedata.normalize('NFC', ...)` is applied **always**, not
probed. macOS normalises stored names, so NFC and NFD are one file there; a filesystem that
does not normalise makes them two, and folding them there is a false refusal in the loud
direction. Probing normalisation the way case is probed is not possible without writing,
because it needs an existing name whose own spelling is decomposable.

**Cache the probe per `st_dev`, for the run.** Case sensitivity is a property of the MOUNT, not
of the OS — APFS folds, ext4 does not, and one checkout can span both — so it can be neither a
constant nor `sys.platform`, and `st_dev` is the correct granularity. Cached because otherwise
the gate re-probes for every path in the plan. Pinned by
`test_the_case_probe_is_taken_once_per_device` (cold run costs strictly more `os.stat` calls
than the warm one; the cache holds exactly one entry, keyed by the device).

**When no ancestor exists at all** — an absolute path on a device that is not mounted, or a root
that cannot be stat'd — the walk reaches a fixed point at the root and there is no inode to
anchor to. It degrades to a lexical key, but a **folded** one, so the case and normalisation
aliases still collapse instead of reopening the hole. Nothing can be written to such a path
either, so the executor fails on it a moment later. **A path escaping the project root** still
gets a real identity, because the key is absolute: `../other/x.py` is a file like any other
here. Whether the plan is ALLOWED to write there is a different gate's question and the
executor's path guard answers it; conflating the two would make this function refuse for the
wrong reason.

**This replaces the `_aliases` grouping only, NOT `_canon`.** See Phase 0. `test_the_two_keys_are_not_one_key`
states the design as an assertion so a future round cannot quietly merge them.

### Step 2b — the alias check must read every path the config NAMES

The identity is worth nothing if the refusal does not follow, and the follow-through had its own
hole: `simulate` records a `code_edit` of a not-yet-existing spelling as a MISS and `continue`s,
so that path entered none of `files` / `created` / `deleted` and the alias check **never saw
it**. That is precisely the round-3 reproduction shape (`file_create new.py` + `code_edit
New.py`): the second spelling is unmodellable *because* it is an alias. So `simulate` returns a
fifth value, `named` — every path any path-bearing operation names — and `check` groups over
`named | set(files) | deleted | created`. The union keeps the set from shrinking if `named` is
ever narrowed. The `sorted(...)` over alias groups gains `key=repr`, because identity tuples are
no longer homogeneous (`('lex', ...)` vs `('ino', int, int, str)`) and comparing them directly
raises `TypeError`.

## Step 3 — retire what the invariant subsumes

* **File:** `tests/test_ops_parse_gate.py` — Modify (delete three functions).
* **Deleted**, because each is one row of the parametrised matrix and the matrix asserts more:
  * `test_one_file_named_in_two_cases_is_refused_not_half_checked` → rows
    `case-existing-file` / `case-existing-dir`, whose gate-level test carries the same
    `names one file (` / no-bare-inode message assertions verbatim.
  * `test_a_hardlinked_pair_is_refused_too` → row `hardlink`.
  * `test_distinct_files_and_new_files_are_never_called_aliases` →
    `test_the_identity_keeps_genuinely_distinct_paths_distinct` plus
    `test_the_gate_still_passes_a_plan_of_distinct_and_new_files`, which assert the same
    over-refusal direction at both levels.
* **Kept deliberately:** `test_the_canonical_key_is_the_executors_own_function` (the `_canon`
  ↔ executor parity pin — load-bearing, and the one thing this plan must NOT change);
  `test_a_symlink_alias_is_refused_because_neither_side_models_it` and its executor twin (the
  only end-to-end proof that the refusal stops the writer, and the twin's docstring
  cross-references it); `test_deleting_a_target_and_editing_its_link_is_refused` (it pins the
  alias check's INPUT SET, not the identity, which is a different claim);
  `test_a_dot_slash_alias_is_one_file_to_the_gate_as_it_is_to_the_executor` and its twin (they
  pin `_canon`, not `_identity`).

## Step 4 — CHANGELOG

* **File:** `CHANGELOG.md` — Modify. A new bullet under `[Unreleased]`, directly after the
  existing inode-identity bullet, stating the not-yet-existing-path hole, the fix, and that the
  property rather than any one spelling is now what is pinned.

---

## Paths this ops config writes

Exactly three, all `code_edit`:

1. `.claude/operations/scripts/ops_precompile.py`
2. `tests/test_ops_parse_gate.py`
3. `CHANGELOG.md`

No file is created, deleted, renamed, or moved; no `run_command` operation is used.

## Evidence: the over-refusal proof that must not regress

The reviewer swept 601 real archived ops configs through the alias check and got zero false
flags. **Re-run against this design, with the patched module: 601 configs read, 0 flagged**
(identical to the current code's 0, and to a pre-change control run). The probe measured this
device as case-insensitive (`{16777233: True}`), so the sweep exercised the *collapsing*
direction — the pessimistic one — and still refused nothing. Command recorded in Testing below.

Post-state proofs, all run against a scratch copy of the patched tree (nothing in the worktree
was modified by this planning pass):

* `tests/test_ops_parse_gate.py`: **107 passed, 1 skipped** (baseline 72 passed).
* `ruff check --line-length 100` on both patched files: clean.
* `ast.parse` on both patched files: clean.
* Every `find` anchor verified unique with `str.count(...) == 1` (never `grep -c`).
* `validate-config-json.py`: **APPROVED**.

## Testing Strategy — per behaviour, the mutation that reds it

| Behaviour | Test | Mutation that reds it |
|---|---|---|
| **Headline.** Identity is invariant under every fold | `test_the_identity_is_invariant_under_every_alias_spelling` | Revert `_identity` to round 3's lexical fallback (`return ('path', os.path.realpath(p))` for anything not on disk, inode otherwise) → reds **`case-new-file`, `case-new-dir`, `nfc-nfd-new`** — three rows, not one. Revert further to `realpath` only (round 2's identity) → reds **seven** rows: those three plus `case-existing-file`, `case-existing-dir`, `nfc-nfd-existing`, `hardlink`. Revert to `relpath` only (round 1's) → reds **twelve**. That escalation is the point of a property: one mutation, every fold it breaks, named at once. |
| NFC folding | same test, rows `nfc-nfd-*` | Drop `unicodedata.normalize` from `_fold` → both rows red |
| Symlink resolution is not subsumed by the ancestor walk | same test, rows `symlink-dir-*`, `dangling-link-vs-target` | Drop `os.path.realpath` from `_identity`'s first line → three rows red |
| Case folding is per device, not per platform | same test, `case-*` rows | Hardcode `case_insensitive = False` → four rows red; hardcode `True` → the distinct-paths test reds on a case-sensitive host |
| Over-refusal (identity level) | `test_the_identity_keeps_genuinely_distinct_paths_distinct` | Return a constant for any path that cannot be stat'd → the two new-file rows red |
| Over-refusal (verdict level) | `test_the_gate_still_passes_a_plan_of_distinct_and_new_files` | Fold every not-yet-existing path to one key → the two `file_create`s become an ALIAS group and every ordinary two-file plan is refused |
| The refusal follows the identity | `test_every_alias_spelling_is_refused_by_the_gate_not_half_checked` | Remove the `_aliases` loop from `check` → every row reds |
| Alias detection reads NAMED paths | same test, `case-new-*` / `nfc-nfd-new` rows | Pass `set(files) \| deleted \| created` to `_aliases` instead of `named` → the rows whose second spelling is a modelled-away miss red |
| The message names a path, not an inode | same test | Print the group key instead of `realpath(_keys[0])` → the no-bare-inode regex reds |
| The probe leaves no file behind | `test_the_case_probe_writes_nothing_into_the_tree` | Probe with `tempfile.mkstemp(dir=...)` and skip the unlink → red |
| The probe is cached per device | `test_the_case_probe_is_taken_once_per_device` | Drop `_CASE_FOLD` → the warm run costs the same as the cold one → red |
| Two keys stay two | `test_the_two_keys_are_not_one_key` | Make `_canon` return `_identity(path)` → the executor-parity test reds; group `_aliases` on `_canon` → every fold row reds |
| `_canon` still equals the executor's key | `test_the_canonical_key_is_the_executors_own_function` (**unchanged**) | Any change to `_canon` |
| `simulate`'s new arity | `test_the_gate_normaliser_agrees_with_the_executors` and the existing 5-tuple unpack at line 585 | Forget the fifth return value → `ValueError` at every call site |

**Commands** (this workstream never runs the full suite):

```bash
ECC_HOOK_PROFILE=minimal python3 -m pytest tests/test_ops_parse_gate.py -q
ruff check .claude/operations/scripts/ops_precompile.py tests/test_ops_parse_gate.py
python3 .claude/operations/scripts/validate-config-json.py \
  .claude/plans/plan-parse-gate-fold-invariance.ops.json
python3 scripts/check-plan-artifacts.py --check
# the over-refusal sweep, re-run after the change:
python3 - <<'EOF'
import json, glob, importlib.util
spec = importlib.util.spec_from_file_location(
    'g', '.claude/operations/scripts/ops_precompile.py')
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
n = flagged = 0
for f in sorted(glob.glob('.claude/plans/archive/**/*.json', recursive=True)):
    cfg = json.load(open(f))
    if not isinstance(cfg, dict):
        continue
    n += 1
    paths = {g._canon(o['path']) for o in (cfg.get('operations') or [])
             if isinstance(o.get('path'), str) and o['path']}
    paths |= {g._canon(o['path']) for o in (cfg.get('files') or [])
              if isinstance(o, dict) and isinstance(o.get('path'), str) and o['path']}
    if g._aliases(paths):
        flagged += 1
        print('FLAGGED', f)
print('configs:', n, 'flagged:', flagged)
EOF
```

A design that refuses even one real archived config is wrong; the required output is
`configs: 601 flagged: 0`.

## Rollback

Every operation is a `code_edit` on a tracked file, so the whole change is one revert:

```bash
git checkout -- .claude/operations/scripts/ops_precompile.py \
                tests/test_ops_parse_gate.py CHANGELOG.md
```

If the change is already committed: `git revert <sha>`. The engine's own backup set covers the
same three files (restorable with `restore-backup.py`). Nothing is deleted, no file is created,
no schema or on-disk format changes, so a rollback needs no migration. The three deleted test
functions come back with the revert. **Partial rollback is not safe:** reverting
`ops_precompile.py` alone leaves the new tests referencing `_identity` and `_CASE_FOLD`, and
reverting the test file alone leaves the five-value `simulate` unpacked in four places. Revert
all three or none.

## Risk Assessment

* **Low.** The CHANGELOG edit. The three test deletions (each claim is re-asserted by a named
  replacement). `_canon` and the executor are untouched, so the writer-parity pin cannot move.
* **Medium — over-refusal.** Always-NFC and probe-failure-collapses both refuse more than
  strictly necessary, by design. Bounded by measurement: 601 archived configs, 0 flagged, in
  the collapsing direction. The residual case is a repo that deliberately keeps two files
  differing only by case or by unicode normalisation *and* names both in one plan; that plan
  gets a loud `ALIAS` refusal telling it to name the file once. Accepted, and stated in the
  function's docstring rather than left for a fourth reviewer to discover.
* **Medium — blast radius.** `simulate`'s return arity changes, which touches `check` and one
  test call site; both are in this config. `grep -rn "simulate("` over
  `.claude/operations/scripts`, `tests`, `src` finds exactly those two callers, so there is no
  third. `ops_precompile.py` is called by `execute-json-ops.py` on the dry-run AND execute
  paths, so a defect here fails every ops run closed — loudly, never silently, which is the
  correct direction for this module.
* **Medium — the probe stats a case-swapped sibling.** On a case-sensitive filesystem that
  `stat` raises `ENOENT` and is caught; it never writes and never follows a symlink it did not
  already resolve. Worst case is one extra failed `stat` per device per run.
* **Not a risk here.** `.claude/project-graph.json` is absent in this worktree
  (`project-graph.py` exits 3), so no hub/GOD-NODE analysis applies.

## Follow-up (record only — do NOT fix here)

Round 3 recommends **shipping** the 3.9 host-grammar limit: `ast.parse` uses the interpreter the
gate runs on, so on this repo's 3.9 floor a plan adding a valid `match` statement is refused as
`invalid syntax`. The refusal fails closed and the message names the interpreter, which is the
honest behaviour, and there is no stdlib way to parse a grammar newer than the running one. The
real defect is downstream of it: the only escape is `--no-parse-check`, which blinds the gate to
**every** file in the plan in order to excuse **one**. That is the same shape as the alias hole —
a global opt-out purchased for a local problem — and it is how a genuine break gets waved
through. Either a per-file opt-out (the config names the file whose grammar the host cannot
read, and every other file is still checked) or parsing with the project's declared floor
(`requires-python`, via `feature_version`, which lowers the grammar and so at least makes the
limit explicit and per-project) would fix both. Not in scope; no code in this plan.
