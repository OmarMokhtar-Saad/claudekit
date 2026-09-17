# Implementation Plan: upstream the qa-agents hardening into the kit

**Ops config:** `.claude/plans/plan-qa-agents-hardening.ops.json` (14 operations, validator APPROVED)
**Payloads:** `.claude/plans/payloads/qa-agents-hardening/` (11 files, referenced by `*_path` + `*_sha256`)
**Tier:** 3 — security/hook/executor surface.
**Revision 2** — answers the REJECTED (60/100) review at `.claude/reports/reviews/qa-agents-hardening.md`.
Every claim below was **measured** in a scratch copy of this repo with the ops applied
(`/private/tmp/.../scratchpad/s1`), not reasoned about.

## Phase 0 — design precheck

The kit is upstream and stays upstream. qa-agents is a downstream fleet project that hardened
three kit assets against real incidents while simultaneously falling BEHIND the kit on other
parts of the same files, so every file here is a **three-way merge**, never a copy. The value
sits in the four files the ops config touches plus the tests that pin them.

**Prior searches.** `review-record.py rejections search "command-guard executor worktree
hardening upstream"` → `e2e-lane-a` (CONDITIONAL 87) is the validated match: its MAJOR finding
was *mutation-proof overclaim*. **Revision 1 reproduced that exact defect** — a shipped mutation
control that failed on the unmutated tree (H1). The lesson is now applied mechanically: every
new and edited test in this revision was **executed** before this document was rewritten.

## Scope

| File | kit | qa | upstreamed | deliberately NOT upstreamed |
|---|---|---|---|---|
| `.claude/hooks/command-guard.sh` | 78 | 184 | stdout/stderr split; crash-vs-verdict discriminator; anchored pattern; degraded-mode warning; OUT→ERR deny fallback | the `hooks/vendor/` fallback (the kit ships no vendor dir); every `claude-kit` string (kit package is `claudekit-agents`) |
| `execute-json-ops.py` | 1415 | 1621 | `_preflight_validate` (**narrowed** — see below), `_git_toplevel`, `_resolve_root`, `--root`, `--skip-validation`, `OperationTransaction._audit` + audited rollback | `audit_bypass`/`bypass.log` (out of scope); every qa regression — payload-by-reference, directory-keyed approval slugs, `check_parses(config)`, the exit-6 self-review cause and the parse-gate ordering comments all STAY kit |
| `worktree-manager.py` | 406 | 577 | `is_branch`, `local_of`, `base_branch`, `containment_ref`, `unmerged_commits`, the `base_branch` registry field, the `cmd_remove` containment block | qa's registry-count cap (a regression — the kit counts git's own `live_worktree_paths`) and qa's black reformatting. `cmd_prune` was reported as "reworked": **it is not** — that diff is pure reformatting |
| `validate-config-json.py` | 1064 | 944 | `full_verdict` **plus a new, narrower `preflight_verdict`** | everything else — qa is behind |

**Docs touched** (ops 12 and 13, restored after a round-2 regression dropped them from this
plan and reddened `check-plan-artifacts.py --check`): `docs/HOOKS.md` gains the command-guard
crash-vs-verdict row, and `docs/PARALLEL_AGENTS.md` gains the worktree remove-refusal rows.

The eight `gate-check/` harnesses become **pytest tests, not kit assets** (gatepincheck's own
docstring records that a hand-run harness let both gates be deleted unnoticed for nine days;
task 008 forbids near-duplicate assets). `vendorparity.py` skipped; `rootcheck.py`'s
real-worktree case is preserved but gated behind `CK_SLOW_TESTS=1` (not-for-CI).

## [C1] The preflight is narrowed, and the per-file decision is measured

**The defect in revision 1.** `_preflight_validate` called `full_verdict`, the CLI's *whole*
rule set. The executor repeats most of that rule set a moment later with far better,
per-operation diagnostics — so refusing first **shadowed** the parse gate, the setuid/create-mode
refusal, the tampered-payload digest check, the ambiguous-anchor abort and the `run_command`
allowlist. Measured: 0 failures → 29 failures across 8 files.

**The fix — a preflight that answers only what nothing downstream repeats.** New
`preflight_verdict(config_file)` in the validator returns a verdict on exactly two things:

1. **the schema** — structure and unknown top-level keys. This *is* the incident class the gate
   was added for (a forbidden top-level `description` key was rejected by the validator and
   executed to completion anyway);
2. **backup compatibility** — with a non-writable `backups/`, the CLI printed REJECTED while the
   executor ran on to die at `backup_dir.mkdir` outside any rollback.

