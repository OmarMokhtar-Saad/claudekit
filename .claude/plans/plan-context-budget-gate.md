# Implementation Plan: context-budget-gate

## Overview

Main sessions have no ceiling. Every cap that shipped today — the 12K Bash stdout cap,
`read-window-guard`, per-agent `maxTurns`, per-role `effort` — is declared in **our agent
frontmatter**, which cannot reach (a) the main agent, which has no frontmatter, or (b) a
built-in agent such as `general-purpose`, whose definition we do not author. Measured
2026-09-18: one main session at 842K context / 428 turns / 202M cumulative tokens with zero
compactions and nine hand-authored ops configs; two more at 283K/159 turns and 241K/131 turns;
a fourth at 209K in 43 turns that routed a redesign to `general-purpose`, which then ran 56
turns to 246K (8.7M tokens) entirely outside our controls.

This plan adds ONE new blocking PreToolUse hook, `.claude/hooks/context-budget-gate.py`, which
is the only place both gaps are reachable: PreToolUse fires for the main agent *and* every
subagent, and its stdin payload carries `session_id` and `transcript_path`
(`reflection-gate.py:320` already reads the latter, so the field is confirmed present in this
runtime).

## Phase 0 — Design precheck (ownership / where the value sits)

The unit of ownership is **one transcript = one agent's context**. Claude Code writes a
separate JSONL per agent: the main session's transcript, and each subagent's
`<project>/<session-id>/subagents/agent-*.jsonl` (measured layout, confirmed on disk).
A PreToolUse hook is handed the transcript of *the caller that is about to use the tool*, so a
budget computed from `transcript_path` is inherently per-agent and needs no session
bookkeeping, no parent/child model, and no cross-process state. Ownership also decides the
*verdict*: only a main session can act on a block (it can run `/save-session` and `/compact`
and can export the hatch), so only a main session is blocked — a subagent over the same line
gets an advisory telling it to hand back, because a block would leave it with no legal move. The value therefore sits in
exactly two files that this plan writes: the hook (the decision) and the dispatch registry row
(the reachability). A hook with no registry row is inert — that is the failure mode task 008
and `tests/test_structure.py::TestHookWiringIsHonest` exist to catch — so the registry row is
not a detail, it is half the change, and `tests/test_context_budget_gate.py` asserts both the
row and the verdict through the real `dispatch.sh` path. Warning de-duplication is the one
piece of genuine state (a counter per `session_id` under `.claude/hooks/.state/`); it is
advisory-only, so its failure mode is noise, never a wrong verdict.

**Prior-art searches (mandatory, both run):**

- `review-record.py rejections search "context budget transcript hook"` → exit 0, 6 keyword
  matches, none about a context-size gate. The two closest are validated and accounted for:
  `agent-memory-learning` (CRITICAL: a new `.py` under `.claude/hooks/` changed the
  gen-docs hook count and the plan did not carry the count change) — this plan differs by
  naming the count consequence explicitly (hook count 29→30, reachable 26→27) and by editing
  the hand-written reachable prose in the ops while leaving the generated counts to
  `scripts/gen-docs.py` post-execution. And `iron-law-enforcement-hook` (MAJOR: a hook's
  allow/deny table was incomplete against the real tool surface) — this plan differs by
  deciding on an explicit closed tool set (`Write|Edit|NotebookEdit|Bash|Agent|Task`) with everything else
  falling through to exit 0, rather than an open denylist.
- `knowledge-ledger.py search "context budget"` → exit 0, `no match`. Treated as **unknown**,
  not as evidence of novelty.

## Scope

- **In Scope:**
  - New hook `.claude/hooks/context-budget-gate.py` (stdlib, py3.9, fail-open).
  - Two decisions in that one hook: a context budget (warn/block) and a spawn guard for the
    built-in `general-purpose` agent.
  - Registry wiring in `.claude/hooks/dispatch-registry.json` (blocking tier).
  - Behavioural tests `tests/test_context_budget_gate.py`.
  - Hand-written reachable-count prose in `README.md` and `docs/HOOKS.md` (26 → 27).
  - `CHANGELOG.md` `[Unreleased]` entry; `.gitignore` entry for the new state directory.
