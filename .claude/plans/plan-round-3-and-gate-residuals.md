# Implementation Plan: round 3, the two gate residuals, and the hook perf cluster

**Status:** EXECUTED 2026-08-25. Tier 3 (the file-guard half repairs a widening of a
deny-shaped decision, for the third time).

Four items, taken together because the owner asked for all four: the third adversarial review
of `8f89ae2`, the `check-plan-artifacts.py` skip count, two one-line gate residuals, and the
perf cluster (F35, F40) from the triage.

---

## Item 1 — round 3 of the review. Same class, fourth axis.

**2 High, 4 Medium, 2 Low, all confirmed by execution.** The reviewer's summary is the finding:

> Branch 8 matches the *last* element of an arbitrarily long extension chain; the repair strips
> exactly *one*. And the generated invariant — the commit's centrepiece — varies exactly one
> appended extension, so it is blind to precisely that axis.

Verified against the pre-allowlist guard (`f76f5d5`) before changing anything:

| path | pre | at `8f89ae2` |
| --- | --- | --- |
| `tests/credentials.json.pem.key` | flagged | **clean** |
| `tests/secrets.json.pem.key` | flagged | **clean** |
| `tests/passwd.pem.key` | flagged | **clean** |
| `tests/id_rsa.pem.key` | flagged | **clean** |
| `tests/wallet.dat.key.pem` | flagged | **clean** |
| `testdata/prod.sqlite.crt.pem` | flagged | **clean** |
| `.ssh/authorized_keys.pub` | flagged | **clean** |
| `.ssh/deploy.key.pub` | flagged | **clean** |
| `.kube/tests/tls.key` | flagged | **clean** |
| `secret/tests/x.pem` | flagged | **clean** |
| `certs/tests/server.key` | flagged | **clean** |
| `ssl/tests/x.key` | flagged | **clean** |

`tests/credentials.json.pem` — the exact path the previous round *added to the corpus* — stayed
flagged. Append one more suffix and it went silent.

### H1 — the strip iterates now

The single `${filepath%.*}` became a loop that peels while the trailing extension is itself a
certificate extension, re-classifying at each step and stopping at the basename so
`tests/foo.bar/key` cannot strip into its own directory (the reviewer's L2, avoided by
construction).

### H2 — the generator's axes

The generator now varies **chains** (`.pem.key`, `.key.pem`, `.crt.pem`, `.pem.pem`,
`.pem.crt.key`), **case** (`.PEM`, `.Key`), and crosses `SECRET_DIRS` with every category
exemplar — which the old version never did, testing the veto only against a basename of
`anonymous`. Branch *shapes* are covered rather than one exemplar per branch: 1,213 generated
cases, up from 481.

**Three of my first nine branch-shape cases were wrong expectations, not defects.** `app.token`,
`app.secret` and `service-account.json` classify as nothing on their own (`pre=0`), so a `.key`
under `tests/` freeing them is the *intended* widening. I checked each bare name before
asserting; asserting the expectation I had assumed would have manufactured three defects and
then "fixed" working code.

### M1/M2 — the secret-directory veto, both directions

Missing families added: `secret` (singular), `.kube`, `certs`, `certificates`, `ssl`, `tls`,
`private`, `.docker`, `.gcloud`, `.gpg`, `key`, `credential`.

And the reverse direction, which matters as much: the veto preceded the `example.*`/`sample.*`/
`dummy.*` case, silently reversing the documented promise that those names are public wherever
they live. Since `file-guard-gate.sh` passes the **absolute** path, any project rooted under a
directory called `prod` or `keys` had every fixture re-flagged — the exact false-positive noise
the allowlist exists to remove. Name-asserted public material is now checked first.
**Residual stated rather than hidden:** the veto is a name match on whatever path it is given, so
an absolute path can still contribute components from outside the project; for a
non-example-named file that errs toward FLAGGED, which is the safe direction for an advisory.

### M3 — the `.pub` bypass

