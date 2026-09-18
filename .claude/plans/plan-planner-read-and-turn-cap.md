# Plan: planner-read-and-turn-cap

## Overview

Bash stdout is now capped at 12,000 chars by `output_filter.py`, but `Read` is uncapped and
subagent turn counts are prompt-enforced only. Measured (caller-verified, not re-measured here):
Read results across planner runs total 16.2M bytes with 5.0M over 12K; in the last 40
planner/reviewer runs 83 of 284 Reads carried no `limit` and 85 results exceeded 12K (2.0M excess
bytes). The prompt's "hard ceiling 30 tool calls" is ignored in practice — the first post-fix
qa-agents planner run made 91 tool calls (279K context; the previous run ended at 894K).

Two mechanical controls close both gaps:

1. a `PreToolUse`/`Read` hook that refuses an unwindowed `Read` of a file longer than 200 lines;
2. `maxTurns` in the frontmatter of the four expensive agents, so a runaway run stops with a
   PARTIAL handback (resumable via SendMessage) instead of burning context.

## Phase 0 — Design precheck

Ownership: the value of this change sits in exactly two mechanisms — the dispatcher's
`PreToolUse` handler table (`.claude/hooks/dispatch-registry.json`, the only place a new hook
becomes live; `.claude/settings.json` already delegates every `PreToolUse` to `dispatch.sh` with
matcher `""`, so **no settings.json edit is needed or wanted**) and the agent frontmatter blocks
that the harness reads at spawn. Both are files this plan touches. The guard's decision model is
per-tool-call and stateless: it sees `tool_input` and the filesystem, nothing else, so it cannot
be defeated or helped by session state. `maxTurns` is host-enforced at the subagent boundary; no
repo code reads it, so the only risk it carries is frontmatter validity and prompt byte ceilings,
both of which are gated by existing tests.

### Prior-art searches (mandatory, both run)

- `review-record.py rejections search "read limit hook maxTurns"` → exit 0, 5 matches. One is a
  validated PRIOR: `agent-memory-learning` round 2, CRITICAL — *"gen-docs.py `HOOK_GLOBS`
  includes `*.py` so the hook count moves"* when a new `.py` lands in `.claude/hooks/`. Re-read
  `scripts/gen-docs.py:77-82`: confirmed still true. **What this plan does differently:** it
  treats the count move as a required regeneration step (see Step 7) instead of hand-editing a
  count (CLAUDE.md hard rule 8). The other matches (`e2e-lane-a`, mutation-proof overclaim) are
  answered by the Testing Strategy naming two mutants that must be *applied*, not asserted.
- `knowledge-ledger.py search "read window guard"` → exit 0, 1 weak match
  (`reflection-4e2c41055d84`, "assumed `subprocess.run` inherited the parent env", wontfix).
  Directly applicable to Step 6: the tests spawn the hook with an explicit `env=` and must
  **pop `CK_RAW_READ` from the inherited environment**, or a developer with the hatch exported
  silently turns every block test green. The plan does that.

## Scope

In scope: one new hook, one registry row, four frontmatter lines, one new test file, one
CHANGELOG entry, one docs regeneration.
Out of scope: capping Read *output* (PostToolUse `updatedToolOutput` for Read is undocumented —
deliberately not attempted), changing `output_filter.py`, growing any agent prompt with new prose
(the Discovery-budget rule is already in `planner.md`), and any `install.sh` change (`install.sh`
copies `"$DEST"/hooks/*` wholesale at line 303, so a new hook ships with no installer edit).

## Prerequisites

- `ECC_HOOK_PROFILE=minimal` present in `.claude/settings.local.json` (session-start rebuilds it).
- Nothing else; stdlib only, py3.9 target, bash 3.2 untouched.

## Implementation Steps

### Step 1 — `.claude/hooks/read-window-guard.py` (new)

- **File:** `.claude/hooks/read-window-guard.py`
- **Action:** create
- **Description:** `PreToolUse` handler. Blocks a `Read` with no usable `limit` when the target
  file exceeds 200 lines.
