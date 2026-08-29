# Plan — custom-asset preservation must not abort on one bad entry

## Overview

**Approach:** make the preserve loop per-entry fault tolerant, stop following symlinks, widen
the pre-manifest heuristic to every directory the kit manages, and report what was not
preserved as a count and a list instead of one vague warning.

**Correcting the record:** the first diagnosis of this loss — "install.sh rebuilds the manifest
from a bare directory walk, so project files get recorded as kit-owned and deleted" — was
**wrong**, and was refuted by the data before any code was written. `agents/bug-reporter.md`,
one of the lost files, is **not** in qa-agents' v2.1.0 manifest (236 entries, checked), so the
`if rel in old_manifest: continue` rule never applied to it. The real cause is below and is
reproduced end-to-end.

## 1. Scope (Steps)

| # | File | Change |
|---|---|---|
| A | `install.sh` (preserve block) | Per-entry `try/except`; a failed entry is counted, never fatal |
| B | `install.sh` (preserve block) | Recreate symlinks as symlinks; never dereference into `copy2` |
| C | `install.sh` (preserve block) | Widen the pre-manifest `ASSET_DIRS` heuristic |
| D | `install.sh` (preserve block) | Report the count and names of files NOT preserved |
| E | `tests/test_install_receipts.py` | Behavioural coverage for each |
| E2 | `tests/test_eject.py` | Its comment names the old three-entry `ASSET_DIRS`; goes stale here |
| F | `CHANGELOG.md` | `[Unreleased]` entry |

## 2. Evidence — reproduced, not inferred

Restoring qa-agents' real pre-update `.claude` into a scratch project and running `ck update`:

```
pre-update files: 2366
[✓] Preserved settings.local.json
FileNotFoundError: [Errno 2] No such file or directory:
  '.../.claude.bak-.../plans/b2-harness/shadow/.tmp_shyj5646_jira_content_string.txt'
[!] Custom-asset preservation failed (files remain in the backup)
post-update files: 1719
lost: 656
```

That path is a **dangling symlink** — it points at
`/Users/omarmokhtar/IdeaProjects/qa-agents/.tmp_shyj5646_jira_content_string.txt`, which no
longer exists:

```
lrwxr-xr-x  .tmp_shyj5646_jira_content_string.txt -> /Users/.../qa-agents/.tmp_...txt
is symlink: YES   target exists: NO
```

`os.walk` lists it, `shutil.copy2` follows it and raises, the exception escapes the `for` loop,
and the shell's `|| print_warn` catches the dead process. **Every custom file the loop had not
yet reached is abandoned** — 656 of them: the project's own `bug-reporter.md` and
`exploratory-coach.md` agents, 281 files under `operations/`, 118 under `reports/`, 55 under
`plans/`, and its scratch dirs. The operator sees one yellow line saying the files "remain in
the backup", which is true and reads like a minor note.

qa-agents is the only repo in the fleet carrying dangling symlinks (15 of them). One of them
cost it everything the walk had not yet visited.

**A second, independent gap in the same block**, found while reading it: when there is no old
manifest (a legacy/pre-manifest install), preservation falls back to
`ASSET_DIRS = ("agents", "commands", "skills")` and drops everything else. rest-framework was
exactly that case and lost its custom `hooks/format-compile.sh` and `hooks/quick-verify.sh`.

## 3. Design decisions

1. **Per-entry isolation is the fix; the symlink is only the trigger.** Any unreadable entry —
   a permissions error, a race with another process, a path too long — aborts the same way.
   Wrapping each copy is what makes the loop's failure mode proportional to the damage.
2. **Recreate symlinks, never dereference them.** `copy2` on a link copies the *target's*
   bytes, so even a working symlink is silently converted to a regular file today. `os.symlink`
   of the same `readlink` value preserves what the project actually had, and cannot fail on a
   dangling target because it never reads it.
