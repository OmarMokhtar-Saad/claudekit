# Implementation Plan: Context Recovery Refinement (adoption A3)

## Overview

Two narrow refinements to assets that already exist: make the session-context injected at
SessionStart carry the **unfinished** half of the saved state instead of a positional
prefix of the file, and make task state land on disk **during** the session rather than
only when a human runs `/save-session`. No new agent, command or skill; no new file in
`.claude/hooks/`.

## Phase 0: Design precheck

**Ownership model.** `.claude/session-context.md` is **human/model-owned** — written by
`/save-session`, and in a fleet project possibly hand-written in a private format. The new
`.claude/session-footprint.md` is **machine-owned** — written only by
`reflection-gate.py`, never hand-edited, never merged. This plan keeps those two files
strictly disjoint: nothing here ever writes `session-context.md`, and the footprint is a
separate path. That is what makes the change fleet-safe, and it is the single assumption
the whole design rests on. The value of the change sits in
`.claude/hooks/session-start.sh` (what gets injected) and `.claude/hooks/reflection-gate.py`
(when state is persisted) — both are covered by operations below.

**Rejection-brief search (mandatory).** `review-record.py rejections search "session
context precompact injection recovery"` → exit 0, 14 matches. One is a validated match:

- `agent-memory-learning` (round 2, REVISE 81) — CRITICAL: *"session-start.sh op splits
  the helper invocation across two lines so gen-docs.py `_is_helper_module()` does not
  classify session-memory-context.py as a helper; HOOK_GLOBS includes `*.py` so the hook
  count moves."* **Verified still live**: `scripts/gen-docs.py:76` `HOOK_GLOBS = ("*.sh",
  "*.py")` and `_hook_files()` globs `.claude/hooks` only; `session-start.sh:243-249`
  carries the warning comment.
  **What this plan does differently:** the new Python file is created at
  `.claude/operations/scripts/session_digest.py`, **outside** `.claude/hooks/`, so it is
  not in the counted set at all and no helper-classification question arises. This is the
  same precedent `heal_local_settings.py` and `repo-hygiene.py` already set
  (`session-start.sh:95-98` states the reason in the tree). The single-literal-line
  invocation of `session-memory-context.py` at `session-start.sh:248-249` is **not
  touched** by any operation here.

The other 13 matches are mutation-proof-overclaim and licensing findings from unrelated
plans; the overclaim class is answered by the "shown capable of failing" column in
Testing Strategy. Silence elsewhere is not evidence — the two deltas below were each
verified by reading the current files, not inferred from the research note.

## Findings that justify the change (verified against the current tree)

**Delta 1 — the injection is positional, not selective. CONFIRMED.**
`.claude/hooks/session-start.sh:191`:

```bash
_ctx_excerpt=$(head -20 "$CONTEXT_FILE" | head -c 4000)
```

That is the first twenty lines of the file, whatever they contain. In the format
`/save-session` actually writes (`.claude/commands/save-session.md:43-70`,
`.claude/skills/context-keeper/SKILL.md:17-63`) the sections run: header, `## Current
Status`, `## What Was Done`, **then** `## Next Steps (in order)`. So the bound cuts in the
worst possible place: it injects the *finished* work and truncates the *unfinished* work.
Measured on the plan's own test fixture (ten "What Was Done" bullets, which is normal for
a real session): line 20 of the file is the literal `## Next Steps (in order)` heading, so
every next step falls outside the bound. This half of A3 is **worth taking**.

**Delta 2 — nothing persists task state on the way in. CONFIRMED.**
The registered `PreCompact` hook is `reflection-gate.py`
(`.claude/settings.json:94-104`). Its handler, `reflection-gate.py:400-433`, writes a
carry-over file containing **reflection duties only** (`reflection.duty_summary`), and
only `if duties:`. It never touches `session-context.md` and records nothing about the
task. `/save-session` is user-invoked and end-of-session. Therefore: **a session that ends
without `/save-session` loses its task state today.** Two further limits found while
verifying, which shape the design:

- The reflection carry-over is keyed by session id (`reflection.py:422
  carryover_path`) and replayed only into the same session, so it cannot help a *new*
  session after a crash. The footprint must be a plain project file instead.
- `reflection-gate.py:561-564` returns early when `ECC_HOOK_PROFILE=minimal`, **before**
  `Stop` is dispatched. This repo runs `minimal` (CLAUDE.md session-setup gotcha). A
  footprint written inside `handle_stop` would therefore never be written here. The call
  must sit above that gate — which is exactly what the file's own PROFILE CONVENTION
  header (lines 40-49) says: `minimal` suppresses *blocking*, not *recording*.

## Scope

- **In Scope:** `.claude/operations/scripts/session_digest.py` (new),
  `.claude/hooks/session-start.sh` (injection branch + footprint block),
  `.claude/hooks/reflection-gate.py` (write the footprint at Stop/PreCompact),
  `tests/test_session_digest.py` (new), `CHANGELOG.md`, and — so the machine-owned
  footprint can never become a tracked or managed artifact — `.gitignore`, `install.sh`
  (`NEVER_MANAGED`) and `.claude/operations/scripts/preserve_assets.py` (`SKIP_NAMES`).
- **Out of Scope:** any new agent, command or skill; any new file under `.claude/hooks/`;
  changing `/save-session`'s output format; the unused `session-state.json` schema in
  `context-keeper` SKILL.md:186+; the reflection duty/receipt machinery itself; making
  anything blocking.

## Prerequisites

None. Python 3.9 stdlib only, bash 3.2 safe, no new dependencies.

## Implementation Steps

### Step 1: Create the digest helper
- **File:** `.claude/operations/scripts/session_digest.py`
- **Action:** Create
- **Description:** One stdlib script, three subcommands.
  - `excerpt <file>` — parse the save-session sections and print only `**Task:**`,
    `Current Status`, `Next Steps`, **unchecked** `Open Questions`, `Active Plan` and
    `Context for Fresh Agent`. Drops `What Was Done`, `Files Touched`, `Decisions Made`.
    **Exit 3 = "format not recognised"**, which is the caller's signal to keep its own
    excerpt.
  - `footprint --root R` — write `.claude/session-footprint.md` from git facts only
    (branch, HEAD, changed paths, ops configs present). Never model prose.
  - `footprint-show --root R` — print it, but only when it is **newer** than
    `session-context.md`.
- **Details:** Heading matching is prefix-based, not equality — the shipped format writes
  `## Next Steps (in order)`, and an equality test silently drops the most important
  section. (This was a real bug in the first draft, caught by executing it.) Bounds are
  per-line (160 chars) **and** per-digest (1600 chars), because a single huge line passes
  any line-count bound — the defect `test_a_single_huge_line_is_bounded_by_bytes_not_just_lines`
  already records. **Exactly one bound per axis, deliberately:** an earlier draft of
  `footprint_show()` *also* sliced the line list at `MAX_FILES + 8`, a third truncation
  point with a different rule, which made "bounded by bytes" not identically true there
  and left a reader unable to tell which limit had fired. That slice is removed rather
  than documented, because the line count is already bounded at **write** time
  (`footprint_text` emits a fixed header plus at most `MAX_FILES` paths), so it bought
  nothing. `session-start.sh` applies its own outer `head -c` as belt-and-braces. Refuses to write through a symlink.
- **Why not in `.claude/hooks/`:** `scripts/gen-docs.py:76` counts `*.py` there as hooks;
  see Phase 0.

### Step 2: Use the digest for the injected excerpt, with a fallback
- **File:** `.claude/hooks/session-start.sh`
- **Action:** Modify (replace line 191 only)
- **Description:** Try `session_digest.py excerpt`; if python3 or the script is missing,
  or the digest is empty (exit 3, unrecognised format), fall back to the existing
  `head -20 | head -c 4000`.
