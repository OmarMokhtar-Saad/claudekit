# Plan — carry over symlinked directories, and pin the failure report

## Overview

Follow-up to `plan-preserve-fault-tolerance.md`, found by verifying that fix against the real
failing case rather than trusting it. The fault-isolation fix took qa-agents' loss from **656
files to 46**; this closes the residual.

**Approach:** handle symlinks that `os.walk` reports in `dirs`, and replace an
absence-only assertion with one that pins the failure report using an entry that genuinely
cannot be read.

## 1. Scope (Steps)

| # | File | Change |
|---|---|---|
| A | `install.sh` (preserve block) | Carry over symlinks found in `dirs`; never descend through them |
| B | `install.sh` (preserve block) | Refuse — and report — symlinks that escape the project or are self-referential |
| C | `tests/test_install_receipts.py` | Split the dangling-link test; add count, dir-symlink, escape and cycle tests |

## 2. Evidence — measured after the previous fix

Replaying qa-agents' real pre-update `.claude` through `ck update` with the fault-isolation fix
in place: `2685 -> 2648` entries, **46 lost**, of which 9 are the deliberately superseded kit
agents and 1 is `hooks/hooks.log` (skipped by design). The other **36** are all symlinks under
`plans/b2-harness/shadow/` — `.claude`, `backups`, `corpus`, `data`, `docs`, `scripts`, … —
and every one of them **resolves**:

```
.claude    islink=yes  isdir=yes  target=/Users/.../qa-agents/.claude
corpus     islink=yes  isdir=yes  target=/Users/.../qa-agents/corpus
```

`os.walk` classifies a symlink to an *existing* directory as a directory, so it appears in
`dirs`, never in `names` — and the preserve loop only iterates `names`:

```
root=tmp…  dirs=['real']  names=['link-to-dir', 'plain.txt']
```

(That listing also shows the asymmetry: a **dangling** dir-symlink is classified as a file and
does reach `names`, which is why this gap only manifests for links whose target still exists —
and why the previous round's dangling-link work did not surface it.)

## 3. Design decisions

1. **Recreate the link; never walk through it.** The entry is removed from `dirs` as well as
   carried over. `os.walk` defaults to `followlinks=False` so it would not descend anyway, but
   one of these links is `shadow/.claude -> <project>/.claude` — a link from inside the tree
   being replaced back to that tree's live path. Relying on a default for that is not worth the
   saving; removing it from `dirs` states the intent.
2. **Same skip rules as files, deliberately.** `lexists` in dest, `old_manifest` membership, and
   the `ASSET_DIRS` fallback are applied identically. A symlink is an asset like any other, and
   a second, subtly different set of rules for it is how the last two defects here happened.
3. **Refuse escaping and self-referential links, and say so (round 2, reviewer MAJORs).**
   Recreating whatever a backup contains was the one place in this repo that rebuilt an
   arbitrary symlink target verbatim, while `security/path_guard.py` rejects targets escaping
   the project root and `review-record.py:_safe_write` refuses to write *through* a link at any
   level. Same class of trust, so it now gets the same answer: a link whose resolved target
   leaves the project is not recreated, and neither is a directory link that resolves to an
   ancestor of itself — `plans/x/shadow/.claude -> <project>/.claude` bakes a cycle into the
   installed tree that the next `find -L` or `followlinks=True` walker descends forever. Both
   are REPORTED with the reason and remain in the backup; refusing silently would be the same
   defect this whole line of work is about.
4. **`_within` must `realpath` BOTH sides.** Resolving only the child made every legitimate
   link look like an escape on macOS, where a temp dir is `/var/folders/...` — itself a symlink
   to `/private/var/...`. Caught by running the tests: three previously-passing tests went red.
5. **The count test needed a different fixture than the reviewer suggested.** The round-2
   reviewer asked for a positive assertion on `N file(s) could NOT be preserved` in the
   dangling-symlink test. That test cannot carry it: once symlinks are recreated rather than
   dereferenced, a broken link **succeeds**, so no failure is reported and the assertion would
   fail. The right fixture is a genuinely unreadable entry — a mode-`000` file, verified to
   raise `PermissionError` for its owner on this platform. The dangling case keeps its
   absence-only assertion, with a docstring saying why that is the correct shape for it.
6. **The count test also pins the isolation itself** — a readable sibling must survive the
   unreadable one. Asserting only the message would pass against a loop that reported the
   failure and still abandoned everything after it.

## 4. Testing / Verification

- `python3 -m pytest tests/ -q`; `shellcheck install.sh`; ruff, mypy, drift gates.
- New behavioural tests: a symlinked directory is preserved as a symlink and its target content
  is reachable through it; an unreadable file is reported by name with a count while its
  readable sibling survives; a dangling link is not reported as a failure at all.
- **The end-to-end check that motivated this**, measured on qa-agents' real pre-update tree:
  `2685 -> 2683` entries, **11 lost** — the 9 deliberately superseded agents, two hook runtime
  logs, and the one self-referential `shadow/.claude` link, refused by name. Down from 656.
  **Harness caveat, stated because it changes the number:** replaying into a temp directory
  makes every absolute link point outside the copy, so all 319 are correctly refused as escapes
  and the run reports 329 losses. That is an artifact of relocating the tree, not of the change;
  the measurement above repoints those links at the scratch root first, which is what an
  in-place `ck update` actually sees.
- **Mutation proof:** removing the `dirs` loop must fail the dir-symlink test.
- **Run before submitting.** The previous round was REJECTED for a test that failed 100% of the
  time on the platform the plan claimed to have verified. This ops.json was applied to a scratch
  clone and the suite run there first: 37 passed, shellcheck clean.

## 5. Rollback

Two files, both `code_edit`, no creates or deletes; the executor backs up each before writing.

1. `restore-backup.py --list` then `--backup <dir>`.
2. Or `git checkout -- install.sh tests/`.
3. **Blast radius:** confined to the preserve block, which runs after the atomic swap, cannot
   fail the install, and leaves `.claude.bak-*` untouched regardless. A bug here changes only
   how many custom entries are restored.
