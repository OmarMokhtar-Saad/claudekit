# Plan: two regressions the install-receipts change introduced

Slug: `receipts-regressions`. **Tier 2** — three files, no new surface. Both defects were found by
**running the full suite after execution**, not by reading the diff; one of them was explicitly
probed during review and cleared.

## Problems

1. **A non-git source aborted the install with rc=128 and no manifest.**
   `install.sh` records provenance with two commands. The first is guarded:
   `git rev-parse HEAD 2>/dev/null || echo ""`. The second is not, and it is a **pipeline**:
   `git status --porcelain 2>/dev/null | head -1`. Under `set -o pipefail` a failing `git` upstream
   fails the whole pipeline, and under `set -e` that aborts the installer.
   Installing from a copied tree or a tarball is a supported case — `tests/test_hook_delivery.py`
   builds exactly such a kit copy — and provenance is best-effort, never a precondition.
   **The review probed this and concluded it degraded gracefully**, because it checked the
   `rev-parse` line. Only executing it found the other one.
2. **`ck uninstall` raised `AttributeError` for any caller that builds its own `Namespace`.**
   The new code read `args.force` / `args.keep_modified` directly, and `tests/test_cli.py` (like
   any programmatic caller) constructs a `Namespace` with only the flags it knows about.

## Approach

- `|| true` on the pipeline, with a comment naming *why* this one differs from the line above it —
  the next person will otherwise see two similar `git` calls and assume one guard covers both.
- `getattr(args, "force", False)` — `cmd_*` functions take a `Namespace` from argparse *and* from
  hand-rolled callers, so a newly added flag must never be a hard requirement of the signature.

## Operations (3)

| # | Type | Path | Why |
|---|------|------|-----|
| 1 | code_edit | `install.sh` | `\|\| true` on the `git status` pipeline |
| 2 | code_edit | `src/claudekit/cli/main.py` | read the new flags with `getattr` |
| 3 | code_edit | `tests/test_install_receipts.py` | regression test for the non-git source |

## Tests

`test_installing_from_a_non_git_source_still_succeeds` copies the kit to a temp dir **without**
`.git`, installs from it, and asserts rc=0, that a manifest exists, and that provenance is recorded
honestly (`commit: null`, `pinned: false`) rather than fabricated. Defect 2 is already covered by
the pre-existing `tests/test_cli.py::test_uninstall_removes_and_backs_up`, which is what caught it —
no new test needed, and adding one would duplicate an existing guard.

Both proven by mutation: removing `|| true` fails the new test; reverting `getattr` fails the CLI
test. Reproduced on disk before the fix was applied, so the transaction is real rather than
retrofitted.

## Risks

- `|| true` on a pipeline can mask a *real* git failure, not just "not a repo". Accepted: the value
  is only ever used to decide whether to mark provenance dirty, and the fallback — treating an
  unreadable status as clean-but-unpinnable — is the conservative one. It cannot make the manifest
  claim a pin it does not have, because `pinned` is driven by the commit, which has its own guard.

## Rollback

`git revert`, or `/rollback` against the engine backup. All three are whole-file replacements that
fail closed on drift. Reverting restores the aborting installer, so it should not be reverted alone.