- **Details:** decision table, in order — non-`Read` tool → allow; `CK_RAW_READ=1` → allow;
  missing/blank `file_path` → allow; integer `limit` in `1..200` → allow; allowlisted path →
  allow; not a regular file (missing/unreadable) → allow (let `Read` report it); ≤200 lines →
  allow; otherwise **exit 2** with a single stderr line naming `limit` and the override.
  A `limit` greater than 200 falls through to the block, and the message names the fix.
  Allowlist: `.claude/plans/plan-*.md`, `.claude/plans/ops-*.json`,
  `.claude/agents/_shared/*.md`, `CLAUDE.md`, `.ai/*.md` (one pattern only — `fnmatch` does not
  treat `/` specially, so it already matches every depth; `.claude/project-index.md` is NOT
  allowlisted, the file does not exist).
  The `file_path` is resolved ONCE against `CLAUDE_PROJECT_DIR` (when relative) and that single
  value feeds both the allowlist match and the `isfile`/line-count stat, so the guard cannot
  silently fail open when the hook's cwd is not the project root.
  A windowed Read with `limit > 200` is blocked by design (the window is still too wide); the
  message names the fix, so the first encounter reads as guidance, not a false positive.
  Fail direction: every unexpected exception → `return 0`. The guard's own bug must never block a
  read (the fail-soft convention `output_filter.py` documents); a *decision* to block is the only
  exit 2, per hard rule 2 (exit 2 + stderr, never exit 1, never stdout-as-decision).
  Line counting is short-circuited at 201 lines, so a 2M-line file costs 201 iterations.
- **Done when:** `echo '{"tool_name":"Read","tool_input":{"file_path":"install.sh"}}' | python3
  .claude/hooks/read-window-guard.py` exits 2 and prints one stderr line.

### Step 2 — register the hook in the dispatcher

- **File:** `.claude/hooks/dispatch-registry.json`
- **Action:** edit — insert a row at the head of `events.PreToolUse`
- **Details:** `{"id": "read-window-guard", "file": "read-window-guard.py", "runner": "python3",
  "tier": "blocking", "matcher": "Read"}`. `tier: blocking` is honest and required: the registry's
  own invariant (checked by `tests/test_dispatch_merge.py`) is one-directional — a row declared
  `blocking` MUST be able to reach `exit 2`, and this one can. It declares **no**
  `command_matcher`, so the resolver's "only an advisory row may carry a precondition" invariant
  is satisfied and the handler still runs on an unreadable payload (where it allows, by design).
  Row order is execution order only; the outcome is `max(severity)`, so position cannot change it.
- **Done when:** `python3 -c "import json;json.load(open('.claude/hooks/dispatch-registry.json'))"`
  succeeds and `dispatch.sh PreToolUse` lists the handler.

### Steps 3-6 — `maxTurns` in agent frontmatter

| File | Line added | Current bytes | After | Ceiling |
|---|---|---|---|---|
| `.claude/agents/planner.md` | `maxTurns: 40` | 9963 | 9976 | 10000 |
| `.claude/agents/reviewer.md` | `maxTurns: 25` | 12384 | 12397 | 12400 |
| `.claude/agents/implementer.md` | `maxTurns: 30` | 11920 | 11933 | (none declared) |
| `.claude/agents/code-reviewer.md` | `maxTurns: 30` | 23061 | 23074 | (none declared) |

- **Correction to the brief:** the added line is 13 bytes (`maxTurns: 40` + `\n`), not 14.
  `planner.md` lands at 9976 ≤ 10000 and `reviewer.md` at 12397 ≤ 12400, both measured with
  `wc -c` at this HEAD. **No compensating trim is needed, and none is planned** — deleting a
  prompt line to buy headroom we already have would be an unforced behaviour change.
  `reviewer.md` headroom drops to 3 bytes; that is called out in Risk Assessment.
- `scripts/gen-model-policy.py` only locates and rewrites the `model:` line inside the
  frontmatter span (`frontmatter_span`, `scripts/gen-model-policy.py:33,152`); it neither
  enumerates nor rejects other keys, so `--check` is unaffected by an added key.
- **Done when:** `python3 scripts/gen-model-policy.py --check` and
  `python3 -m pytest tests/test_agent_prompt_size.py -q` both pass.

