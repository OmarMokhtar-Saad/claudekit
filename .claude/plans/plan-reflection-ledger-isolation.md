# Implementation Plan: Reflection Ledger Root Isolation and Hardening

## Overview

`reflection.ledger_dir()` falls back to a single, predictable, machine-shared directory
(`$TMPDIR/claudekit-reflection`) keyed only by `sha256(session_id)[:32]`. Two projects on
one host share it; on Linux hosts where `TMPDIR` is unset the parent is `/tmp` (mode
`1777`), which makes the path a classic pre-creation/symlink target. This plan
discriminates the fallback root by user and project **and** makes the directory private
and verified on every use, without moving the ledger inside the repository and without
changing the semantics of an explicit `CLAUDEKIT_REFLECTION_DIR`.

## Context Summary (what was read and measured)

- `.claude/hooks/reflection.py:181-196` — `ledger_dir()`; override wins if absolute,
  else `Path(base, "claudekit-reflection")`.
- Write sites: `append_entry` (`:265`), `ensure_session_token` (`:330`) both do
  `path.parent.mkdir(parents=True, exist_ok=True)`. `:810` is the **inbox** parent, which
  is project-local already and is out of scope for the ledger root.
- `.claude/hooks/reflection-gate.py:403` also does `path.parent.mkdir(...)` on the
  **ledger** root (PreCompact carry-over), and `:310` reads the carry-over file back into
  `stdout` at SessionStart.
- `inbox_path()` (`:226-244`) derives from `project_root()`, **not** from `ledger_dir()`.
  The gate's `is_receipt_inbox_write()` resolves the same function and compares
  `realpath(parent) + basename`. Moving the ledger root therefore does **not** move the
  inbox and does **not** change the gate's exact-path comparison.
- Session continuity: `ledger_dir()` is a pure function of environment + project root,
  re-evaluated per process. Nothing per-invocation may enter it.
- `tests/conftest.py::reflection_env` sets both env vars absolutely; the fallback is never
  exercised by the current 83 tests, and `test_reflection_ledger.py:424` asserts
  `ledger_dir() == tmp_path / "ledger"` **verbatim** — the override must stay exact.

### Measured security behaviour of the current fallback

Reproduced locally (Python 3.9+ semantics, macOS):

```
mkdir on symlink->dir: OK (silently followed)
victim now: orig
{"pwned":1}
/tmp mode: 0o41777
```

1. `Path.mkdir(parents=True, exist_ok=True)` **follows** a symlink planted at the root: it
   raises `FileExistsError` internally and swallows it because `is_dir()` (which follows
   links) is true. A co-user who plants `/tmp/claudekit-reflection -> /path/they/choose`
   redirects the whole ledger silently.
2. A pre-created directory owned by another uid with mode `0777` is accepted without any
   check. They may then plant `<key>.jsonl` as a symlink; `open("a")` follows it, giving an
   **append-only write primitive into any file our uid can write** (e.g. a shell rc file →
   code execution as us). Demonstrated above.
3. The `O_EXCL` token creation protects the token from being *overwritten*, but not from
   being *pre-created*: if the attacker writes `<key>.token` first, `O_EXCL` raises
   `FileExistsError` and the code falls back to `read_session_token()`, adopting the
   attacker's key. Receipt HMACs are then forgeable by them. (Note the module already, and
   correctly, disclaims adversarial strength against the *agent* itself — hard rule 6 —
   but this is a different principal: another **uid** on the host.)

**Honest sizing.** The session key is a SHA-256 of an unpredictable session id, so the
*file* names are not guessable — the exploitable surface is the **directory**, whose name is
fully predictable, plus a watch-and-race on newly created names. On a single-user macOS
laptop the practical risk is ~zero: `TMPDIR` is a per-user `/var/folders/.../T` created
mode `0700`, so no other uid can reach the path at all. The exposure is real on
**multi-tenant Linux build machines and shared CI runners**, where `TMPDIR` is typically
unset and the parent is world-writable `/tmp`. This is a genuine local privilege/integrity
issue in that environment, not a remote one and not a sandbox escape. The
**cross-project/cross-session collision**, by contrast, affects every user on every
platform and is the primary defect.

