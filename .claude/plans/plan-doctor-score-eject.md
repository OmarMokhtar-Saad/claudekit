# Plan: doctor readiness score + `ck eject`

Slug: `doctor-score-eject` · Ops: `.claude/plans/ops-doctor-score-eject.json`
Tier: **2** (multi-file, public CLI surface, no security/schema surface)
Origin: ruvnet/ruflo review (2026-08-23) — MetaHarness readiness grading + `eject`.

## Problem

**1. `ck doctor` collapses a graded signal into a boolean.** `cmd_doctor`
(`src/claudekit/cli/main.py:220`) already tallies `checks_passed` /
`checks_failed` / `checks_warned` / `checks_skipped` and prints all four
(`main.py:496-509`), then throws the ratio away and returns 0/1. Consequence:
every project that clears the floor reads identically green, so a bare install
and a fully configured one are indistinguishable, and `/adapt` has no numeric
exit gate — "is this project properly kitted?" is re-judged per session across
16 kitted projects.

**2. There is no sanctioned exit from kit management.** The CLI offers `init`,
`update`, `uninstall` — adopt, re-adopt, remove. A project that wants to keep
its assets but stop tracking the fleet has only two options: keep drifting
under a manifest that no longer describes it, or `uninstall` and lose the
files. Fleet sync is already constrained to be surgical because downstream
changes never merge back; `eject` gives that state a name and a receipt.

## Non-goals

- No score for `ck diff`, no JSON output mode, no fleet-wide aggregation
  (follow-ups; a grep-able score line is enough to compare projects today).
- Eject does **not** delete or rewrite any asset. It removes exactly one file
  (the manifest) after copying its contents into the eject record.
- No new dependencies (hard rule 8), stdlib only, Python 3.9 target.

## Design

### A. Readiness score

New pure helper, placed next to `cmd_doctor`:

```python
def _readiness_score(passed, warned, failed):
    total = passed + warned + failed
    if total == 0:
        return 100
    return round(100 * (passed + 0.5 * warned) / total)
```

- **Skipped is excluded from the denominator**, matching the semantics already
  documented at `main.py:224-231`: a designed absence must neither inflate the
  passed count nor fail `--strict`. Excluding it does neither.
- **A warning is half credit.** A warning is a real deficiency (shellcheck
  absent, a hook unconfigured) but not a broken install, so it must move the
  number without zeroing it.
- Printed as `Readiness: NN/100` in the existing summary block.

New flag `--min-score N`: after the existing pass/fail logic decides, a score
below `N` returns 1 with a message naming both numbers. Ordering is
deliberate — a hard failure still returns 1 on its own message, so `--min-score`
can only *add* failures, never mask one. Composes with `--strict`.

### B. `ck eject`

New constant `EJECT_NAME = ".claudekit-ejected.json"`, written beside the
manifest in `<target>/.claude/`.

`cmd_eject(args)`:
1. Load manifest. Absent → if an eject record exists, report already-ejected
   and return 1; else "no manifest, nothing to eject", return 1.
2. Classify via the existing `_classify_manifest` (modified / missing /
   unchanged) — provenance, not a gate. Eject never refuses on local edits;
   preserving them is the entire point.
3. `--dry-run` prints the summary and returns 0 without writing.
4. Prompt unless `--yes` (same idiom as `cmd_uninstall`).
5. Write the eject record: kit version and mode ejected from, UTC stamp, the
   manifest's full `files` map (hashes preserved as provenance), and the
   modified/missing lists as of eject.
6. `unlink` the manifest. Nothing else is touched.

Post-conditions, all already-correct behaviour of existing commands:
- `ck diff` falls back to kit-source comparison (`_diff_against_source`,
  `main.py:666`) — provenance unknown, which is now true.
- `ck uninstall` errors "no manifest" — correct: nothing is kit-owned any more.
- `ck init` / `ck update` re-adopt deliberately, so eject is reversible.

`cmd_doctor` gains one check: eject record present and manifest absent →
`"skip"` (not a failure — an ejected install is healthy by design).

`cmd_doctor`'s `--minimal` excuse at `main.py:287-301` reads the manifest, so
after eject it would evaporate and a minimal install's absent skills/hooks
would hard-FAIL in the same run that reports the ejection as healthy. The
record carries both facts the excuse needs (`mode` and the same `files` map),
so a new `_load_eject_record` helper backs a fallback: manifest first, eject
record second. The excuse survives the ejection.

`cmd_update` treats a missing manifest as a *legacy, pre-manifest* install and
falls through to `mode or "full"` (`main.py:1066`), so re-adopting an ejected
`--minimal` project would silently reinstall it as `full` — changing what the
project ships as a side effect of a round trip advertised as reversible. The
record carries `mode` and `language`, so `cmd_update` reads it back and reports
a re-adopt instead of a legacy install.