### Step 7 — regenerate the published hook count

- **File:** `README.md`, `AGENTS.md`, `docs/HOOKS.md` (all generator-owned; these are the three
  files `gen-docs.py` rewrites for a hook-count move)
- **Action:** run `python3 scripts/gen-docs.py`
- **Details:** `HOOK_GLOBS = ("*.sh", "*.py")` (`scripts/gen-docs.py:77`) counts the new file, so
  the published hook count moves by one. Hard rule 8 forbids hand-editing it.
  **This is NOT a `run_command` op.** `ALLOWED_RUN_COMMANDS`
  (`.claude/operations/scripts/shared.py:76-86`) is `{pip-compile, black, isort, ruff, prettier,
  gofmt, goimports, rustfmt}`; `python3` is absent and
  `CLAUDEKIT_RUN_COMMAND_EXTRA_ALLOW` is unset in this repo (grepped `.claude/settings.json` and
  `.claude/settings.local.json`: no hits). A `run_command` op with argv `["python3",
  "scripts/gen-docs.py"]` would be **rejected by validator GUARD 31**, failing the whole config.
  The implementer therefore runs it as an explicit post-execution command, immediately after
  `execute-json-ops.py` returns.
- **Done when:** `python3 scripts/gen-docs.py --check` exits 0.

### Step 8 — tests

