# Implementation Plan: close the parse gate's divergence from the executor

PR #37 (`fix/parse-gate-ordering`) was REJECTED at 60/100 by adversarial code review. Both
Criticals are the same defect wearing two hats: **`ops_precompile.py` models a different plan
than `execute-json-ops.py` runs.** A gate that models the wrong plan is worse than no gate,
because it prints a true sentence about a file that will never exist and exits 0.

## Overview

Give the gate the executor's *own* path identity and the executor's *own* normalised config,
refuse the one aliasing case neither side can model, and stop four verdict lines from claiming
more than they know. Every fix carries a behavioural pin with a stated mutation.

## Phase 0 — design precheck

The ownership model this change assumes: **the executor owns both the schema and the file
identity; the gate is a leaf that models what the executor will do.** Today the gate re-derives
both independently, and it is exactly at those two re-derivations that the value leaks. So the
fix direction is one-way: the executor hands its normalised config *down* to the gate, and the
gate adopts `os.path.relpath` because that is the function the executor keys on — not because
it is the best canonicaliser. The files that carry the value are the gate, the executor's
`check_parses` seam, and the test file that pins the pair against each other; all three are in
the ops config.

Rejection-brief search (mandatory): `review-record.py rejections search "parse gate path
identity normalize divergence"` → **exit 0, 11 matches**. These are priors, not proofs, and I
re-read the files rather than the briefs. The one validated match is
`.claude/knowledge/rejections/e2e-lane-a.md` (CONDITIONAL 87), whose lead MAJOR is a
**mutation-proof overclaim**: a plan asserted each mutant was applied and the suite re-run,
and it had not been. That is precisely the shape of the Tests section below, so what this plan
does differently is stated plainly: every one of the 14 mutations in the table was **executed**
against the post-state in a scratch copy at `/private/tmp/pg-verify`, each with a named test
selector, and the observed red/green result is recorded per row — including the one row where
the mutation I first wrote did **not** turn the test red (the `./x.py` end-to-end case, which
`_aliases` also catches), which is why that row names the combined mutation instead of
pretending. The second-nearest match (`iron-law-enforcement-hook`, allowlisted commands that
write) does not apply: this config contains no `run_command`.

## Scope

- **In scope:** `ops_precompile.py` (path identity, schema normalisation, symlink-alias
  refusal, four verdict-line corrections), the `check_parses` seam in `execute-json-ops.py`,
  new behavioural tests, CHANGELOG.
