# Implementation Plan: Reflection Test Isolation (Workstream 11)

## Overview

Make `tests/test_reflection_ledger.py` and `tests/test_reflection_gate.py` hermetic by
routing their ledger/inbox redirection through a single `reflection_env` fixture in a new
`tests/conftest.py` that **restores** the caller's environment instead of deleting it.

**Headline finding, stated plainly:** the claimed order dependence of
`TestCli::test_receipt_via_cli_clears_the_checkpoint` **could not be reproduced**. A
different, real, order-dependent state mutation in the same two files **was** reproduced
and is what this plan fixes. See "Reproduction Record" — no fix is proposed for anything
unproven.

## Reproduction Record

### 1. The reported flake — NOT reproduced

Every one of the following ran green, in this working tree, at commit `cbfdcec`:

| Invocation | Result |
|---|---|
| `pytest tests/test_reflection_ledger.py::TestCli::test_receipt_via_cli_clears_the_checkpoint -q` | 1 passed |
| `pytest tests/test_reflection_ledger.py -q` | 40 passed |
| `pytest tests/test_reflection_ledger.py::TestCli -q` | 6 passed |
| collection order **reversed** (custom `pytest_collection_modifyitems` plugin) | 40 passed |
| 10 random shuffle seeds over ledger + gate files (79 tests each) | all passed |
| reversed + 3 random shuffle seeds over the **whole** suite | 1006–1013 passed |
| each of the 39 other `tests/test_*.py` files run **before** the target test, one pair per process | no failure in any pair |

No random-order plugin is installed (`pytest-randomly` / `pytest-random-order` / `xdist`
are all absent), so the suite's order is deterministic today; the risk is latent, not live.

I also verified the two files leave **no** trace in the real shared ledger dir
(`$TMPDIR/claudekit-reflection`): the session keys `737794c2…` (`session-under-test-0001`)
and `8a488f7f…` (`gate-session-0001`) do not appear there before or after a run, and a
probe file placed in that directory confirmed the directory is untouched by the run. The
target test therefore cannot be inheriting ledger state through the temp-dir fallback.

**Conclusion:** the target test's own isolation (unique `tmp_path` ledger dir per test) is
sound. I did not invent a fix for it, and the assertion it makes is untouched by this plan.

### 2. The real leak — reproduced, root-caused, fixed

Both files' `ref` fixtures end with:

```python
os.environ.pop("CLAUDEKIT_REFLECTION_DIR", None)
os.environ.pop("CLAUDEKIT_REFLECTION_INBOX", None)
```

That is an unconditional delete of a **process-global** value, not a restore. If the caller
has those variables exported — which is exactly what a live ClaudeKit session or a CI job
that pins the ledger location does — the first reflection test to run destroys them for
every test that runs afterwards in the same process, and those tests silently retarget the
real, host-shared `$TMPDIR/claudekit-reflection`.

Reproducing invocation (probe test asserts the ambient value survives):

```bash
cat > tests/_probe_test.py <<'EOF'
import os
def test_ambient_reflection_dir_survives():
    assert os.environ.get("CLAUDEKIT_REFLECTION_DIR") == "/ambient/sentinel/dir"
    assert os.environ.get("CLAUDEKIT_REFLECTION_INBOX") == "/ambient/sentinel/inbox"
EOF
CLAUDEKIT_REFLECTION_DIR=/ambient/sentinel/dir \
CLAUDEKIT_REFLECTION_INBOX=/ambient/sentinel/inbox \
ECC_HOOK_PROFILE=minimal \
python3 -m pytest tests/test_reflection_ledger.py tests/_probe_test.py -q -p no:cacheprovider
```

* probe alone (control): **1 passed**
* after `test_reflection_ledger.py`: **1 failed, 40 passed** —
  `assert None == '/ambient/sentinel/dir'`
* after `test_reflection_gate.py`: **1 failed, 39 passed** — identical failure

Same probe against the patched tree (prototype, see "Proof"): **83 passed, 0 failed**.

This is order dependence by definition: the probe's result is a function of whether a
reflection test ran before it.

### 3. Sibling audit

* **`tests/test_reflection_ledger.py`** — 1 leaking fixture (`ref`), which **all 40 tests**
  in the file depend on. Additionally `load_module()` writes `os.environ` as a side effect
  of an import helper, and the file does **not** force `ECC_HOOK_PROFILE`, contrary to the
  project convention its sibling gate file follows.
* **`tests/test_reflection_gate.py`** — 1 leaking fixture (`ref`), depended on by 21 of its
  39 tests. Its `env` fixture is already clean (it builds a fresh dict and never mutates
  `os.environ`). It shares the identical `pop`-instead-of-restore defect, which is the
  justification for including it in this workstream.
* No other test file in the repo references `CLAUDEKIT_REFLECTION_DIR`.
* **Total: 2 leaking fixtures, 61 tests transitively exposed.**