`elif ... == *.pub` freed *anything* classified `ssh-keys`, and branch 3 classifies every file
under `.ssh/` — so `.ssh/deploy.key.pub` and `.ssh/authorized_keys.pub` were clean.
`authorized_keys` is an access-control file the guard lists deliberately. Now: the enumerated
`id_*.pub` names are public above the veto; every other `*.pub` is public only below it; and
`authorized_keys.pub` / `known_hosts.pub` are excluded outright.

**A related gap found and deliberately NOT closed:** nothing classifies `*.pub` outside `.ssh/`
at all — branch 8's extension set excludes `pub`, so `keys/deploy.key.pub` was clean *before*
the allowlist existed too (`pre=0`). Adding `pub` to branch 8 would flag every public key, which
is the noise this whole allowlist exists to remove. Filed, not fixed.

### M4 — a structural test that could not fail

The reviewer built a mutant restoring full v1 semantics *inside* `check_file()` and all three
assertions passed while every category was freed again. The test asserted textual location, not
application order, and its slice went vacuous if `public_material` moved above `classify`.

It now asserts **behaviour** — twelve known secrets must still classify — plus a structural hint
bounded to `classify()`'s own body (opening brace to the first closing brace in column 0), which
is neither vacuous when the function moves nor falsely red when a sibling is defined between two
others. **Proven:** the same mutant now fails 543 tests including this one.

### L1 — the baseline floor

A fixed 12-path floor proves the baseline is not empty, never that it is representative. Added a
per-category floor: the baseline must produce at least 8 distinct categories across the corpus.

### Proof the gate now catches round 3's own hole

    # 8f89ae2's guard restored, run against the pre-allowlist baseline
    $ python3 scripts/check-fileguard-differential.py --baseline f76f5d5
    FAIL: ... - secret/tests/x.pem - certs/tests/server.key - .ssh/deploy.key.pub ...
    rc=1
    # with the fix
    rc=0

---

## Item 2 — `check-plan-artifacts.py`, and my own framing was wrong twice

I called this "a naming convention, not code" and quoted a growing skip count. Measured
properly, the count conflated **two unrelated things**:

- **205 configs have no plan document at all.** Spent long ago, several predating the convention
  that a plan is written. No code can resolve those, and reporting them as "skipped" makes an
  unfixable historical residue look like a growing bug.
- **51 configs name a plan that EXISTS** but declared a step-slug (`ops-triage-refresh-records`
  against `plan-triage-refresh.md`) that resolved to nothing. **That is a real gate hole**, and
  six of the 51 were mine.

Fixed: a hyphen-boundary prefix walk, longest match first, which can only ever bind to a
`plan-<slug>.md` that really exists. The two categories are now reported separately, and the
actionable one is a `WARNING` that currently reads **zero**. Paths verified went 430 → 461.

**The first checked run of those 51 immediately found 6 real drifts** across three plans, which
are now named in those plans. Making the misdeclared count fatal is a separate, owner-gated
call — 205 legacy configs must not redden CI for history nobody can change.

**And I broke a test doing it:** dropping the config names from the NOTE reintroduced exactly the
silent-pass this gate has a test against (`test_a_config_that_resolves_to_no_plan_is_named_not_
silently_green`). Names restored, truncated at 12 with the remainder counted.

## Item 3 — the two one-liners, one of which was already done

- **`gen-docs.py` is NOT broken.** `HOOK_GLOBS = ("*.sh", "*.py")` already covers python hooks
  and it reports `hooks=26`. **My "verified just now" last turn was wrong** — I read a truncated
  `grep` showing only the agents/commands/skills globs and inferred the hooks one. The BACKLOG
  entry claiming `hooks=19` is stale; the code is fine.
- **`iron-law-gate.py` was genuinely missing two.** `_CHECK_ONLY_SCRIPTS` held
  `gen-docs.py` and `gen-registry.py`; `gen-model-policy.py` and `gen-plan-index.py` were blocked
  in **every** form, including `--check` — so the agent bound by the Iron Law could not run two of
  the checks the Iron Law's own Definition of Done demands. Both added, with tests asserting both
  directions (`--check` allowed, bare invocation still blocked) for all four.