- **Details:** The excerpt is produced **before** the existing scanner call and flows into
  the unchanged scan/print branches, so the injection-scan guarantee and every assertion in
  `tests/test_session_context_scan.py` are preserved by construction. Those tests copy only
  the hook, `lib.sh` and the scanner into a tmp tree — no digest — so they now exercise the
  fallback path and stay green. The `session-memory-context.py` invocation at lines 248-249
  is untouched.

### Step 3: Print the footprint at session start
- **File:** `.claude/hooks/session-start.sh`
- **Action:** Modify (new block after the session-context block)
- **Description:** Run `session_digest.py footprint-show`, pipe it through
  `prompt-injection-scanner.sh`, print only on exit 0, else print a "not shown" line.
- **Details:** Silent when there is no footprint, when the scanner is missing, or when a
  newer `/save-session` exists. Machine-written or not, a path in a shared repo is
  attacker-influenceable, so it is scanned like everything else on this path.

### Step 4: Write the footprint on the way in
- **File:** `.claude/hooks/reflection-gate.py`
- **Action:** Modify
- **Description:** Add `import importlib.util`, add `record_footprint()`, and call it for
  `Stop`, `SubagentStop` and `PreCompact` **before** the `blocking_enabled()` gate in
  `main()`.
- **Details:** Loads `session_digest.py` by path (the same technique
  `session-memory-context.py:45-55` already uses for `knowledge-ledger.py`) and calls
  `write_footprint(root)`. Wrapped in `try/except Exception` and logged at WARN: a recovery
  convenience must never change whether a turn is blocked. **Nothing here becomes
  blocking** — hard rule 2 is about blocks, and this path issues none.

### Step 5: Tests
- **File:** `tests/test_session_digest.py`
- **Action:** Create
- **Description:** Twelve behavioural tests driving the real hook and the real gate as
  subprocesses. See Testing Strategy.

### Step 6: Keep the footprint untracked and unmanaged
- **Files:** `.gitignore`, `install.sh`, `.claude/operations/scripts/preserve_assets.py`
- **Action:** Modify
- **Description:** Add `.claude/session-footprint.md` to `.gitignore` beside the other
  runtime-state rules (after the `.claude/locks/` block, matching the sectioned-comment
  structure at lines 51-79 rather than appending loose); add `session-footprint.md` to
  `install.sh`'s `NEVER_MANAGED` and to `preserve_assets.py`'s `SKIP_NAMES`, which
  `preserve_assets.py:38` requires to stay in step.
- **Details:** This is decided, not optional: the file is regenerated at every Stop and
  carries branch, HEAD and changed paths. The reachability evidence for each of the three
  is in "Can the fleet machinery reach the footprint?" above.

### Step 7: Changelog
- **File:** `CHANGELOG.md`
- **Action:** Modify — add an `[Unreleased]` entry.

## Testing Strategy

Every claim below names a test **and** how to make it go red. The two tests marked RED
already fail against the unmodified tree today — that is the measurement, not a promise.

