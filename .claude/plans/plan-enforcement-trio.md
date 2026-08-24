# Implementation Plan: the enforcement trio

**Status:** **EXECUTED 2026-08-24** — owner approved "gate first, then widen" for the
file-guard allowlist. Tier 3 (enforcement layer). 9 ops configs; artifacts and evidence are
tabled below. Written first as an approval request, which is why the sections below are phrased
as proposals — they are kept in that voice deliberately, so the record shows what was asked and
what was answered.

Job 4 of handoff 9. Three findings held back from `plan-triage-refresh.md` because they sit in
the enforcement layer, where a change can turn a REJECT into an ALLOW.

**Two of the three are smaller than the backlog says, and one is not a code change at all.**
Measured before proposing, because that is the whole point of this plan.

| # | Finding | Site at `HEAD` | Real scope |
| --- | --- | --- | --- |
| 1 | `ExecutionLock` no-op on Windows; `release()` unlinks another holder's lock | `execute-json-ops.py:150-186` | **Half already fixed.** Only the unlink remains |
| 2 | `file-guard.sh` blocks `cert\|crt\|pem\|key\|p12\|pfx` with no allowlist | `.claude/hooks/file-guard.sh:93-97` | **It does not block.** Advisory, strict-profile only |
| 3 | `config.schema.json` claims "195+ patterns" for a ~47-pattern script | `config.schema.json:75,81` | Doc-only. The "wired into nothing" half is already false |

---

## 1 — `ExecutionLock.release()` unlinks a lock it may not hold

**What the backlog claims:** "`ExecutionLock` is not a lock on Windows, and `release()` unlinks
a lock another process may hold" — `execute-json-ops.py:159-183`.

**What is true at `HEAD`.** The Windows half landed already:

    class ExecutionLock:
        """File-based lock to prevent concurrent executor runs.

        Uses fcntl.flock on Unix. On Windows (where fcntl is unavailable),
        falls back to a simple lock file with no blocking detection.
        """

`:164-165` takes `fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)` whenever `_HAS_FCNTL`,
and the docstring states the Windows limitation instead of implying protection it does not have
— which is hard rule 6 applied to a docstring. **That half is closed, and the backlog row
overstates what is left.**

The remaining defect is `:183-186`:

    self._fd = None
    try:
        os.unlink(self.lock_path)
    except OSError:
        pass

`release()` unlinks the path unconditionally. On Unix this is now a narrow race rather than a
broken lock — B can `os.open` the path, block on `flock`, and have the file unlinked from under
it by A's `release()`; B then holds a flock on an unlinked inode while a third process creates a
fresh path and acquires it. Two executors run concurrently. On Windows, with no `flock` at all,
the unlink is the *entire* mutual-exclusion story and it removes whoever's turn it was.

**Proposed fix.** Do not unlink. A lock file whose presence means nothing and whose *flock*
means everything does not need removing, and removing it is what creates the race. Release
becomes: `flock(LOCK_UN)`, `close()`, leave the path. A stale zero-byte file at
`.claude/plans/.execution.lock` is not a leak worth a race — and the pid written at `:166`
makes it a diagnostic.

**Windows stays honestly unprotected.** No `msvcrt.locking` shim is proposed here. Adding one
would be a new concurrency mechanism on the enforcement path, tested on no Windows machine this
project has access to. The docstring already says what it does not do; extending that honesty
to a comment on `release()` is the correct amount of change.

**Differential-gate implications: none.** `scripts/check-protected-differential.py` imports
`shared.py` and exercises `is_protected_file`; `scripts/check-validator-differential.py` is
pinned to `src/claudekit/security/command_validator.py`. Neither reaches `ExecutionLock`, so
neither would notice this change — **which is itself the finding worth recording**: the executor's
mutual exclusion has no differential gate at all. Not proposed here (a third differential gate is
its own decision), but it belongs in the backlog either way.

**Behavioural test.** Two `ExecutionLock` instances in one process against a `tmp_path` lock:
second `acquire()` returns False while the first is held; after the first `release()`, the second
succeeds; and — the mutation-sensitive assertion — the lock path still exists after `release()`,
so reintroducing the `os.unlink` fails the test. Mutation proof both directions before I claim it
binds.

---

## 2 — `file-guard.sh` classifies by extension with no allowlist

**Correcting the framing first.** The backlog row and the handoff both say file-guard "blocks".
It does not:

    # file-guard-gate.sh — advisory wrapper around the file-guard classifier.
    # Runs `file-guard.sh` against the Edit/Write target and WARNS (never blocks)
    # ECC_HOOK_PROFILE: strict only. Exit 0 always.

`file-guard-gate.sh:21` is `[ "${ECC_HOOK_PROFILE:-standard}" != "strict" ] && exit 0`, and the
gate exits 0 on every path. So a `public.pem` produces a stderr warning, under an opt-in profile,
and the edit proceeds. **The defect is false-positive noise on an advisory channel, not a blocked
edit** — and an advisory that cries wolf gets ignored, which is the real cost.