- **Out of Scope:**
  - Any change to agent frontmatter (`maxTurns`, `model`, `effort`) — the frontmatter contract
    tests and `gen-model-policy.py --check` are untouched by design.
  - Auto-compaction, auto-`/save-session`, or any hook that mutates the session.
  - Generated component counts (hook count 29→30) — regenerated post-execution by
    `python3 scripts/gen-docs.py`, never hand-edited (hard rule 8).
  - PostToolUse/Stop telemetry on context size; a Stop-event reporter is a separate change.

## Prerequisites

- `.claude/settings.local.json` present with `ECC_HOOK_PROFILE=minimal` (session-start rebuilds
  it) so the ops engine can write; never bypass hooks.
- Execution via the operations engine (Iron Law): `ops-context-budget-gate.json`.

## Implementation Steps

### Step 1: The hook

- **File:** `.claude/hooks/context-budget-gate.py`
- **Action:** Create
- **Description:** One PreToolUse handler carrying both decisions; modelled line-for-line on
  `read-window-guard.py` (module docstring stating WHY / THE DECISION / FAIL DIRECTION / ESCAPE
  HATCH, `_decide()` computing a verdict inside `try`, emission outside it).
- **Details:**
  - Guarded tools: `Write`, `Edit`, `Bash`, `Agent`, `Task`. Anything else → exit 0.
    (`Task` is included alongside `Agent` because the spawn payload shape
    `{subagent_type, prompt, description, model?}` is the same and the runtime tool name for
    agent dispatch has historically been `Task`; guarding both names costs nothing and is the
    difference between a live guard and an inert one. The registry matcher carries both.)
  - **Context budget.** `_context_size(transcript_path)`: `os.path.getsize`, `seek(size -
    65536)` when larger, read 64 KB, decode `errors="replace"`, split on `\n`, **drop the
    first element when the file was larger than the window** (it is a fragment). Walk the
    lines in reverse; skip any without the literal `"usage"`; `json.loads` each in a
    `try/except`; accept the first record whose `message.usage` is a dict and whose
    `type`/`message.role` is assistant (or absent); sum `input_tokens +
    cache_read_input_tokens + cache_creation_input_tokens`, integers only (`bool` excluded);
    return the total when > 0. No usage record inside the window → `None` → allow.
  - Thresholds: `_threshold("CK_CONTEXT_WARN", 200000)` and
    `_threshold("CK_CONTEXT_BLOCK", 400000)`; a non-integer or non-positive env value falls
    back to the default rather than disabling the gate.
  - `>= BLOCK` → exit 2, one stderr line naming the size, `/save-session`, `/compact` or a new
    session, and the hatch `CK_RAW_CONTEXT=1`.
  - `>= WARN` (and below BLOCK) → exit 0 plus at most one stderr line per 20 guarded calls per
    `session_id`. Counter file `.claude/hooks/.state/context-budget-<sanitised session id>`
    (alnum/`-_.` only, 64 chars); read int, write int+1, warn when `seen % 20 == 0` (so calls
    1, 21, 41…). Any state failure → warn (advisory noise is a safer failure than silence).
    On exit 0 `dispatch.sh` routes handler stderr into `ADVISORY_NOTES`, printed on stdout
    after the merge (dispatch.sh:333-345) — so the advisory does surface and can never affect
    the verdict.
  - `CK_RAW_CONTEXT=1` skips the whole budget branch (warn and block).
  - **Spawn guard.** For `Agent`/`Task` only: block when `tool_input.subagent_type` is absent,
    empty, or `general-purpose`, unless `CK_ALLOW_GENERAL_PURPOSE=1`. stderr names the scoped
    alternatives (`explore` search, `planner` plans, `code-reviewer` review, `docs` writing)
    and the hatch. `Explore`, `Plan`, `claude-code-guide` and every kit agent fall through.
  - **Ordering inside `_decide()`:** BLOCK-on-context returns immediately; a WARN is held as a
    pending note so it cannot swallow the spawn check; the spawn block outranks the note.
  - **Fail direction:** `json.load` failure, non-dict payload, or any exception inside
    `_decide()` → exit 0. A block is exit 2 + stderr only, never exit 1, never stdout
    (hard rule 2).
  - Subagents: documented in the docstring — a subagent's `transcript_path` is its own
    `agent-*.jsonl`, so this budget is per-agent and needs no cross-process state.
