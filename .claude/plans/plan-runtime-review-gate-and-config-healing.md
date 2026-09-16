# Implementation Plan: Runtime author≠reviewer gate (A2) + auto-healing local config (B2)

Ops config: `.claude/plans/plan-runtime-review-gate-and-config-healing.ops.json`

## Phase 0 — Design precheck

**Ownership / data model.** A2's invariant is *"the identity that recorded the verdict must
not be the identity that authored the ops.json."* The value therefore sits in two records,
not in the ops.json: the review record (`.claude/reports/reviews/<ops_slug>.json`, written by
`write_verdict`, read by `cmd_check`) and — today — **nowhere at all** for the author.

Evidence that no author identity is persisted today, gathered by reading the files rather
than trusting the research note:

| Claim | Evidence |
|---|---|
| The review record holds no reviewer identity | `write_verdict` builds `record` at `review-record.py:771-786`; keys are plan/slug/ops_path/ops_sha256/score/decision/findings/verdict_origin/recorded_utc + `load_ops_summary`. No session field. |
| A session id *is* resolvable and already implemented | `_session_id()` (`:485`) → env `CLAUDE_SESSION_ID`/`CLAUDEKIT_SESSION_ID`, else `_session_from_pointers()` (`:425`), else the literal `"unknown"`. |
| The session id is currently used only for rejection briefs | It reaches `emit_brief(slug, record, rounds, session_id)` (`:864`) and nothing else; `cmd_check` (`:907-965`) never sees it. |
| The executor records no author identity either | `execute-json-ops.py` writes `manifest.json` with `plan`, `timestamp`, `files`, `created_files` only (`:407-429`). `grep -n "session" execute-json-ops.py` returns only the words "concurrent session" in comments. |
| The stamp mechanism mutates the ops.json | `stamp_baseline` writes `config['baseline']` back to the config file (`validate-config-json.py:885-892`). |

So: **no author identity is persisted today. Persisting it is part of this plan.**

**Where it must NOT go: inside the ops.json.** `cmd_check:939` binds the verdict to
`sha256_of(ops_path)` over raw bytes, and its own error text (`:944-950`) names the recorded
trap: writing anything into the config after a verdict deadlocks the gate as DRIFT. An
`"authored_by"` key in the ops.json would reintroduce exactly that failure. Authorship
therefore lives in a **sidecar beside the record**: `.claude/reports/reviews/<ops_slug>.author.json`.
Writing it can never move the ops.json hash, at any point in the sequence.

**Rejection-brief search (mandatory).** Run and read:

```
review-record.py rejections search "review gate author reviewer identity session"   # exit 0, 14 matches
review-record.py rejections search "settings.local.json heal config"                # exit 0, 2 matches
```

One hit is a validated match and is honoured below:
`.claude/knowledge/rejections/agent-memory-learning.md` — *"session-start.sh op splits the
helper invocation across two lines so gen-docs.py `_is_helper_module()` does not classify
session-memory-context.py as a helper; HOOK_GLOBS includes `*.py` so the hook count [moves]"*.
Verified still live: `scripts/gen-docs.py:77` `HOOK_GLOBS = ("*.sh", "*.py")` and
`:82` globs **`.claude/hooks/` only**. **What this plan does differently:** the B2 healer is
placed in `.claude/operations/scripts/heal_local_settings.py`, which `HOOK_GLOBS` never sees,
so no hook count moves and no helper-classification rule applies. The remaining hits
(`e2e-lane-a`, `retro2-*`, `fleet-a2b-d1-d3`) are about mutation-proof overclaim, a stale
heldout MANIFEST and licence files; re-read, none constrains this change beyond the
"prove the check can fail" discipline already enforced in the test sections below.

---

## Overview

Two independent, small changes:

