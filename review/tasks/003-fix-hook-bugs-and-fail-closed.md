# Task 003 — Fix Hook Bugs & Make Guards Fail Closed

## Problem
The hook layer — ClaudeKit's enforcement mechanism — is riddled with wiring bugs that make it silently non-functional:
1. **Nothing blocks.** Every "blocking" hook ends with `exit 1` and prints to stdout (`block-no-verify.sh:46,59`, `ops-enforcement.sh:79,96`, `config-protection.sh:91`, `commit-quality.sh:133`). Claude Code's contract: **exit 2 blocks and feeds stderr to the model; any other non-zero proceeds.** No enforcement hook has ever blocked anything.
2. **Dead telemetry chain.** settings.json's PostToolUse passes `"$CLAUDE_TOOL_NAME" "$CLAUDE_TOOL_RESULT" "$CLAUDE_TOOL_ARGS"` — env vars Claude Code never sets (hooks receive JSON on stdin). `post-tool-use.sh:14` gets `TOOL_NAME="unknown"` forever; the `case` at line 155 never matches; cascade: `cost-tracker.sh:26` counts log lines that are never written, so `TOOL_CALLS` is always 0 and the session summary never prints.
3. **Ops filename split-brain.** Plans ship as `*.ops.json`, but `pre-commit.sh:91` and the settings.json Stop hook search `ops-*.json` (match zero files, forever), while `ops-enforcement.sh:56`'s allow-regex `(^|/)ops(-[^/]+)?\.json$` blocks the agent from writing the repo's own plan files.
4. **Fail-open guards.** `config-protection.sh`/`security-reminder.sh`/`ops-enforcement.sh` extract JSON with `python3 -c ... 2>/dev/null`; any payload-shape drift ⇒ empty value ⇒ `exit 0` (allow). An advertised guard that fails open is worse than none.
5. **Broken detection logic:** `pre-commit.sh:115-128` embeds `\x27` in `grep -E` classes (not ERE — single-quoted secrets never caught); `commit-quality.sh:60` uses bash-4 `${VAR,,}` (stock macOS bash 3.2 → "bad substitution"); `block-no-verify.sh:32` matches `--no-verify` anywhere (blocks commit *messages* mentioning it); `ROOT=$(git rev-parse ...)` with no fallback → hooks source `/.claude/hooks/...` outside git repos.
6. **Dormant defenses:** `templates/hooks/file-guard.sh` and `prompt-injection-scanner.sh` (the strongest defenses in the repo) are copied by install.sh but never referenced by settings.json.
7. **Misc rot:** `suggest-compact.sh:23-34` mkdir-mutex with no stale-lock recovery (one crash freezes the counter forever) and GNU-only `date -r` (daily reset never fires on macOS); `format-typecheck.sh:29-42` reconstructs edited files by scraping bash-command logs (wrong data source); `auto-checkpoint.sh:144-153` swallows `git stash apply` failures (uncommitted work vanishes into a stash) and records `stash@{0}` refs that drift, so pruning drops the wrong stash.

## Root Cause
Silent-failure culture: nearly every python3 sub-call ends in `2>/dev/null` with bare `except`, so protocol drift (env-var era → stdin-JSON era) degraded everything to no-ops with zero diagnostics. Copy-pasted `log()`/`get_project_config()`/extractor blocks across 10+ hooks diverged instead of being shared. No test ever executed a hook against a payload.

## Files
- `.claude/settings.json` (PostToolUse entries, Stop hook find pattern, new file-guard/scanner matchers)
- `.claude/hooks/`: `block-no-verify.sh:32,46,59` · `ops-enforcement.sh:56,79,94,96` · `config-protection.sh:19-30,77,91` · `commit-quality.sh:44,60,77,133` · `pre-commit.sh:91,115-128,141,153` · `post-tool-use.sh:14,155` · `cost-tracker.sh:26,37` · `session-start.sh:77` · `suggest-compact.sh:23-34` · `format-typecheck.sh:29-42,84` · `security-reminder.sh` · `command-log-audit.sh` · `pre-push.sh` · `pre-plan.sh:81`
- `templates/hooks/auto-checkpoint.sh:91,103,140,144-153` · `file-guard.sh:94-97` · `prompt-injection-scanner.sh:62` · `check-comment-replacement.sh:39,98`
- New: `.claude/hooks/lib.sh` (shared ROOT resolution, logging, JSON extraction, ops-file pattern)

## Priority
**P0** for items 1–2 (enforcement + telemetry), **P1** for 3–6, **P2** for 7.

## Estimated Time
4–6 days for the full sweep; the P0 subset is <1 day.