- **File:** `tests/test_read_window_guard.py` (new)
- **Action:** create
- **Details:** behavioural — each case spawns the hook as a subprocess with a synthetic
  `PreToolUse` JSON payload on stdin and asserts exit code and stderr. The environment is built
  explicitly and **`CK_RAW_READ` is popped from the inherited env** (see the ledger prior above).
  Cases: 201-line file, no `limit` → exit 2, stderr contains `limit`, stdout empty; same file
  with `limit=100` → exit 0; 200-line file, no `limit` → exit 0; `CK_RAW_READ=1` → exit 0;
  missing file → exit 0; non-`Read` tool → exit 0; unparseable stdin → exit 0; plus a frontmatter
  test asserting each of the four agents declares its stated `maxTurns`.
  **Allowlist pair (a fake project root, so nothing depends on a real file's length):** with
  `CLAUDE_PROJECT_DIR=tmp_path`, a 250-line `.claude/plans/plan-x.md` → exit 0
  (`test_allows_an_allowlisted_path`) and a 250-line `docs/notes-x.md` of the same length →
  exit 2 (`test_blocks_a_same_length_file_outside_the_allowlist`). Only the allowlist branch can
  allow the first, so mutant 2 lands on it.
  **Dispatch end-to-end (the shipped control is the registry row, not the script):**
  `test_registry_registers_the_guard_as_blocking` asserts the `PreToolUse` row exists with
  `file: read-window-guard.py`, `matcher: Read`, `tier: blocking`;
  `test_dispatch_blocks_an_unwindowed_read` and `test_dispatch_allows_a_windowed_read` pipe the
  payload through `bash .claude/hooks/dispatch.sh PreToolUse` exactly as `settings.json` invokes
  it (`ECC_HOOK_PROFILE=standard`, `CLAUDE_PROJECT_DIR`, cwd = repo root — the pattern
  `tests/test_dispatch_merge.py` already uses) and assert exit 2 / exit 0.

### Step 9 — CHANGELOG

- **File:** `CHANGELOG.md`, under `## [Unreleased]`
- **Action:** edit (`add_after` the heading; payload carries its own leading newline)

## Testing Strategy

`python3 -m pytest tests/ -q` · `ruff check` · `mypy` · `gen-docs.py --check` ·
`gen-model-policy.py --check` · `check-context-floor.py --check` · `check-plan-artifacts.py --check`.

**Mutants (apply them, do not merely assert them — see the `e2e-lane-a` MAJOR):**

1. In `read-window-guard.py`, change `THRESHOLD = 200` to `THRESHOLD = 20000`. Expected:
   `test_blocks_unwindowed_read_of_a_long_file` goes RED (exit 0 instead of 2); the 200-line
   allow test and every allowlist test stay GREEN. If the block test stays green, it is measuring
   nothing.
2. In `read-window-guard.py`, delete the `if _allowlisted(path): return 0` branch. Expected:
   `test_allows_an_allowlisted_path` (250-line `.claude/plans/plan-x.md` under a fake root) goes
   RED — it is the only branch that can allow that file. The block test and
   `test_blocks_a_same_length_file_outside_the_allowlist` stay GREEN.
3. In `.claude/hooks/dispatch-registry.json`, flip the new row's `tier` to `"advisory"`.
   Expected: `test_registry_registers_the_guard_as_blocking` RED and
   `test_dispatch_blocks_an_unwindowed_read` RED (an advisory row cannot deny). Deleting the row
   outright must turn the same two RED. `tests/test_dispatch_merge.py` does **not** react to this
   flip — measured, 86 passed — which is exactly why these tests exist.

## Rollback Plan

Per-op and ordered: (1) `git checkout -- .claude/hooks/dispatch-registry.json` disarms the guard
instantly — the hook file can stay on disk, unreferenced and inert; (2)
`rm .claude/hooks/read-window-guard.py tests/test_read_window_guard.py` then re-run
`python3 scripts/gen-docs.py` to restore the count; (3) `git checkout -- .claude/agents/` reverts
the four frontmatter lines; (4) `git checkout -- CHANGELOG.md`. No data migration, no state.
Emergency per-user escape without a revert: export `CK_RAW_READ=1`.

## Risk Assessment

- **HIGH — a guard on `Read` can brick every agent.** `Read` is the single most-used tool; a
  false block stalls all work. Mitigated by: (a) six explicit allow branches before any block;
  (b) blanket `except → return 0`, so only a *decision* ever blocks; (c) the `CK_RAW_READ=1`
  hatch, named in the stderr message itself; (d) `.claude/settings.json` unchanged, so a single
  registry-line revert disarms it.
- **MEDIUM — `reviewer.md` lands 3 bytes under its 12400 ceiling.** The next edit to that file
  will fail `test_agent_prompt_size.py`. This is the ratchet working as designed, but it is a
  trap for the next author; the Risk is recorded so the trim is a deliberate decision then, not a
  surprise.
- **MEDIUM — the hook count moves.** Exactly the `agent-memory-learning` CRITICAL. Mitigated by
  Step 7 regeneration, and by `gen-docs.py --check` in the DoD gate. Note this hook is not
  imported by any other hook, so `_is_helper_module` will not reclassify it.
- **LOW — `maxTurns` semantics.** Docs (fetched today) say the subagent stops with a PARTIAL
  handback, resumable via SendMessage. Worst case is a truncated plan, which is visible, not
  silent. Values chosen with headroom over observed medians, not at them.
- **UNVERIFIED:** whether this Claude Code build honours `maxTurns` in agent frontmatter is not
  provable from inside the repo — no test here can observe the host's turn accounting. The
  frontmatter test asserts only that the declaration is present and correct. If the host ignores
  the key, the cost is one inert line per agent, not a regression.
- **Blast radius:** `.claude/hooks/dispatch-registry.json` is a hub (every `PreToolUse` handler
  resolves through it) and `.claude/agents/*.md` are read on every spawn. No `project-graph.json`
  query was run (file not consulted within budget); treat the registry as a god-node by
  inspection. Routed to `reviewer`.

## Post-execution commands (implementer runs these, in order)

```
python3 scripts/gen-docs.py
python3 -m pytest tests/test_read_window_guard.py tests/test_agent_prompt_size.py tests/test_dispatch_merge.py -q
python3 scripts/gen-model-policy.py --check && python3 scripts/gen-docs.py --check
```

## HANDOFF TO: reviewer

- Plan: `.claude/plans/plan-planner-read-and-turn-cap.md`
- Ops: `.claude/plans/ops-planner-read-and-turn-cap.json`
- Ops count: 8 (2 `file_create`, 6 `code_edit`; 0 `file_delete`, 0 `run_command` — see Step 7 for
  why the regeneration is a post-execution command and not an op)
- Focus: the guard's allow-before-block ordering, the `blocking` tier claim, and the two mutants.