- **A2** — build the enforcement *point* for "author ≠ reviewer", and ship it
  **inert-but-honest**: persist the ops.json author's session id in a sidecar, persist the
  reviewer's session id in the review record, and refuse execution in `cmd_check` when the
  two are known and equal. In this repo's actual sessions the comparison will **not bind**,
  because nothing exports `CLAUDE_SESSION_ID`/`CLAUDEKIT_SESSION_ID` and both sides record
  `"unknown"` (making them resolve is explicitly out of scope, owner decision). So this ships
  a proven mechanism and a printed disclosure, not an enforced invariant — CLAUDE.md's review
  floor remains prompt-enforced in practice, and no doc in this change may say otherwise.
- **B2** — make the gitignored `.claude/settings.local.json` self-healing in the ClaudeKit
  repo itself, so a missing or malformed override stops costing a manual restoration.

## Scope

- **In scope:** `review-record.py`, `validate-config-json.py`, `execute-json-ops.py` (one
  message-map entry), a new `heal_local_settings.py`, one invocation block in
  `session-start.sh`, two new behavioural test files, CHANGELOG + CONTRIBUTING.
- **Out of scope:** A1/A3/B1/C1 from the research note; changing the approval threshold;
  making `_session_id` resolve more often; any fleet sync; any `docs/` count change (no
  asset is added under a counted directory — verified: `gen-docs.py:64-82` counts
  `.claude/agents|commands|skills|hooks` only).

## Prerequisites

- `ECC_HOOK_PROFILE=minimal` in the session (CONTRIBUTING.md) — B2 exists to make this
  self-repairing but does not change how it is set today.
- No new dependency; everything is stdlib, Python 3.9-compatible, bash 3.2-safe.

---

## Part A2 — Author ≠ reviewer: the runtime enforcement point (shipping inert)

### Step A2.1 — Exit-code contract and usage header

- **File:** `.claude/operations/scripts/review-record.py` · **Action:** Modify · header docstring
- Add to the usage block: `review-record.py author  <ops.json> [--session-id UUID]`
- Add one exit code line: `6  SELF-REVIEW - the recorded verdict came from the session that authored this ops.json (blocking)`