## Risk
Medium. Turning enforcement **on** for the first time will surface false positives users never experienced (config-protection blocking new pyproject.toml creation — `config-protection.sh:77`; block-no-verify matching substrings). Fix those known false-positive bugs in the same pass, and stage via `ECC_HOOK_PROFILE`.

## Step-by-step Implementation
1. Create `.claude/hooks/lib.sh`: `resolve_root()` (git rev-parse with `${PWD}` fallback + bail if no `.claude/`), `log()`, `extract_json_field()` (single python3 call, **logs parse failures to hooks.log instead of /dev/null**), `OPS_GLOB`/`OPS_REGEX` constants matching both `*.ops.json` and `ops-*.json`.
2. Blocking semantics: in the four blocking hooks, route denial messages to stderr and `exit 2`. Advisory hooks keep `exit 0`.
3. Fail-closed: in blocking guards only, JSON-parse failure or empty mandatory field ⇒ stderr reason + `exit 2`.
4. Fix settings.json PostToolUse/PostToolUseFailure to pipe stdin JSON (no env vars); rewrite `post-tool-use.sh` to `TOOL_INPUT=$(cat)` + one python parse; verify cost-tracker starts counting.
5. Ops pattern: replace `pre-commit.sh:91` find, Stop-hook find (also quote the loop — it word-splits), and `ops-enforcement.sh:56` regex with the lib.sh constants.
6. Detection fixes: rebuild secret patterns without `\x27` (compose quotes via `"'"` concatenation or move matching into the python helper); `tr '[:upper:]' '[:lower:]'` instead of `${VAR,,}`; scope block-no-verify to actual git invocations (`(^|[;&|]\s*)git\s[^;&|]*--no-verify`); anchor config-protection basenames and allow Write of a **new** pyproject.toml lacking lint sections; remove pre-commit.sh:153's suggestion to use `--no-verify` (the escape hatch a sibling hook exists to block).
7. Wire dormant hooks: settings.json PreToolUse matchers running `file-guard.sh` on Read/Write/Bash targets and `prompt-injection-scanner.sh` on UserPromptSubmit (word-boundary-anchor its patterns first; document both as best-effort). Add an exceptions file for file-guard's extension blocks (`public.pem` false positives, `file-guard.sh:94-97`).
8. auto-checkpoint: record stash **SHAs** (`git rev-parse stash@{0}`) not indices; check `stash apply` exit and print recovery instructions on failure; lock the registry read-modify-write.
9. suggest-compact: stale-lock age check (`find "$_lock_dir" -mmin +5 -exec rmdir {} \;`); BSD/GNU `stat`/`date` branch.
10. Remove ops-enforcement.sh:94's bypass hint ("use Bash cp/sed") and extend the guard to obvious Bash write patterns (`sed -i`, `tee`, `>` redirects into source paths).
11. Sweep the remaining P3s: quote `basename "$(pwd)"` (session-start.sh:77), remove dead `PM_INSTALL`/`SESSION_LOG` vars, unify log paths on `$SCRIPT_DIR`.

## Acceptance Criteria
- Self-test harness: feeding a `git commit --no-verify` payload to block-no-verify returns **exit 2** with reason on stderr; a commit message *containing* "--no-verify" passes.
- An Edit targeting `eslint.config.js` without approved ops.json is actually blocked in a live Claude Code session.
- `pre-commit.sh` validates a staged `foo.ops.json` (nonzero match count in hooks.log).
- Malformed stdin JSON to any blocking guard ⇒ exit 2.
- `api_key = 'abcdef123456'` (single quotes) staged ⇒ commit blocked.
- cost-tracker prints a session summary with TOOL_CALLS > 0 after one Edit.
- All hooks pass `bash -n` + ShellCheck; hooks run clean on macOS bash 3.2.

## Testing Strategy
- New `tests/test_hooks_behavioral.py`: subprocess each hook with fixture JSON payloads (good/bad/malformed), assert exit codes and stderr — replaces keyword-grep theater (testing-review missing tests 9, 10).
- Adversarial corpus for prompt-injection-scanner (25 known-bad strings ⇒ nonzero; benign text ⇒ 0) and file-guard (`.env`, `id_rsa`, `terraform.tfstate` ⇒ block; `src/main.py` ⇒ allow).
- macOS CI runner (task 011) exercises the bash-3.2 and BSD-date paths.

## Rollback Plan
`ECC_HOOK_PROFILE=minimal` disables the enforcement set at runtime without reinstalling. Each hook fix is an independent commit — revert individually. lib.sh is additive; hooks keep working if it's sourced conditionally (`[ -f lib.sh ] && source`), so a bad lib rollout degrades to previous inline behavior.