**Site.** `.claude/hooks/file-guard.sh:93-97`:

    # 8. Certificates and private keys
    case "${basename##*.}" in
        cert|crt|pem|key|p12|pfx)
            echo "certificates"; return ;;
    esac

`public.pem`, `test-fixture.key`, `ca-bundle.crt` all classify as `certificates`. `:125`'s
`*"customer"*"data"*` is the same shape and catches `customer_data_schema.sql`.

**Proposed fix.** A name-based allowlist checked before the extension `case`, covering the three
families that are public by construction: a `public`/`pub` stem (`public.pem`, `id_rsa.pub`), a
`test`/`fixture`/`example`/`sample` component in the path, and `ca-bundle`/`ca-certificates`.
Plus one narrowing: `*"customer"*"data"*` gains a negative for `schema`/`fixture`.

**Why an allowlist and not a narrower denylist.** The extension set is *right* — `.pem` usually
is a key. The problem is that "usually" has no escape hatch, and hard rule 6's honesty applies
here too: this is a denylist speed bump, and speed bumps need marked exits or people drive around
them.

**Differential-gate implications.** `check-protected-differential.py` does **not** cover this
file — it imports `shared.py`'s `is_protected_file`. So the gate that exists for exactly this
class of change ("no change may turn a REJECT into an ALLOW") **would not fire**, and I am not
going to describe this change as gate-verified when it is not. Two options for the owner:

- **(a)** Land the allowlist with a behavioural test enumerating both directions — every allowed
  name classifies clean, every genuine secret name still classifies — and record in the backlog
  that `file-guard.sh` has no differential gate.
- **(b)** Extend `check-protected-differential.py` to a second subject (`file-guard.sh` via
  subprocess, since it is shell) *first*, then land the allowlist under it. Slower, and it is the
  option that matches why that script was written: it exists because the *first* widening of
  `is_protected_file` "sailed straight through" CI. This is a widening of a different guard.

**I recommend (b), and it is the owner's call, not mine.** It is more work and it is the one that
does not repeat a mistake this repo has already made once and documented.

---

## 3 — `config.schema.json` overpromises

**Site**, and the line numbers have moved since both the triage (`:58,64`) and the backlog (`:75`):

    $ grep -n 195 config.schema.json
    75:  "description": "Blocks access to sensitive files matching 195+ patterns (secrets, credentials, keys, certificates)"
    81:  "description": { "type": "string", "default": "Blocks access to sensitive files matching 195+ patterns" }

**Two sites, and two false claims in each.** Measured against the shipped script:

    $ grep -c 'echo "[a-z-]+"; return' .claude/hooks/file-guard.sh   # categories
    18
    # case alternatives + == comparisons, counted by script: 30 + 17 = ~47 patterns

So "195+" overstates by roughly 4×. And "**Blocks**" is wrong for the reason in §2 — the wrapper
is advisory and strict-only.

**The "wired into nothing" half of the backlog row is already false.** It claims `file-guard`,
`prompt-injection-scanner` and `check-comment-replacement` have "**0** references in
`.claude/settings.json`". `file-guard-gate.sh` and `injection-scan-gate.sh` are registered; only
`check-comment-replacement.sh` is genuinely unreferenced. Repeating the 0 would ship a third
stale claim about a file whose problem *is* stale claims.

**Proposed fix.** Replace the number with what is true and cannot rot: "Warns (advisory,
`ECC_HOOK_PROFILE=strict`) on paths matching the sensitive-file classifier's 18 categories."
No count of individual patterns in prose — hard rule 8's reasoning generalises: a hand-written
count drifts the moment the file is edited. If a number is wanted it should be generated, and
that is a bigger change than this finding earns.

**Also in scope, because it is the same sentence:** the schema documents
`check-comment-replacement` as a hook while it has zero `settings.json` references. Either the
description says "shipped, not wired" or the hook gets wired — **wiring is owner-gated and not
proposed here.**

**Differential-gate implications: none.** JSON descriptions, no decision surface. But
`ck doctor --strict` validates the shipped config against this schema (`[✓] Hooks config.json
matches config.schema.json`), so a malformed edit fails a DoD gate — that is the check that binds.

---

## Ops shape, if approved

Three configs, in dependency order, not one:

1. `ops-enforcement-trio-lock.json` — `execute-json-ops.py` `release()` + comment, and the
   behavioural test. **Touches the engine that executes every ops config, so it runs last and
   alone**, after the suite is green on the other two.
2. `ops-enforcement-trio-fileguard.json` — allowlist + test, under option (a) or (b) as decided.
3. `ops-enforcement-trio-schema.json` — the two description strings.

Per-config DoD, plus: a fresh adversarial `code-reviewer` prompted to REFUTE, per the review
floor. **The last three periods carry no independent verdict because they could not spawn
agents; if that is still true when this executes, the plan says so rather than implying a review
happened.**

## Explicitly NOT proposed

- No `msvcrt` locking for Windows.
- No wiring of `check-comment-replacement.sh`.
- No generated pattern count in the schema.
- No change to `file-guard-gate.sh`'s advisory-or-blocking status, or to its `strict` gating.
  Making it block is a user-visible enforcement change and squarely owner-gated.


