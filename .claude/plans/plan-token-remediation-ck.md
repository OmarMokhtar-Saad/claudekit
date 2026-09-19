# Plan: token-spend remediation — claudekit repo (work item B)

Ops config: `.claude/plans/ops-token-remediation-ck.json` (10 operations, all `code_edit`).
Parent spec: `.claude/plans/plan-token-spend-remediation.md` section B.

## Overview

The token-spend audit found three cost sinks inside this repo's own prompt corpus and hook
wiring: (1) the reflection gate runs on six events and is a write-only loop — it has produced
no read in two days, yet every Stop/SubagentStop/PreCompact/PostToolUse firing costs a hook
round trip; (2) `command-log-audit.sh` has never successfully parsed a payload (3,137 parse
failures) and is spawned on every Bash call; (3) the three pipeline agents carry no binding
turn cap and the planner carries Bash, which is what lets a planner run turn into a 400K-token
exploration. Five agents declare `memory: project` that has never been written to.

This change is prompt-corpus + config only. No Python or shell source is touched.

## Design precheck (ownership / data model)

The value of this change sits in exactly four kinds of file, and the ops config covers all
four: the agent frontmatter (`.claude/agents/*.md` — the only place `tools:`/`maxTurns:` is
declared), the live hook wiring (`.claude/settings.json` — the only file Claude Code reads to
decide which hooks fire), the dispatch table (`.claude/hooks/dispatch-registry.json` — the
PreToolUse resolver's source of truth), and the user-visible record (`CHANGELOG.md`). Nothing
in `src/` or `tests/` carries the behaviour being changed. Caveat recorded in Risk Assessment:
frontmatter is advisory to the runtime in some paths (see the repo's own agent-contract gate),
so the turn caps are enforcement-by-prompt plus gate, not by the platform.

## Scope

In scope (10 files, one `code_edit` op each):

- `.claude/agents/planner.md` — `tools` drops `Bash`; `maxTurns: 40` → `15`
- `.claude/agents/reviewer.md` — `maxTurns: 25` → `8`; drop `memory: project`; add a
  three-sentence scope paragraph under `# Reviewer Agent`
- `.claude/agents/implementer.md` — `maxTurns: 30` → `12`
- `.claude/agents/explore.md`, `debugger.md`, `verifier.md`, `security-scanner.md` — drop the
  `memory: project` frontmatter line
- `.claude/settings.json` — drop reflection-gate on PostToolUse, PreCompact, Stop,
  SubagentStop; drop the `command-log-audit.sh` PostToolUse entry
- `.claude/hooks/dispatch-registry.json` — drop the reflection-gate PreToolUse row
- `CHANGELOG.md` — one `[Unreleased]` bullet

Out of scope (deliberately, per spec): deleting `reflection-gate.py` or
`command-log-audit.sh`; the registry's advisory reflection-gate rows on
PostToolUse/PreCompact/Stop/SubagentStop; the `## Durable memory` body sections in the five
agents that lose `memory:`; work items A, C, D, E of the parent spec.

## Prerequisites

- Branch `main`, 77 uncommitted paths belong to other concurrent sessions — the executor must
  touch only the ten files above.
- `ECC_HOOK_PROFILE=minimal` present in `.claude/settings.local.json` (session-start rebuilds
  it) or `ops-enforcement` blocks the Write.

## Implementation Steps

### 1. planner.md — remove Bash, cap turns
- **File:** `.claude/agents/planner.md`
- **Action:** edit frontmatter lines 10–11
- **Details:** `maxTurns: 40` → `maxTurns: 15`; `tools: ["Read", "Grep", "Glob", "Write",
  "Bash"]` → `tools: ["Read", "Grep", "Glob", "Write"]`. `memory: project` stays (the planner
  memory dir is actively written).
- **Done when:** `grep -n 'maxTurns\|^tools:' .claude/agents/planner.md` shows 15 and a
  four-entry tools list with no `Bash`.

### 2. reviewer.md — cap turns, drop memory, narrow the read surface
- **File:** `.claude/agents/reviewer.md`
- **Action:** one frontmatter edit (lines 11–16) plus one body insertion
- **Details:** `maxTurns: 25` → `8`; the `memory: project` line is deleted; a paragraph is
  inserted between `# Reviewer Agent` and the `You are the **Reviewer**` sentence: "Read only
  plan.md and ops.json. Do not explore the codebase; the validator already checks paths. Hand
  back within 8 turns."
- **Done when:** frontmatter has no `memory:` key and `maxTurns: 8`; the paragraph is the
  first prose under the H1.

### 3. implementer.md — cap turns
- **File:** `.claude/agents/implementer.md`
- **Action:** `maxTurns: 30` → `maxTurns: 12`
- **Done when:** `grep -c 'maxTurns: 12' .claude/agents/implementer.md` returns 1.

### 4. Drop unused `memory: project` from four more agents
- **Files:** `.claude/agents/explore.md`, `debugger.md`, `verifier.md`, `security-scanner.md`
- **Action:** delete the frontmatter `memory: project` line only
- **Details:** each anchor includes the preceding `color:` line, because the literal string
  `memory: project` also appears inside the body heading "## Durable memory
  (`memory: project`)" and would otherwise be ambiguous.
- **Done when:** `grep -c '^memory: project'` returns 0 in all four files and the body
  heading is untouched.

### 5. settings.json — unwire the write-only reflection gate and the dead audit hook
- **File:** `.claude/settings.json`
- **Action:** four block deletions
- **Details:** (a) the PostToolUse reflection-gate entry, (b) the PostToolUse
  `command-log-audit.sh` entry, (c) the whole `"PreCompact"` key (its only entry was the
  reflection gate — an empty event array is left behind otherwise), (d) the Stop
  reflection-gate entry (Stop keeps cost-tracker, desktop-notify, format-typecheck), (e) the
  whole `"SubagentStop"` key (same reason as PreCompact). Kept: reflection-gate on
  SessionStart and PostToolUseFailure, and every non-reflection hook.
- **Done when:** `python3 -c 'import json;json.load(open(".claude/settings.json"))'` succeeds
  and `grep -c reflection-gate .claude/settings.json` returns 2.

### 6. dispatch-registry.json — drop the blocking PreToolUse row
- **File:** `.claude/hooks/dispatch-registry.json`
- **Action:** delete the single row
  `{"id": "reflection-gate", ..., "tier": "blocking", ..., "args": ["--event", "PreToolUse"]}`
- **Details:** the four advisory reflection-gate rows on other events are left in place per
  the spec; `blocking_events` still needs `"PreToolUse"` for the other blocking handlers.
- **Done when:** JSON parses and the PreToolUse event list has no reflection-gate row.

### 7. CHANGELOG.md — record the user-visible change
- **File:** `CHANGELOG.md`
- **Action:** insert one bullet as the first item under `## [Unreleased]`
- **Done when:** the bullet is present above the existing "Token-spend fixes from the audit"
  bullet.

## Testing Strategy

Run from the repo root, in this order; zero failures tolerated:

```bash
python3 -m pytest tests/ -q
ruff check src/ tests/ scripts/ .claude/operations/scripts/
python3 scripts/gen-docs.py --check
python3 scripts/gen-model-policy.py --check
python3 scripts/check-plan-artifacts.py --check
```

Plus two direct assertions, because a green suite can measure nothing here:

- `python3 -c 'import json;json.load(open(".claude/settings.json"))'` and the same for
  `.claude/hooks/dispatch-registry.json` — both must exit 0 (the two hand-edited JSON files).
- Positive control for the unwiring: after the edits, start a session (or run
  `bash .claude/hooks/dispatch.sh PreToolUse` with a Bash payload) and confirm
  `.claude/hooks/hooks.log` records no reflection-gate PreToolUse/Stop invocation, while
  SessionStart still records one. If reflection-gate still appears on Stop, the edit did not
  reach the live settings file.

`gen-model-policy.py --check` is the gate that reads agent frontmatter; `gen-docs.py --check`
is the count gate (hook count is unchanged — no hook file is added or deleted, only unwired).

## Rollback Plan

Every operation is a string edit on a tracked file. `git checkout --
.claude/agents/planner.md .claude/agents/reviewer.md .claude/agents/implementer.md
.claude/agents/explore.md .claude/agents/debugger.md .claude/agents/verifier.md
.claude/agents/security-scanner.md .claude/settings.json
.claude/hooks/dispatch-registry.json CHANGELOG.md` restores the pre-change state. No file is
created or deleted, so there is nothing to un-create. Caution: other sessions hold 77
uncommitted paths — roll back only the ten paths named, never `git checkout -- .`.

## Risk Assessment

- **HIGH — settings.json / dispatch-registry.json drift.** After this change the registry
  still lists advisory reflection-gate rows for PostToolUse, PreCompact, Stop and SubagentStop,
  and a `command-log-audit` PostToolUse row, while settings.json no longer wires them. From
  this repo's own memory: "Registry row is not PostToolUse wiring — settings.json wires
  PostToolUse hooks individually; dispatch.sh is PreToolUse only", so the two files are
  independent by design and the divergence is expected, not a bug. `UNVERIFIED:` whether
  `scripts/gen-registry.py --check` or `tests/test_dispatch_merge.py` cross-checks registry
  rows against settings.json — this plan was scoped to not read tests. If either gate fails,
  the follow-up is mechanical: delete the four advisory reflection-gate rows and the
  `command-log-audit` row from `dispatch-registry.json` and re-run. Do not widen the ops
  config speculatively.
- **MEDIUM — removing whole event keys.** `PreCompact` and `SubagentStop` lose their only
  entry, so the keys are removed rather than left as `[]`. `UNVERIFIED:` whether any test
  asserts those keys exist in settings.json. If one does, the minimal fix is to restore the
  key with an empty array.
- **MEDIUM — turn caps may not bind.** Repo memory records that agent frontmatter does not
  bind at the platform level (`maxTurns` ignored, callers override `model`), and that the
  agent-contract gate now enforces the three fields. These caps are therefore a contract the
  gate checks and the caller must honour, not a runtime limit. The real spend control remains
  the prompt-level discovery budget.
- **LOW — stale prose left behind.** The five agents that lose `memory:` keep their
  "## Durable memory (`memory: project`)" body sections, and dispatch-registry.json keeps a
  comment line saying "reflection-gate is blocking on PreToolUse". Both are now inaccurate.
  Out of scope by instruction; worth a follow-up cleanup commit.
- **LOW — planner loses Bash.** The planner can no longer run
  `validate-config-json.py` itself, so ops configs it writes are validated by the caller or
  the executor's own validation pass. That is the intended trade (Bash was the planner's
  main context sink), but callers must run the validator.
- **Prior-art searches:** `review-record.py rejections search` and `knowledge-ledger.py search`
  were NOT run — this run is under a hard no-Bash-exploration instruction (one validator call
  only). `UNVERIFIED:` prior rejections on reflection-gate / hook-unwiring changes. Treat the
  miss as unknown, not as evidence of none.

## Follow-up configs in the same archive dir

- `ops-followup.json` writes `tests/test_agent_frontmatter.py` (`MEMORY_AGENTS` → code-reviewer, planner)
  and `.claude/agent-memory/README.md` (the memory-agent list).
- `ops-ai-docs.json` writes `.ai/SESSION_STATE.md` and `.ai/CHANGELOG_AI.md`.
- `ops-tests-docs.json` writes `.claude/agents/_shared/INVOCATION.md` (planner grant rows) and
  `tests/test_hook_stdin_wiring.py` (removes the false-green command-log-audit stdin test).
- `ops-tests2.json` writes `.claude/agents/reviewer.md` (drops the stale shell-window line: the
  reviewer has no Bash) and `tests/test_read_window_guard.py` (`AGENT_MAX_TURNS` → 15/8/12).
  Open: `tests/test_pipeline_e2e.py::test_reflection_checkpoint_outranks_the_iron_law_allowance`
  still asserts the removed PreToolUse reflection checkpoint; owner decides (re-wire or invert).
- `ops-boot-trim.json` writes `CLAUDE.md` (policy block v3 -> v5), creates `.ai/TOKEN_MODEL_POLICY.md`, and appends to `CHANGELOG.md`, `.ai/SESSION_STATE.md`, `.ai/CHANGELOG_AI.md`. The `session-start.sh` caps were applied with the Edit tool (hook files are refused to scripted writes).

- Follow-up 2026-09-19: owner-approved deletion of `/refine`, `/santa`, `/gan-build`, `/xpipe` (+ `santa-method`, `gan-harness`, `xpipe.py`, `tests/test_xpipe.py`, `.agents` mirror) via `git rm`; reference cleanup script `scratchpad/patch_ck.py` + `patch_ck2.py` (templates PAP v3, CHANGELOG). qa-agents mirror: `.claude/plans/archive/ops-token-remediation/ops-remove-retired-commands.json`.
