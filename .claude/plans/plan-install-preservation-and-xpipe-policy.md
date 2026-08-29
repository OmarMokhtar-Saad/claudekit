# Plan — installer preservation gaps + stale XPipe policy in templates

## Overview

**Approach:** carry the project's own content across a reinstall in `install.sh`'s existing
preserve block, and correct the parallel-agents policy the templates ship, so that neither
defect can recur on the next `ck update`.

Both defects were measured on the 2026-08-28 fleet update (13 repos, v2.1.0 → v3.0.0), not
inferred. Evidence for each is in section 2. Three of the four projects that lost a
`security` allowlist, and the one that lost its written architecture, were repaired by hand
in that run; this plan removes the cause so the next update does not repeat it.

## 1. Scope (Steps)

| # | File(s) | Change |
|---|---|---|
| A | `install.sh` | Preserve `local/CLAUDE.project.md` and `local/CONSTITUTION.md` on reinstall |
| B | `install.sh` | Merge the previous `hooks/config.json` `security` block into the new config |
| C | `templates/*/CLAUDE.md` (11) | Replace the XPipe-MANDATORY policy with the closed-by-default reality; bump marker v1 → v2 |
| D | `src/claudekit/adapt.py`, `src/claudekit/cli/main.py` | Add `local/CONSTITUTION.md` to `PARTIAL_OWNED_RELS` / `PARTIAL_OWNED` so `ck uninstall` stops deleting it |
| E | `docs/CUSTOMIZATION.md` | Correct the documented behaviour (it currently promises the bug) |
| F | `CHANGELOG.md` | `[Unreleased]` entries for both user-visible changes |
| G | `tests/test_adapt.py` | Move `local/CONSTITUTION.md` across the hardcoded class1/class2 split it asserts |
| H | `tests/test_install_receipts.py` | Three behavioral regression tests, one per defect + the uninstall half |

## 2. Evidence

**A — docs re-rendered over project content.** `install.sh:475/488` and `:501` render
`local/CLAUDE.project.md` and `local/CONSTITUTION.md` from templates unconditionally, on
every install *including a reinstall*. The installer's own closing message (`:742-743`)
says "Review … and customize", i.e. these are seeded then owned by the project.

Measured: all 13 repos re-rendered. `shsmartassistant-qa` lost its real architecture layers —

```
< Tests (src/test/kotlin/qa/*Test.kt)
<       ↓ may depend on
< Harness (SdkAccess.kt, AgentHarness.kt, FixtureApi.kt)
<       ↓ may depend on
< SDK (../shsmartassistant-agent, composite build — READ-ONLY)
---
> # TODO: Define your architecture layers here, e.g.:
```

— plus its description (tests-only repo, no `src/main`, the harness file inventory, the
read-only-SDK rule), replaced by the generic Kotlin template.

**B — the `security` block dropped.** `hooks/config.json` is declared PARTIALLY kit-owned
(`adapt.py:53` `PARTIAL_OWNED_RELS`, mirrored at `cli/main.py:836` `PARTIAL_OWNED`), and
`ck uninstall` honours that. `install.sh` does not: staging's config replaces the file
whole. `security` is the project's own command allowlist and is not regenerable.

Measured losses: AppiumLens 32 `allowedCommands` (`gradlew`, `claude`, `cursor-agent`, …),
shsmartassistant-qa 15, rest-framework 5, qa-agents 1.

**C — templates mandate a closed pipeline.** All 11 `templates/*/CLAUDE.md` carry a
byte-identical block (verified: sha `525407219ced` for all 11) dated 2026-08-09 saying
routing through `/xpipe` is "MANDATORY, not advisory". But `.claude/operations/scripts/xpipe.py:124`
sets `XPIPE_CLOSED_BY_DEFAULT = True` — every call resolves to `solo`. The update injected
this into 12 repos that had never carried it, instructing agents to route through a pipe
that cannot route.

## 3. Design decisions

1. **Preserve whole-file for the two docs, merge one key for the config.** The docs are the
   project's after seeding, so keeping the existing file is right. `hooks/config.json` is
   genuinely shared — the kit updates its structure and `install.sh:505-547` auto-configures
   `project` — so a whole-file keep would freeze the config at its installed version. Only
   `security` moves across.
2. **Placed in the existing preserve block** (`install.sh:556-563`, the `settings.local.json`
   precedent) — after staging is fully built, before the atomic swap, where `$FINAL_DEST`
   is still the old tree. No new lifecycle stage.
3. **Absent old file is not an error.** A fresh install has no `$FINAL_DEST`; the guards are
   `[[ -f ]]` and a missing/typeless `security` exits quietly rather than failing the install.