## Design decision

**Option 4 = Option 1 + Option 3.** Discriminate the fallback root by uid *and* project,
and make every component we own private (`0o700`, owned by us, never a symlink) and
re-verified with `os.lstat` on every use — refusing rather than degrading silently into an
untrusted directory.

- **Option 1 alone** fixes collisions but leaves the `/tmp` pre-creation surface intact:
  the per-project directory name is still fully predictable from a project path.
- **Option 2 (refuse without explicit config) is rejected.** A hook that silently no-ops
  unless an env var is set disables the whole reflection mechanism for every user who
  installs the kit and never reads this file — checkpoints stop firing, `Stop` stops
  owing a learning decision, and *nothing observable happens*. A safety mechanism whose
  default state is "off and quiet" is worse than one with a hardened default. Refusal is
  retained only for the narrow case where the default location is demonstrably
  **untrustworthy** (wrong owner/mode/symlink), which is loud in the hook log and rare.
- **Option 3 alone** hardens the path but leaves two projects sharing one directory —
  ledgers of unrelated work interleaved under colliding session ids.

The ledger stays **outside the repository** (design property 3: survives compaction, cannot
be committed, cannot be read back wholesale). Only the *fallback* changes; an explicit
`CLAUDEKIT_REFLECTION_DIR` is still honoured **verbatim** and is created but **not
permission-audited** — it is the operator's own chosen location and we do not own its
mode. That keeps the `reflection_env` fixture contract and `:424` intact.

## Scope

- **In scope:** fallback root derivation, private-directory creation/verification, guarded
  read paths (`entries`, `read_session_token`), the two ledger-root `mkdir` sites in
  `reflection.py`, the one ledger-root `mkdir` + carry-over read in `reflection-gate.py`,
  and behavioral tests.
- **Out of scope:** the inbox path (already project-local; unchanged), the gate's
  `is_receipt_inbox_write()` comparison (unchanged), `.claude/settings.json`,
  `ops-enforcement.sh`, agents, skills, CHANGELOG/`.ai/**` (owner-gated, separate commit).

## Prerequisites

- `.claude/settings.local.json` with `ECC_HOOK_PROFILE=minimal` present (repo setup gotcha).

## Implementation Steps

### Step 1: New path primitives in `reflection.py`
- **File:** `.claude/hooks/reflection.py` — **Action:** Modify
- Add `import stat`; add `_TMP_ROOT_NAME` and a `_PROJECT_KEY_CACHE` module global next to
  `_ENV_DIR`.
- Add `_current_uid()` (indirected so a test can simulate a foreign-owned directory
  without root), `_project_key()` (sha256 of the realpath'd project root, first 16 hex,
  memoised on `(CLAUDE_PROJECT_DIR, cwd)` so the `git rev-parse` in `project_root()` runs
  at most once per process per project), `ledger_root_is_explicit()`, `_is_private_dir()`
  (`os.lstat`, `S_ISDIR`, owner, `mode & 0o077 == 0`), `ledger_dir_trusted()` (non-creating
  read-side predicate — the blocking gate must have no filesystem side effects),
  `_warn_untrusted_root()` (one-shot stderr advisory), and `ensure_ledger_dir()`.
- `ledger_dir_trusted()` audits the **leaf only**; `ensure_ledger_dir()` audits
  **(parent, leaf)**. The asymmetry is deliberate and is documented in the docstring so a
  later "simplification" cannot quietly make either side insufficient: a private leaf
  cannot have entries planted in it by another uid whoever owns the parent, while the
  write path *creates* the parent and must not create it inside someone else's symlink.