3. **Widen the heuristic to every managed dir plus the project's own subtrees.** The narrow
   triple was already wrong for `hooks/`, and the same reasoning covers `operations/`, `modes/`,
   `local/`, `plans/`, `knowledge/`. Deliberately NOT widened to everything: the manifest path
   is precise and is what runs for any modern install; this is the legacy fallback only.
4. **Failure must be counted, not merely mentioned.** "Custom-asset preservation failed" gave no
   scale. Reporting `N file(s) could NOT be preserved` with the first several names is what
   distinguishes "one scratch symlink" from "656 files, including your agents".
5. **Still never fatal to the install.** A preservation failure leaves the backup intact and
   must not fail the update, matching the existing contract. The change is to how much is lost
   and how loudly, not to the exit code.
6. **`reports/` is NOT in the widened fallback (round 2, reviewer MAJOR).** It was, and that was
   wrong: this repo treats reports as generated rather than source ("re-derive, don't cite" —
   CLAUDE.md), and `install.sh` itself writes `.claude/reports/` into `.gitignore`. Resurrecting
   a scratch report a user had cleaned up, and relabelling it "custom" in `ck diff`, is not
   preservation. The list covers authored content only.
7. **The regression test binds on a documented guarantee, not on filename order (round 2,
   reviewer CRITICAL).** The first draft put the broken link and two custom files in one
   directory and claimed `zz_` "sorts last". `os.walk` does not sort — same-directory order is
   `os.scandir` order, filesystem-defined. The reviewer measured APFS returning *reverse*
   creation order, meaning the test bound here by luck and could pass vacuously against the
   unfixed code on ext4/tmpfs/overlayfs. The link now sits at the `.claude/` ROOT and the custom
   files under `agents/`, relying on top-down `os.walk`'s guarantee that a directory's own
   entries precede its subdirectories'. Verified empirically before rewriting.
8. **No overwrite branch in `carry_over` (round 2, reviewer MAJOR).** The draft removed an
   existing `target` before re-linking. The caller already skips any `rel` that `lexists` in
   dest and the script is synchronous, so that branch was unreachable — dead code in a
   fault-tolerance function is where a later edit quietly puts its trust.
9. **`except Exception`, not `except OSError`.** `SameFileError` is an `OSError` subclass (the
   reviewer confirmed), so `OSError` was sufficient for the known cases — but the entire premise
   is that nothing may end this loop, and a narrow catch re-creates the defect for the next
   unanticipated raise.

## 4. Testing / Verification

- `python3 -m pytest tests/ -q` — zero failures; `shellcheck install.sh`; ruff, mypy, drift gates.
- Behavioural, against the real installer:
  1. **The regression itself:** a dangling symlink at the `.claude/` root plus two custom agents
     under `agents/`; after a reinstall both real files survive. Ordering rests on top-down
     `os.walk`'s documented guarantee, never on filename order — see decision 7.
  2. A dangling symlink does not appear in the new tree as a broken entry or a copied file.
  3. A **working** symlink is preserved as a symlink, not flattened into a regular file.
  4. Pre-manifest (no `.claudekit-manifest.json` in the backup): a custom `hooks/*.sh` survives.
  5. A dangling symlink no longer trips the block's wholesale "preservation failed" warning.
- **Mutation proof:** restoring the un-wrapped `shutil.copy2` loop must fail test 1. A test that
  passes against the old code proves nothing here.

## 5. Rollback

Two files plus the changelog; all `code_edit`, no creates or deletes. The executor backs up each
file before writing.

1. `restore-backup.py --list` then `--backup <dir>`.
2. Or `git checkout -- install.sh tests/ CHANGELOG.md`.
3. **Blast radius:** the block already runs after the atomic swap, cannot fail the install, and
   the backup is untouched either way. A bug here can only change how many custom files are
   restored — the previous tree always remains in `.claude.bak-*`.
4. **Downstream:** no installed project changes until its next `ck update`. The fleet's already
   restored files are unaffected.
