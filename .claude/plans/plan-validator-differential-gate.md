# Implementation Plan: a mechanical check for the class that kept getting through

> Recommended as a follow-up by round 3 of the adversarial review, and by every round before it.
> Owner asked for it, so it is scoped here.

## Why

`command_validator.py` shipped **five** fail-opens in this batch. Every one was found by
*executing payloads*, and none by reading the diff — including two that three plan-review rounds
had already read and approved. Two of the five were introduced by the fix for the previous one.

`.ai/REVIEW_GUIDE.md` records both classes as unmechanised:
`validator-executor-divergence` ("nothing yet — 2 seams") and `fix-introduces-larger-hole`
("nothing mechanical, and probably nothing can be"). That second verdict is wrong for this
seam, and this plan withdraws it with a working check rather than an argument.

## What it does

`scripts/check-validator-differential.py` builds the validator from a git baseline and from the
working tree, runs a generated payload corpus through both in **both `safeMode` states**, and
fails on any payload whose verdict moved **REJECT → ALLOW**. That direction is the whole point:
tightenings are free, widenings must be declared.

- **Declared, not suppressed.** `DISCLOSED_WIDENINGS` entries carry a payload pattern, the
  **baseline verdict** they apply to, and a written reason. The baseline-verdict narrowing is
  what stops a broad pattern (`#`, `\beval\b`) from absorbing an unrelated regression — and one
  entry states its own residual narrowing risk rather than hiding it.
- **Baseline is `auto`:** the merge base with `main`, falling back to `HEAD~1`, and the report
  says which it used. A gate whose baseline is ambiguous is one nobody can act on.
- **A missing baseline SKIPS, it does not pass**, and `--require-baseline` (which CI passes)
  turns that skip into a failure. Two false-PASS routes were found in review and closed, both
  of which would have made this gate green forever:
  * a shallow CI checkout has no `origin/main` and no `HEAD~1`, so `auto` fell through to
    comparing HEAD with itself — hence `fetch-depth: 0` and `--require-baseline`;
  * on a push to `main`, `origin/main` already points at the commit under test, so the merge
    base **is** HEAD while the label still reads "merge-base with origin/main". The check is
    therefore on the resolved SHA, not on the label.
- **`--max-len < 2` is refused**: a corpus of single tokens proves nothing.
- **Widenings are keyed on the EXACT baseline verdict.** The first draft keyed eval/exec on the
  shared `Dangerous pattern (` prefix, which absorbed every other category — IFS evasion,
  interpreter smuggling, fork bombs — for any payload containing the word `eval`, and the
  corpus contains `eval `. A test now forbids that prefix.
- **An exception counts as REJECT**, never as a widening.

Seeded with four entries, all already disclosed in `CHANGELOG.md`: the fd-digit widening,
argument-position `eval`/`exec`, and comment-only lines (which now validate because a line that
is *only* a comment runs nothing in bash either — measured against the branch's merge base:
625 disclosed widenings matched, **zero undisclosed**).

## What it is not

Not a proof. It fuzzes an alphabet of shell metacharacters with two blocklisted commands; it
does not model bash. A clean run means "no payload in this corpus regressed" — the script's own
docstring says so, because the failure mode of a gate like this is being quoted as soundness.

## Implementation Steps

1. `scripts/check-validator-differential.py` — new.
2. `tests/test_validator_differential.py` — new. **Every test builds a mutant of the REAL
   validator** (a one-substitution copy, not a stub) and asserts the gate reports it: a removed
   blocklist entry, and the newline bypass reintroduced. Plus: an identical module must pass, a
   disclosed entry must not hide a defect with a different baseline verdict, `auto` must resolve
   to a real commit, a missing baseline must SKIP, and an exploding validator must count as
   REJECT.
3. `.github/workflows/ci.yml` — one step in the existing **`coverage`** job, plus
   `fetch-depth: 0` on that job's checkout.
4. `.ai/REVIEW_GUIDE.md` — update both ratchet rows, including withdrawing the "probably nothing
   can be" verdict for this seam.
5. `CHANGELOG.md`.

## Testing Strategy

The gate's own tests are mutation tests by construction — a gate that has never been shown to
fail is not evidence. Measured before this plan was written: dropping `"rm"` from the blocklist
produces 644 regressions at `--max-len 3`; the unmodified tree produces 0. Plus the full suite,
`ruff`, `mypy`, and a CI run.

## Risk

- **Medium:** a new CI gate that can block merges. Mitigated by the SKIP path, the declared
  widenings, and `--max-len` bounding the corpus (9,702 payloads × 2 modes ≈ seconds).
- **Low:** false positives are self-describing — the failure prints each payload and the verdict
  the baseline gave.

## Rollback

`git revert` — two new files, three small edits. The CI step is the only thing that can block,
and removing it is a one-line change.