- Rewrite `ledger_dir()` fallback to
  `Path(base, "claudekit-reflection-u<uid>", "<project_key>")`. Override branch unchanged.

### Step 2: Route write sites through `ensure_ledger_dir()`
- **File:** `.claude/hooks/reflection.py` — **Action:** Modify
- `append_entry` and `ensure_session_token` replace their bare
  `path.parent.mkdir(parents=True, exist_ok=True)` with an `ensure_ledger_dir()` guard that
  returns `False`/`None` when the root cannot be trusted (degrade, never raise).

### Step 3: Guard the read sites
- **File:** `.claude/hooks/reflection.py` — **Action:** Modify
- `entries()` returns `[]` and `read_session_token()` returns `None` when
  `ledger_dir_trusted()` is false. This is what actually closes the forged-token and
  attacker-supplied-JSONL paths; neither creates a directory.

### Step 4: De-shadow the `stat` module inside `main()`
- **File:** `.claude/hooks/reflection.py` — **Action:** Modify
- `main()` binds a local named `stat` for the `status` subparser, which would shadow the
  newly imported module. Rename the local to `stat_p` (2 lines).

### Step 5: Close the ledger-root `mkdir` in the gate
- **File:** `.claude/hooks/reflection-gate.py` — **Action:** Modify
- **Justification for touching this file** (the brief scopes it to inbox changes): the
  inbox is *not* changing, but `:403` creates the **ledger root** with the same unguarded
  `mkdir(parents=True, exist_ok=True)`, and `:310` reads the carry-over file from that root
  straight into `stdout`. Leaving either unguarded re-opens exactly the hole Step 1 closes,
  from a different entry point. Both edits are confined to carry-over handling; no inbox
  logic, no exact-path comparison, and no other line of the file is touched.

### Step 6: Behavioral tests — ledger
- **File:** `tests/test_reflection_ledger.py` — **Action:** Modify (append one class)
- `TestFallbackRootIsolation` (9 tests), each pinning `TMPDIR` into `tmp_path` and
  `monkeypatch.delenv("CLAUDEKIT_REFLECTION_DIR")` so the fallback itself is under test and
  the developer's real ledger is still never touched:
  1. two projects, **same session id** → different ledger paths, one entry each, no
     cross-read.
  2. **REGRESSION — session continuity:** two *separate subprocesses* of the real CLI
     (`trigger` then `status`) with no `CLAUDEKIT_REFLECTION_DIR` see the same ledger. Goes
     red if anything per-invocation (pid/time/`mkdtemp`) ever enters the path.
  3. the created root and its parent are mode `0o700` and owned by us.
  4. a pre-created world-writable root → `ensure_ledger_dir()` is `None` **and**
     `append_entry()` is `False`.
  5. a symlink planted at the root → refused, and the symlink target stays empty.
  6. a foreign-owned root (via `monkeypatch.setattr(ref, "_current_uid", ...)`) → refused.
  7. a hostile root with a planted ledger and token → `entries() == []` and
     `read_session_token() is None`.
  8. an explicit override is used verbatim and is **not** permission-audited (bound test
     for the `reflection_env` contract and `:424`).
  Plus 9. a degraded root is **not silent** — `ledger_dir_trusted()` emits one stderr
  warning per process; and 10. the inbox stays project-local and is not under
  `ledger_dir()` when the ledger is on the fallback. (`TestExplicitOverrideUnchanged`
  carries the override-verbatim test.)

