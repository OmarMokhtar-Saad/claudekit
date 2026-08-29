# Plan — the bash oracle must not report clean when it ran no bash

## Overview

`check-validator-vs-bash.py` is a differential security gate: it feeds payloads the validator
ALLOWS into a real bash and reports any that reach a shadowed dangerous command. On
ubuntu-24.04 runners it has been reporting **`pass` while executing no bash at all**.

**Approach:** give the probe a liveness sentinel so "bash ran and reached nothing" is
distinguishable from "the probe never ran", count the latter as `errored` rather than
`executed`, and make `process_isolation()` ask whether `unshare` actually works instead of
assuming that present means permitted.

## 1. Scope (Steps)

| # | Change |
|---|---|
| A | `PROBE` emits `MARKER:__probe_ran__` before the payload |
| B | `markers()` returns the `DID_NOT_RUN` sentinel when that marker is absent |
| C | `run()` counts `DID_NOT_RUN` as `errored`, never `executed` |
| D | `process_isolation()` self-tests `unshare --pid --fork true` and falls back when it fails |
| E | `errored` enters the starvation verdict — denominator **and** its own ratio branch |
| F | `markers()` returns a typed `_DidNotRun`, so mypy checks the three-way branch |
| G | `unverified_ratio` — a combined ceiling, because two independent ones are looser together |
| H | `CHANGELOG.md` — `[3.1.0]` entry, including the `--json` contract change |

## 2. Evidence — measured, not inferred

CI, ubuntu-latest, every Python version:

```
FAILED tests/test_validator_vs_bash.py::TestTheOracleBinds::
       test_a_validator_with_no_blocklist_is_caught_by_bash
AssertionError: {'errored': 0, 'executed': 338, 'finding_count': 0, ...}
assert 'pass' == 'fail'
```

The test hands the oracle a mutant validator with `BLOCKLIST = set()` — it allows `rm`, `sudo`,
everything — and asserts the oracle catches it. On Linux the oracle reported **338 executed, 0
findings, status `pass`**.

Two defects compose to produce that:

1. **`process_isolation()` assumes present means permitted.** It returns
   `["unshare", "--pid", "--fork"]` whenever the binary exists. Ubuntu 24.04 restricts
   unprivileged user namespaces through AppArmor, so `unshare` exists and *fails*. Every probe
   process died before bash started.
2. **`markers()` cannot tell that apart from a clean result.** It returns `[]` both when bash
   ran and reached no shadowed command, and when bash never ran. `run()` then does
   `executed += 1` on both.

The file's own liveness guard — `executed == 0` or `refusal_ratio > 0.5`, written because
"a gate that reports clean because it asked nothing is the failure mode this whole file exists
to avoid" — could not fire, because 338 failed probes *looked* executed.

**This is the same class the gate exists to catch, in the gate itself.**

## 3. Design decisions

1. **A sentinel emitted BEFORE the payload is the only sound discriminator.** Not the return
   code: a payload of `false` legitimately exits non-zero having reached nothing. Not the
   marker count: reaching nothing is a legitimate result. Only "did the probe reach its own
   first line" separates the two, and the payload cannot suppress a line that already ran.
2. **`DID_NOT_RUN` is a unique object, not an empty list.** The first draft used `[]` compared
   by identity. It worked, and it is a trap: `[]` is a *legitimate* return value here, so a
   sentinel that compares equal to a real answer breaks on the next edit that adds a `==`.
3. **`errored`, not `executed`, and not `unverified`.** `unverified` means the validator refused
   the payload, which is information about the validator. A harness that could not run is
   information about the harness; `errored` already carries exactly that meaning in this file.
4. **`errored` must be IN the verdict, not merely counted (round 2, reviewer CRITICAL).**
   The first draft moved dead probes from `executed` to `errored` and stopped there — but
   `starved` reads `not executed or refusal_ratio > 0.5`, and `refusal_ratio` had `errored`
   in neither numerator nor denominator. So `executed=1, unverified=0, errored=337` gave
   `refusal_ratio=0.0`, `starved=False`, `status=pass`: **one live bash process out of 338
   payloads, reported clean.** Fixing only the all-dead case moved the bug rather than closing
   it. `errored` now sits in `offered` and carries `error_ratio > 0.1`.