- **Done when:** `python3 .claude/hooks/context-budget-gate.py < payload.json` exits 0 on a
  small transcript and 2 on a 450K one; `ruff check` clean. (~25 min)

### Step 2: The tests

- **File:** `tests/test_context_budget_gate.py`
- **Action:** Create
- **Description:** Behavioural coverage only — every case spawns the shipped artifact as a real
  subprocess with synthetic stdin and synthetic transcripts in `tmp_path`; nothing is imported
  from the hook. Mirrors `tests/test_read_window_guard.py`, including its ENV DISCIPLINE
  (`CK_RAW_CONTEXT`, `CK_ALLOW_GENERAL_PURPOSE`, `CK_CONTEXT_WARN`, `CK_CONTEXT_BLOCK` are
  popped from the inherited environment, so an exported hatch cannot turn a block assertion
  green).
- **Details (cases):** hook ships on disk · below WARN → exit 0, empty stderr · ≥WARN → exit 0
  with one stderr advisory naming `/compact` · a second guarded call in the same session →
  exit 0 and silent (the counter file) · ≥BLOCK → exit 2 naming `/compact` and
  `CK_RAW_CONTEXT=1` · `CK_RAW_CONTEXT=1` at 450K → exit 0 · `CK_CONTEXT_BLOCK=200000` makes a
  250K session block (thresholds really are read from env) · missing transcript → exit 0 ·
  garbage/malformed transcript → exit 0 · unguarded tool (`Read`) at 450K → exit 0 · **tail
  only**: a 5 MB transcript whose over-BLOCK usage record sits in the first line and whose last
  64 KB contains no usage at all → exit 0 **and** wall time < 1 s · last-not-largest: a 900K
  record followed by a 50K record, both inside the tail → exit 0 · `Agent` +
  `general-purpose` → exit 2 naming `planner` and `CK_ALLOW_GENERAL_PURPOSE=1` · `Agent` with
  no `subagent_type` → exit 2 · `Agent` + `planner` → exit 0 silent ·
  `CK_ALLOW_GENERAL_PURPOSE=1` → exit 0 · unparseable stdin → exit 0 · registry row asserted
  (`file`, `matcher`, `tier == "blocking"`) · through the real
  `bash .claude/hooks/dispatch.sh PreToolUse` (the `run_dispatch` pattern from
  `tests/test_read_window_guard.py:158`): one block (`Agent` + `general-purpose` → rc 2) and
  one allow (`Agent` + `planner` → rc 0).
- **Named mutants (apply them, do not assume them):**
  1. `DEFAULT_BLOCK = 400000` → `4000000` ⇒ `test_blocks_at_the_block_threshold` RED.
  2. Delete the tail seek (read the whole file) ⇒ `test_only_the_tail_is_read` RED — it is a
     *correctness* differential, not only a timing one: the over-budget record lives outside
     the window. A whole-file reader returns the SAME verdict (it still takes the last usage record);
     what changes is `read_bytes` under `CK_CONTEXT_TRACE=1` and wall time — that is what the test
     pins. Mutant 2a (delete the seek only, keep `read(TAIL_BYTES)`) reads the HEAD of the file, so the
     900K record on line 2 wins and `rc` flips to 2 while `read_bytes` stays 65,536; the same
     test kills 2a by `rc` and 2b by `read_bytes` (both measured in review round 3).
  3. Delete the `general-purpose` branch in `_spawn_block` ⇒
     `test_blocks_a_general_purpose_spawn` and `test_dispatch_blocks_a_general_purpose_spawn`
     RED.
