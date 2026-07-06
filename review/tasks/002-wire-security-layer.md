# Task 002 — Wire the Security Layer (or Delete It)

## Problem
The marketed security layer is dead code. `src/security/command_validator.py` (`CommandValidator`) and `src/security/path_guard.py` (`PathGuard`) are imported only by `tests/test_security.py`; no hook, no CLI command, no operations script touches them, and they are never copied into target projects. `docs/ARCHITECTURE.md:535` advertises a "Blocklist check → Block: rm -rf /, sudo rm, eval, curl|bash" pipeline that does not execute. Meanwhile three parallel ad-hoc security implementations exist (bash hook greps, ops-script inline checks, these Python modules), none shared. This is a **false security guarantee** — the security review's single most important finding.

Worse, the dead code has real bugs that must be fixed before wiring:
- `command_validator.py:94` reads `config.get("hooks", {}).get("safeMode")` but `config.schema.json:120-135` defines `safeMode`/`allowedCommands`/`blockedCommands` under **`security`** — user settings are silently ignored.
- `command_validator.py:16,79-87`: `bash`/`sh` are allowlisted and only `argv[0]` is inspected → `bash -c 'rm -rf /'` passes; `echo hi && rm -rf /` passes (no `&&`/`||` segment splitting); `xargs rm`, `find . -delete`, `python -c "os.system(...)"` all pass.
- `command_validator.py:31-43`: `\$\(` bans all command substitution (false positives on legitimate configured commands); `source\s`, `exec\s` match prose.
- `path_guard.py:70`: relative symlink targets resolved against process cwd instead of the link's directory — wrong verdicts both ways; `path_guard.py:64`: substring matching (`".env" in rel_path`) blocks `my.envelope.txt`.

## Root Cause
The modules were written for an architecture that never materialized; enforcement grew organically in bash instead. Nothing in CI measures "is this imported by production code," and the docs were written from the design, not the implementation.

## Files
- `src/security/command_validator.py` (→ `src/claudekit/security/` after task 001)
- `src/security/path_guard.py`
- `config.schema.json:120-135` (security section)
- `.claude/settings.json` (new PreToolUse matcher)
- `src/cli/main.py` (new `check-command` subcommand)
- `docs/ARCHITECTURE.md:535` (claim to fix or delete)
- `tests/test_security.py` (extend with bypass tests)

## Priority
**P1** (High in security review) — a false guarantee is worse than no guarantee.

## Estimated Time
3–5 days (fix bypasses, wire, self-tests). The "delete" option is half a day.

## Risk
Medium. A newly-wired fail-closed command guard can block legitimate workflows (the `\$\(` pattern would break `echo $(date)` in configured commands). Mitigate with a warn-only rollout phase behind `ECC_HOOK_PROFILE=strict`, then default-on. Per security review §1a, treat the result as a **speed bump, not a sandbox** — say so in docs.

## Step-by-step Implementation
1. **Decide: wire (recommended) or delete.** If delete: remove `src/security/`, `tests/test_security.py`, and the ARCHITECTURE.md §"Security Layer" claims. Steps below assume wire.
2. Fix config read: `command_validator.py:94` → `config.get("security", {})`; add a round-trip test using the schema's own example.
3. Fix chaining blindness: split commands on `;`, `&&`, `||`, `|`, newlines; validate each segment's base command. Remove `bash`, `sh`, `env`, `xargs`, `find` from `DEFAULT_ALLOWLIST` or recurse into `-c` payloads.
4. Anchor `DANGEROUS_PATTERNS` (word boundaries, position); drop or scope `\$\(`.
5. Fix `path_guard.py:70`: `target = (Path(file_path).parent / os.readlink(file_path)).resolve()` — or delete the block (the `.resolve()` at line 46 + `relative_to` check at 52 already covers escapes). Fix `:64` to component-level matching (`PurePath(rel_path).name == ".env"` / fnmatch per part). Name the magic depth `20` (line 87).
6. Expose as CLI: `claudekit check-command "<cmd>"` (exit 0 allow / 2 block with reason on stderr) and `claudekit check-path <path>`.
7. Wire a PreToolUse Bash matcher in `.claude/settings.json` calling `check-command` with the extracted command; **fail closed** (parse failure or validator crash ⇒ exit 2). Wire PathGuard into the Write/Edit chain or into `execute-json-ops.py`'s path checks (dedupe the three parallel implementations — ops scripts should import `claudekit.security`).
8. Update `docs/ARCHITECTURE.md` and `SECURITY.md`: describe what actually runs, and state explicitly "denylist speed bump, not a sandbox — use OS sandboxing for real isolation."
9. Rollout: v2.1 ships it under `ECC_HOOK_PROFILE=strict` (warn in `standard`), v3.0 default-blocking.

## Acceptance Criteria
- `grep -rn "CommandValidator\|PathGuard" --include="*.py" --include="*.sh"` shows production call sites (ops scripts and/or hook), not just tests.
- `claudekit check-command "bash -c 'rm -rf /'"` exits 2. Same for `echo hi && rm -rf /`, `xargs rm`, `find . -delete`.
- A user config with `security.safeMode: false` is honored (round-trip test).
- Malformed JSON payload to the hook ⇒ block (exit 2), not silent allow.
- ARCHITECTURE.md/SECURITY.md contain no claim about a control that doesn't run.

## Testing Strategy
- Extend `tests/test_security.py` with the bypass corpus (testing-review items 3–5): interpreter smuggling, chaining, `busybox rm`, `\rm`, `rm${IFS}-rf`, unicode homoglyphs, `..%2f` traversal, in-project symlink → `/etc/passwd` (covers the uncovered symlink branch, currently 73% coverage).
- Hook self-test script: feed known-bad and known-good JSON payloads, assert exit codes (security review fix #3).
- Integration: run the wired hook in a fixture repo via the CI `install.sh → doctor` job.

## Rollback Plan
The hook wiring is a settings.json entry — remove the matcher line to disable instantly (or `ECC_HOOK_PROFILE=minimal`). Library fixes are pure improvements with test coverage; revert commit if a false-positive storm appears, and fall back to warn-only mode while patterns are tuned.
