# Review: plan-hook-stdin-and-reflection

Plan: /Users/omarmokhtar/IdeaProjects/claudekit/.claude/plans/plan-hook-stdin-and-reflection.md
Ops: /Users/omarmokhtar/IdeaProjects/claudekit/.claude/plans/plan-hook-stdin-and-reflection.ops.json
Reviewer: reviewer (no Bash — nothing below was executed; all claims are from reading files)
Date: 2026-09-17 · Tier 3

PRE-VALIDATION: PASS — plan + ops exist, ops parses, 4 ops ↔ 4 steps (no orphans, no phantom
steps), Overview/Steps/Testing/Rollback/Risk all present.

## Verified by reading the repo (refutation attempts that FAILED, i.e. the plan holds)

- **settings.json anchor**: `.claude/settings.json:40` raw text is
  `...; bash \"$ROOT/.claude/hooks/command-log-audit.sh\" &'"`; the op's `find` decodes to
  exactly that and occurs once in the file.
- **Post-state, settings.json**: result is
  `"bash -c 'ROOT=\"…\"; PAYLOAD=$(cat); printf %s \"$PAYLOAD\" | bash \"$ROOT/.claude/hooks/command-log-audit.sh\" &'"`.
  Valid JSON (only `\"` escapes, no raw quote/newline). Valid bash: no single quote is
  introduced inside the single-quoted `bash -c '…'` body; `$(cat)` and `"$PAYLOAD"` are
  expanded by the inner shell. `&` backgrounds the whole pipeline, and the consumer's stdin
  is the pipe (an explicit redirection), so the POSIX `/dev/null` rule no longer applies.
  bash-3.2 safe (no `<<<`, arrays, `wait -n`).
- **reflection-gate.py anchors**: `def project_root() -> Path:` at line 503 (unique);
  the minimal branch at 602–603 matches the `find` verbatim including 8-space indent.
- **Python post-state**: the inserted function is module-level, consistently 4-space
  indented, and every symbol it uses is in scope — `advisory_warnings` (448),
  `reflection.duty_summary` (reflection.py:1110), `reflection.receipt_instructions`,
  `hlog` (88), `json`/`sys` (56/61). `project_root` is defined immediately below but
  resolved at call time. The payload ends with `\n\n`, preserving the two-blank-line gap.
- **Hard rule 2**: the new path only writes stderr/stdout and `return 0`; `deny()` (the sole
  `exit 2` contract, line 97) is untouched; no `exit 1` is added anywhere. Compliant.
- **CHANGELOG**: `## [Unreleased]` occurs once (line 13); the `add_after` payload carries its
  own leading `\n` (literal concat), and existing entries are bullets directly under the
  heading, so the style matches.
- **Test hygiene (tests 1–2)**: `run_hook` forces `ECC_HOOK_PROFILE=standard` explicitly;
  `hook_sandbox` copies `.claude/hooks` into `tmp_path` and `command-log-audit.sh` resolves
  both `hooks.log` and `bash-commands.log` from `$SCRIPT_DIR` (lines 9, 17), so the real logs
  are untouched. Polls are bounded (10 s / 3 s) and the subprocess has `timeout=60`.
- **CLAUDEKIT_HOOK_LOG** is honoured by the gate (`reflection-gate.py:73`), so test 3's log
  assertion does not append to the real hooks.log, and `valid_session` (reflection.py:427) is
  just a non-empty-string check, so the random uuid reaches the advisory branch.

## Blocking findings

1. **[MAJOR] Test 3 mutates the developer's real project state.** It sets
   `CLAUDE_PROJECT_DIR=REPO`, and `main()` calls `record_footprint()` for `Stop` *above* the
   profile gate (line 589–590), plus whatever the advisory reads/writes through
   `reflection.*`. The log file is redirected, the reflection ledger/footprint is not. Fix:
   run test 3 against the same `hook_sandbox(tmp_path)` root the other two use.
2. **[MAJOR] Test 3 does not pin Step 2's actual behaviour.** No unmet duty is ever created,
   so `advise_unmet_duties` takes the `all duties met` branch — which also contains the
   string `"stop advisory"` the test asserts on — and the systemMessage check is guarded by
   `if proc.stdout.strip():`, so it is skipped when nothing is emitted. The test therefore
   passes even if the duty list and the `systemMessage` are never produced, i.e. it does not
   test what the plan's Step 2 "Done when" promises. Fix: seed a duty (e.g.
   `reflection.record_session_start` + `record_activity`/`append_entry`) in the sandbox root
   and assert unconditionally that the last stdout line parses to a `systemMessage`
   containing the duty text, and that `decision` is absent.
3. **[MAJOR] The plan's "Protected-file check" claim is refuted by the code.**
   `is_protected_file` gates **deletes only**: `validate-config-json.py:128` (GUARD 13, inside
   the `file_delete` branch) and `execute-json-ops.py:615` (inside the delete handler).
   Nothing consults it for `code_edit`. The CHANGELOG op will therefore execute normally;
   the plan's instruction to "apply that one hunk by hand" would produce a duplicate edit.
   Fix the plan's evidence section (and drop the manual-hunk contingency).
