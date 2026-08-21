# Plan: the manifest is an ownership receipt, not an inventory

Slug: `install-receipts`. Wave-2 **Phase 3**. Blast radius: **Tier 3** — the installer and the
CLI's destructive command.

## Problem

`.claudekit-manifest.json` already records a sha256 per installed file. Nothing used it to decide
what may be deleted.

1. **`ck uninstall` deleted every path the manifest listed without comparing a single digest**
   (`main.py:685-717`). A prompt a user had spent a week tuning was removed as readily as an
   untouched one. `_classify_manifest()` — which returns exactly the modified/missing/unchanged
   split needed — already existed and was used by `ck update` and `ck diff`, but not here.
2. **The manifest recorded files that are the user's by definition.** It walked the whole install
   tree excluding only itself, so `settings.local.json` became kit-owned. Reproduced against the
   pre-fix installer: `settings.local.json in manifest: True`. That is the standing `.ai/BACKLOG.md`
   defect that forced hand-preservation across 17 projects on 2026-07-31.
3. **No provenance.** An install recorded a version string, so it was traceable to a mutable
   release name and not to an immutable commit.

## Approach

Make ownership *decidable*, then act only on what is owned.

- **Never record what is not ours.** `NEVER_MANAGED` excludes `settings.local.json`, `hooks.log`
  and `.pyc`, kept explicitly in step with the existing `SKIP_NAMES` in the preserve block.
- **Fail closed on mixed ownership.** A digest that no longer matches means the kit's text *plus*
  the user's edits. `ck uninstall` now refuses the whole operation and names the files, with two
  explicit ways out: `--keep-modified` (remove only what the receipt still owns) and `--force`
  (remove them too, backed up first). Neither hides behind `--yes`, which only skips a prompt.
- **Rewrite the receipt when files are kept**, so it describes exactly what is still ours — a kept
  file with a stale receipt entry would read as user-authored to the next install.
- **Pin provenance to a commit.** The manifest gains `source: {commit, pinned, dirty}`.

### On 3.2, honestly

The handoff asks for commit-pinned *downloads* with bounded retries. **There is no downloader.**
`install.sh:13-17` refuses `curl|bash` outright and requires a clone, and adding a fetcher would
add exactly the network surface this repo has avoided. So the *invariant* is adopted — an install
is traceable to an immutable 40-char SHA — and the *mechanism* is rejected. The related invariant,
"a failed install leaves the last verified installation unchanged", is **already satisfied**:
`install.sh:110-121` stages into `.claude.staging.$$` and swaps atomically, with an `ERR` trap that
removes only staging. Verified, not reimplemented.

A dirty source checkout records `pinned: false`. It does not correspond to its own commit, so
claiming a pin would imply a reproducibility the artifact does not have.

## Operations (5)

| # | Type | Path | Why |
|---|------|------|-----|
| 1 | code_edit | `install.sh` | receipt exclusions + source commit pin |
| 2 | code_edit | `src/claudekit/cli/main.py` | fail-closed uninstall, `--keep-modified`, `--force` |
| 3 | file_create | `tests/test_install_receipts.py` | 19 behavioural tests |
| 4–5 | code_edit | `CHANGELOG.md` | user-visible CLI behaviour change + provenance (DoD) |

## Evidence already gathered

Executed against a staged tree, then reverted:

- **19 tests pass in ~11s.** Each runs the real `install.sh` into a real temp project and drives
  the real `ck` CLI. Nothing is mocked — this defect class only exists at that boundary.
- **Mutation 1** — make uninstall ignore digests: **3 tests fail**.
- **Mutation 2** — drop the source pin: **3 tests fail**.
- **Mutation 3** — restore `settings.local.json` to the manifest: **2 tests fail**.

**Mutation 3 initially did not bind, and that is worth recording.** The first version of these
tests created `settings.local.json` after a *fresh* install, where it does not exist at manifest
time — so the assertions passed with or without the fix. The defect only appears on the **second**
install, once the preserve step has restored the file. The tests now re-install, and were confirmed
red against the pre-fix installer before being trusted.

## Review round 1 (APPROVED 93/100) — what changed after

Three warnings, two acted on and one declined with evidence:

- **CHANGELOG was missing** — a user-visible CLI behaviour change with no `[Unreleased]` entry
  violates this repo's own DoD. Added as ops 4–5.
- **`--keep-modified` with *every* file modified was untested** — the `removable == []` path was
  traced sound but unexercised. Two tests added: nothing is removed, the receipt still lists every
  kept file, and a **second** uninstall still fails closed (kept files must stay flagged as
  modified, not silently re-adopted).
- **"no test asserts an unmanaged file survives" — declined, already covered.**
  `FilesTheReceiptNeverSawAreNotTouched::test_a_user_authored_agent_survives_uninstall` creates
  `agents/my-own-agent.md` after install and asserts it survives. Verified before answering rather
  than assumed.

## Risks

- **`--force` is genuinely destructive**, by design. Mitigated by taking the backup first and by a
  test that asserts the modified file's content is recoverable from `backups/uninstall-*/`.
- **`hooks.log`'s exclusion is defensive, not a reproduced fix.** Unlike `settings.local.json` it
  never reaches the manifest today. Stated rather than counted as a defect closed.
- **`NEVER_MANAGED` and `SKIP_NAMES` are two lists that must agree.** They live ~30 lines apart in
  one file with a comment on each pointing at the other; a shared constant is not available across
  the heredoc boundary without restructuring the installer, which is out of scope here.

## Rollback

`git revert`, or `/rollback` against the engine backup. Ops 1–2 are whole-file replacements that
fail closed on drift; op 3 is a new file with no importers. Reverting restores the previous
uninstall behaviour — **already-written manifests are unaffected either way**, since the new fields
are additive and the old code ignores unknown keys.
