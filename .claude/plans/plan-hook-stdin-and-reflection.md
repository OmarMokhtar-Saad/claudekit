# Implementation Plan: hook-stdin-and-reflection

## Overview
Two measured defects in the hook layer, fixed together because both are "a green check that
records nothing": (A) the PostToolUse audit hook is backgrounded inside `bash -c`, so POSIX
redirects its stdin to `/dev/null` and it fail-closes on an empty payload on **every** Bash
call; (B) under `ECC_HOOK_PROFILE=minimal` the Stop duty prompt lives *below* the blocking
gate in `reflection-gate.py`, so a session is never told what it owes and produces zero
receipts.

## Scope
- **In Scope:** `.claude/settings.json` PostToolUse(Bash) wiring for `command-log-audit.sh`;
  an advisory Stop duty path in `.claude/hooks/reflection-gate.py`; one new behavioral test
  file; CHANGELOG `[Unreleased]`.
- **Out of Scope:** the three other backgrounded Stop hooks (evidence below: none reads
  stdin); the 180 historical `unparsable PreToolUse payload (8|15|32 bytes)` blocks (spread
  over 8 days, and `reflection-gate.py` is **not** wired to PreToolUse in settings.json —
  those come from `dispatch.sh` or tests; unverified, open question); hook counts/docs
  (no hook added or removed).

## Prerequisites
- `ECC_HOOK_PROFILE=minimal` present in `.claude/settings.local.json` (session bootstrap).

## Evidence (verified during discovery, not re-derived)

### A. stdin loss
`.claude/settings.json` backgrounds four hooks with a trailing `&` inside `bash -c`
(lines 40, 129, 138, 147). Which of them actually reads stdin:

| Hook | Reads stdin? | Evidence | Action |
|---|---|---|---|
| `command-log-audit.sh` (PostToolUse Bash, L40) | **YES** | `TOOL_INPUT=$(cat 2>/dev/null)` L21, then `json.load(sys.stdin)` L42 | **fix the wiring** |
| `cost-tracker.sh` (Stop, L129) | no | reads `hooks.log`; no `cat`/`read` of stdin | leave as is |
| `desktop-notify.sh` (Stop, L138) | no | derives state from `git status` + `pwd` | leave as is |
| `format-typecheck.sh` (Stop, L147) | no | reads `$SCRIPT_DIR/edited-files.log` | leave as is |

Live proof of the failure: 75 Bash calls on 2026-09-16 19:00–21:00 produced exactly 75
`[command-log-audit] [ERROR] JSON parse failure extracting 'command' (fail-closed)` lines,
and `.claude/hooks/bash-commands.log` does not exist.

### B. zero receipts under `minimal`
`reflection-gate.py::main` records *above* the profile gate (`record_footprint`,
`handle_post_tool_use`, `handle_failure` all run under `minimal` — the PROFILE CONVENTION in
the file header is honoured). So **capture is not the gap**. The gap is the *prompt*:
`advisory_warnings()`, `duty_summary()` and `receipt_instructions()` all live inside
`handle_stop`, which `main` reaches only when `blocking_enabled()` is true. Under `minimal`
the branch is `hlog("INFO", "ECC_HOOK_PROFILE=minimal - Stop blocking suppressed"); return 0`
— 360 such lines on 2026-09-16, 0 receipts. Smallest fix: emit the same duty list as an
**advisory** (hooks.log + stderr + a `systemMessage` JSON on stdout), exit 0. No blocking
semantics change; hard rule 2 untouched (a block is still, and only, `exit 2`).

### Protected-file check (corrected after review)
`is_protected_file()` gates **`file_delete` only** — `validate-config-json.py:128` and
`execute-json-ops.py:615`. No `code_edit` is subject to it, so both the
`.claude/settings.json` and the `CHANGELOG.md` edits execute normally and there is **no
manual contingency**. (`config-protection.sh` is a separate, tool-level guard on Edit/Write;
it does not apply to the ops executor.)

## Implementation Steps

### Step 1: Read stdin before backgrounding the audit hook
- **File:** `.claude/settings.json` (line 40)
- **Action:** Modify
- **Details:** `PAYLOAD=$(cat); printf %s "$PAYLOAD" | bash ".../command-log-audit.sh" &`.
  `$(cat)` runs in the foreground where stdin is still the payload; only the consumer is
  backgrounded, so the non-blocking intent is preserved. bash-3.2 safe (no `<<<`, no
  arrays, no `wait -n`).
- **Done when:** piping a payload into that exact command string appends a line to
  `.claude/hooks/bash-commands.log`. (~5 min)

### Step 2: Advisory Stop duty under non-blocking profiles
- **File:** `.claude/hooks/reflection-gate.py`
- **Action:** Modify — add `advise_unmet_duties(session_id, subagent)` before
  `def project_root()`, and call it from the `if not blocking_enabled():` branch when the
  event is `Stop`/`SubagentStop`.
- **Details:** whole body wrapped in `try/except` — an advisory must never break a Stop.
  Stdout carries only `{"systemMessage": ...}`; no `decision`/`continue` field, so it cannot
  become an accidental block.