## Artifacts — EXECUTED 2026-08-24, owner-approved "gate first, then widen"

Eight ops configs. Every path any of them writes is named here, because
`scripts/check-plan-artifacts.py` refuses a plan that hides its own artifacts — and it
caught this plan doing exactly that on the first run after execution.

| Path | Config | What landed |
| --- | --- | --- |
| `scripts/check-fileguard-differential.py` | `-gate`, `-gate2`, `-disclose`, `-lint` | The gate, its pre-promotion path fallback, the ten disclosed widenings, and an unused-import fix |
| `.github/workflows/ci.yml` | `-fileguard-test` | CI step "No change may un-flag a secret without disclosing it" |
| `.claude/hooks/file-guard.sh` | `-fileguard` | Allowlist ahead of the denylist; `schema`/`model` excluded from `production-data` |
| `tests/test_fileguard_allowlist.py` | `-fileguard-test` | 33 assertions, both directions, including four near-misses |
| `.claude/operations/scripts/execute-json-ops.py` | `-lock` | `release()` no longer unlinks |
| `tests/test_execution_lock.py` | `-lock-test` | 5 assertions; two fail if the unlink returns |
| `config.schema.json` | `-schema` | "195+ patterns" replaced in both places; `check-comment-replacement` labelled shipped-but-not-wired |
| `CHANGELOG.md` | `-changelog` | Fixed / Added / Changed entries |
| `tests/test_pipeline_e2e.py` | `-e2e` | A pre-existing assertion asserted the contract this change reverses: `assert not (project / ".codemanifest.lock").exists()`, justified as "the next run would be blocked by it". **That justification is disproved two assertions earlier in the same test**, which runs the executor to success with the file present. E2E-31's requirement was "no stale lock **that blocks the next run**" and the assertion had shortened it to "no lock file" — a stronger, different, and false claim under `flock`. Reconciled to the requirement as written, plus a check that the retained file carries the holder pid. The test is renamed to match what it now proves |
| `tests/test_pipeline_e2e.py` | `-e2e` | Named here as its own row: this config writes the plan document too, and the gate correctly refused the first attempt for omitting it |
| `.gitignore` | `-gitignore` | **A consequence of my own fix that I did not predict.** Not unlinking the lock means `.codemanifest.lock` now PERSISTS in the repo root after every executor run. It was untracked and un-ignored, so the first `git status` after the change showed a new file in a tree that is supposed to stay clean — and `.gitignore` already carried a sibling entry (`.claude-core.lock`) that should have made this obvious while the plan was being written. Ignored, with the reason recorded beside the entry |
| `.ai/SESSION_STATE.md`, `.ai/CHANGELOG_AI.md` | `-close` | The period record for all three approved plans |
| `.claude/plans/archive/README.md` | `-archive`, `-count` | The archive rows for this plan's three siblings, and the correction of a hand-written config count in one of them |
| `.claude/plans/plan-enforcement-trio.md`, `.claude/plans/plan-command-bash-parse-gate.md`, `.claude/plans/plan-hook-log-dedup.md` | `-plandocs`, `-status` | These three plan documents: the artifact tables above and the status headers below. Named here because `check-plan-artifacts.py` flagged their omission twice — first the code artifacts, then the plan documents themselves. The gate is right both times: a plan that does not name what it wrote cannot be reviewed for it |

**Order actually followed: gate, then widen.** The gate landed and was proven against a real
baseline *before* the allowlist was written, then the allowlist was written and the gate
**failed on all ten paths as undisclosed**, then each was disclosed with its reason. That is the
sequence the owner chose, and it is why the ten widenings are individually on the record instead
of being a diff nobody was asked about.

**Two things the plan predicted wrongly, corrected by running them.**

1. **The gate SKIPPED on its first run.** At `origin/main` there is no
   `.claude/hooks/file-guard.sh` — batch 1 promoted it out of `templates/hooks/`, so
   `git show <baseline>:<path>` failed and the script printed `SKIP` and returned 0. A gate that
   skips is a gate that passes forever, which is the exact failure this repo has recorded four
   times. Fixed with a `LEGACY_GUARD_PATHS` fallback; the run now prints
   `Baseline guard found at its pre-promotion path: templates/hooks/file-guard.sh`.
2. **`file-guard.sh` does not source `lib.sh`.** The plan's §2 assumed the differential subject
   would need `lib.sh` copied alongside a baseline extraction. It is self-contained, so the
   temp-directory extraction is enough.

**No independent review.** No `code-reviewer` verdict was obtained for this work. The review
floor asks for a fresh adversarial reviewer and this period did not run one, so this plan says
so rather than implying otherwise.

## What I got wrong while writing this

I inherited "`file-guard.sh` **blocks** `cert|crt|pem|…`" from the handoff table and the backlog
row and started drafting a fix for a blocking hook. It has not blocked since the gate wrapper
landed. Reading `file-guard-gate.sh` — 45 lines, `exit 0` on every path — changed the finding's
severity, its class, and which of the two options in §2 is defensible. The handoff's own lesson 4
says a verdict from code shape is not a verdict; I nearly filed severity from a *table row*,
which is worse.