## Scope

* **In scope:** `tests/conftest.py` (new), `tests/test_reflection_ledger.py`,
  `tests/test_reflection_gate.py`.
* **Out of scope:** `.claude/hooks/reflection.py`, `.claude/hooks/reflection-gate.py`,
  `.claude/settings.json`, and every non-test file. No product code changes.
* **Not weakened:** no assertion is relaxed, removed, reordered or made conditional. No
  `skip`, no `xfail`, no sleep, no retry. The diff is fixture plumbing plus three new
  additive tests.

## Prerequisites

`ECC_HOOK_PROFILE=minimal` in the session (`.claude/settings.local.json`), per CLAUDE.md.

## Implementation Steps

### Step 1: Create `tests/conftest.py`

* **File:** `tests/conftest.py` · **Action:** Create
* `scoped_env(**overrides)` — context manager that snapshots the prior value of each
  variable (including *absence*), sets the overrides, and restores exactly the prior state
  in `finally`.
* `reflection_env` fixture (function-scoped, depends on `tmp_path`) — sets
  `CLAUDEKIT_REFLECTION_DIR=<tmp_path>/ledger`,
  `CLAUDEKIT_REFLECTION_INBOX=<tmp_path>/inbox` and `ECC_HOOK_PROFILE=minimal` for the
  duration of one test, restoring on teardown.
* A conftest fixture is used rather than a shared helper module so neither test file needs
  a sibling import, and so nothing is imported by unrelated test files that do not request
  the fixture.

### Step 2: Rewire `tests/test_reflection_ledger.py`

* **File:** `tests/test_reflection_ledger.py` · **Action:** Modify
* `load_module()` loses its `tmp_path` parameter and its two `os.environ` writes; it is now
  a pure import helper.
* `ref` becomes `def ref(reflection_env): return load_module()` — no yield, no teardown, no
  environment mutation.
* `TestCli.run()` drops its `tmp_path` parameter and passes `dict(os.environ)` to the child,
  which already carries the per-test ledger from `reflection_env`. The five call sites and
  the inline `--json-stdin` env dict are updated to match. The parent and the subprocess
  still read and write the same ledger, so every CLI assertion keeps its meaning.
* Adds `from conftest import scoped_env` for the bound tests below.
* Cosmetic: six test methods that no longer use `tmp_path` drop the unused parameter.

### Step 3: Add bound tests for the isolation itself (`TestIsolation`)

* **File:** `tests/test_reflection_ledger.py` · **Action:** Modify (append)
* `test_each_test_starts_from_an_empty_per_test_ledger` — asserts `ledger_dir()` is under
  this test's `tmp_path`, the ledger file does not yet exist, and no checkpoint is pending.
* `test_the_fixture_restores_an_ambient_ledger_dir` / `test_the_fixture_restores_absence` —
  bind `scoped_env`'s two-way contract (value restored; absence restored). Revert
  `scoped_env` to a bare `pop` and they go red.
* **`test_a_reflection_test_does_not_destroy_an_ambient_ledger_dir` — the regression test
  for the defect itself.** The leak is only observable from *outside* the process, so this
  test writes an inline probe module into `tmp_path` and runs a real pytest subprocess with
  `CLAUDEKIT_REFLECTION_DIR=/ambient/sentinel/dir`,
  `CLAUDEKIT_REFLECTION_INBOX=/ambient/sentinel/inbox` and `ECC_HOOK_PROFILE=minimal`
  exported, over one cheap `ref`-using victim from **each** reflection file
  (`test_reflection_ledger.py::TestPrivacy::test_session_token_is_owner_only` and
  `test_reflection_gate.py::TestFailureRecording::test_failure_is_persisted`) followed by
  the probe, and asserts `returncode == 0`. Never a whole file: running this file inside
  itself would recurse.
* All four are hermetic themselves (they use `scoped_env`, never a raw `pop`). An earlier
  draft that used `try/finally: os.environ.pop(...)` reintroduced the very leak it tested;
  the probe caught it.

### Step 4: Rewire `tests/test_reflection_gate.py`

* **File:** `tests/test_reflection_gate.py` · **Action:** Modify
* `env(tmp_path)` becomes `env(tmp_path, reflection_env)`; the two
  `CLAUDEKIT_REFLECTION_*` keys are dropped from its literal because `dict(os.environ, …)`
  already carries the identical values (`tmp_path/"ledger"`, `tmp_path/"inbox"` — byte-for-
  byte what the fixture used to build). `ECC_HOOK_PROFILE="standard"` still overrides the
  fixture's `minimal` explicitly, so the gate's blocking behaviour is unchanged.
* `ref` stops writing and popping `os.environ` and returns the module instead of yielding.

## Testing Strategy

Prototyped and executed against an `rsync` copy of the tree in the scratchpad — the real
tree and the real ledger dir were never mutated.