- **Out of scope, deliberately:**
  - **A differential oracle** (`simulate()` vs the executor's dry-run `sim_state`). See
    "Oracle: no, not in this plan" below.
  - **The executor's dry-run `sim_state` keying**, which has the same symlink blindness. This
    plan refuses such configs at the gate instead, so the hole is closed without touching the
    writer's state machine.
  - **Parsing a grammar newer than the running interpreter.** Not possible in the stdlib.
  - Hardlink and case-insensitive-filesystem aliasing — stated as known limits in the
    docstring rather than silently implied away.

## Prerequisites

- `.claude/settings.local.json` with `ECC_HOOK_PROFILE=minimal` present (CONTRIBUTING.md).
- Work in the `fix/parse-gate-ordering` worktree at `ac9d018` or later.

## Reproductions (run before planning, recorded here as evidence)

All three in `/private/tmp/pg-repro`, against the real executor, `--no-approval`:

1. **C1, `./x.py`.** `x.py` edited to `A = 2\nB = 3`, then `./x.py` edited `B = 3` → `B = (`.
   Gate: `MISS ./x.py … / ? ./x.py not checked / OK x.py still parses`, **exit 0**. Executor:
   `status: success`, both ops `edited`; `x.py` is `A = 2\nB = (` → `SyntaxError: unexpected
   EOF while parsing`.
2. **C1, symlink alias.** `pkg/m.py` plus `sym.py -> pkg/m.py`, same edit shape. Gate exit 0.
   Executor exit 0. `pkg/m.py` fine; `sym.py` is now a **regular file** holding `A = 2\nB = (`
   — the atomic `os.replace` write replaced the link instead of following it.
3. **C2, both schema keys.** `files` duplicates the `A = 1` anchor, `operations` then edits it.
   Gate: `MISS y.py: anchor is ambiguous … / ? y.py not checked`, **exit 0**. Executor applies
   only the modern op and leaves `y.py` as `A = (`. With `jsonschema` importable the validator
   REJECTS this config; with the import blocked (a **default zero-dependency install**) it
   prints `All find patterns exist in files` → **APPROVED**. Confirmed both ways.

## Verdict on the proposed design

**Point 1, "one path identity": right goal, wrong key. Use `os.path.relpath`, not `realpath`.**

The requirement is not a *better* canonicaliser, it is *the executor's* canonicaliser.
`execute-json-ops.py:684` keys on `os.path.relpath(str(file_path))`, and `relpath('./x.py') ==
'x.py'` — so plain `relpath` closes C1 with exact parity, by construction, forever. `realpath`
would be a *third* identity, and a gate whose file identity differs from the writer's is the
class of bug being fixed.

On the **symlinked-parent hazard you asked me to construct**: I built `/private/tmp/pg-repro/link
-> real` and ran from inside `link/repo`. `os.getcwd()` returned the *physical* path
(`/private/tmp/pg-repro/real/repo`) — the kernel cwd is always physical, so the feared `../../..`
garbage did not appear even for the naive `relpath(realpath(p), getcwd())` form. The hazard is
real for a *logical* cwd (shell `$PWD`) but Python never gives one. That said, `relpath` is
purely lexical and cannot produce it at all, which is one more reason to prefer it. A test pins
`_canon(spelled) == os.path.relpath(spelled) == "x.py"` for `x.py`, `./x.py` and `pkg/../x.py`
from inside a symlinked parent.

`realpath` still has a job — **detection, not keying**. The symlink alias must not be *modelled*
by either identity: the gate reads the link before the executor's earlier write, and the
executor's `os.replace` breaks the link. So `_aliases()` groups the plan's keys by `realpath`
and any group of size > 1 is **refused** (`ALIAS`, `bad += 1`), not withheld — withholding is
what exited 0. This is the honest verdict: *this gate cannot model this plan.* It also names
both spellings and the shared real file, where a `realpath` key would have printed a misattributed
`BREAK` against a file the executor leaves intact.

**Miss rendering:** the key groups, the spelling informs. `misses` stays `(path, reason)` with
`path` = the `_canon` key (or `unresolved` lands on nothing), and when the author's spelling
differs the reason is prefixed `written in this config as ./x.py — …`. Both halves pinned.

**Point 2, "one normaliser": adopted, in the inverted direction.** Do **not** import
`normalize_config` into the gate — the gate is the leaf the executor loads by path, and a
hyphen-named module imported back up is exactly the fragile dependency you feared (it also drags
`shared` onto `sys.path`; I hit that in the test and had to insert it explicitly). Instead
`check_parses(config: dict)` hands over the config `normalize_config` already produced
(`execute-json-ops.py:1036`), and `check()` accepts a dict **or** a path. On the execution path
there is then exactly **one** normaliser. The standalone CLI keeps a five-line `_normalize` with
the same precedence, and
`test_the_gate_normaliser_agrees_with_the_executors` asserts the two produce the identical
`operations` list for legacy, modern and both-keys configs — so the duplication cannot drift
silently. `simulate()` calls `_normalize` on its first line, which makes the precedence
idempotent and removes the legacy `files` loop entirely.

**MAJOR (host grammar): take the minimum, and say why.** There is no reliable discriminator.
`ast.parse(feature_version=…)` only *lowers* the grammar, never raises it, so a 3.9 interpreter
cannot represent 3.10+ syntax at all; the differential property does not help (it exempts files
already unparseable, not new syntax); and any heuristic that guessed "too new" would either fail
open — the silent pass this module exists to prevent — or misclassify a genuine break. So: the
`BREAK` line names the grammar it judged with (`as CPython 3.9 reads it …`), the docstring gains
a `WHOSE GRAMMAR` paragraph pointing at `--no-parse-check`, and the limitation is stated in the
CHANGELOG. Raising the floor or shelling to a project interpreter is a separate, owner-gated
change.

## Oracle: **no — not in this plan**

Yes it is the right instrument for the class, and no it does not belong here, for a
disqualifying reason: **the reference side is itself wrong.** The executor's dry-run `sim_state`
is keyed by `os.path.relpath` and populated only along the dry-run branches, and my symlink
reproduction shows it does not model `os.replace`-through-a-link either. An equality oracle
built today would pin `simulate()` to a known-defective reference — it would have been *green*
on the symlink case, because both sides are wrong in the same direction. Making the oracle
meaningful first requires making `sim_state` the single modelled post-state (its own change,
with its own blast radius in the writer's transaction path). Half-building it here would
manufacture false confidence, which is the failure mode of this whole PR. Recommendation: file
it as its own plan, `plan-ops-postState-oracle`, sequenced **after** this one, and have it
delete `simulate()`'s independent modelling rather than merely compare against it.

## Implementation steps

### Step 1 — `.claude/operations/scripts/ops_precompile.py`: docstring states the grammar limit
- **Action:** Modify. Adds the `WHOSE GRAMMAR` paragraph after `WHAT THIS IS NOT`.

### Step 2 — `.claude/operations/scripts/ops_precompile.py`: `_apply` carries the spelling; `delete` is literal
- **Action:** Modify. `_apply(src, edit, path, misses, spelling=None)`; a nested `_miss()`
  appends `(key, reason)` and prefixes the author's spelling when it differs.
  `edit.get('delete')` → `edit.get('delete') is True`, matching `execute_code_edit`.

### Step 3 — `.claude/operations/scripts/ops_precompile.py`: one identity, one schema
- **Action:** Modify. Adds `_canon`, `_aliases`, `_normalize`; rewrites `simulate`'s body to
  normalise first, drop the legacy `files` loop, key every accumulator on `_canon(path)`, skip
  `run_command`, and record a miss for an operation with no path (which today raises `TypeError`
  in `os.path.exists(None)`).

### Step 4 — `.claude/operations/scripts/ops_precompile.py`: `check()` takes the executor's config
- **Action:** Modify. `check(config, quiet=False)` accepts dict-or-path; adds the `ALIAS`
  refusal loop after `unresolved`; `BREAK` names the interpreter; `PRE` no longer asserts the
  edits are innocent; a `run_command` in the config emits an explicit "not modelled" note.

### Step 5 — `.claude/operations/scripts/execute-json-ops.py`: hand the config over
- **Action:** Modify. `check_parses(config: dict)`, `module.check(config)`, and the call site
  `check_parses(config)` at the gate. Docstring records why it is handed over, not re-read.

### Step 6 — `tests/test_ops_parse_gate.py`: the pins
- **Action:** Modify (append 13 tests). The reviewer's own three reproductions, at gate level
  *and* against the real executor, plus the four lesser findings and the two parity properties.

### Step 7 — `CHANGELOG.md`: record the user-visible change
- **Action:** Modify. Replaces the `## [Unreleased]` heading with heading + entry.

## Paths this ops.json writes (all four, for `check-plan-artifacts.py --check`)

1. `.claude/operations/scripts/ops_precompile.py` — steps 1–4 (`code_edit`)
2. `.claude/operations/scripts/execute-json-ops.py` — step 5 (`code_edit`)
3. `tests/test_ops_parse_gate.py` — step 6 (`code_edit`)
4. `CHANGELOG.md` — step 7 (`code_edit`)

No `file_create`, no `file_delete`, no `run_command`. 7 operations, 16 edits.

## Testing strategy

`python3 -m pytest tests/test_ops_parse_gate.py tests/test_ops_hardening.py -q` →
**83 passed** (68 + 15) against the post-state, measured in a scratch copy at
`/private/tmp/pg-verify`. `ruff check` clean; `mypy` clean (37 files). Then the DoD gates
(`gen-docs --check`, `check-plan-artifacts --check`, full suite) before commit.

### Mutation proofs (every one executed against the post-state; all confirmed RED)

| Fix | Test | Mutation that turns it red | Result |
|---|---|---|---|
| C1 `_canon` | `test_a_dot_slash_alias_is_one_file_to_the_gate_as_it_is_to_the_executor` | `_canon` returns `path` (raw key) | RED — `ok` True, `not checked` instead of BREAK |
| C1 end-to-end | `test_the_dot_slash_alias_refusal_also_stops_the_real_executor` | revert `_canon` **and** delete the `_aliases` loop (either alone refuses; noted in the docstring) | RED — executor exits 0, `x.py` unparseable |
| C1 parity | `test_the_canonical_key_is_the_executors_own_function` | key on `realpath`, or on `normpath` alone | RED |
| C1 spelling | `test_a_miss_on_an_alias_names_the_spelling_the_author_wrote` | drop the `written in this config as` branch, or render under the spelling | RED |
| C1 symlink | `test_a_symlink_alias_is_refused_because_neither_side_models_it` | delete the `_aliases` loop from `check` | RED — `ok` True |
| C1 symlink e2e | `test_the_symlink_refusal_also_stops_the_real_executor` | delete the `_aliases` loop | RED — link replaced, unparseable |
| C2 precedence | `test_a_config_carrying_both_schema_keys_is_simulated_as_the_executor_runs_it` | process `files` as well as `operations` (old behaviour) | RED — ambiguous, `ok` True |
| C2 end-to-end | `test_the_both_keys_refusal_also_stops_the_real_executor` | restore the legacy loop | RED — executor exits 0, `y.py` = `A = (` |
| C2 one rule | `test_the_gate_normaliser_agrees_with_the_executors` | flip `_normalize`'s precedence | RED |
| M1 vacuous branch | `test_a_crashing_checker_fails_the_run_closed` | `except Exception … return True` | RED — exits 0 and writes |
| MAJOR grammar | `test_the_break_line_names_the_grammar_it_judged_with` | drop the version from the BREAK line | RED |
| M2 PRE wording | `test_the_pre_line_does_not_claim_the_edits_are_innocent` | restore "The edits here are not the cause" | RED |
| L1 delete | `test_delete_is_modelled_only_on_a_literal_true` | `edit.get('delete')` truthy | RED |
| L2 run_command | `test_run_command_writes_are_declared_unmodelled` | drop the note | RED |

The M1 test is the one the reviewer proved vacuous: it writes a sibling `ops_precompile.py`
whose module body is `raise RuntimeError(...)`, runs a copy of the engine on a **valid**
edit, and asserts exit 1, `parse checker itself failed to run`, `parse-gate` in the output,
and the target byte-identical. Fail-open therefore writes, and the test goes red.

## Rollback plan

- **Before execution:** nothing to undo; the two artifacts are plan files.
- **After execution, whole change:** `git checkout -- .claude/operations/scripts/ops_precompile.py
  .claude/operations/scripts/execute-json-ops.py tests/test_ops_parse_gate.py CHANGELOG.md`
  (or the engine's own backup dir, `restore-backup.py <backup>`; the run creates one).
- **Per step:** each operation is a self-contained `code_edit` whose `find`/`replace` pair
  inverts by swapping the two strings. Step 5 (`execute-json-ops.py`) must be reverted together
  with Step 4, because `check_parses(config)` and `check(dict)` are one seam: reverting only one
  side leaves the executor passing a dict to a path-only `check`, which returns
  `CANNOT READ {...}` and **refuses every run**. The reverse partial (revert Step 5 only) is
  harmless — `check` still accepts a path.
- **If a later finding invalidates only the `ALIAS` refusal:** delete that one loop. Nothing
  else depends on `_aliases`, and the `./x.py` fix survives it.

## Risk assessment

- **Low:** Steps 1, 2 (docstring, `is True`, miss prefix), 7 (CHANGELOG). Output-parity for
  ordinary repo-relative paths is exact — `relpath('x.py') == 'x.py'` — and all 68 pre-existing
  assertions were re-run unchanged.
- **Medium:** Step 3 rewrites `simulate`'s body, the module's core. Mitigated by the 68 existing
  tests plus 13 new ones, all executed. Newly *refusing* a symlink-aliased config is a
  behaviour change that could in principle block a legitimate plan; it is loud, precise, names
  the fix ("name the file once, by one path"), and `--no-parse-check` remains the break-glass.
- **Medium:** Step 4+5 change `check`'s and `check_parses`'s signatures. Both are internal;
  every in-repo caller was grepped (all positional, all in `tests/test_ops_parse_gate.py` and
  the one executor call site). Downstream installed trees ship both files together, so a
  half-updated pair cannot arise from an install — only from a partial revert, which the
  Rollback section calls out.
- **High:** none. No security surface, no schema change, no deletions, no protected files, no
  new dependency, no `--stamp-baseline`.
- **Blast radius / hubs:** `.claude/project-graph.json` is absent in this worktree
  (`project-graph.py` has no graph to query), so no hub verdict is available; `execute-json-ops.py`
  is nonetheless the engine's central module, which is why this plan confines its change to a
  single seam (three edits, one of them a docstring).

## Open questions for the owner

1. The `ALIAS` refusal is new behaviour that can block a previously-runnable plan. Accept, or
   downgrade to a miss (which re-opens the exit-0 hole and I do not recommend)?
2. The oracle: file `plan-ops-postState-oracle` as the follow-up, and does it get to change the
   executor's `sim_state`?
3. The 3.9 grammar ceiling is now *documented* rather than fixed. Is raising the tooling floor,
   or shelling the parse out to the project's own interpreter, worth its own plan?