| Claim | Test | How it goes red |
|---|---|---|
| The unfinished work reaches the transcript | `test_the_injected_excerpt_carries_the_unfinished_work` | **RED today**: `head -20` stops at the `## Next Steps` heading, so the marker is absent |
| The finished work stops being re-injected | `test_the_injected_excerpt_drops_the_finished_work` | **RED today**: the first 20 lines print the DONE marker ten times |
| Ticked questions are dropped | `test_a_ticked_open_question_is_not_injected` | delete the `- [x]` filter in `excerpt()` |
| A fleet project's own format still loads | `test_a_project_with_its_own_format_keeps_todays_behaviour` | make `excerpt` exit 0 with empty output instead of 3 — that project's context vanishes |
| The digest is byte-bounded | `test_the_digest_is_bounded_by_bytes` | remove the `LINE_CHARS`/`MAX_CHARS` caps |
| The digest is not a scan bypass | `test_a_poisoned_context_file_is_still_not_echoed` | move the new excerpt branch below the scanner call |
| State lands on disk with no `/save-session` | `test_task_state_lands_on_disk_without_save_session` | **RED today**: no writer for `session-footprint.md` exists |
| It is written under `minimal` | `test_the_footprint_is_written_under_the_minimal_profile` | move `record_footprint()` below `blocking_enabled()` — every other test stays green |
| PreCompact writes it too | `test_pre_compact_also_writes_the_footprint` | drop `PreCompact` from the event set |
| A project's own context file is untouched | `test_the_footprint_never_touches_a_projects_own_session_context` | point `write_footprint()` at `CONTEXT_NAME` |
| It stays quiet under a newer save | `test_the_footprint_is_silent_when_a_newer_save_exists` | drop the mtime comparison (ordering is forced with `os.utime`, so the verdict cannot depend on filesystem mtime granularity) |
| ...but it does print when it is the fresher record | `test_the_footprint_shows_when_it_is_newer_than_the_save` | make `footprint_show` always return `""` — which would satisfy the row above on its own |
| The footprint is scanned before printing | `test_a_poisoned_footprint_is_not_echoed` | drop the scan from the new block |
| It is never tracked, manifested or preserved | `test_the_footprint_is_never_a_tracked_or_managed_artifact` | drop any one of the three entries (`.gitignore`, `NEVER_MANAGED`, `SKIP_NAMES`) |

Plus the existing suite, unchanged and expected green: `tests/test_session_context_scan.py`
(now exercising the fallback path — this is the fleet-compat regression net) and
`tests/test_dispatch_payload.py` / `scripts/gen-docs.py --check` / `ck doctor --strict`
for the hook count, which must remain unmoved.

**Definition of Done gate:** `python3 -m pytest tests/ -q`, `ruff check`, `mypy`,
`gen-docs.py --check`, `gen-registry.py --check`, `check-context-floor.py --check`,
`check-plan-artifacts.py --check`, `shellcheck install.sh .claude/hooks/*.sh`.

## Fleet behaviour (explicit)

A downstream project that has its **own** `.claude/session-context.md`:

- **Never written.** No operation and no new code path writes that file. The footprint is
  a different path, and `test_the_footprint_never_touches_a_projects_own_session_context`
  mechanises it.
- **Never silently dropped.** If the file does not use the save-session headings, `excerpt`
  exits 3 and the hook prints exactly what it prints today.
- **Never repeated.** If the project does use `/save-session`, the fresher human record
  wins and the footprint stays silent.
- **No `session-context.md` at all** (the common case in a fresh project): the
  `if [ -f "$CONTEXT_FILE" ]` block at `session-start.sh:164` is skipped entirely, the
  digest is never invoked, and only the footprint block fires. So a project that has never
  run `/save-session` gets recovery state it did not have before, and nothing else changes.
- `.claude/session-footprint.md` is machine-owned and regenerated on every Stop, so a sync
  that overwrites it loses nothing. It is now gitignored **in this repo** (op
  `gitignore-footprint`), and excluded from the install manifest and the preservation
  pass — see the next section.

## Can the fleet machinery reach the footprint? (verified; a reviewer got this wrong)

An earlier review round asserted that `preserve_assets.py` and `fleet-enhance.py` do not
exist here. **They do**, and the question was worth asking. Answers, with the lines that
prove them, so the next reader does not re-derive this:

- **`fleet-enhance.py` — CANNOT reach it.** `kit_files()` at
  `.claude/operations/scripts/fleet-enhance.py:58-68` walks only
  `os.path.join(KIT, sub)` for `sub in SYNC_DIRS` (line 41:
  `("skills", "agents", "commands", "hooks", "modes")`). `.claude/session-footprint.md`
  sits at the `.claude/` **root**, under no `SYNC_DIR`, so it is never enumerated and its
  `NEVER` set (line 45) never has to mention it. No change made — adding it would imply a
  reach that does not exist.