4. **[MAJOR] The mutation control (test 2) cannot distinguish "starved" from "broken".** It
   asserts only the absence of the marker, which is also the outcome if the sandbox copy
   fails, the hook crashes, or python3 is missing. Fix: additionally assert the sandbox
   `hooks.log` contains the fail-closed line (`JSON parse failure extracting 'command'`),
   which is the specific signature of an empty payload.

## Notes

- `PAYLOAD=$(cat)` now runs in the **foreground** of the PostToolUse hook: it blocks until
  stdin EOF. If the client ever leaves the hook's stdin open, the Bash tool's PostToolUse
  hook stalls to its timeout, where today it returned instantly. Worth one line in the risk
  section (the non-blocking intent is only partly preserved).
- `{"systemMessage": …}` on a **Stop** hook: I could only read code. No other file in this
  repo emits `systemMessage`, so there is no in-repo precedent to check against, and I have
  no Bash to run a live Stop hook. **Unverified by execution** — eyeball it in a live session
  (the plan already lists this as the one thing to watch) before any fleet sync.
- Plan Step 3's prose ("asserts … a `systemMessage` naming the duty") overstates the test file
  actually shipped in the `file_create` payload; they must be reconciled with finding 2.

## Scores

- Plan Quality:  [██████████████████░░░░░░░] 74/100 (×0.40) — evidence and anchors are strong;
  ops.json test content under-pins Step 2 and the protected-file evidence is wrong.
- Architecture:  [██████████████████████░░░] 90/100 (×0.30) — minimal diff, correct layer,
  respects the PROFILE CONVENTION.
- Security:      [█████████████████████░░░░] 85/100 (×0.30) — no secrets, no eval, payload
  moves through a pipe not an argument; new stdout on Stop is the only new surface.
- **TOTAL: 82/100 → REVISE**

---

# Round 2 (delta review, 2026-09-17)

Scope: the delta only. The two `code_edit` ops are byte-identical to round 1 (already
verified), so this round re-checks the rewritten `file_create` payload and the plan text.

- **F1 sandboxing — CLOSED.** All three tests now go through `hook_sandbox(tmp_path)` +
  `sandbox_env()`, which pins `CLAUDE_PROJECT_DIR=<tmp>/proj` **and** `TMPDIR=<tmp>/tmpdir`.
  That is the correct pair: `ledger_dir()` (reflection.py:252–272) is
  `$TMPDIR/<root-name>-u<uid>/_project_key()`, and `_project_key()` (222–243) hashes
  `realpath(project_root())`, which returns `CLAUDE_PROJECT_DIR` when it is a directory
  (386–389) — `cwd` enters only the memo key, not the value. So the seeding subprocess
  (cwd = pytest's) and the gate run (cwd = sandbox) address the **same** ledger, and neither
  touches the real repo or the developer's real ledger. `ensure_ledger_dir` creates and
  audits only the two components it owns, so a 0o755 `tmpdir` base is not a problem.
- **F2 test 3 now pins the behaviour — CLOSED.** `seed_learning_loop_duty` calls
  `reflection.record_activity(sid, 'mutation-or-delivery')` and asserts
  `learning_loop_pending(sid)` before the gate runs — both exist (reflection.py:880, 993) and
  `duty_summary` emits `"LEARNING LOOP: this session mutated or delivered…"` (1122–1127), so
  the asserted substring is the real duty text, not a guess. The assertions are now
  unconditional: exit 0, `stop advisory` in the redirected hook log, non-empty stdout, stdout
  parses as JSON, no `decision` key, `LEARNING LOOP` in `systemMessage`. Pre-fix this fails at
  the log assertion; post-fix a silent advisory fails at the stdout assertion. Env ordering is
  right (`sandbox_env` pops `CLAUDEKIT_HOOK_LOG`, the test sets it afterwards).
- **F3 protected-file text — CLOSED.** Plan §"Protected-file check (corrected after review)"
  now states delete-only gating with the two correct citations and deletes the manual
  contingency.
- **F4 control fails for the right reason — CLOSED.** Test 2 additionally waits for
  `JSON parse failure extracting 'command'` in the sandbox `hooks.log` (the copied
  `command-log-audit.sh` writes it to `$SCRIPT_DIR/hooks.log`), so a hook that never ran can
  no longer masquerade as a passing control.
- **F5 both risks documented — CLOSED.** The foreground `PAYLOAD=$(cat)` blocking risk and
  the "`systemMessage` verified by reading the documented shape, not by execution" caveat are
  both in the Risk Assessment.

Still true and still not executable by me: the `systemMessage` rendering contract on a live
Stop hook. The plan now says so in the risk section rather than implying verification, which
is the correct disposition for a reviewer with no Bash. Mutation proof and the suite remain
the implementer's/verifier's step.

Round 2 scores: Plan Quality 92 (×0.40) · Architecture 90 (×0.30) · Security 88 (×0.30)
→ **TOTAL 90/100 → APPROVED**, zero blocking findings.

## Round 2 verdict block (from reviewer reply)

```
=== REVIEW ===
SCORE: 90
DECISION: APPROVED
- [MINOR] systemMessage rendering on a live Stop hook remains verified by documentation only; eyeball one live Stop before any fleet sync, as the plan's risk section says
=== END REVIEW ===
```