## Files

| File | Change |
|---|---|
| `src/claudekit/cli/main.py` | `_readiness_score`, summary line, `--min-score`, `EJECT_NAME`, `_load_eject_record`, `cmd_eject`, doctor eject check + minimal-excuse fallback, argparse + dispatch entries |
| `src/claudekit/cli/main.py` | `cmd_update` restores an ejected project's recorded mode/language |
| `tests/test_doctor_score.py` | new — scoring arithmetic + `--min-score` exit behaviour |
| `tests/test_eject.py` | new — behavioural: real tree, real command, assert outcomes |
| `docs/cli.md` | doctor section updated; `eject` section added |
| `CHANGELOG.md` | `[Unreleased] / Added` |

## Test plan (behavioural, per CLAUDE.md)

`tests/test_doctor_score.py`
- `_readiness_score` boundaries: all-pass → 100; all-fail → 0; one warn of two
  → 75; empty → 100; skipped never reaches it (caller excludes).
- `ck doctor --min-score 101` on a healthy tree → exit 1, message names the score.
- `ck doctor --min-score 0` → exit 0.
- A failing check still returns 1 with `--min-score 0` (min-score cannot mask).

`tests/test_eject.py`
- Install a fixture tree with a manifest → `cmd_eject(--yes)` → manifest gone,
  eject record present, **every managed file still on disk byte-identical**.
- Record round-trips the manifest's file hashes and names the version.
- Locally-modified file is preserved and listed under `modified_at_eject`.
- `--dry-run` writes nothing (manifest still present, no record).
- Second eject on the same tree → exit 1, "already ejected".
- `ck uninstall` after eject → exit 1 (no manifest).
- `ck doctor` after eject → reports the ejected state **and exits 0**: the
  minimal excuse survives via the record.
- `ck update` after eject → re-adopts with the **original mode preserved**
  (a `--minimal` project must not come back as `full`), the stale receipt gone,
  and neither receipt filename in the new manifest.

## DoD gates

`pytest -q` · `ruff check src/ tests/ scripts/` · `mypy` ·
`gen-docs.py --check` · `gen-registry.py --check` ·
`gen-model-policy.py --check` · `check-context-floor.py --check` ·
`shellcheck` (untouched, run anyway) · `ck doctor --strict`

## Rollback

- **Code:** the change is purely additive — no existing flag, exit code, or
  command changes behaviour — so `git revert` of the single commit restores the
  prior CLI exactly. The executor also writes a backup dir per run
  (`ck rollback --list`).
- **Data:** the only file the feature removes at runtime is a target project's
  manifest, and `.claudekit-ejected.json` contains that manifest verbatim under
  its `manifest` key. Restoring it by hand is a copy of one JSON value;
  `ck update` does it automatically.

## Risk

Low. Both changes are additive: no existing flag, exit code, or command
changes behaviour. The one destructive act in the whole plan is
`manifest.unlink()`, and its contents are written to the eject record
immediately before, in the same function, so the operation is recoverable by
hand from the record alone — the record stores the entire manifest verbatim,
not a chosen subset of its fields.

## Review

`reviewer` scored the first revision **80/100 CONDITIONAL** (2 MAJOR, 2 MINOR).
All four findings are fixed in this revision: the `install.sh` exclusion sets,
the minimal-excuse fallback through the eject record, full-manifest fidelity in
the record, and `--stamp` suppressed from public help (`argparse.SUPPRESS`)
plus this Rollback section.

Round 2 scored **95/100 APPROVED**. Its one MINOR (a vacuous self-comparison in
`test_doctor_score.py`) was fixed.

**Post-approval mutation proofs changed two of those conclusions.** Every fix
was re-verified by reverting it and re-running the test that claimed to cover
it:

- Round 1's MAJOR #1 (`install.sh` must exclude the receipt from `NEVER_MANAGED`
  / `SKIP_NAMES`) rested on a false premise, and round 2 endorsed it. Both
  additions are **inert**: the manifest walk runs *before* backup restoration,
  and restoration only covers `ASSET_DIRS` (agents, commands, skills) while the
  receipt sits at the `.claude/` root — so neither set can ever see it. Proven
  by reverting each set independently and watching the tests still pass. The
  `install.sh` change was reverted rather than shipped as dead defensive code.
- The real defect in that area was the one above: `cmd_update` silently
  upgrading an ejected `--minimal` project to `full`. Its test fails when the
  fallback is reverted (`test_eject.py:174`), so it binds.