- **Done when:** with `ECC_HOOK_PROFILE=minimal` and a session holding an unmet duty, the
  Stop invocation exits 0 and its stdout parses to a `systemMessage` naming the duty. (~20 min)

### Step 3: Behavioral regression test
- **File:** `tests/test_hook_stdin_wiring.py` (new)
- **Action:** Create
- **Details:** every test runs in a tmp sandbox — `.claude/hooks/` copied into `tmp_path`,
  `CLAUDE_PROJECT_DIR` and `TMPDIR` both pointed inside it, `ECC_HOOK_PROFILE` forced
  explicitly. `CLAUDE_PROJECT_DIR` must NEVER be the repo: `record_footprint()` runs above
  the profile gate and would mutate this repo's own state from the suite. Three tests:
  1. the exact `command-log-audit.sh` command string out of settings.json, fed a realistic
     `{"tool_name":"Bash","tool_input":{"command":"echo hello-stdin-<uuid>"}}` payload, must
     land the marker in the sandbox `bash-commands.log` (polled 10 s for the backgrounded child);
  2. mutation control — the pre-fix backgrounded form must NOT record the marker **and**
     must write `JSON parse failure extracting 'command'` into the sandbox `hooks.log`, so a
     hook that crashed on startup cannot pass as a control;
  3. seeds a real unmet duty (`reflection.record_activity(sid, "mutation-or-delivery")` with
     no routed receipt — `learning_loop_pending()` then returns True) in the same env, drives
     `reflection-gate.py --event Stop` under `minimal`, and asserts unconditionally: exit 0,
     `stop advisory` in the hook log, stdout parses as JSON, no `decision` key, and
     `LEARNING LOOP` present in `systemMessage`.
- **Done when:** all three pass after Steps 1–2. (~30 min)

### Step 4: CHANGELOG
- **File:** `CHANGELOG.md`
- **Action:** Modify — one `[Unreleased]` bullet.
- **Done when:** entry present. (~2 min)

## Testing Strategy
- `python3 -m pytest tests/test_hook_stdin_wiring.py -q` (new, must pass)
- `python3 -m pytest tests/test_reflection_gate.py tests/test_hook_delivery.py tests/test_hooks_behavioral.py -q`
  — `test_minimal_profile_suppresses_blocking` and `test_minimal_profile_still_records` are
  the two that pin the profile convention; both must stay green (the change adds an
  advisory, it does not move the blocking boundary).
- `python3 -m pytest tests/ -q` · `ruff check` · `mypy` · `python3 scripts/gen-docs.py --check`
  (counts must be unchanged — no hook added or removed) · `shellcheck install.sh .claude/hooks/*.sh`.
- **Mutation proof (required before the fix is believed):** run
  `tests/test_hook_stdin_wiring.py::test_wired_command_log_audit_receives_stdin` against the
  CURRENT `settings.json`. Expected failure: `AssertionError: the wired PostToolUse command
  never recorded the payload; bash-commands.log exists=False` (the file is not created at
  all, because `CMD` is empty and the hook returns before the append). Likewise
  `test_minimal_profile_still_prompts_the_stop_duty` must fail pre-fix on the missing
  `stop advisory` log line. If either passes before its fix lands, the test is inert — fix
  the test, not the anchor.

## Rollback Plan
- `git checkout -- .claude/settings.json .claude/hooks/reflection-gate.py CHANGELOG.md` and
  `rm tests/test_hook_stdin_wiring.py`. No state migration, no generated artifact, no
  installed-tree change; the hooks are read fresh from settings.json each session.

## Risk Assessment
- **Low:** CHANGELOG bullet; the test file; the three untouched backgrounded Stop hooks
  (verified not to read stdin).
- **Medium:** `PAYLOAD=$(cat)` **blocks in the foreground until stdin EOF**. That is the
  whole point — it is where the payload is captured — but it means the PostToolUse hook is
  no longer instantly-returning: if Claude Code ever held that pipe open, the hook would
  wait rather than return. Today the payload is written and the pipe closed immediately, and
  the expensive half (the hook body) stays backgrounded; watch for any Bash-call latency
  after this lands.
- **Medium:** `.claude/settings.json` is the live wiring for this repo's own session — a
  malformed command string breaks every Bash call's PostToolUse. Mitigated by the exact-string
  test and by the fact that a failing PostToolUse hook is non-blocking. `.claude/settings.json`
  is also mirrored downstream by `ck fleet update`; this plan does NOT sync the fleet.
- **Medium:** new stdout on the Stop path. **The `systemMessage` contract is verified only by
  reading Claude Code's documented hook-output shape, not by execution** — the test asserts
  the JSON we emit, not that the client renders it. Eyeball one live Stop before any fleet
  sync. Only `systemMessage` is emitted and the writer is exception-wrapped, so the worst
  case is an unrendered line, not a block.
- **High:** none.
- **UNVERIFIED:** the 180 `[BLOCK]` / `unparsable PreToolUse payload` pairs (8/15/32 bytes,
  2026-09-04 → 2026-09-16). `reflection-gate.py` is not wired to PreToolUse in
  settings.json, so the caller is `dispatch.sh` or the test suite; not diagnosed here.
- **UNVERIFIED:** 598 `event PreToolUse without a session id` WARNs — same origin question.