**Why 6 and not 2 or 4** (the plan's answer to "pick a coherent code"): the file's documented
contract already assigns `2 = DRIFT` and `4 = verdict does not authorise execution`
(`:19-25`). Reusing `2` would report a self-review as a hash mismatch — a lie about the
file. Reusing `4` is semantically defensible but collapses two different remedies into one
cause string, and `execute-json-ops.py:964-977` exists specifically to keep refusal causes
distinct in RESULT-JSON ("'no record exists' and 'a verdict exists but does not authorise
this ops.json' have different remedies and must not read identically"). `5` is taken by
`write`. `6` is additive: codes 0-4 keep their exact meanings, so nothing that reads them
breaks.

**Relation to hard rule 2.** Hard rule 2 governs *blocking hooks* (`exit 2` + stderr, fail
closed). `review-record.py` is a CLI, not a hook; the hook-shaped surface in this pipeline is
`ops-enforcement.sh`, which already exits 2. What rule 2 demands of this path — a
**non-zero exit, a message on stderr, and failing closed** — is satisfied: the message is
printed to stderr and `check_approval` turns any non-zero code into a refusal by default
(`execute-json-ops.py:964`, `.get(code, ...)` fallback). Flagging this for the reviewer as a
deliberate, justified deviation from a literal reading of "exit 2".

### Step A2.2 — Persist author identity (sidecar)

- **File:** `.claude/operations/scripts/review-record.py` · **Action:** Modify
- Add `AUTHOR_SUFFIX`, `SELF_REVIEW_EXIT = 6`, `author_path(slug)`, `load_author(slug)`,
  `record_author(ops, session_id=None)`, `cmd_author(args)` immediately before `cmd_check`.
- `author_path` reuses `record_paths`' sanitisation rule and `_records_dir()`, so the sidecar
  always lands next to the record it describes, keyed by the same `ops_slug`.
- `record_author` writes through `_safe_write` (symlink-refusing, `:306`). **First known
  author wins**: an existing sidecar naming a *known* session is never overwritten (a
  re-stamp is the same author re-running the same step); an existing sidecar naming
  `"unknown"` is upgraded when a real id becomes resolvable.
- Returns 0 even when the id is `"unknown"`, printing a NOTE to stderr. `"unknown"` is an
  honest answer here for the same reason `_session_from_pointers` documents at `:426-441`.

### Step A2.3 — Capture authorship on the sanctioned stamp path

- **File:** `.claude/operations/scripts/validate-config-json.py` · **Action:** Modify · `main()` at the `--stamp-baseline` branch
- After the existing `Baseline stamped: N file(s)` line, best-effort import
  `review-record.py` by path and call `record_author(args.config)`.
- **Fail-soft by construction**, mirroring the `emit_brief` contract (`review-record.py:31-36`):
  wrapped in `except Exception`, cannot change the validator's exit code, prints a NOTE on
  failure. A bookkeeping feature must never be able to reject a valid config.
- Stamping is the right moment: it is the last step the *author* performs before review, and
  it already mutates the ops.json, so the hash is settled from here on. The sidecar itself
  does not touch the config.

### Step A2.4 — Persist reviewer identity

- **File:** `.claude/operations/scripts/review-record.py` · **Action:** Modify · `write_verdict`
- Add `"reviewer_session": _session_id(session_id),` to the `record` dict.
- This writes to `.claude/reports/reviews/<slug>.json`, **never** to the ops.json — no hash
  moves, so the stamp/verdict deadlock cannot be reintroduced.
- `ROUND_KEYS` is deliberately left alone: `cmd_check` reads the top level, and the existing
  comment at `:788-790` makes "rounds is purely additive" a load-bearing property.

### Step A2.5 — The gate

- **File:** `.claude/operations/scripts/review-record.py` · **Action:** Modify · `cmd_check`
- Inserted **after** the DRIFT check and **after** the APPROVED/threshold check, immediately
  before the final `OK:` print, so a self-reviewed but already-rejecting verdict still
  reports its real cause (4), and a drifted one still reports DRIFT (2).
- Blocks only when `author != "unknown" and reviewer != "unknown" and author == reviewer`:
  stderr block + `return SELF_REVIEW_EXIT`.
- When either identity is unknown, exit stays 0 and a NOTE says the gate **did not bind**.
  That line is the whole defence against an inert green check: the limitation is printed at
  the moment of use, not buried in a doc.

### Step A2.6 — Distinct cause in the executor

- **File:** `.claude/operations/scripts/execute-json-ops.py` · **Action:** Modify · `check_approval` cause map
- Add `6: "the recorded verdict was written by the session that authored this ops.json (self-review)"`.
- Behaviour is already fail-closed without this edit (the `.get` fallback refuses on any
  non-zero code); the edit only makes the refusal legible.

### Step A2.7 — Behavioural test

- **File:** `tests/test_author_not_reviewer.py` · **Action:** Create
- Modelled on `tests/test_approval_machinery.py`: real scripts, real temp tree, real
  execution (never `--dry-run` — the recorded trap is that a dry run skips `check_approval`
  entirely, see that file's comment at `:105-107`), `ECC_HOOK_PROFILE=minimal` forced per
  subprocess.
- Identity is forced through `CLAUDEKIT_SESSION_ID`, which `_session_id` accepts (`:493-495`)
  — so the test does not depend on SessionStart pointers existing.

**Proof the gate can FAIL (not just pass):**

| Test | Setup | Asserted outcome |
|---|---|---|
| `test_self_review_refuses_execution` | author sidecar + verdict both written with session `AAA` | `check` exits **6**; a real `execute-json-ops.py` run exits non-zero; `payload.txt` still contains `alpha` — **the edit did not apply** |
| `test_distinct_reviewer_authorises_execution` (positive control) | author `AAA`, reviewer `BBB`, identical otherwise | `check` exits **0**; execution exits 0; `payload.txt` contains `ALPHA` |
| `test_unknown_identity_does_not_block` | no sidecar at all, reviewer `AAA` | `check` exits 0 and stderr names the gate as not bound — pins the backward-compatible path so the change cannot brick existing records |
| `test_self_review_is_not_reported_as_drift` | same-session pair | stderr contains `SELF-REVIEW` and **not** `DRIFT` — pins the exit-code choice |
| `test_author_sidecar_never_touches_the_ops_json` | sha256 of ops.json captured before `author`/`write`, compared after | byte-identical — the deadlock trap cannot return |

The first row is the failure demonstration the repo's "inert green check" history demands:
the two rows differ **only** in the reviewer's session id, so if the comparison in `cmd_check`
is removed or mis-wired, row 1 flips to a pass-through and fails loudly.

### A2 rollback

Revert the four edits (three files) and delete `tests/test_author_not_reviewer.py`; stale
`*.author.json` sidecars under `.claude/reports/reviews/` become inert data read by nobody.
No migration, no state to unwind: existing records lack `reviewer_session`, and the gate
treats a missing field as `"unknown"` → non-blocking.

### A2 risk

- **HIGH — self-application lockout.** This repo runs its own pipeline. If author and
  reviewer resolve to the same id, our own `/implement` stops. Mitigations, in order: (1) the
  gate binds **only** when both ids are resolvable and equal — today neither env var is
  exported (`review-record.py:489-491`: *"nothing exports them"*) and `_session_from_pointers`
  needs a SessionStart pointer, so the common case is `"unknown"` and non-blocking; (2)
  `--no-approval` already exists as a loudly-logged escape hatch (`execute-json-ops.py:1071-1075`)
  and no new bypass is added; (3) reverting one `code_edit` disables the gate.
- **MEDIUM — the gate ships inert, by owner decision.** Not "may rarely bind": with nothing
  exporting the session env vars, the expected state in this repo is `unknown`/`unknown` and
  the gate is open on every execution. What ships is the enforcement point plus a printed
  disclosure. Three places must carry that framing in the same voice, and a reviewer should
  check all three read alike: the CHANGELOG bullet (which leads with the caveat), `cmd_check`'s
  runtime NOTE, and this risk entry. Any wording that calls the invariant "enforced" is a
  defect in this change, not a nicety — hard rule 6's honesty requirement applied to a review
  control instead of to security. Follow-up (not in this plan): a deliberate export of a
  session id on the `/plan` and `/review` paths is what would make it bind.
- **LOW — sidecar collisions.** `author_path` reuses `record_paths`' sanitiser and
  `ops_slug`, so the sidecar shares the record's proven keying (including the
  `operations/<dir>/ops.json` form fixed at `:167-198`).

---

## Part B2 — Auto-healing `.claude/settings.local.json`

### Design constraints, verified against the tree

| Constraint | Evidence | Consequence for the design |
|---|---|---|
| The file is never preserved by the asset walk | `preserve_assets.py:39` `SKIP_NAMES` includes it; `:172` skips it before `_consider` | Healing this one file **cannot** make preservation skip a real file — `_consider`, the function that carries the "written before preservation" trap, is never reached for this name |
| The installer preserves it separately | `install.sh:577-583` copies an existing one into staging; `:669` `NEVER_MANAGED` | Healing must run in a **live session**, never during install, or it could pre-create a file the installer then carries forward over the user's own |
| It must stay untracked / unsynced | `.gitignore`; `main.py:184` `_HOOK_DENY_NAMES`, `:977` `DIFF_IGNORED`; `ops-enforcement.sh:63` | The healer writes the file and nothing else — no manifest entry, no git operation, no template shipped into a counted asset directory |
| The profile takes effect at the next session start | CONTRIBUTING.md:45 | The healer announces this; it repairs the file, it does not retro-fit the running session's env |
| `minimal` disables enforcement | `ops-enforcement.sh:13` | **Healing must never fire in a fleet project** — writing `minimal` downstream would silently switch enforcement off across 14+ repos |

That last row is the design's load-bearing decision: the healer is **repo-gated**. It acts
only when the project root's `pyproject.toml` declares `name = "claudekit-agents"`, matched by
regex (no `tomllib` — this must run on Python 3.9). In any other project it exits 0 having
done nothing.

### Step B2.1 — The healer

- **File:** `.claude/operations/scripts/heal_local_settings.py` · **Action:** Create
- Placed under `operations/scripts/`, **not** `.claude/hooks/`: `gen-docs.py:77-82` globs
  `*.sh`/`*.py` under `.claude/hooks/` for the hook count, and the `agent-memory-learning`
  rejection brief records a plan rejected for moving that count. Nothing here moves a
  generated count.
- Public function `heal(root) -> (action, message)`; `action` ∈ `not-claudekit`, `no-claude-dir`,
  `symlink-refused`, `created`, `repaired`, `merged`, `kept`, `error`.
- Behaviour:
  - missing → write `{"env": {"ECC_HOOK_PROFILE": "minimal"}}` (`created`)
  - unparseable / not a JSON object → move aside to
    `.claude/settings.local.json.corrupt-<UTC>` first, then write the default (`repaired`)
  - valid object **without** `env.ECC_HOOK_PROFILE` → insert **only** that key, every other
    key preserved byte-for-value (`merged`)
  - valid object **with** any `ECC_HOOK_PROFILE` value, including `standard`/`strict` →
    untouched (`kept`). A deliberate choice is never overridden.
  - a symlink at the path → refused, untouched (same discipline as `_safe_write`)
- Writes atomically (temp file in the same directory + `os.replace`); exits 0 always —
  advisory, never blocking.

### Step B2.2 — Wire it into session start

- **File:** `.claude/hooks/session-start.sh` · **Action:** Modify
- Inserted after the existing `CK_ROOT=` assignment (line 90) — it must resolve against the
  **project** root, which is what `CK_ROOT` is for (see the comment at `:88-90`).
- bash 3.2-safe: `command -v python3`, `[ -f ... ]`, no arrays, no `${var,,}`, no process
  substitution; stderr discarded; never blocks (`session-start.sh` ends `exit 0`).

### Step B2.3 — Behavioural test

- **File:** `tests/test_local_settings_healing.py` · **Action:** Create
- Runs the real script against real temp trees; `ECC_HOOK_PROFILE` forced explicitly on
  every subprocess.

**Proof the healing can FAIL (each row fails against a plausible mis-implementation):**

| Test | Setup | Asserted outcome | What it catches |
|---|---|---|---|
| `test_missing_file_is_created` | claudekit-shaped tmp repo, no file | file exists, `env.ECC_HOOK_PROFILE == "minimal"` | healer silently no-ops |
| `test_healed_file_actually_unblocks_edit` | heal, then read the healed JSON and run the **real** `ops-enforcement.sh` with that env vs `standard` | exit **0** with the healed profile, exit **2** + `OPS ENFORCEMENT` on stderr without it | the healed value being the wrong key/value — and it is a *negative control that must fail*, proving the check measures something |
| `test_foreign_project_is_never_healed` | tmp repo whose `pyproject.toml` names something else | no file created, action `not-claudekit` | the fleet-safety gate being dropped — this is the highest-consequence failure |
| `test_same_name_fork_is_healed_known_limitation` | tmp repo that *keeps* `name = "claudekit-agents"` | file **is** created — asserted deliberately | characterisation of the known name-only gate; fails if the gate is narrowed, which is the signal to delete this test |
| `test_existing_custom_content_is_preserved` | valid file with `{"permissions": {...}, "env": {"FOO": "bar"}}` | every original key/value still present, only `ECC_HOOK_PROFILE` added | a wholesale overwrite |
| `test_deliberate_standard_profile_is_kept` | file already sets `ECC_HOOK_PROFILE: "standard"` | untouched, action `kept` | the healer overriding a maintainer's choice |
| `test_malformed_file_is_moved_aside_not_destroyed` | file containing `{ not json` | a `*.corrupt-*` sibling holds the original bytes; new file is the default | data loss |
| `test_symlink_is_refused` | path is a symlink to a file outside | target unchanged, action `symlink-refused` | writing through a symlink |

### B2 rollback

Delete `.claude/operations/scripts/heal_local_settings.py` and
`tests/test_local_settings_healing.py`, revert the `session-start.sh` block. No persistent
state beyond the file the maintainer wanted anyway; any `*.corrupt-*` sidecar is inert.

### B2 risk

- **HIGH — enforcement silently disabled in a fleet project.** Mitigated by the repo gate
  (`pyproject.toml` name match) and pinned by `test_foreign_project_is_never_healed`. Stated
  plainly: if that gate ever regresses, 14+ repos lose `ops-enforcement`.
- **MEDIUM — the repo gate is a NAME match and nothing more (known limitation, follow-up).**
  A fork, a vendored copy, or any tree that keeps `name = "claudekit-agents"` in its
  `pyproject.toml` is healed too, and has `ECC_HOOK_PROFILE` flipped to `minimal` there.
  `test_foreign_project_is_never_healed` covers only the *different name* case, so this plan
  adds `test_same_name_fork_is_healed_known_limitation` — a **characterisation** test that
  pins the current behaviour so the limitation lives in the suite rather than only in prose,
  and fails the day the gate is narrowed. **Hardening is deliberately deferred** (scope, per
  the round-1 review): a secondary check — git remote matching this project's origin, or a
  canonical-path comparison — is the fix, and it should be filed as a follow-up rather than
  smuggled into this change. Blast radius until then: a fork of this kit, not an installed
  fleet project (which fails the name match already).
- **MEDIUM — clobbering a maintainer's own local settings.** Mitigated by merge-one-key +
  `kept` semantics + move-aside on corruption, pinned by three tests.
- **LOW — preservation interaction.** `settings.local.json` is in `SKIP_NAMES`/`NEVER_MANAGED`,
  so the "written before preservation" trap cannot apply; healing runs at session start,
  never inside `install.sh`.
- **LOW — session-start cost.** One short Python process; the hook already spawns several.

---

## Files touched (every ops target path, named)

| Path | Action |
|---|---|
| `.claude/operations/scripts/review-record.py` | Modify (A2.1, A2.2, A2.4, A2.5) |
| `.claude/operations/scripts/validate-config-json.py` | Modify (A2.3) |
| `.claude/operations/scripts/execute-json-ops.py` | Modify (A2.6) |
| `tests/test_author_not_reviewer.py` | Create (A2.7) |
| `.claude/operations/scripts/heal_local_settings.py` | Create (B2.1) |
| `.claude/hooks/session-start.sh` | Modify (B2.2) |
| `tests/test_local_settings_healing.py` | Create (B2.3) |
| `CHANGELOG.md` | Modify (user-visible behaviour change) |
| `CONTRIBUTING.md` | Modify (the manual remedy now has an automatic first line) |

## Verification / Definition of Done

```bash
python3 .claude/operations/scripts/validate-config-json.py \
        .claude/plans/plan-runtime-review-gate-and-config-healing.ops.json
python3 -m pytest tests/test_author_not_reviewer.py tests/test_local_settings_healing.py -q
python3 -m pytest tests/ -q                      # zero failures tolerated
ruff check src/ tests/ scripts/ .claude/operations/scripts/
mypy
python3 scripts/gen-docs.py --check              # counts must NOT move
python3 scripts/gen-registry.py --check
python3 scripts/check-plan-artifacts.py --check
shellcheck install.sh .claude/hooks/*.sh
```

Plus one refutation pass before claiming done: re-run
`tests/test_author_not_reviewer.py::TestSelfReview::test_self_review_refuses_execution` with
the `cmd_check` comparison deleted and confirm it **fails**. A green check that has never
been shown red is not evidence (`a-passing-check-can-measure-nothing`).

## Risk Assessment (summary)

- **High:** fleet enforcement disabled by a regressed repo gate (B2); self-application
  lockout of our own pipeline (A2).
- **Medium:** the A2 gate is inert whenever identity is unresolvable — disclosed, not
  overclaimed; clobbering maintainer-local settings (B2).
- **Low:** sidecar keying, session-start cost, preservation interaction, exit-code
  deviation from a literal reading of hard rule 2 (justified in A2.1).
