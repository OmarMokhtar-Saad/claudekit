# Implementation Plan: discharge the second adversarial review (a1d695f + bc20e2d)

**Status:** EXECUTED 2026-08-24. Tier 3 — it repairs a widening of a deny-shaped decision,
for the second time.

Round 2 found **5 High, 4 Medium, 8 Low, every one confirmed by execution.** Round 1 fixed
`d945278`; this round found that **the fix was wrong in the same direction**, and the corpus
written to catch it was blind in the same way. Every finding is discharged below.

## The verdict that matters, again

> The repair narrowed one axis of an over-wide rule and left another axis open.

`classify()` returns on the **first** match. Round 1's repair gated the allowlist on the file's
**extension** — but extension is not category, so every `.key`/`.pem` still reached the
certificate branch before branches 9–13 could claim it. Verified before fixing:

    k8s/tests/secret-tls.key      rc=0   (canonical checked-in TLS secret)
    tests/fixtures/.ssh/deploy.key rc=0
    tests/api_key.key             rc=0
    pii/tests/customers.key       rc=0
    production/tests/data.key     rc=0

My commit message said the allowlist was "UNREACHABLE for any other extension". True, and
irrelevant — which is exactly what the reviewer said about round 1's claim, one round earlier.

## What the fix is now (H1)

The allowlist moved **out of `classify()` entirely** and into `check_file()`, where it is applied
to the *classification*:

1. `classify()` is pure again — no exemptions inside it.
2. If the verdict is `certificates`, ask **would any other category have fired?**
   (`classify "$filepath" skip_certs`). If yes, that category wins.
3. Also ask what the file is with the certificate suffix **removed** — see below.
4. Only then consult `public_material()`.

`ssh-keys` keeps a narrow exemption for `*.pub`, because a public key is the half you publish.

## The generated invariant — because this class has now shipped three times (H5)

Three occurrences of one class earn a mechanical check, not more examples. Both previous corpora
were thorough and both were blind, each written around the hole that had just been found.

`tests/test_fileguard_allowlist.py` now generates the cross product of **12 non-certificate
category exemplars × 6 test-shaped directory prefixes × 6 certificate extensions**, asserting the
file stays flagged. On first run it failed **151 cases** — more than the review found:

    tests/credentials.json.pem    tests/credentials.json.key   ...
    testdata/wallet.dat.key       fixtures/prod.sqlite.crt     ...
    secrets/backup.bak.p12        ...

**A new sub-class the review did not report.** Appending a certificate suffix breaks the
*exact-basename* match those categories rely on (`credentials.json`, `wallet.dat`, `prod.sqlite`,
`backup.bak`), so only the certificate branch fires. Fixed by step 3 above: strip the suffix and
re-classify. All 150 pass.

**And the differential gate then caught one the invariant could not:** `k8s/tests/tls.key`.
Branch 13 requires the literal word "secret" in the path, so a TLS key named `tls.key` never
reaches it. "No stronger category fired" turned out not to mean "nothing about this path is
sensitive", so `public_material()` now refuses any path under `k8s/`, `kubernetes/`, `pii/`,
`production/`, `prod/`, `secrets/`, `credentials/`, `.ssh/`, `.aws/`, `.gnupg/`, `vault/` or
`keys/`. **Two independent mechanisms each caught what the other missed** — that is the argument
for having both.

## H4 — the schema exclusion, third attempt

Round 1 anchored to `${basename%%.*}`, which the reviewer showed still frees
`customer_data_schema.sql.bak` — stripping *every* suffix leaves a stem ending `_schema`. My own
repair reproduced that: `.sql.bak`, `.csv.gz`, and `customer/data/dump-schema.csv` (the words are
directories) all came back clean on the first attempt.

Now **two conditions, both required**: the stem must *end* in `-schema`/`_schema`/`-model`/`_model`,
**and** the extension must be a description format (`sql|md|json|yaml|yml|graphql|prisma|proto|xsd|rst|txt`).
A `.bak`, `.gz` or `.csv` is data no matter what the stem says. Predicate on the path, exclusion on
the basename.

## H2, H3, M1 — the session-context scan, honestly bounded

- **H2:** the scanner was resolved from a **cwd-relative** candidate, so anyone who can write the
  context file — precisely the threat model — could drop their own `exit 0` scanner beside it and
  the payload printed. Verified. That candidate is gone; only `$SCRIPT_DIR` is consulted.
- **H3, and this one is a claim I have to withdraw.** The scanner is a **25-phrase keyword
  denylist**. A payload written to evade it — "Disregard the safety rules above" — passes, and the
  content prints. My CHANGELOG said this path is now covered by "the mitigation [that] existed";
  what exists catches naive shapes. **Restated in CHANGELOG and in the test docstring as exactly
  that, with no upgrade in tone.** The structural fix (withhold by default, print only on explicit
  `/resume-session`) is a UX change and is filed, not taken.
- **M1:** the scanner exits non-zero when it *fails*, not only when it detects — `set -e` plus a
  cwd-relative `LOG_FILE` made a benign input exit 1 in any cwd without `.claude/hooks/`. So
  `session-start.sh` reported "matched an injection pattern" about an innocent file, permanently.
  Measured before: `rc=1` + `No such file or directory`. After: `rc=0`, detection still `rc=1`.
  Exit 1 is now distinguished from exit >1, and the scanner's `LOG_FILE` is `$SCRIPT_DIR`-relative
  — which also closes **F107's fourth form**, the one the previous commit flagged as not-fixed.

