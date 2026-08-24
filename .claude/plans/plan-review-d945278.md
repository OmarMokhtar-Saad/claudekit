# Implementation Plan: discharge the adversarial review of `d945278`

**Status:** EXECUTED 2026-08-24. Tier 3 — it repairs a widening of a deny-shaped decision.
9 ops configs.

The review I said `d945278` did not have. It found **3 High, 4 Medium, 2 Low, all CONFIRMED by
execution**, and the two High findings are the same defect seen twice: **I widened a security
classifier further than I claimed, and the gate I wrote in the same commit to catch exactly that
could not see it.** Every finding is discharged below.

## The verdict that matters

> The commit's own headline claim — "narrow on purpose… never substring" — is true about
> *substrings* and false about *scope*.

That is exactly right, and it is the sentence I should have written myself. I tested the property
I was thinking about (stem versus substring) and never tested the property that mattered (which
branches the allowlist skips). `.claude/hooks/file-guard.sh`'s `classify()` returns early, so an
allowlist placed at the top is not a certificate exemption — **it is an exemption from all
thirteen categories.**

**Verified independently before fixing anything**, against the real pre-commit guard extracted
with `git show d945278^:.claude/hooks/file-guard.sh` (my first attempt at this comparison read
`0` for every path because the extraction silently produced nothing — the same mutation-did-not-land
trap, on the third occurrence in two days):

| path | before | after `d945278` |
| --- | --- | --- |
| `tests/fixtures/.env` | BLOCKED `env-files` | **clean** |
| `test/secrets.json` | BLOCKED `api-tokens` | **clean** |
| `tests/credentials.json` | BLOCKED `credential-files` | **clean** |
| `tests/id_rsa` | BLOCKED `ssh-keys` | **clean** |
| `testdata/wallet.dat` | BLOCKED `crypto-wallets` | **clean** |
| `spec/fixtures/terraform.tfstate` | BLOCKED `cloud-configs` | **clean** |
| `home/tests/.aws/credentials` | BLOCKED `cloud-configs` | **clean** |
| `k8s/tests/secret-db.yaml` | BLOCKED `k8s-secrets` | **clean** |
| `pii/model_training_data.csv` | BLOCKED `production-data` | **clean** |
| `pii/customer_model.csv` | BLOCKED `production-data` | **clean** |
| `pii/datamodel.csv` | BLOCKED `production-data` | **clean** |
| `customer-data-schema-dump.sql` | BLOCKED `production-data` | **clean** |
| `model-customer-data.csv` | BLOCKED `production-data` | **clean** |

A checked-in `.env` under `tests/fixtures/` and a `terraform.tfstate` under `testdata/` are the
two commonest real shapes of a leaked secret. Both went silent.

**The bound, stated because it is real and not because it excuses anything:** `file-guard-gate.sh`
is `strict`-profile only and `exit 0` always, so this was a loss of *detection coverage on a
warning channel*, never a bypassed block. The reviewer reached High rather than Critical for that
reason and I agree with the call.

**The CHANGELOG claim was also false.** It said "every path it frees is enumerated with its reason
in `DISCLOSED_WIDENINGS`". The path-component rule frees an *unbounded* set; ten examples were
enumerated. Corrected.

---

## H1 — the allowlist is now scoped to the extensions that motivated it

`.claude/hooks/file-guard.sh:36-70`. The three allowlist rules are nested inside

    case "${basename##*.}" in
        cert|crt|pem|key|p12|pfx|pub)

so the allowlist is **unreachable** unless the file carries a certificate/key extension. `pub` is
in the set for `id_rsa.pub`. Everything else — `.env`, `credentials.json`, `id_rsa`, `wallet.dat`,
`*.tfstate`, `passwd`, `*.sqlite`, `.pgpass`, `.npmrc`, k8s and `pii/` — keeps its flag under any
directory name.