1. **Before (red):** the probe invocation in §2 → `1 failed` after each reflection file.
2. **After (green):** same invocation on the patched copy → probe passes. Reversed order and
   3 shuffle seeds over both files → `83 passed` each. Ledger file alone: `44 passed`.
3. **The regression test binds — measured.** Reverting the `ref` fixture to its true
   pre-fix design (fixture sets `os.environ` itself, teardown pops without restoring):
   * `test_reflection_ledger.py` reverted → **`1 failed, 43 passed`**, the failure being
     `TestIsolation::test_a_reflection_test_does_not_destroy_an_ambient_ledger_dir`.
   * `test_reflection_gate.py` reverted (ledger file untouched) → the same single test
     **fails** (`1 failed`), proving the gate victim in the subprocess is load-bearing.
   * Both files restored → **`44 passed`** / **`83 passed`** across the two files.
   * Recorded negative result: reintroducing *only* the `pop` teardown while keeping the
     `reflection_env` dependency leaves all 44 green — correctly, because fixture teardown
     runs inner-first and `scoped_env`'s outer restore repairs the damage. That mutant is
     genuinely harmless; the one that matters (dropping the outer restore) is red.
4. **Not vacuous:** the receipt-clearing behaviour was neutralised in the copy's
   `reflection.py` (`active_entries` no longer resets `active = []` on a valid receipt).
   `TestCli::test_receipt_via_cli_clears_the_checkpoint` went **RED**
   (`tests/test_reflection_ledger.py:366: AssertionError`), together with 3 sibling
   receipt-clearing tests: `4 failed, 39 passed`. Restoring the hook returned it to green.
5. **Full suite** on the patched copy: `1005 passed, 12 failed`. All 12 are the
   `test_ops_enforcement_scope.py` / `test_hooks_behavioral.py::TestOpsEnforcement` cases
   that resolve `REPO` from `__file__` and shell out to `git check-ignore`, which cannot
   work in an rsync copy with no `.git`; they fail identically with `conftest.py` removed
   and pass 50/50 in the real tree. **Expected in the real tree: 1017 passed** (1013
   baseline + 4 new `TestIsolation` tests).
6. **Lint:** `ruff check src/ tests/ scripts/` with the project config and **no flags**
   (`select = ["E", "F", "W", "I"]`, `ignore = ["E501"]`) → **All checks passed**. `I001` is
   not tripped by `from conftest import scoped_env`.

Post-execution the implementer must re-run, in the real tree:
`ECC_HOOK_PROFILE=minimal python3 -m pytest tests/ -q` (expect 1017 passed, zero failures)
and `ruff check src/ tests/ scripts/`.

## Rollback Plan

`git checkout -- tests/test_reflection_ledger.py tests/test_reflection_gate.py` and
`rm tests/conftest.py`. Three files, no product code, no migration, no state to unwind.

## Risk Assessment

* **Low** — `tests/conftest.py` is new and defines one opt-in fixture plus one helper; no
  autouse fixture, no hook, so no test that does not request `reflection_env` can be
  affected. Verified against the full suite.
* **Low** — the gate `env` fixture's values are provably identical to what it built inline;
  `ECC_HOOK_PROFILE="standard"` remains an explicit override.
* **Medium — the reported flake is unproven and therefore unfixed.** If someone can produce
  a failing invocation for `test_receipt_via_cli_clears_the_checkpoint`, this plan does not
  claim to address it. It removes the only shared-state channel I could find and prove;
  another may exist. Adding a random-order plugin to the dev extras would convert this from
  latent to detectable — that is a separate, owner-gated decision (a new dev dependency).
* **Medium — PRODUCT-SIDE DEFECT, DELIBERATELY NOT FIXED HERE.**
  `reflection.ledger_dir()` falls back to `$TMPDIR/claudekit-reflection` — a directory
  shared by every session, every project and every user process on the host — whenever
  `CLAUDEKIT_REFLECTION_DIR` is unset. Session ids are the only separator, and any code
  path that reuses a session id, or any test that forgets the override, reads and writes
  another session's ledger. That fallback is the structural reason these tests are one
  forgotten environment variable away from cross-contamination, and no amount of test-side
  isolation removes it. **It belongs in `.claude/hooks/reflection.py`, which this workstream
  does not own.** Recommend a follow-up item: per-invocation subdirectory, or refusing to
  operate without an explicit ledger root. Flagged, not silently changed.
* **Low** — the regression test spawns a pytest subprocess (~5s). It is the only way to
  observe process-global env damage from inside the suite; it uses explicit node ids, no
  sleeps and no retries, and has a 120s timeout.
* **Low** — `from conftest import scoped_env` relies on pytest's rootdir `sys.path`
  insertion for `tests/` (no `__init__.py`, default `prepend` import mode). Verified
  working in the full-suite run.