## M2, M3, M4 — the crypto check, both directions

- **M2:** stripping only *line-leading* comments left the trailing-comment case live — the very
  fixture that misled me one commit earlier. Now end-of-line comments and docstrings are stripped
  too. **And the bare-word branch is gone entirely**, because `BANNED = ["RC4", "MD5"]` — a
  *denylist* — still warned, and a string literal is not a comment. A check that fires on a file
  forbidding MD5 is the false positive that makes an advisory ignorable.
- **M3:** the module-adjacent pattern caught one spelling. `import hashlib as _h; _h.md5()`,
  `from hashlib import md5`, `hashlib . md5(`, `getattr(hashlib, "md5")` were all silent. Now
  matched by call shape, plus an import shape — that last one added because removing the bare-word
  branch dropped `from Crypto.Hash import SHA1`, which **one of my own earlier assertions caught**.
- **M4:** the `PARTIAL SCAN` notice went to **stderr** while the warnings it qualifies go to
  stdout, and a PreToolUse hook exiting 0 does not surface stderr. So the "silence" I said I fixed
  was still silent where it mattered, and my test passed only because it merged the streams. Now
  on stdout, asserted on `proc.stdout` alone.

## Lows

**L1** `head -c 4000` as well as `head -20` (a 2 MB single line printed in full). **L2** `fchmod`
after acquisition — the `0o600` on `os.open` applies only at creation, so a lock file from a
pre-fix run kept mode `0o666` forever. **L3** the pid test compared against `os.getpid()`, which
holder and contender share, so truncate-then-write passed; now a sentinel. **L4** `[a-z0-9-]` in
the category regex — `k8s-secrets` did not match, so a legitimate category was reported as the
`flagged-uncategorised` sentinel meant for a broken guard. **L5** the baseline canary checked 2 of
67 paths; now a 12-path root-level floor. **L7** extension matching lowercased (`SERVER.PEM` was
clean, and the extension is now load-bearing). **L8** a non-string `content` value is refused
rather than scanned as a `repr`.

**L6 is the one worth reading.** The fence census asserted against a hardcoded list of seven
"suspicious" tags, so a new spelling passed silently — and since the corpus holds only
bash/markdown/json/text, **the test could not fail at all.** Inverted to an allowlist, it
immediately failed on ```` ```Every ````, ```` ```Status ````, ```` ```FOR ```` — **my own regex
bug**: in Python `\s` matches a newline, so `^\s*```\s*(\w+)` was reading the first word of the
line *after* an untagged fence. The denylist version had hidden it. Fixed to `[ \t]*`.

## L5's floor, and a design choice worth recording

My first version of the floor required half the corpus to be flagged. It fired against
`d945278` — which flags 31 of 76 because that is the commit whose bug this gate exists to catch.
Conflating "broken baseline" with "buggy baseline" would make the gate refuse to run in exactly
the case it is for. The floor is now 12 named root-level, category-diverse secrets.

## What the reviewer confirmed as fixed

Round 1's H1 (root-level and non-cert shapes), H2 (corpus, partially — now fully), H3 (`pii/`
veto), M1 (`O_TRUNC`), M2 (guarded assertion), M3 (fence spelling), L2 (empty baseline). Their
verdicts are in the round-1 plan; only the still-open halves are re-fixed here.

## The lesson, and it is the same one

Round 1: *I proved the property I was thinking about, not the property that mattered.* Round 2 is
that sentence applied to the fix for round 1. The pattern is not carelessness about evidence — I
ran mutation proofs both times — it is **choosing the axis to vary**. Extension instead of
category. Line-leading instead of end-of-line. Stem instead of extension type. Each time the
mutation landed, the test bound, and the axis was wrong.

The only thing that broke the pattern was **generating** the cases instead of choosing them:
151 failures on first run, one sub-class nobody had named, and then a second mechanism catching
what the generator missed. That is what goes in the review guide.

## Artifacts

| Path | Config |
| --- | --- |
| `.claude/hooks/file-guard.sh` | `-guard`, `-h4`, `-strip`, `-dirs` |
| `.claude/hooks/session-start.sh`, `.claude/hooks/prompt-injection-scanner.sh` | `-session` |
| `.claude/hooks/security-reminder.sh` | `-crypto`, `-strip2`, `-bareword`, `-import` |
| `scripts/check-fileguard-differential.py` | `-gate`, `-floor` |
| `.claude/operations/scripts/execute-json-ops.py` | `-lock` |
| `tests/test_fileguard_allowlist.py` | `-invariant`, `-strip`, `-dirtests` |
| `tests/test_security_reminder_coverage.py`, `tests/test_session_context_scan.py` | `-tests` |
| `tests/test_execution_lock.py` | `-lock` |
| `tests/test_command_bash_parse.py` | `-census`, `-regex` |
| `CHANGELOG.md`, `.claude/plans/plan-review-round-2.md`, `.claude/plans/archive/README.md`, `.ai/SESSION_STATE.md` | `-docs` |

## Definition of Done

Full gate list, suite output to a file and read from the file, `Plan-Id: review-round-2`, configs
archived with a README row, `INDEX.md` regenerated after committing. **A third review has not
been run.** Given that rounds 1 and 2 each found real High findings in the previous round's fix,
the prior on a third round finding something is not low.