**Why scoping rather than deleting the component rule:** the false positives that motivated it are
real (`tests/fixtures/test.pem` is not a secret) and the extension set is where that judgement
belongs. The fix makes the *stated* scope the *actual* scope.

## H3 — the schema/model exclusion no longer reaches past the predicate it corrects

`.claude/hooks/file-guard.sh:148-165`. `production/*data*` and `pii/*` are now **unconditional**,
in their own branch. The exclusion applies only to `*"customer"*"data"*`, and is anchored to the
`-schema.` / `_schema.` / `-model.` / `_model.` **shapes** rather than the bare substrings — so
`customer-data-schema-dump.sql` (a dump *is* data) and `pii/datamodel.csv` stay flagged, while
`customer_data_schema.sql` and `docs/customer-data-model.md` remain freed as intended.

## H2 — the gate's corpus was drawn from the change it was policing

`scripts/check-fileguard-differential.py:46-80`. Not one of the original "genuine secret" entries
carried a `test`/`tests`/`testdata`/`fixtures` component, and all four component-bearing entries
were the allowlist's own `.pem`/`.key`/`.p12`/`.crt` targets. **A corpus drawn from the change
under test can only confirm it.**

Nineteen paths added — one per category under a test component, plus the `pii/` and dump shapes.
Mirrored in `tests/test_fileguard_allowlist.py`'s `STILL_FLAGGED`.

**Proven both ways, which is the whole point:**

    # with the original blanket allowlist restored
    $ python3 scripts/check-fileguard-differential.py --baseline d945278^
    FAIL: ... - tests/fixtures/.env [was env-files] ... - model-customer-data.csv [was production-data]
    rc=1
    # with the fix
    rc=0

and `tests/test_fileguard_allowlist.py` goes **16 failed / 33 passed** against the original defect,
49 passed against the fix. Before this change, both reported success.

The reviewer's aggravating note is the sharpest part of the finding and is worth repeating: once
`d945278` reaches `origin/main`, `--baseline auto` resolves to a merge-base that *contains* the
allowlist, so those paths could never have been re-detected. **The blindness was permanent, not a
one-run miss.**

## M1 — `O_TRUNC` destroyed the pid the persisting file exists to carry

`execute-json-ops.py:161-172`. `O_TRUNC` truncates on **open**, before the `flock` that decides
ownership — so a contender that goes on to be *refused* still empties the file first, in exactly
the situation the pid is for. Measured before: A holds, file reads `85189`; B refused; file reads
``. Now: open without `O_TRUNC` at mode `0o600`, `ftruncate` **after** the lock is ours. Measured
after: the pid survives a refused acquisition, mode `0600`. The comment that said "zero-byte file
holding the last holder's pid" was self-contradictory and is rewritten.

## M4 — the refusal message told the operator to reopen the race

`execute-json-ops.py:206-215`. It said "remove the lock file if stale"; following that while a
holder is live lets a third process acquire a *fresh* path. Harmless when a leftover file was
abnormal — and `d945278` made it the normal post-run state. The message now names the holding pid
(`_holder_hint()`), says plainly **not** to delete the file, and explains that a dead pid means the
flock is already gone so a retry simply succeeds.

## M2 — the reversed e2e assertion was guarded by the property it should assert

`tests/test_pipeline_e2e.py:555-563`. My replacement was `if lock.exists(): assert ...isdigit()`.
The reviewer confirmed the *reversal* was justified — `recovered` at `:543` runs the executor to
success with the file present, so E2E-31 never required the file's absence — but the replacement
was weaker than I described: restoring `os.unlink` made the branch dead and left the test green.
Now unconditional in both halves.

## M3 — the parse gate was evadable by fence spelling

