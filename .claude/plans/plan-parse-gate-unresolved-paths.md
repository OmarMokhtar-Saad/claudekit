# Implementation Plan: the parse gate must recover a miss's path as data, not by re-splitting a string

## Overview

`ops_precompile.py::check` rebuilds the set of files whose parse verdict must be withheld by
re-parsing its own rendered output: `unresolved = {m.split(':', 1)[0] for m in misses}`. A colon
is legal in a filename on macOS and on Linux, so that split can recover the WRONG key — and when
the wrong key names another file the same plan genuinely breaks, the gate prints `not checked`
instead of `BREAK` and returns `ok=True`. Proven by execution below. The fix is to carry
`(path, reason)` pairs in `misses` and render once, at the point of output.

This is the engine the Iron Law routes all implementation through, and the defect is a *silent
pass in a gate* — the exact failure mode `ops_precompile.py`'s own docstring says it exists to
prevent. Tier 3 by surface, though the diff is small and local.

## Design precheck (ownership / data model)

The data model this change assumes: a miss is a **pair** — the file it is about, and why. The
current model flattens that pair into one presentation string at the moment of recording and then
asks a consumer forty lines later to un-flatten it. The un-flattening is not decidable, because
the delimiter (`:`) also occurs inside both halves. Every miss is produced in exactly two
functions (`_apply`, `simulate`) and consumed in exactly one (`check`), all in one file, so the
model change is closed over `.claude/operations/scripts/ops_precompile.py`; the value of the
change is carried by that file plus its behavioural pins in `tests/test_ops_parse_gate.py`.

Rejection-brief search (mandatory):

```
$ python3 .claude/operations/scripts/review-record.py rejections search "parse gate miss path colon split"
REJECTIONS: 12 match(es) for 'parse gate miss path colon split'   (exit 0)
```

Twelve hits, all keyword coincidences on `gate`/`path`/`split` except **one that validates
against this plan**: `.claude/knowledge/rejections/e2e-lane-a.md`, round -1, CONDITIONAL 87 —
`[MAJOR] Mutation-proof overclaim. plan-e2e-lane-a.md:145-159 states each mutant was applied and
"the suite re-run" ... That is [not evidenced]`. Re-read the brief and confirmed the shape: a plan
asserting mutation results it had not run. That is the single most likely way this plan fails,
because its whole argument rests on mutation proofs.

What this plan does differently: every mutation in the Testing Strategy table was actually
applied to a scratch copy of the post-state and `pytest` was actually run, and the plan records
the observed verdict per mutation plus the pass counts and the exact `FAILED ::` test names (see
Testing Strategy). No mutation is listed whose run is not reported. The remaining briefs
(`agent-memory-learning`, `fleet-a2b-d1-d3`, `iron-law-enforcement-hook`,
`e2e-pipeline-test-task`) concern unrelated assets — hook counts, licence files, a `run_command`
allowlist, a stale case count — and none of their findings has a surface in these three files.
Briefs are PRIORS, not proofs; a miss would have meant unknown, not clear.

## What was proved by execution (not by reasoning)

Every `misses.append(...)` format string in the module today:

| site | format |
|---|---|
| `_apply` :59 | `'%s: edit has no find pattern' % path` |
| `_apply` :63 | `'%s: anchor not found: %r' % (path, find[:60])` |
| `_apply` :66 | `'%s: anchor is ambiguous — it appears %d times, ... : %r' % (path, seen, find[:60])` |
| `_apply` :85 | `'%s: edit names no action (replace/add_after/add_before/delete)' % path` |
| `simulate` :114 | `'%s: no such file to edit' % path` (LEGACY `files:` schema) |
| `simulate` :128 | `'%s: file_create has no content key (the executor would KeyError on it)' % path` |
| `simulate` :144 | `'%s: edited after this same plan deletes it' % path` |
| `simulate` :147 | `'%s: no such file to edit' % path` (MODERN `operations:` schema) |

**Case 1 — a path containing a colon: MISATTRIBUTES, in both directions.**
`a:b.py` with a missing anchor yields `unresolved == {'a'}` while `files` holds `'a:b.py'`:

```
=== CASE1 colon-in-path, anchor missing ===
  misses: ["a:b.py: anchor not found: 'nowhere'"]
  unresolved keys: ['a']
  files keys: ['a:b.py']
  ok: True
   | MISS  a:b.py: anchor not found: 'nowhere'
   | OK    a:b.py still parses after the edits in this plan
```

