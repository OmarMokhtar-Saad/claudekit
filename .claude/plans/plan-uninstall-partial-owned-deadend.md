# plan-uninstall-partial-owned-deadend — uninstall must not dead-end on the edit install.sh prescribes

Fixes the BLOCKING finding of PR #20's composed-diff review (REJECTED, 82/100), plus the
two output defects in the same branch. Findings MAJ-2, MIN-2, MIN-3.

## MAJ-2 (blocking) — reproduced end to end

`install.sh` ends by telling the user to fill in `build/test/lint_cmd` in
`.claude/hooks/config.json` or `ck doctor --strict` exits 1 ("That is deliberate").
Do exactly that, then uninstall:

```
$ ck uninstall --yes            -> rc=1  "Refusing to uninstall: 1 managed file(s)
                                          have local modifications"
$ ck uninstall --yes --force    -> rc=0  "Removed 229 file(s)"
                                          "Kept 1 locally-modified file(s): hooks/config.json"
$ ck uninstall --yes --keep-modified -> identical: 229 removed, config.json kept
```

Two defects compose:

1. **The refusal fires on a file deletion can never touch.** `modified` (main.py:1447) is
   deliberately unfiltered because it drives the receipt rewrite. main.py:1476 then reuses
   it for the *deletion* refusal — but `PARTIAL_OWNED` was already filtered out of both
   `listed` (1445) and `unchanged` (1448), so a modified `hooks/config.json` is unremovable
   under every flag and still hard-blocks the command. The comment at 1440-1443 says an
   earlier revision "conflated" deletion and provenance; the refusal re-conflates them one
   branch down.
2. **`--force`'s advertised behaviour is unreachable for exactly those files.** `removable`
   (1487) draws from the filtered `listed`, so "remove them too (your edits are backed up
   first)" is false for the file that triggered the refusal, and `--force` and
   `--keep-modified` produce byte-identical outcomes — the user is told to "choose
   explicitly" between two flags that do the same thing, one of which promises a
   destructive act it will not perform.

Why the suite missed it: `tests/test_install_receipts.py:216` edits a whole-file asset, and
`tests/test_adapt.py:735` runs `adapt` first, which re-stamps the receipt. Nothing exercises
"the only modified file is partially-owned" — the default state of any project that followed
the installer's closing instruction.

## Fix

Split the two questions the refusal conflates. `blocking` = modified files that deletion
could actually reach; `modified` stays whole for the receipt rewrite. When `blocking` is
empty there is nothing to refuse, so uninstall proceeds and the closing summary says which
files were kept and *why* — partially-owned (never the kit's alone to delete) is a different
fact from locally-modified-and-you-chose-to-keep-them.

## MIN-2 — the refusal prints one file twice

`partial_kept` (1449-1453) prints between the refusal's `err()` header and its own file list,
so `hooks/config.json` appears in both, the second time with no header. Move it below.

## MIN-3 — "Nothing to uninstall" on an ejected tree with 231 files on disk

main.py:1424 keys off the manifest alone. `ck eject` says `ck update` re-adopts the project
but never that uninstall stops working; `_load_eject_record` is already used this way at
:1187. The refusal is right; the message is false and omits the recovery path.

## Files
- `src/claudekit/cli/main.py` — four edits in `cmd_uninstall`.
- `tests/test_install_receipts.py` — the missing regression, plus a flag-distinguishability test.

## Mutation proof
`test_uninstall_is_not_blocked_by_a_modified_partially_owned_file` asserts rc 0 with no flags
after editing only `hooks/config.json`. Reverting the `blocking` filter makes it fail with
rc 1. `test_force_and_keep_modified_differ_on_a_modified_whole_file_asset` asserts the two
flags produce DIFFERENT outcomes on a file force can reach — reverting makes both keep it.
Neither is a presence assertion: both read the exit code and the file's existence.

---

## Review round 1: REJECTED — 74/100. What it found, and what round 2 does

The diagnosis and the core fix survived: `blocking` does not leak, `--force` stays honest for
files it can reach, and the receipt/`ck adapt` contract holds (proven live in both install
modes, all four flag shapes, plus install→eject→uninstall→update→uninstall). It was rejected
for breaking the suite and for leaving two more instances of the very class it was written to kill.

- **[B1] I broke a test.** Renaming the message to "partially-owned file(s) **will be** KEPT"
  broke `tests/test_adapt.py:717`, which asserts the old string. One real failure, isolated from
  17 pre-existing worktree-environment ones. Round 2 keeps the real-run string byte-identical and
  gives only the dry-run line a "would be " prefix, so no assertion moves.
- **[M1] `--dry-run` stopped predicting the real run.** Moving the `partial_kept` print below the
  refusal also moved it below the dry-run early return, so `--dry-run` reported "113 would be
  removed" and named the survivors nowhere — a reader concludes their edited
  `local/CLAUDE.project.md` is going away. Round 2 extracts `_report_partial_kept(prefix)` and
  calls it on both paths.
- **[M2] The confirmation prompt was the same bug, one line below the fix.** `extra = "(including
  locally-modified files)" if force and modified` promised a destructive act for a run that
  removes nothing. Now keyed on `blocking`.
- **[M3] My second test was vacuous** and I claimed a mutation proof I had not run.
  `a_managed_file()` prefers `agents/`, a whole-file asset the two flags already treated
  differently, so it passed without the fix and duplicated two existing tests. Replaced with the
  invariant that actually fails pre-fix: on a PARTIAL_OWNED-only edit, no-flags / `--force` /
  `--keep-modified` must all three exit 0 and all three keep the file.
- **[N1]** The closing tally derived `_kept_partial` from `kept`, so an UNEDITED survivor was
  missing: the same run opened "2 will be KEPT" and closed "Kept 1". Now derived from
  `partial_kept`.
- **[N2]** The ejected-tree count now uses the `file_count`-first pattern `cmd_update` already
  established at :1206, instead of a second derivation of the same number.
- **[N3]** The regression test now installs `--full`, because only a full install receipts
  `hooks/config.json` — the file the bug report is actually about. It asserts that explicitly.
- **CHANGELOG** `### Fixed` entry added (repo DoD; this is user-visible behaviour).

## The ratchet: `modified` is renamed, not just fixed

The reviewer counted three entries for `deletion-question-answered-with-the-provenance-set` in
this one function's history — the original pre-`PARTIAL_OWNED` conflation, the refusal (MAJ-2),
and the prompt text (M2) — and called for a mechanical guard. A test asserting which identifiers
appear at which use sites would be brittle source introspection. The structural fix is cheaper
and stronger: `modified` becomes **`modified_for_receipt`**, named for its one job. Deletion-side
code reads `blocking` or `removable`; anyone reaching for the receipt set in a deletion context
now has to notice they are in the wrong set. That is the guard.

## Artifacts this change writes

- `src/claudekit/cli/main.py` — `cmd_uninstall`: the `blocking`/`modified_for_receipt` split
- `tests/test_install_receipts.py` — the regression, flag agreement, dry-run parity
- `CHANGELOG.md` — `[Unreleased] ### Fixed`, because behaviour and messages change