`tests/test_command_bash_parse.py`. It matched `startswith("```bash")` only, so ` ```sh ` and
` ``` bash ` (a space, valid in common renderers) returned zero findings for a body that ` ```bash `
flags. No such fence exists in the corpus today, which is what made it a drift hole rather than a
live miss — **and nothing enforced the spelling.** Now `bash|sh|shell|zsh` with optional space and
attributes, plus two new tests: every alternate spelling is linted, and a census test fails if a
command file starts using a shell-ish tag the gate does not cover.

## L1 — delegating `log()` broke the graceful degradation the source guard promises

`.claude/hooks/{format-typecheck,security-reminder,session-start}.sh`. `[ -f "$SCRIPT_DIR/lib.sh" ] &&`
promises the hook survives a missing library; `log() { hlog "$@"; }` made it print
`hlog: command not found` to stderr per call, where the old body ended in `2>/dev/null`. Added
`command -v hlog >/dev/null 2>&1 || hlog() { :; }`. Verified by running `session-start.sh` from a
directory holding only that file: zero `command not found` lines.

## L2 — an empty baseline made the gate green

`scripts/check-fileguard-differential.py:190-200`. `bash` on an empty script exits 0, so a
truncated `git show` would make every `was` read `None`, record no regressions, and print OK. The
gate now refuses a baseline that cannot flag `.env` and `id_rsa`.

---

## What the reviewer could not break, recorded because a negative result is a result

Stem/substring matching (`publickeys.pem`, `latest.pem`, `samples.key`, `contest/prod.key`,
`.env.example` all still flagged); `classify()`'s `flagged-uncategorised` sentinel; `_is_disclosed`
exact-string matching; `LEGACY_GUARD_PATHS` and `--baseline auto` resolution; the line-number
arithmetic in the parse gate; no `lib.sh` name collisions, no source-time side effects, no stdin
consumption, `SCRIPT_DIR` defined before use, no `log()` call before the source line, profile gates
unchanged.

## Out of scope, filed not fixed

`ruff` reports 5 findings in `.claude/operations/scripts/execute-json-ops.py` (unsorted imports,
an unused `PROTECTED_PATTERNS` import, three placeholder-free f-strings). **All five predate
`d945278`** — verified against that commit — and this path is outside the DoD's
`ruff check src/ tests/ scripts/` scope, which `.ai/BACKLOG.md` already records as a gap.

## The lesson, stated once

Three of the four defects in `d945278` and all three High findings here share one shape: **I proved
the property I was thinking about and not the property that mattered.** The stem/substring tests
were correct and irrelevant; the corpus was thorough and self-confirming; the e2e assertion was
reversed for a sound reason and then written so it could not fail. An adversarial reader found in
eight minutes what four mutation proofs of my own did not. **The review floor is not a formality,
and I argued for skipping it by noting nobody was available.**

## Artifacts

| Path | Config |
| --- | --- |
| `.claude/hooks/file-guard.sh` | `-guard` |
| `scripts/check-fileguard-differential.py` | `-gate` |
| `tests/test_fileguard_allowlist.py` | `-tests` |
| `.claude/operations/scripts/execute-json-ops.py` | `-lock` |
| `tests/test_pipeline_e2e.py`, `tests/test_command_bash_parse.py` | `-tests2` |
| `tests/test_execution_lock.py`, `tests/test_command_bash_parse.py` | `-tests3` |
| `.claude/hooks/format-typecheck.sh`, `.claude/hooks/security-reminder.sh`, `.claude/hooks/session-start.sh` | `-hlog` |
| `tests/test_hook_log_delegation.py` | `-hlog-test` |
| `CHANGELOG.md`, `.claude/plans/archive/README.md`, `.ai/SESSION_STATE.md`, `.claude/plans/plan-review-d945278.md` | `-docs` |

## Definition of Done

The full gate list, suite output written to a file and read from the file, `Plan-Id: review-d945278`,
configs archived with a README row, `INDEX.md` regenerated after committing. **A second adversarial
review of THIS commit is the obvious next step and has not been run** — saying so is the whole
point of the section above.