### Step 7: Behavioral tests — gate
- **File:** `tests/test_reflection_gate.py` — **Action:** Modify (append one class)
- `TestUntrustedLedgerRootInTheGate` (3 tests). Its fixture pins `TMPDIR` and
  `CLAUDE_PROJECT_DIR` **both** in the subprocess env dict and, via `monkeypatch.setenv`,
  in this process — the existing `env` fixture only builds a dict copy, so without that
  the in-process `ref.inbox_path()` would resolve a *different* project through
  `git rev-parse` and create `<repo>/.claude/reflection` in the developer's real checkout.
  1. **inbox** — `seed_two_failures()` FIRST (without a pending checkpoint
     `handle_pre_tool_use` returns 0 at `:361-363` and never reaches
     `is_receipt_inbox_write()`, so both legs would pass vacuously), then the inbox Write
     is `returncode == 0` and a sibling Write is `returncode == 2`.
  2. **SessionStart carry-over** — a `0o777` fallback root containing a planted
     `<key>.carryover`: exit 0, and the planted text appears in neither stdout nor stderr.
  3. **PreCompact** — duties seeded while the root is fully private, then only the
     **parent** made `0o777`. Reads still trust the leaf, so duties are non-empty and the
     write path is genuinely reached; `ensure_ledger_dir()` (parent **and** leaf) refuses,
     no carry-over file is created, and the hook still returns 0.

## Testing Strategy

- `ECC_HOOK_PROFILE` forced explicitly in every added test (`minimal` in-process,
  `standard` for the gate, matching the existing fixtures).
- Every test is **bound**, and each gate guard is bound by its OWN surgical mutant (see
  Measured evidence): ledger test 2 fails on any per-invocation path; 4/5/6 fail if
  `_is_private_dir` is deleted; 7 fails if the read guards are removed; 8 fails if the
  override branch starts appending a project segment; the three gate tests fail when, and
  only when, their respective guard is reverted.
- Run: `python3 -m pytest tests/test_reflection_ledger.py tests/test_reflection_gate.py -q`
  (expect 83 + 13 = 96 passed), then the full suite, `ruff check`, `mypy`, and
  `shellcheck` per the DoD.
- Report measured pass counts; do not claim a number that was not observed.

## Rollback Plan

`git checkout -- .claude/hooks/reflection.py .claude/hooks/reflection-gate.py
tests/test_reflection_ledger.py tests/test_reflection_gate.py`. No data migration: an
existing ledger under the old flat path is simply orphaned, and orphaning it is harmless —
the ledger is session-scoped and disposable by design. No schema change
(`SCHEMA_VERSION` stays 1).

## Risk Assessment

- **Low:** override semantics unchanged (bound by an existing assertion); inbox untouched;
  `SCHEMA_VERSION` untouched; failures degrade (`False`/`None`/`[]`) exactly as today.
- **Medium:** `_project_key()` invokes `project_root()`, which may shell out to
  `git rev-parse` when `CLAUDE_PROJECT_DIR` is unset. Mitigated by the per-process memo and
  the existing 10s timeout; in hook context `CLAUDE_PROJECT_DIR` is set by Claude Code. A
  session whose project root *changes mid-session* (rare: `cd` into a different repo with
  no `CLAUDE_PROJECT_DIR`) would retarget its ledger — an acceptable, explicit consequence
  of project discrimination, and strictly better than silently sharing state.
- **Medium:** refusal on a hostile or legacy world-writable `claudekit-reflection-u*`
  directory means reflection degrades on that host until it is removed. It must not do so
  *quietly* — that is the very failure mode Option 2 is rejected for — so
  `_warn_untrusted_root()` writes one advisory line to **stderr per process** (never
  stdout, never a non-zero exit). Before this revision nothing logged it at all.
- **Medium (new latency on a blocking path):** `entries()` -> `ledger_dir_trusted()` ->
  `ledger_dir()` -> `project_root()` can spawn `git rev-parse` (10 s timeout) on every
  `PreToolUse` when `CLAUDE_PROJECT_DIR` is unset. The `_project_key()` memo is
  per-process and each hook invocation is a fresh process, so memoisation cannot help.
  Claude Code sets `CLAUDE_PROJECT_DIR` in practice, so the real-world impact is low, but
  the cost is real and is stated here rather than hidden.