## Item 4 — the perf cluster, measured

**F35 — `pre-commit.sh` secret scan, 9.4× faster.** It ran `git show | grep` once per pattern
inside a per-file loop: 2 subprocesses × N files × M patterns on the commit path. Now one
combined alternation as a filter, with per-pattern identification only for a file that matched.
Measured on 40 staged files: **9470 ms → 1008 ms**. Detection parity verified by planting
`api_key`, `password` and an RSA header and diffing the warnings against the old hook: identical.

**And I nearly shipped a secret-leaking log line doing it.** My first version named the match
with `grep -oiE`, which prints the *matched text* — for `api_key\s*[:=]\s*["'][^"']{8}` that is
the first eight characters of the credential, into the hook log and the transcript. A secret
scanner that prints secrets has defeated itself, and it *looks* right. Caught pre-commit, fixed
to report the pattern, and pinned by
`test_the_warning_never_echoes_the_secret_itself` — mutation-proven by restoring `grep -oiE`.

**F40 — `pre-plan.sh` duplicate check, 58× faster.** One `python3` per plan file inside a loop on
a **UserPromptSubmit** hook: ~110 interpreter startups before the user's prompt is seen. Now one
interpreter for the whole corpus. Measured with 105 plans: **5795 ms → 99 ms**, with identical
verdicts (same plan named, same clean case).

**F105 is only partly addressed.** F40 removes the worst offender; the three PreToolUse hooks
still spawn ~10 interpreters per guarded tool call. That is the single-dispatcher work, not this.

---

## The pattern across three rounds

Round 1: I proved the property I was thinking about, not the property that mattered. Round 2 was
that sentence applied to round 1's fix. Round 3 is it applied to round 2's — **and this time the
generated test I introduced as the cure varied only the axis the last defect lived on.**

Each round the mutation landed, the test bound, and the axis was wrong: extension not category,
one suffix not a chain, the veto's example not its family. Generating cases helps only where the
generator's axes are chosen adversarially, which is a judgement the generator cannot make for
you. The differential gate caught what the generator missed and vice versa, twice — that pair is
worth more than either alone.

## Artifacts

| Path | Config |
| --- | --- |
| `.claude/hooks/file-guard.sh` | `ops-review-3-guard`, `ops-review-3-pub` |
| `scripts/check-fileguard-differential.py` | `ops-review-3-gate` |
| `tests/test_fileguard_allowlist.py` | `ops-review-3-gen`, `-shapes`, `-slice` |
| `scripts/check-plan-artifacts.py` | `ops-gate-residuals`, `-names` |
| `.claude/hooks/iron-law-gate.py` | `ops-gate-residuals` |
| `tests/test_check_plan_artifacts.py`, `tests/test_iron_law_hook.py` | `ops-gate-residuals-tests`, `-testfix` |
| `.claude/plans/plan-dispatcher-payload.md`, `.claude/plans/plan-fleet-skill-enhancement.md`, `.claude/plans/plan-protected-docs-scope.md` | `ops-gate-residuals-plans` |
| `.claude/hooks/pre-commit.sh` | `ops-perf-hooks-f35`, `-f35b` |
| `.claude/hooks/pre-plan.sh` | `ops-perf-hooks-f40` |
| `tests/test_day_one_blockers.py` | `ops-perf-hooks-test` |
| `CHANGELOG.md`, `.ai/BACKLOG.md`, `review/code-review-triage.md`, `.claude/plans/plan-round-3-and-gate-residuals.md`, `.claude/plans/archive/README.md` | `ops-round3-docs` |

## Definition of Done

Full gate list, suite output to a file and read from the file, `Plan-Id: round-3-and-gate-residuals`,
configs archived with a README row, `INDEX.md` regenerated against the committed tree only —
another session is working in this repo and its plans must not be recorded prematurely.

**A fourth review has not been run.** Three rounds, three sets of confirmed High findings in the
previous round's fix. I would not describe the file-guard allowlist as settled.
