# Implementation Plan: Preserve File Modes Across the Ops Engine

## Overview
`execute-json-ops.py` silently narrows permission bits on every write: a `code_edit` on
`install.sh` changed it from 0755 to 0600 (measured), and `file_create` produces 0600 files.
Fix it once, in the single shared write helper (`atomic_write`), so no write site can be missed.

## Context: this was a known, pre-diagnosed defect
`review/code-review.md:286` already recorded it as a P2 **with the fix spelled out** ("Copy the
original mode ... before replace") and it was left unfixed. It went on to strip the exec bit
from `install.sh`, `.claude/hooks/ops-enforcement.sh` and `scripts/gen-docs.py` — the latter two
shipped in a commit before anyone noticed. That is the argument for triaging the remaining
findings in that file rather than letting them age.

## Root cause (file:line evidence)
`.claude/operations/scripts/execute-json-ops.py:84-96` — `atomic_write()`:
- line 91: `fd, tmp_path = tempfile.mkstemp(dir=..., suffix='.tmp')` — mkstemp creates the temp
  file with mode **0600** by design (it is a security-sensitive API).
- line 96: `os.replace(tmp_path, str(file_path))` — rename replaces the *inode*, so the target
  inherits the temp file's 0600 and the original mode is discarded.

`atomic_write` is the only content-write path, called from **both** mutating op types:
- `execute_file_create` -> line 486 (`file_create`)
- `execute_code_edit` -> line 704 (`code_edit`)

Measured on the current tree (tmp project, umask 022): 0755 `s.sh` -> `-rw-------` after a
`code_edit`; `file_create` -> `-rw-------`. This was already flagged as P2 in
`review/code-review.md:286` and never fixed.

Paths that are **already correct** (verified, no change needed):
- backup capture (lines 539, 616) and rollback (line 183) use `shutil.copy2`, which copies mode
  via `copystat`. Measured: backup of a 0755 file is 0755, and rollback after a mid-batch
  failure restores 0755.
- `snapshot_post_state` (line 316) uses `copy2`; `restore-backup.py:231` uses `copy2`.
  The post-state checkpoint was wrong only *transitively*, because it snapshotted an
  already-corrupted 0600 file. Fixing `atomic_write` fixes it.

## Scope
- **In Scope:** mode preservation in `atomic_write` (edit + create), a chosen and justified
  mode for newly created files, behavioral tests covering edit / create / rollback /
  post-state restore.
- **Out of Scope:** `restore-backup.py` (already mode-correct — see Risks); a `mode` field on
  `file_create` in the ops schema; `install.sh`, hooks, agents, skills, CHANGELOG, `.ai/**`.

## Prerequisites
- `ECC_HOOK_PROFILE=minimal` in `.claude/settings.local.json` (repo self-hosting gotcha).
- This ops.json lives under `.claude/plans/`, so the approval gate applies: it needs a review
  record before execution. All verification for this plan was done against a *copy* of the
  scripts dir in a scratch tmp project; the real tree was never mutated.

## Implementation Steps

### Step 1: Behavioral tests
- **File:** `tests/test_ops_file_modes.py`
- **Action:** Create
- **Description:** Real-executor subprocess tests in `tmp_path`, `ECC_HOOK_PROFILE=minimal`
  forced in the child env, modes asserted with `os.stat`/`stat.S_IMODE`.
- **Details:** 7 tests — edit keeps 0755; edit keeps 0644; edit keeps 0664 (no normalisation);
  `file_create` == `0666 & ~umask` and not executable; rollback after a mid-batch failure keeps
  0755; a `file_create` **over an existing** 0755 file inherits 0755 (execute_file_create,
  lines 484-489, does not check existence, so `current_mode` wins over `DEFAULT_CREATE_MODE` —
  this is the wanted behavior and must be pinned); rollback after a mid-batch failure keeps
  0755; post-state checkpoint is 0755 and `restore-backup.py --post --force` restores 0755
  after an external wipe.

### Step 2: Mode-preserving write helper
- **File:** `.claude/operations/scripts/execute-json-ops.py`
- **Action:** Modify (5 edits, one `code_edit` op)
- **Details:**
  1. Header feature bullet: permission-preserving writes.
  2. `import stat`.
  3. Module constants after `MANIFEST_NAME`: read the process umask once at import
     (`_PROCESS_UMASK = os.umask(0); os.umask(_PROCESS_UMASK)`) and derive
     `DEFAULT_CREATE_MODE = 0o666 & ~_PROCESS_UMASK`. Read-and-restore is safe here: it runs at
     import, single-threaded, before any work. The snapshot is intentional and commented: a
     umask changed *after* import is ignored, which is irrelevant for the CLI entrypoint and
     documented for any future in-process reuse.
  4. New `current_mode(path) -> Optional[int]` helper (`None` when the path does not exist) and
     an `atomic_write(..., mode: Optional[int] = None)` signature that resolves
     `mode` -> existing target mode -> `DEFAULT_CREATE_MODE`. The docstring records that
     `stat.S_IMODE` carries the 0o7000 bits (setuid/setgid/sticky) as well as the low 9, so a
     setuid target has those re-applied to the temp file before the rename — same owner, content
     already written and fsynced, so no escalation, but stated explicitly on a security chokepoint.
  5. `os.chmod(tmp_path, target_mode)` immediately before `os.replace`, wrapped in
     `except (OSError, NotImplementedError): pass` so a platform where chmod is a no-op
     degrades to today's behavior instead of failing the write.

**Why a single helper, not per-site fixes:** both call sites (486, 704) already funnel through
`atomic_write`; per-site chmod is exactly how one path gets missed. Any future write site
inherits the fix for free.

**Why `0666 & ~umask` for new files** (rather than a fixed 0644 or copying a sibling):
it is what every normal tool produces (shell redirect, editor, `pathlib.write_text`), so
engine-created files stop being distinguishable from hand-created ones (the 0600
`review/tasks/015-*.md` vs 0644 `014-*.md` inconsistency disappears); it honours an operator who
deliberately sets a stricter umask, which a hardcoded 0644 would override; and git only records
the exec bit, so 0644 is the correct default for non-executables. A plan that must create an
*executable* script still cannot express that — see Risks. Note this default is a **widening**
for `file_create`, not a tightening; that trade-off is stated in Risks rather than buried here.

## Testing Strategy
`python3 -m pytest tests/test_ops_file_modes.py -q`, then the full suite, `ruff`, `mypy`,
`gen-docs --check`. `.claude/**` is ruff/mypy-excluded, but the new test file is not.

**Binding proof (measured, not asserted):** the tests were run against the unpatched tree and
against a patched copy of the scripts dir in a scratch project.
- Unpatched (fix reverted): **6 failed, 1 passed** — every mode assertion failed
  (`assert 384 == 493`, i.e. 0600 vs 0755).
- Patched: **7 passed**.
- The one test that passes both ways is `test_rollback_after_midbatch_failure_keeps_0755`: it is
  a regression guard on the `copy2` rollback path, which is already correct. It is kept
  deliberately (the recovery path is where a mode bug is worst) and is honestly *not* bound to
  this fix.

## Rollback Plan
`git checkout -- .claude/operations/scripts/execute-json-ops.py && rm
tests/test_ops_file_modes.py`, or `restore-backup.py --backup backups/<dir> --force`.
The change is 5 localized edits in one function plus two module constants; no state or
on-disk format changes, so rollback is total.

## Risk Assessment
- **Low:** the change is additive inside one helper; the failure mode of the chmod is swallowed,
  so no write can start failing because of it. Tests are hermetic (`tmp_path` only).
- **Low:** `restore-backup.py` is deliberately untouched — `shutil.copy2` at line 231 already
  restores mode, verified end-to-end by the post-state test in this plan. Owning it would be an
  unjustified edit to a second core script.
- **Medium:** import-time `os.umask(0)` briefly clears the umask. Single-threaded, at import,
  restored on the next statement — but it is a global process side effect, so it is confined to
  two lines with a comment.
- **Medium — this fix WIDENS permissions in exactly one direction, scoped to `file_create`.**
  A newly created file goes from 0600 (accidentally restrictive) to 0644 (world-readable). It is
  *not* "strictly better": `PROTECTED_PATTERNS` (`.claude/operations/scripts/shared.py:14-31`)
  guards deletes only and lists no `.env` or credential names, so a `file_create` of a sensitive
  file is expressible today and would now be world-readable. Mitigation, stated as policy:
  **secrets must never be authored through ops.json** — the engine is a code-change tool, not a
  secret writer. `code_edit` is unaffected: an existing 0600 file is correctly preserved by
  `current_mode`, and a `file_create` over an existing path inherits that path's mode (pinned by
  test 7).
- **Medium:** `file_create` cannot produce an executable file — a plan that creates a script
  still needs a follow-up `chmod` (not in the `run_command` allowlist). Tracked as a schema
  question (`mode` field on `file_create`), explicitly out of scope here.
- **Portability:** no Windows branch is added; `os.chmod` there sets only the read-only bit and
  the `except` clause covers a platform where it raises. macOS/Linux behavior is exact.
- **Blast radius:** `execute-json-ops.py` is the Iron-Law chokepoint for all implementation
  (hard rule 1) — every op of every plan flows through the edited function. Mitigated by the
  full existing ops suites (`test_ops_hardening`, `test_ops_approval_gate`,
  `test_run_command_ops`, `test_work_loss_protection`, `test_checkpoint`) which must all pass.
