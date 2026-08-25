# Implementation Plan: round 4, and the corpus that derives itself

**Status:** EXECUTED 2026-08-25. Tier 3.

Fourth adversarial review of the file-guard allowlist: **2 High, 3 Medium, 2 Low, all
confirmed by execution.** It also subsumes the two residuals I had filed against my own
round-3 work (item 4 of the owner's list), so those are closed here rather than separately.

## The reviewer verified the four closed axes are genuinely closed

Stated first because it is the part I did not have to take on trust: rounds 1-3's fixes were
re-verified by execution against both baselines, a 200-link chain terminates, all ten
`DISCLOSED_WIDENINGS` entries are still reachable, and **both tests the prompt singled out as
likely-vacuous were proven non-vacuous.** Round 3's work is real.

## H1 — the fifth axis: chain COMPOSITION, not chain length

Branch 8 matches the last element of a chain and cares nothing for what precedes it. My peel
loop walked only chains made **entirely** of certificate extensions:

    case "$_peeled_ext" in
        cert|crt|pem|key|p12|pfx|pub) ;;
        *) break ;;                      # <-- one .gz and the walk stops

Interpose one ordinary wrapper and round 3's hole reopens. **100 of 360 generated cases freed**,
verified against the pre-allowlist guard:

    tests/credentials.json.gz.key    flagged -> clean
    tests/id_rsa.tar.pem             flagged -> clean
    tests/passwd.bak.crt             flagged -> clean
    tests/wallet.dat.zip.p12         flagged -> clean
    testdata/prod.sqlite.gz.key      flagged -> clean

`.gz` and `.bak` are the *likeliest* real interposition — a compressed or backed-up key.

**Fix, and the reviewer's argument for it is the good part:** peel ANY suffix. Over-peeling is
safe by construction, because `classify` on a shorter stem can only ever *return* a category,
never remove one — so the extension restriction was pure loss with no compensating safety. The
`*.*` guard already prevents stripping into a directory, which was the only stated reason for
a bound.

## H2 — the gate certified this commit's own widening as clean

Round 3's M2 hoisted `example.*`/`sample.*`/`dummy.*` above the secret-directory veto. That
freed real paths — `secrets/example.key`, `vault/sample.pem`, `keys/dummy.key`,
`.aws/example.pem`, `.gnupg/sample.key`, `production/dummy.p12` — and the differential gate
reported **"OK: no undisclosed path lost its flag"** at that exact baseline, because not one
corpus path had an example/sample/dummy basename inside a secret directory. `DISCLOSED_WIDENINGS`
gained zero entries. **Third time the corpus was blind precisely because it was rebuilt around
the previous hole.**

Fixed two ways. The paths are in the corpus (the gate now FAILS on that same run — proven by
restoring the old guard and re-running). And the ordering is reverted: only names asserting a
**cryptographic role** (`public.*`, CA bundles) sit above the veto. `example.`/`sample.`/`dummy.`
assert an *author's intent*, which is the exact class of claim the veto exists to distrust — its
own comment argues a `tests/` component is not evidence, and a filename prefix is under
identical authorial control. They now sit below it.

## The ratchet, and this is the durable part

Five occurrences of `correction-narrower-than-the-predicate-it-corrects` across five rounds.
The reviewer's diagnosis is exact: *more hand-picked examples cannot close it, because the
hand-picking IS the class.* Each round's corpus was written around the hole just found and was
blind to the next by construction.

So the corpus now **derives itself from the guard**. `tests/test_fileguard_allowlist.py` extracts
branch 8's extension set, the veto's directory list and the test-component list **out of
`file-guard.sh` at test time**, and crosses them with category exemplars and wrapper suffixes.
3,566 cases. A correction narrower than its predicate now fails in the round it is written.

**Proven:** restoring the round-3 guard fails
`test_a_wrapped_secret_keeps_its_category[tests/credentials.json.gz.cert]` on the first case.

**And the derivation bit me immediately, which is the honest part.** My first extraction regex
searched for the next `case` after `# 8. Certificates` and — because `re.S` let `.*?` cross the
branch — matched the *production-data description list* (`sql|md|json|...|txt`). 1,981 cases
then asserted an invariant that is not one: branch 8 fires only when the LAST extension is a
certificate one, so those paths were clean before and after and there was nothing to catch. **A
wrong derivation manufactures defects as confidently as a blind corpus hides them.** Anchored to
`echo "certificates"` with an assertion that `pem` is in the result, so a mis-extraction fails
loudly; `test_the_extractions_are_not_empty` guards the collapse-to-empty case.

## M1 — a floor that was implied by the floor it strengthened

My 8-distinct-category baseline check was vacuous against the exact adversary its own comment
named. `BASELINE_FLOOR`'s twelve paths span 9-10 categories on their own, so any baseline
clearing the path floor cleared the category count automatically. Measured on a floor-only
baseline: `floor_missing: 0`, 10 categories, both gates PASS, 78 of 90 corpus paths look clean.

Now it compares against **HEAD**: for every category HEAD produces, the baseline must produce it
somewhere. Same floor-only baseline: **13 categories blind, gate FAILS.**

## M2 — the veto was case-sensitive on a case-insensitive filesystem

`K8s/tests/tls.key` — the canonical case the veto was written for — freed by one capital letter,
along with `SECRETS/`, `PII/`, `Production/`, `.SSH/`. On the APFS this project targets those are
*the same directories* as their lowercase forms, so it was a live bypass. The path is lowercased
once before the veto, and uppercase forms are in both corpora.

## Lows

**L1** `${_peeled##*/}` instead of `$(basename ...)` — half the forks removed from the peel loop.
**L2** is H2's ordering question, resolved above in the reviewer's direction.

## M3 — recorded, NOT fixed (pre-existing, out of diff)

`txt`, `json`, `yaml` and `sql` in the description-extension list free real data:
`db/customer-data/full_schema.sql`, `export/customer/data/rows_model.json`,
`customer-data-model.txt`. The comment's justification is false for three of its own members —
`.sql` is the standard container for an `INSERT INTO` dump. `production/` and `pii/` are immune,
which contains the damage to `*customer*data*` paths. Filed rather than bundled: it predates this
diff and gating H1's fix on it would be the mistake the reviewer explicitly warned against.

## Artifacts

| Path | Config |
| --- | --- |
| `.claude/hooks/file-guard.sh` | `ops-review-4-guard` |
| `tests/test_fileguard_allowlist.py` | `ops-review-4-derived`, `-extract` |
| `scripts/check-fileguard-differential.py` | `ops-review-4-gate` |
| `.claude/hooks/command-log-audit.sh`, `.claude/hooks/cost-tracker.sh` | `ops-triage-tail`, `-audit` |
| `.claude/operations/scripts/restore-backup.py` | `ops-triage-tail` |
| `tests/test_hook_log_delegation.py` | `ops-triage-tail-tests`, `-audit-test`, `-import` |
| `.ai/BACKLOG.md` | `ops-triage-tail-backlog` |
| `CHANGELOG.md`, `.claude/plans/plan-round-4-derived-corpus.md`, `.claude/plans/archive/README.md`, `review/code-review-triage.md` | `ops-round4-docs` |

## Definition of Done

Full gate list, suite output to a file and read from it, `Plan-Id: round-4-derived-corpus`,
configs archived with a README row, `INDEX.md` generated against the committed tree only
(another session is active in this repo).

**No fifth review has been run.** Four rounds, four sets of confirmed High findings in the
previous round's fix. The difference this time is that the corpus is derived rather than
hand-picked — which is a structural claim, and the only honest test of it is whether round 5
finds a sixth axis anyway.