- *Direction A — the colon-bearing path falls OUT of `unresolved`:* it is over-checked. The gate
  prints `OK ... still parses` about a file whose anchor never landed. That line is a false
  claim (the text modelled is the on-disk text, not the executor's result) but it cannot hide a
  break in that file, because the breaking edit was never applied to it. **Over-checking, plus a
  reporting lie.**
- *Direction B — the truncated prefix falls wrongly IN `unresolved`:* the file actually named by
  the prefix is silently skipped. **This is the hole**, and it is a refusal turned into a pass:

```
=== HOLE: 'mod.py:v1' miss hides a real BREAK in 'mod.py' ===
  on disk: ['mod.py', 'mod.py:v1', 'ops.json']
  misses: ["mod.py:v1: anchor not found: 'nowhere'"]
  unresolved: ['mod.py']
  ok: True
   | MISS  mod.py:v1: anchor not found: 'nowhere'
   | ?     mod.py not checked — an anchor above did not land, so the text this would parse is not the text the executor would write
   | skip  mod.py:v1 (not Python — this check has nothing to say about it)

=== CONTROL: same break, no colon path ===
  ok: False
   | BREAK mod.py: f-string: expecting '}' at line 2
```

Same breaking edit; `ok: True` with the colon path present, `ok: False` without it. The colon
filename was really created on disk (`ls` line above), so the case is reachable on this OS.

**Case 2 — a reason string containing a colon: does NOT misattribute.** `split(':', 1)` takes the
*first* colon, and every format string above puts the path before it, so colons inside the reason
(`anchor not found: %r`, and the ambiguity reason's two) are never reached:

```
=== CASE2 reason contains a colon ===
  misses: ["p.py: anchor not found: 'nowhere'"]
  unresolved keys: ['p.py']        <- correct
```

No fix is needed for this case. It is nevertheless pinned, because the refactor moves the
rendering and could regress it.

**Case 3 — a miss whose prefix is not a path: UNREACHABLE as a misattribution.** All eight sites
interpolate `path` first, so the only way to get a non-path prefix is `path is None` (an operation
with no `path` key). Executed: the `code_edit` branch raises before recording anything —

```
TypeError: stat: path should be string, bytes, os.PathLike or integer, not NoneType
  (ops_precompile.py:146, os.path.exists(path))
```

— and the `file_create` branch records the literal prefix `None`, which matches nothing in
`files` and misattributes nothing:

```
=== path-absent file_create ===
  misses: ['None: file_create has no content key (the executor would KeyError on it)']
  unresolved: ['None']
  files keys: []
  ok: True   | note  this ops.json writes no files — nothing to parse
```

`validate-config-json.py` rejects a pathless writing operation upstream, and
`check-plan-artifacts.py:221-226` refuses one independently. **No fix and no test is planned for
case 3** — a fix for an unreachable case is dead code. The tuple refactor removes the class of
defect anyway, as a side effect and not as a claim.

**Blast radius, stated honestly.** End-to-end, every miss kind the gate records is *also* refused
by `execute_code_edit` (`missing-find-pattern`, `pattern-not-found`, `ambiguous-pattern`,
`no-action-specified`, `execute-json-ops.py:749-796`), and the executor breaks out of its
operation loop and calls `txn.rollback()` on the first failure (`:1253-1261`). So the proven
consequence is **a false verdict from the gate**, not "a broken file lands silently": the gate is
documented as a standalone command (`python3 ops_precompile.py <ops.json>` — "exit 0 = every
touched .py still parses") and as the defence-in-depth layer that runs in `--dry-run`, and in both
of those roles `ok=True` on a plan whose result does not compile is a flat lie. That is worth
fixing on its own terms; it is not worth overstating.

## Consumers of `misses` (every one, from `grep -rn "misses" .claude/operations/scripts/ tests/`)

- `ops_precompile.py::_apply` — producer (4 appends); receives the list as a parameter.
- `ops_precompile.py::simulate` — producer (4 appends); creates the list and returns it as the
  second element of its 3-tuple.
- `ops_precompile.py::check:299` — sole consumer: unpacks the 3-tuple, renders each entry at
  `:318-319` (`'MISS  %s' % miss`), and derives `unresolved` at `:324`.
- `execute-json-ops.py::check_parses:1006` — calls `module.check(config_file)` only. It never
  touches `misses` or `simulate`, so its contract is unaffected.
- `tests/test_ops_parse_gate.py` — drives `gate.check(...)` in all 49 existing tests; asserts on
  the rendered text only (`"MISS" in blob`, `"ambiguous" in line`, `"no find pattern" in line`,
  `"no content key" in line`, `"deletes it" in line`, `"not checked" in blob`). No existing test
  reads `misses` or calls `simulate`.
- `tests/test_ops_hardening.py:246` — copies `ops_precompile.py` verbatim into a tmp tree; content-
  agnostic.
- Every other `grep` hit for `misses`/`unresolved` in the repo is an unrelated identifier
  (`review-record.py`, `check-plan-artifacts.py`, `src/claudekit/**`) or English prose.

Conclusion: `simulate`'s second value is consumed in exactly one place, so changing its element
type from `str` to `Tuple[str, str]` is safe, and **no existing assertion has to change** because
the rendered output is preserved byte-for-byte.

## Scope

- **In scope:** the `misses` element type in `ops_precompile.py`; the two lines in `check` that
  render and un-parse it; behavioural pins in `tests/test_ops_parse_gate.py`; a CHANGELOG bullet
  inside the existing (unreleased) parse-gate entry.
- **Out of scope:** the `path is None` crash (case 3, unreachable — see above); the
  Direction-A `OK ... still parses` line for a file with a *non-colon* path and a missed anchor
  (there is none: without a colon the key is exact); any change to what the gate refuses vs
  reports; any change to `execute-json-ops.py`.

## Prerequisites

None. The change is confined to files already on this branch (`96fdc08`).

## Implementation Steps

### Step 1: carry the pair in `_apply`
- **File:** `.claude/operations/scripts/ops_precompile.py`
- **Action:** Modify
- **Details:** Four `misses.append('%s: ...' % path)` calls become
  `misses.append((path, '...'))`, with the `'%s: '` prefix removed from each reason. The
  ambiguity reason keeps its `%d`/`%r` interpolation, now over `(seen, find[:60])`.

### Step 2: carry the pair in `simulate`, and say why in its docstring
- **File:** `.claude/operations/scripts/ops_precompile.py`
- **Action:** Modify
- **Details:** The remaining four appends (legacy no-such-file, `file_create` without content,
  edit-after-delete, modern no-such-file) become tuples. The docstring's return description
  becomes `[(path, reason) misses]` and gains a paragraph naming the colon hazard, so the next
  reader does not re-flatten it.

### Step 3: render once, and stop re-parsing
- **File:** `.claude/operations/scripts/ops_precompile.py`
- **Action:** Modify
- **Details:** `for miss in misses: out.append('MISS  %s' % miss)` becomes
  `for miss_path, miss_reason in misses: out.append('MISS  %s: %s' % (miss_path, miss_reason))`
  — identical output. `unresolved = {m.split(':', 1)[0] for m in misses}` becomes
  `{miss_path for miss_path, _ in misses}`, with a comment recording the measured
  refusal-into-pass so the split is not reintroduced.

### Step 4: pin it, in both directions
- **File:** `tests/test_ops_parse_gate.py`
- **Action:** Modify (append a new section at end of file)
- **Details:** Five tests, listed under Testing Strategy with the mutation that reddens each.

### Step 5: record it
- **File:** `CHANGELOG.md`
- **Action:** Modify
- **Details:** A third bullet inside the existing `[Unreleased]` parse-gate entry (the gate has
  not shipped, so this belongs in that entry rather than in a separate `Fixed` section).

## Paths this ops.json writes

Exactly three, all `code_edit`:

1. `.claude/operations/scripts/ops_precompile.py`
2. `tests/test_ops_parse_gate.py`
3. `CHANGELOG.md`

No file is created, deleted, renamed, or moved. No `run_command` operation.

## Testing Strategy

New tests, appended to `tests/test_ops_parse_gate.py`. Each names the mutation that turns it red;
each mutation below was **executed** against the post-state and observed to fail.

| test | behaviour pinned | mutation that reddens it | observed |
|---|---|---|---|
| `test_a_colon_in_one_path_does_not_hide_a_break_in_another` | Direction B, the hole: a miss on `mod.py:v1` must not withhold the verdict for `mod.py`, which this plan breaks. Asserts `ok is False` and `BREAK mod.py:`. | restore `unresolved = {m.split(':', 1)[0] for m in misses}` | FAILED |
| `test_the_withheld_verdict_lands_on_the_path_that_missed` | Direction A: `a:b.py` (missed) gets `? ... not checked`, its clean sibling `a.py` gets `OK`. | same revert (`a:b.py` then falls out of `unresolved` and is wrongly reported `OK ... still parses`) | FAILED |
| `test_simulate_carries_the_path_as_data_not_a_formatted_string` | the `simulate` contract: `misses[i][0]` is the path itself, colons included. | same revert (the 2-tuple unpacking raises `ValueError: too many values to unpack`) | FAILED |
| `test_the_miss_line_text_is_unchanged_by_the_structured_record` | output preservation: the exact line `MISS  target.py: anchor not found: 'nowhere at all'`. | render the tuple instead of the pair (`out.append('MISS  %s' % ((miss_path, miss_reason),))`) | FAILED |
| `test_a_reason_with_colons_of_its_own_still_names_the_right_path` | case 2: a reason carrying its own colons still names its path, in the right order. | swap the append to `(reason, path)` | FAILED |

The last two are green on a plain revert by construction — a revert does not change the rendered
text, which is the point of preserving it — so their mutation is a rendering mutation, stated
above and executed. The swap mutation also reddens the pre-existing
`test_an_ambiguous_anchor_alone_does_not_fail_the_gate`, which is additional evidence rather than
a substitute.

No existing test changes. The rendered output is byte-identical (`'MISS  %s' % ('%s: %s' %
(path, reason))` and `'MISS  %s: %s' % (path, reason)` produce the same string), and the executor
only calls `check`.

**Verification already run against the post-state** (edits applied in memory via
`ops_precompile.simulate`, written to a scratch tree, never to the worktree):

```
$ python3 -m pytest <scratch>/tests/test_ops_parse_gate.py -q
54 passed in 0.49s                       # 49 existing + 5 new

$ ruff check --line-length 100 --target-version py39 <scratch post-state>
All checks passed!

$ python3 .claude/operations/scripts/ops_precompile.py plan-parse-gate-unresolved-paths.ops.json
OK    .claude/operations/scripts/ops_precompile.py still parses after the edits in this plan
skip  CHANGELOG.md (not Python — this check has nothing to say about it)
OK    tests/test_ops_parse_gate.py still parses after the edits in this plan
```

Commands to run after execution: `python3 -m pytest tests/test_ops_parse_gate.py
tests/test_ops_hardening.py tests/test_check_plan_artifacts.py -q`, then `ruff check`, `mypy`,
`python3 scripts/check-plan-artifacts.py --check`, then the full suite.

## Post-review correction (Tier 1, `--no-approval`, after the APPROVED 96 record)

`plan-parse-gate-unresolved-paths-citation.ops.json` fixes the reviewer's one MINOR — the
`check-plan-artifacts.py` guard citation was off by one line. It writes only
`.claude/plans/plan-parse-gate-unresolved-paths.md`.

## Rollback

- **Before execution:** delete `.claude/plans/plan-parse-gate-unresolved-paths.md` and
  `.claude/plans/plan-parse-gate-unresolved-paths.ops.json`. Nothing else has been touched.
- **During execution:** the executor's own transaction covers it — a failed operation triggers
  `txn.rollback()` and the pre-run backup manifest under `.claude/backups/` restores every file
  in the plan (`restore-backup.py`).
- **After execution, uncommitted:** `git checkout -- .claude/operations/scripts/ops_precompile.py
  tests/test_ops_parse_gate.py CHANGELOG.md` in the worktree
  `/Users/omarmokhtar/IdeaProjects/.ck-agent-memory-wt`.
- **After commit:** `git revert <sha>`. The change is three `code_edit`s in one commit with no
  schema, interface, or on-disk-format consequence — `check` keeps its `(ok, lines)` signature and
  its exact output text, so a revert restores the prior behaviour (including the defect) with no
  migration.
- **Partial rollback is safe in one direction only:** reverting `ops_precompile.py` alone leaves
  three new tests red, which is the intended signal. Reverting the tests alone silently restores
  the hole's cover, so do not do that.

## Risk Assessment

- **Low:** output text is preserved byte-for-byte, so no existing assertion or consumer moves;
  `misses` never leaves the module; `ruff`/`mypy` clean on the post-state; py3.9-safe (tuples,
  `%`-formatting, no new imports, stdlib only).
- **Medium:** this is `.claude/operations/scripts/`, the engine the Iron Law routes all
  implementation through, and the file is a **gate** — a mistake here is a mistake in the thing
  that catches mistakes. Mitigated by 54 behavioural tests over the post-state and by five
  executed mutation proofs. Also medium: `simulate`'s public-ish return type changes element type;
  every in-repo caller was enumerated above, but an out-of-repo caller (a kitted downstream
  project that imported `simulate` rather than `check`) would break. The gate is new on this
  branch and unreleased, so no downstream can yet depend on it.
- **High:** none. No deletions, no renames, no protected files, no `run_command`, no version bump,
  no generator-owned counts.
- **Project graph:** `.claude/project-graph.json` is absent in this worktree (exit 3 — no graph),
  so no hub/GOD-NODE analysis is available. Standing in for it: the only inbound edge to
  `ops_precompile.py` is `execute-json-ops.py::check_parses`, which imports the module by path and
  calls `check` alone — read directly and reported above rather than inferred.