- **Low (documented behaviours, not defects):** with `CLAUDE_PROJECT_DIR` unset **and**
  cwd outside any git repo, `project_root()` falls back to `Path.cwd()`, so the ledger
  root follows cwd within a session; worktrees and symlinked checkouts are unaffected
  (the path is realpath'd). `ensure_ledger_dir()` uses `os.mkdir` per audited component,
  so `os.makedirs(base, exist_ok=True)` is called first to preserve the old behaviour
  when `$TMPDIR` itself does not exist.
- **High:** none. No blocking-hook exit path, no protected file, no deletion, no version
  bump.

## Follow-ups (not in this plan, owner-gated)

- CHANGELOG `[Unreleased]` entry and `.ai/SESSION_STATE.md` note — excluded from this
  workstream's file ownership.

## Measured evidence (plan dry-run, 2026-08-20, revision 2)

Applied to a mirrored copy of the four files; the working tree was never modified
(`git status --porcelain` shows only plan files, and `<repo>/.claude/reflection` does not
exist).

- `validate-config-json.py ...ops.json` -> `APPROVED`; 13 anchors, each `count == 1`.
- Patched mirror: **96 passed** (83 existing + 13 new; no existing test modified).
- `ruff check --line-length 100` on the patched mirror: `All checks passed!`
- Product reverted / tests applied, ledger classes: **8 failed, 2 passed**. The two greens
  are regression guards by design (cross-process continuity, inbox locality) and are bound
  by mutation instead.
- **Per-guard surgical mutants**, each run against `TestUntrustedLedgerRootInTheGate`
  (3 tests) — every mutant kills exactly its own test and no other (`1 failed, 2 passed`):
  | reverted guard | killed test |
  |---|---|
  | `is_receipt_inbox_write()` early return removed | `test_exactly_the_resolved_inbox_is_permitted_on_the_fallback` |
  | `ledger_dir_trusted()` dropped from SessionStart carry-over read | `test_session_start_never_echoes_carryover_from_an_untrusted_root` |
  | `ensure_ledger_dir()` restored to `mkdir(parents=True, exist_ok=True)` in PreCompact | `test_pre_compact_writes_no_carryover_into_an_untrusted_root` |
- Continuity mutant: appending `os.getpid()` to the fallback path turns
  `test_a_session_ledger_persists_across_separate_hook_invocations` red.
- `mypy` is configured over `src/`; `.claude/hooks/` is outside its scope.

## Review findings addressed (revision 2)

- **MAJOR 1** — the gate inbox test now seeds a checkpoint first and asserts `0` / `2`; the
  two tautological assertions are gone; boundness proven by mutant. Plan text corrected.
- **MAJOR 2** — both `reflection-gate.py` edits now have a dedicated, individually bound
  test (SessionStart carry-over; PreCompact via the private-leaf / hostile-parent layout).
- **MAJOR 3** — the fixture sets `TMPDIR` and `CLAUDE_PROJECT_DIR` in-process via
  `monkeypatch` as well as in the subprocess env, so `project_root()` never falls through
  to `git rev-parse` and no directory is created in the real checkout; verified absent.
- **MINOR** — `_warn_untrusted_root()` added (one stderr line per process) with its own
  test; the false "logged by the gate" claim replaced.
- **MINOR** — leaf-only vs `(parent, leaf)` audit asymmetry documented in the
  `ledger_dir_trusted()` docstring and in Step 1.
- **MINOR** — `git rev-parse` latency on the `PreToolUse` path named in Risk Assessment.
- **MINOR** — cwd-derived root edge (no `CLAUDE_PROJECT_DIR`, cwd outside a repo)
  documented; worktrees/symlinked checkouts explicitly unaffected.
- **MINOR** — `os.makedirs(base, exist_ok=True)` restores the old missing-`$TMPDIR`
  behaviour before the audited components.
- CHANGELOG untouched — owned by the coordinator.