- **Done when:** `python3 -m pytest tests/test_context_budget_gate.py -q` passes and each
  mutant above has been applied, observed RED, and reverted. (~30 min)

### Step 3: Registry wiring

- **File:** `.claude/hooks/dispatch-registry.json`
- **Action:** Modify
- **Description:** Add the PreToolUse row directly after the `read-window-guard` row (the model
  row, `dispatch-registry.json:48`).
- **Details:** `{"id": "context-budget-gate", "file": "context-budget-gate.py", "runner":
  "python3", "tier": "blocking", "matcher": "Write|Edit|NotebookEdit|Bash|Agent|Task"}` — `add_after` with a
  payload that carries its own leading newline and the file's 6-space indentation.
- **Done when:** `test_registry_registers_the_gate_as_blocking` passes and
  `test_dispatch_blocks_a_general_purpose_spawn` returns rc 2 through `dispatch.sh`. (~5 min)

### Step 4: Reachable-count prose (README)

- **File:** `README.md`
- **Action:** Modify
- **Description:** The hand-written reachable count at `README.md:265` is pinned by
  `tests/test_structure.py::test_the_published_reachable_count_matches_the_docs`, which derives
  `len(published) - len(UNWIRED)` = 30 − 3 = **27**.
- **Details:** `` `.claude/hooks/`; 26 are reachable `` → `` `.claude/hooks/`; 27 are
  reachable ``. The adjacent `29 hooks ship` is generator-owned and is deliberately left for
  `scripts/gen-docs.py` (hard rule 8).
- **Done when:** `python3 -m pytest tests/test_structure.py -q` passes after the hook exists
  and gen-docs has been run. (~2 min)

### Step 5: Reachable-count prose (docs/HOOKS.md)

- **File:** `docs/HOOKS.md`
- **Action:** Modify
- **Description:** Same derived count, in the hard-wrapped sentence at `docs/HOOKS.md:3`
  (`26 are\nreachable:` — the structure test normalises whitespace, so the wrap is fine).
- **Details:** `library). 26 are` → `library). 27 are`.
- **Done when:** as Step 4. (~2 min)

### Step 6: CHANGELOG

- **File:** `CHANGELOG.md`
- **Action:** Modify
- **Description:** One `[Unreleased]` bullet — user-visible behaviour change (a new blocking
  hook with two hatches).
- **Details:** `add_after` the `## [Unreleased]` heading, payload carrying its leading newline
  so the existing first bullet stays intact. Names the measurements, both thresholds, both env
  hatches, and the per-agent transcript semantics.
- **Done when:** `## [Unreleased]` is followed by the new bullet and the previous first bullet
  is unchanged. (~3 min)

### Step 7: Ignore the state directory

- **File:** `.gitignore`
- **Action:** Modify
- **Description:** `.claude/hooks/.state/` holds per-session warn counters — machine-local
  runtime state, re-derivable, and exactly the class already ignored one line above
  (`.claude/hooks/compact-counter.txt`). Without this, the dispatch-path tests leave untracked
  files that redden the secret self-scan.
- **Details:** `add_after` the `.claude/hooks/compact-counter.txt` line with a leading newline,
  a one-line rationale comment, and the entry.
- **Done when:** `git status --porcelain` is clean after
  `python3 -m pytest tests/test_context_budget_gate.py -q`. (~2 min)

## Testing Strategy

- `python3 -m pytest tests/test_context_budget_gate.py -q` — the new behavioural suite,
  including the two `dispatch.sh` end-to-end cases.
- Apply, observe RED, and revert each of the three named mutants (Step 2). An unmeasured
  mutant claim is an overclaim — this repo has rejected plans for exactly that.
- `python3 -m pytest tests/ -q` — zero failures; watch `tests/test_structure.py`
  (hook wiring + reachable count) in particular.
- `ruff check src/ tests/ scripts/ .claude/operations/scripts/` plus
  `ruff check .claude/hooks/context-budget-gate.py`; `mypy`.