5. **A COMBINED ceiling, because splitting one threshold into two loosened it (round 3,
   reviewer MAJOR).** Round 2 replaced a single ratio with `refusal_ratio > 0.5` and
   `error_ratio > 0.1` — tighter per cause, and looser together: at refusal 0.5 and error 0.1,
   both AT and neither OVER, only 40% of the corpus reaches bash and nothing fires.
   `unverified_ratio = (unverified + errored) / offered > 0.5` closes it, and subsumes the
   refusal branch (same numerator plus errored, so it can only be larger) — which is why that
   branch is gone rather than kept beside it. `refusal_ratio` stays in the report because it
   says WHY a run was thin, which the aggregate cannot.
6. **A ratio, not `errored == 0`.** The existing code already counts a validator that raises
   as `errored` and deliberately does not fail on it — that is a finding about the validator,
   not a broken harness. A test pins this, so a later tightening has to argue with it.
7. **`_DidNotRun` is a class, not `object()` and not `[]`.** `object()` forced a
   `# type: ignore[return-value]` that would have switched the branch off mypy forever; `[]` is
   a legitimate return here, so a sentinel equal to a real answer breaks on the next `==`.
8. **Falling back to no isolation is consistent with the file's own reasoning.** Its docstring
   says the namespace is "the smallest" of three reasons executing here is acceptable — payload
   shapes that can escape are refused before bash sees them, and CI runs on an ephemeral runner
   that is discarded. Losing the narrowest of the three is better than a gate that runs nothing.
   The self-test is `lru_cache`d: `process_isolation()` is called from `markers()`, i.e. once
   per allowed payload per `safe_mode` pass — up to ~676 times per run. The round-1 plan
   claimed "one `unshare true` per run", which was simply wrong about its own change; the
   reviewer measured the call site and the cache is what makes the claim true.

## 4. Testing / Verification

- Applied to a scratch clone and run there BEFORE submitting:
  - `tests/test_validator_vs_bash.py` — **23 passed**.
  - **The regression, simulated:** stub `process_isolation()` to a wrapper that always fails,
    then run the oracle against the empty-`BLOCKLIST` mutant. Before: `executed=338, errored=0,
    status=pass`. After: **`executed=0, errored=338, status=fail`**.
- Full suite, ruff, mypy, shellcheck, drift gates.
- **Round-2 verification, run in a scratch clone BEFORE resubmitting:** ruff clean, mypy clean
  (33 files), `tests/test_validator_vs_bash.py` **25 passed**, and the reviewer's CRITICAL case
  reproduced and closed — `executed=1, errored=254, error_ratio=0.996 -> FAIL`.
  Two defects in my own ops.json surfaced only by running it: the `lru_cache` decorator had
  been prepended to a *body* edit rather than the `def` line so it never landed, and `Union`
  was used without being imported. Neither would have been visible from reading the diff.
- **Round-3 verification.** 26 passed, ruff and mypy clean. The new
  `test_refusals_and_errors_starve_a_run_together` is mutation-proven: it passes with the
  combined ceiling and FAILS when `unverified_ratio` is reverted to `refusal_ratio`.
  It took two attempts to make it bind, and both failures are the point:
  the first delegated its "executed" case to the real `markers`, which refuses payloads
  itself and pushed BOTH ratios over their thresholds — so it passed against the very logic
  it was written to catch. The second sat exactly ON 45%/10%, and since the corpus is not a
  multiple of the modulus, drift put `error_ratio` at 0.102 and it failed its own
  precondition. It now holds clear of the boundary at 46%/6%.
- **What this does NOT prove:** that Ubuntu 24.04 is the precise cause. That diagnosis is
  inference from the runner image and the symptom; the fix is correct for *any* cause of a
  probe failing to start, which is why it is written against the symptom rather than the guess.
  CI is the confirmation.

## 5. Rollback

One file, all `code_edit`; the executor backs it up before writing.

1. `restore-backup.py --list` then `--backup <dir>`, or `git checkout -- scripts/`.
2. **Blast radius:** this gate only reports; it mutates nothing and gates no execution path in
   the product. The worst case from a bug here is a noisier CI signal, never a weaker one — the
   change can only move outcomes from `pass` toward `fail`.