Everything else is left to the executor, which enforces it and names the operation that failed.
A config that cannot be read or parsed is **deferred**, not refused: the executor's own loader
reports `config-load-error` in RESULT-JSON, which is strictly more informative (this alone fixed
`test_ops_hardening::test_engine_level_abort_still_emits_result_json`).
`full_verdict` stays as THE CLI verdict; the executor refuses outright against a validator too
old to expose `preflight_verdict`, so the gate cannot silently fall back to a weaker rule set.

**Second measured defect, fixed in the same op:** the validator was resolved as
`Path(__file__).parent / "validate-config-json.py"`. Four existing tests copy the engine to a
tmp dir and run it with `PYTHONPATH=SCRIPTS`; that copy could not find the validator and
fail-closed on every run. Resolution now falls back to the directory the `shared` module was
imported from — the engine's own dependency set.

**Per-file decision (all 29 re-run; final state green):**

| File | new failures (rev 1) | decision | why |
|---|---|---|---|
| `test_ops_content_by_path.py` (2), `test_run_command_ops.py` (2), `test_work_loss_protection.py` (2), `test_validator_sequence_mode.py` (1) | 7 | **no change** — narrowing alone fixes them | their configs are invalid only in ways the executor itself catches (anchors, digests, allowlist): exactly the checks the preflight no longer duplicates |
| `test_ops_hardening.py` (3) | 3 | **no change** — narrowing + validator resolution | one is an unparseable config (now deferred to `config-load-error`); two copy the engine to tmp |
| `test_ops_parse_gate.py` (10) | 9 | **fixture corrected** — `write_ops` wrote `"plan_name"`, which `normalize_config` accepts but the schema does not | the key was incidental to every assertion in the file; the subject is the parse gate |
| `test_ops_parse_gate.py::…both_keys…` | 1 | **preflight asserted + `--skip-validation`** | a config carrying BOTH `files` and `operations` is genuinely schema-invalid; the subject (the precompile refusal) is downstream |
| `test_ops_file_modes.py::test_setuid_is_refused_by_the_executor` | 1 (of 3) | **preflight asserted + `--skip-validation`** | the test's own docstring says "a config that never went through the validator" — which is precisely what the flag reproduces |
| `test_ops_file_modes.py` (other 2) | 2 | **no change** | fixed by narrowing |
| `test_ops_approval_gate.py::…no_plan_field…` | 1 | **preflight asserted + `--skip-validation`** | the config deliberately omits `"plan"`; the subject is the approval gate keying by DIRECTORY |

Only **three** tests take `--skip-validation`, and none of them takes it blindly: each first
asserts `returncode == 2` + `validation_failed` **without** the flag, then steps past it. That is
the opposite of a blanket allowlist — the preflight gains coverage in those files instead of
losing it, and the downstream gate keeps its end-to-end proof.

## [H1] The mutation control now points at the mechanism that carries the behaviour

The reviewer was right and the measurement is reproduced: with the channels split, a refusal
echoed on **stdout** never reaches the discriminator, so dropping the `RC -ne 2` exclusion
changes nothing. **Both** conditions are load-bearing, in different scenarios, and each now has a
control that fails on the unmutated tree only when its mutant survives:

- `STDERR_REFUSAL` — a validator that reports its refusal on **stderr** with rc 2, its message
  beginning `ImportError: `. The real hook blocks it (`test_stderr_refusal_carrying_a_crash_token_still_blocks`);
  drop the rc-2 exclusion and it is waved through. **This is what the rc-2 exclusion buys.**
- `RC1_STDOUT_CRASH_TOKEN` — rc 1 with an anchored crash token on **stdout**. The real hook
  blocks it; mutate the discriminator to search `"$OUT$ERR"` (the historical defect, verbatim)
  and it is waved through. **This is what the split buys.**
- The `if false` and unanchored-pattern controls are unchanged and still kill.

Measured: `tests/test_command_guard_crash.py` → 13 passed, 0 failed.

## [H2] mypy — `full_verdict` can return `(True, [], None)`

The `--stamp-baseline` branch now refuses (exit 1, `REJECTED (config could not be re-read for
stamping)`) instead of handing `None` to `stamp_baseline`, which was a latent crash in exactly
the path where a hash/verdict deadlock is most confusing. Measured: `mypy` → *no issues found in
42 source files*.

## [H3] ruff F401

`import sys` dropped from `tests/test_command_guard_crash.py`; payload re-stamped. Measured:
`ruff check src/ tests/ scripts/ .claude/operations/scripts/` → *All checks passed!*

## Implementation Steps

1. `.claude/hooks/command-guard.sh` (op 1) — channel split, crash discriminator, deny fallback.
2. `execute-json-ops.py` (op 2) — audited rollback; `_git_toplevel`/`_resolve_root`/
   `_preflight_validate` (narrowed, with the `shared`-relative validator fallback); `--root`
   and `--skip-validation` plus both gates in `main()`.