- **`preserve_assets.py` — CANNOT reach it by directory.** The gate at
  `preserve_assets.py:145` is `return rel.split(os.sep)[0] in ASSET_DIRS`; for a
  root-level file the first path component is the filename itself, which is not in
  `ASSET_DIRS` (lines 33-36). **But** line 38 states `SKIP_NAMES` "must stay in step with
  `NEVER_MANAGED` in install.sh's manifest block", and that set does need the entry —
  see below — so `SKIP_NAMES` is updated to match (op `preserve-skip-names`). This is a
  coherence fix, not a reachability fix, and is labelled as such.
- **`install.sh` — CAN reach it, and this is the one that mattered.** The manifest walk at
  `install.sh:673-683` is `os.walk(dest)` over the **whole** installed tree, filtered only
  by *basename* against `NEVER_MANAGED` (line 669). A root-level runtime file is therefore
  hashed into `.claudekit-manifest.json`, after which `ck diff` reports permanent drift on
  a file that is rewritten at every Stop — exactly the failure `hooks.log` is already in
  that set to avoid. `session-footprint.md` is added (op `installer-never-managed`).

`test_the_footprint_is_never_a_tracked_or_managed_artifact` pins all three entries.

## Rollback Plan

1. `git revert` the commit, or delete `.claude/operations/scripts/session_digest.py` and
   `tests/test_session_digest.py` and revert the two hook files.
2. `.claude/session-footprint.md` is generated state — delete it; nothing reads it once
   the hook block is gone.
3. No schema, no migration, no persisted format to unwind. The digest is read-only over
   `session-context.md`, so a revert cannot have corrupted a saved session.

## Risk Assessment

- **Low:** the digest helper itself (new file, no caller depends on it succeeding — every
  failure path degrades to today's behaviour); the CHANGELOG entry.
- **Low:** the footprint file's content — git-derived, bounded (one bound per axis; see
  Step 1), control-characters stripped, scanned before printing.
- **Low, but touching the installer:** the `NEVER_MANAGED` / `SKIP_NAMES` edits are
  single-name additions to two sets that must agree (`preserve_assets.py:38`). The risk is
  not the edit, it is forgetting one of the pair — which is why the test asserts both.
- **Medium:** `session-start.sh` is a GOD-NODE-ish asset — it ships to the whole fleet and
  runs in every profile. Mitigations: the edit is one replaced line plus one appended
  block, both with explicit fallbacks, and `tests/test_session_context_scan.py` is an
  existing, independent net over the path being touched.
- **Medium:** `reflection-gate.py` is a **blocking** hook. The call is placed on a
  non-blocking path, wrapped in a bare `except Exception`, and returns `None` — but an
  unbounded exception escaping `main()` here would emit rc 1, which hard rule 2 forbids.
  This is the one line a reviewer should stare at.
- **Medium:** the digest's heading matching is heuristic. If `/save-session` drifts from
  the documented format, the digest silently degrades to the fallback rather than to
  nothing — chosen deliberately, but it means a format drift will be quiet.
- **Blast radius, measured by grep, not by graph:** `.claude/project-graph.json` does
  **not** exist in this tree (`project-graph.py query` returns "no graph ... fall back to
  grep"), so the impact query was unavailable and inbound references were established by
  grep instead: `session-context.md` is referenced by `tests/test_008_batch2_merges.py`,
  `tests/test_session_context_scan.py`, `.claude/skills/context-keeper/SKILL.md` and both
  session commands. Nothing reads `session-start.sh`'s stdout programmatically except
  those tests. Treat the blast radius as unknown-but-grepped, not as graph-verified.