- **Post-execution, not ops (`python3` is not an allowlisted `run_command` executable):**
  `python3 scripts/gen-docs.py` (hook count 29 → 30), then
  `python3 scripts/gen-docs.py --check`, `python3 scripts/check-context-floor.py --check`,
  `python3 scripts/check-plan-artifacts.py --check`,
  `python3 scripts/gen-registry.py --check`, `python3 scripts/gen-model-policy.py --check`.
- Manual smoke: `printf '%s' '{"tool_name":"Agent","tool_input":{"subagent_type":"general-purpose"}}' | python3 .claude/hooks/context-budget-gate.py; echo $?` → `2`.

## Rollback Plan

- Ops-level: `git checkout -- .claude/hooks/dispatch-registry.json README.md docs/HOOKS.md
  CHANGELOG.md .gitignore && rm -f .claude/hooks/context-budget-gate.py
  tests/test_context_budget_gate.py`, then `python3 scripts/gen-docs.py` to restore the counts.
- Runtime-level, without a revert: the hook is registry-driven — deleting the
  `context-budget-gate` row makes it inert immediately; `CK_RAW_CONTEXT=1` and
  `CK_ALLOW_GENERAL_PURPOSE=1` disable each decision per process tree.
- State files under `.claude/hooks/.state/` are disposable: `rm -rf .claude/hooks/.state`.

## Risk Assessment

- **Low Risk:** the four prose/config edits (README, HOOKS.md, CHANGELOG, .gitignore) — all
  anchored on `grep -cF`-verified unique strings; `.state/` ignore entry sits beside an
  identical precedent.
- **Low Risk:** fail-open design — every unexpected condition (missing/rotated/garbage
  transcript, unwritable state dir, unparseable payload) exits 0, matching the documented
  convention in `read-window-guard.py` and `output_filter.py`.
- **Medium Risk:** *false blocks on Write/Edit/Bash near the ceiling.* At ≥400K the hook denies
  the main agent's edits, which is the point, but a user mid-task must run `/compact` or export
  `CK_RAW_CONTEXT=1`. Mitigation: the block message names both routes; the warn line arrives
  200K earlier; thresholds are env-tunable without a code change.
- **Medium Risk:** *the tail window can miss the usage record.* A transcript whose last 64 KB is
  one enormous tool-result line yields no usage → the hook allows. Chosen deliberately over a
  widening retry, because the retry would erase the only observable difference between
  "tail-read" and "whole-file read" and make mutant 2 undetectable. Consequence is a missed
  block, never a false one.
- **Medium Risk:** *spawn-guard tool name.* `UNVERIFIED:` this repo contains no reference to
  the agent-dispatch tool name (`grep` for `subagent_type` / `"Task"` across `.claude/hooks/`
  and `src/claudekit/security/` returns nothing), so the runtime name is taken from the
  caller's measurement (`Agent`) and hedged by also guarding `Task`. If the live name is
  neither, the spawn branch is inert — it cannot mis-fire, only under-fire. First live block
  (or its absence) settles it.
- **Medium Risk:** *dispatch end-to-end tests run the whole PreToolUse chain.* `reflection-gate`
  has an empty matcher and is blocking, so it executes on every tool; the allow-case assertion
  (`Agent` + `planner` → rc 0) depends on it staying quiet, exactly as
  `tests/test_read_window_guard.py::test_dispatch_allows_a_windowed_read` already does. A
  failure there is a real signal about the chain, not test flake.
- **Medium Risk:** *component counts.* Adding one `.py` under `.claude/hooks/` moves the
  generated hook count 29 → 30 and the derived reachable count 26 → 27. The ops edits ONLY the
  hand-written reachable prose; forgetting `python3 scripts/gen-docs.py` after execution leaves
  `--check` red. This is the exact CRITICAL recorded against `agent-memory-learning`, and it is
  called out in Testing Strategy for that reason.
- **High Risk:** none. No security surface, no schema migration, no public API, no deletions
  (`file_delete` count: 0).