4. **Marker bumped v1 → v2**, because the region's content changed and `adapt.py`'s parser
   reads the version off the START marker. The END marker carries no version (matching the
   shipped shape), so it stays as-is.
5. **Only the first two bullets of the policy change.** Parallel implementation, safety
   invariants and batch dispatch are unaffected by XPipe's closure and stay byte-identical.
6. **`local/CONSTITUTION.md` joins the partially-owned set (round 2, reviewer CRITICAL).**
   Stopping `install.sh` from overwriting it is only half the guarantee: `cmd_uninstall`
   (`cli/main.py:1646-1653`) builds `removable` from `unchanged`, and a file preserved just
   *before* the manifest is written always hashes as `unchanged` against its own fresh
   entry. So a customized constitution survived reinstall and was then deleted by an
   ordinary `ck uninstall`, under a prompt that never flagged it as modified. "Partial"
   understates the case — `ck adapt` writes into no part of this file — but this set is
   what the deletion paths actually consult, so it is the correct place for the guard.
   `tests/test_adapt.py:210` asserts the two constants stay in step; both are edited.
7. **One test hardcodes the split and must move with it (round 3, reviewer CRITICAL).**
   `TestOwnershipIsAComplement::test_class1_is_every_receipted_key_minus_the_receipted_class2_members`
   (`tests/test_adapt.py:213-226`) uses `local/CONSTITUTION.md` as its Class-1 example and
   asserts both tuples literally, so `classify_ownership`'s `class1 = files - partial` /
   `class2_receipted = files & partial` (`adapt.py:698-700`) moves it and the test goes
   stale. The property under test — that the two classes are complements — is unchanged;
   only which side the file sits on is, so the fix is to move it, not to weaken the
   assertion. Every other test consulting the set derives its expectation from
   `adapt.PARTIAL_OWNED_RELS` dynamically and needs no edit.

## 4. Testing / Verification

- `python3 -m pytest tests/ -q` — zero failures
- `shellcheck install.sh`
- `ruff check`, `mypy`, `gen-docs.py --check`, `gen-registry.py --check`
- Behavioral, **automated** (hard rule: run the installer, assert outcomes) — new class
  `TheInstallerKeepsWhatTheProjectOwns` in `tests/test_install_receipts.py`, reusing that
  file's real-installer fixtures (`InstalledProject`, `ck()`):
  1. a customized `local/CONSTITUTION.md` survives a reinstall;
  2. it also survives a subsequent `ck uninstall --yes` (the deletion half — see decision 6);
  3. a hand-edited `hooks/config.json` `security` block survives a reinstall **and** the
     kit still rewrites its own `project` half, so the test cannot pass by the installer
     simply keeping the whole file and going stale.
- Assert all 11 templates carry the v2 marker and no `MANDATORY, not advisory` remains.
- **Uninstall-after-customize (round 2):** install to a scratch dir, edit `CONSTITUTION.md`,
  reinstall, then `ck uninstall` — assert the file survives and is reported under
  "partially-owned file(s) KEPT". This is the scenario the round-1 plan could not have
  caught, because it never exercised the deletion path.
- `docs/CUSTOMIZATION.md` no longer claims the two docs are "regenerated from templates".

8. **Regression coverage lands with the fix, not after it (round 4, reviewer CONDITIONAL).**
   Both defects were install.sh-only and invisible to every existing test, which is why
   they reached 13 repos before a manual diff caught them. Shipping the fix with only a
   one-time manual verification would leave a future `install.sh` refactor free to
   reintroduce either with no CI signal — directly against this plan's own stated goal.
   The three tests are behavioral (real installer, real `ck`), per the repo's test
   philosophy, and cost little because `tests/test_install_receipts.py` already has the
   fixtures.

## 5. Rollback

All 12 operations are `code_edit` — no creates, no deletes, no `run_command`. The executor
writes a timestamped backup of every touched file before the first write.

1. **Primary:** `python3 .claude/operations/scripts/restore-backup.py --list`, then
   `restore-backup.py --backup <dir>` to restore all 12 files in one step.
2. **Equivalent:** `git checkout -- install.sh templates/` — the branch
   `fix/install-preservation-and-xpipe-policy` is cut from the clean `3.0.0` release commit
   (`015a2e7`), so the working tree has no other uncommitted work to lose.
3. **Blast radius if not rolled back:** the installer changes are additive and guarded by
   `[[ -f ]]`; on a fresh install (no `$FINAL_DEST`) both new blocks are skipped entirely,
   so a regression can only affect reinstall/`ck update`, never a first install. The
   template changes are prose in a product artifact — no executable path reads them.
4. **Downstream:** nothing here touches an installed project. The 13 fleet repos already
   carry the hand-repaired state; they pick up these fixes only on their next `ck update`.