3. `validate-config-json.py` (op 3) — `preflight_verdict` + `full_verdict`; `main()` routed
   through `full_verdict`; the stamping branch narrowed against `None`.
4. `worktree-manager.py` (op 4) — `Tuple` import, `base_branch` registry field, the five
   containment helpers, the `cmd_remove` block.
5. Existing-test edits (ops 5-7) — `test_ops_parse_gate.py` (2 edits), `test_ops_file_modes.py`,
   `test_ops_approval_gate.py`, per the C1 table.
6. New tests (ops 8-11) — four files, stdlib + pytest only.
7. Docs + CHANGELOG (ops 12-14).

## Testing Strategy

| Test file | Pins | Mutation control (each verified to fail only when its mutant survives) |
|---|---|---|
| `tests/test_ops_gate_enforced.py` | schema-invalid config refused; `--skip-validation` is the only way past; valid config runs; cross-worktree config refused (exit 3); `--root` states intent | `_preflight_validate → True,[]`; the `hasattr(preflight_verdict)` guard removed (must still refuse); `_resolve_root → None,[]` |
| `tests/test_command_guard_crash.py` | crash permissive under `standard`, blocking under `strict`; plain rc-2 blocks; stdout- and stderr-echoed crash tokens in a real verdict still block | drop the rc-2 exclusion (stderr refusal must be waved through); search `"$OUT$ERR"` (stdout token must be waved through); unanchor the pattern; `if false` |
| `tests/test_worktree_containment.py` | `base_branch` recorded; merged work removable without `--force`; unmerged refused naming the ref; unresolvable ref refuses rather than deletes; `origin/main` → `main` | range from `base_sha..HEAD`; `if not ref` → `if False` |
| `tests/test_rollback_audit.py` | `backups/<run>/rollback.log` names the removed file with tree+pid; an unwritable audit cannot break rollback | `self._audit("removed", fp)` → `pass` |

## Validation — executed in the scratch copy with all 14 ops applied

| Command | Result |
|---|---|
| `execute-json-ops.py <ops.json> --no-approval` (rev 1) | 11/11 ops, all sha256 pins matched |
| `ruff check src/ tests/ scripts/ .claude/operations/scripts/` | **All checks passed!** |
| `mypy` | **no issues found in 42 source files** |
| `shellcheck .claude/hooks/command-guard.sh` | **clean** |
| the 8 files C1 names, before (real tree) | **231 passed, 2 skipped, 0 failed** |
| the 8 files C1 names, after (scratch, patched) | **258 passed, 3 skipped, 0 failed** (incl. the 4 new files) |
| `validate-config-json.py .claude/plans/plan-qa-agents-hardening.ops.json` | **APPROVED** |
| `gen-docs.py --check` / `gen-registry.py --check` / `check-context-floor.py --check` | OK (reviewer-executed; counts are unmoved — no agent, command, skill or hook is added) |

`check-plan-artifacts.py --check` → OK. `test_every_wired_hook_is_counted` is unaffected:
`command-guard.sh` keeps its name, path and settings entry.

## Rollback Plan

The engine backs every modified file into `backups/<run>/` and now records the rollback in
`backups/<run>/rollback.log`. Manual undo: `git checkout -- .claude/ docs/ tests/ CHANGELOG.md`
then delete the four new test files. No `file_delete` ops, so no `MAX_DELETIONS` exposure.

## Risk Assessment

- **HIGH — the executor is a GOD-NODE.** Every ops.json flows through it. Mitigated by the
  narrowing (the preflight now refuses only what nothing downstream catches), by both gates
  living in `main()` so in-process callers are untouched, and by a measured green suite.
- **MEDIUM — `--root` can refuse runs that work today**, but only when the config's git toplevel
  differs from the cwd's, which is the silent-wrong-tree signature. Configs outside any repo are
  unaffected.
- **MEDIUM — the crash discriminator is a permissive path in a security hook.** Reachable only
  for rc ∉ {0,2,127} with an anchored traceback on stderr; `strict` still blocks; four mutation
  controls now stop it widening.
- **LOW — three tests carry `--skip-validation`.** Each asserts the preflight refusal first, so
  the flag cannot silently hide a regression in the gate.
- **LOW — `audit_bypass`/`bypass.log` omitted** (out of scope): the two new bypass flags announce
  themselves on stderr only. Worth a follow-up decision.
- `UNVERIFIED:` the **full** `pytest tests/ -q` run (11449 baseline) was started in the scratch
  copy but not read back before this document was written; the 12 files with any plausible
  interaction were run and are green. The implementer must run the full suite and report actual
  numbers.
- `UNVERIFIED:` the three `--skip-validation` invocations were validated by the measured green
  run, not by a reviewer's independent judgement that each test's subject really is downstream.
  The C1 table states the reasoning per file so it can be refuted.
