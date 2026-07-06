# ClaudeKit — Staff Engineer Code Quality Review

**Date:** 2026-07-05
**Scope:** All executable code — `src/`, `install.sh`, `.claude/hooks/`, `templates/hooks/`, `.claude/operations/scripts/`, `.claude/settings.json`, `config.schema.json`, `pyproject.toml`
**Tooling used:** `python3 -m py_compile` (all pass), `bash -n` (all pass), ShellCheck 0.11.0, live import verification of the build backend.

Severity scale: **P0** = broken/ships wrong, **P1** = major bug or silent failure of a core promise, **P2** = real bug with narrower blast radius, **P3** = smell/polish.

---

## 1. pyproject.toml

### P0 — Invalid build backend: `pip install .` fails outright
`pyproject.toml:3`

```toml
build-backend = "setuptools.backends._legacy:_Backend"
```

Verified in a clean environment:

```
>>> import setuptools.backends
ModuleNotFoundError: No module named 'setuptools.backends'
```

`setuptools.backends._legacy` **does not exist in any setuptools release**. Every `pip install .`, `pip install claudekit`, and `python -m build` fails at backend import. The package as shipped is uninstallable, meaning the `claudekit` / `ck` console scripts have never worked from a real install.

**Fix:**
```toml
[build-system]
requires = ["setuptools>=64"]
build-backend = "setuptools.build_meta"
```

### P1 — Installs a top-level `src` package
`pyproject.toml:29-31, 39-40`

```toml
[project.scripts]
claudekit = "src.cli.main:main"

[tool.setuptools.packages.find]
include = ["src*"]
```

This installs packages literally named `src`, `src.cli`, `src.security` into site-packages. `src` is the single most common scratch package name in the Python ecosystem; the first other project that does the same thing clobbers or shadows this one, and `import src.security` from user code is meaningless. This is the classic src-layout misconfiguration — src-layout means the *package* lives under `src/`, not that `src` *is* the package.

**Fix (src-layout done properly):**
```
src/claudekit/__init__.py
src/claudekit/cli/main.py
src/claudekit/security/...
```
```toml
[project.scripts]
claudekit = "claudekit.cli.main:main"
ck = "claudekit.cli.main:main"

[tool.setuptools.packages.find]
where = ["src"]
```

### P2 — Version chaos and unused setuptools-scm
- `pyproject.toml:7` says `2.0.0`; `src/cli/main.py:13` says `__version__ = "1.1.0"`; `shared.py:3` says `3.1.0`; executor docstring says v3.0; validator says v2.0; `install.sh:7` says 2.0.0. Five version strings, four values.
- `pyproject.toml:2` requires `setuptools-scm>=8` but no `[tool.setuptools_scm]` section exists and `version` is static — a dead build dependency that slows and can break isolated builds.

**Fix:** single source of truth — either `dynamic = ["version"]` + setuptools-scm, or drop setuptools-scm and read the version in code via `importlib.metadata.version("claudekit")`.

### P3 — Metadata polish
- `license = {text = "MIT"}` + the `License ::` classifier is the deprecated combo (setuptools ≥77 warns; PEP 639 wants `license = "MIT"`).
- No `dependencies` at all — `jsonschema` is optionally imported by the validator; declare it as `[project.optional-dependencies] validation = ["jsonschema>=4"]`.
- No 3.13 classifier; no `[project.optional-dependencies] dev = ["pytest", ...]` although a test suite exists.

---

## 2. `.claude/settings.json` (hook wiring) — the enforcement layer

### P0 — "Blocking" hooks exit 1, but Claude Code only blocks on exit 2
Every enforcement hook (`block-no-verify.sh:46,59`, `ops-enforcement.sh:79,96`, `config-protection.sh:91`, `commit-quality.sh:133`) ends with `exit 1` and prints its "BLOCKED" explanation to **stdout**.

Claude Code's hook contract: **exit 2 blocks the tool call and feeds stderr back to the model; any other non-zero exit is a non-blocking error** — the tool call proceeds. So the framework's flagship features (no `--no-verify`, ops-only editing, config protection, secret-commit blocking) **do not actually block anything**. The messages also go to stdout, which is not what gets shown to the model on a block.

**Fix (every blocking hook):**
```bash
echo "BLOCKED: ... reason ..." >&2
exit 2
```
Non-blocking warnings keep `exit 0` (with output on stdout).

### P1 — `post-tool-use.sh` reads env vars Claude Code never sets
`settings.json` PostToolUse entry:
```
bash ".../post-tool-use.sh" "$CLAUDE_TOOL_NAME" "$CLAUDE_TOOL_RESULT" "$CLAUDE_TOOL_ARGS"
```
`CLAUDE_TOOL_NAME` / `CLAUDE_TOOL_RESULT` / `CLAUDE_TOOL_ARGS` are not part of the hooks protocol (hooks receive a JSON payload on **stdin**). Result: `TOOL_NAME="unknown"` on every invocation (`post-tool-use.sh:14`), the `case` at line 155 never matches, so ops.json revalidation and git-op tracking are dead code that has never run. Same for the `PostToolUseFailure` entry (`${CLAUDE_TOOL_NAME:-unknown}` is always "unknown").

**Cascade:** `cost-tracker.sh:26` counts `Tool:` lines in hooks.log that only `track_modification` writes → `TOOL_CALLS` is always 0 → the session summary block (line 37) never prints. Two features dead from one wiring bug.

**Fix:** read stdin JSON like the other hooks do:
```bash
TOOL_INPUT=$(cat)
TOOL_NAME=$(echo "$TOOL_INPUT" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("tool_name",""))')
```

### P1 — `ROOT` may be empty; hook paths become `/.claude/hooks/...`
Every wrapper does `ROOT=$(git rev-parse --show-toplevel 2>/dev/null)` with no fallback. Outside a git repo, `bash "/.claude/hooks/ops-enforcement.sh"` fails silently — all enforcement disappears in non-git projects. Fix: `ROOT=${ROOT:-$PWD}` or bail out explicitly.

### P2 — Stop-hook inline script: unquoted `$(find ...)` loop
The first Stop hook iterates `for f in $(find "$ROOT/.claude/plans" -name "ops-*.json" ...)` — breaks on paths with spaces, and (see §4) the glob doesn't match the actual plan-file naming anyway.

---

## 3. install.sh

`bash -n` clean; ShellCheck: one warning (SC2010). The script is generally careful (`set -euo pipefail`, safe `config.env` parsing without `source`), but has several structural problems.

### P1 — `settings.json` is never installed → hooks are never registered
The script copies agents, commands, operations, skills, hook *scripts*, and modes — but never copies `.claude/settings.json` (grep confirms: no reference anywhere in `install.sh`). Claude Code discovers hooks via `settings.json`; without it, the 15 installed hook scripts in a target project are inert files. The whole "15 hooks installed" claim in the summary (line 405) is not functionally true.

**Fix:** copy (or generate, with mode-appropriate subsets) `settings.json` into `$DEST`, and honor `--minimal` by emitting a reduced hooks map.

### P1 — ERR trap destroys the user's pre-existing `.claude/` with no restore
`install.sh:94-101`

```bash
_cleanup_on_failure() {
    if [[ -d "$DEST" ]]; then
        rm -rf "$DEST"
    fi
}
trap '_cleanup_on_failure' ERR
```

The trap is installed *before* the overwrite prompt and doesn't distinguish "directory I created" from "directory that already existed". If the user has an existing `.claude/` (agreed to overwrite, or used `--force`) and *any* later command fails — a missing template, a sed error, a permission problem — the trap deletes their original configuration permanently. That is a rollback that rolls forward off a cliff.

**Fix:** move the existing dir aside first and restore it on failure:
```bash
if [[ -d "$DEST" ]]; then mv "$DEST" "$DEST.bak.$$"; PREV="$DEST.bak.$$"; fi
_cleanup_on_failure() {
    rm -rf "$DEST"
    [[ -n "${PREV:-}" ]] && mv "$PREV" "$DEST"
}
# on success: rm -rf "${PREV:-}"
```

### P2 — `curl | bash` is guaranteed to fail, unsafely
The README-style one-liner install cannot work: the script depends on `$SCRIPT_DIR/.claude` existing locally (line 9, used at line 160 `cp "$CLAUDE_SRC"/agents/*.md`). When piped, `BASH_SOURCE[0]` is empty so `SCRIPT_DIR` becomes the *cwd*, the `cp` fails, and the ERR trap `rm -rf`s `$DEST` (possibly the user's existing `.claude`, per the previous finding). Additionally, the interactive `read -r` prompts (lines 82, 107) consume the remainder of the piped script as input.

**Fix:** guard at the top:
```bash
if [[ ! -d "$CLAUDE_SRC" ]]; then
    print_err "ClaudeKit source not found. Clone the repo and run ./install.sh (curl|bash is not supported)."
    exit 1
fi
```
And add `--yes` / detect `[[ -t 0 ]]` before any `read`.

### P2 — Not idempotent with `--force`: stale files survive
With `--force` (or "y" at the prompt) the script copies *over* the existing `$DEST` without clearing it. Files removed or renamed between ClaudeKit versions linger — e.g. an old hook keeps firing forever. Fix: after taking the backup described above, install into a fresh directory.

### P2 — sed templating breaks on `|` or `&` in commands
`install.sh:306-337` — placeholder substitution uses `|` as the sed delimiter and raw values on the RHS. A `config.env` with `BUILD_CMD=npm run build | tee build.log` (or any command containing `&`, which sed expands to the matched text) corrupts the generated CLAUDE.md/CONSTITUTION.md or errors out mid-install — triggering the destructive ERR trap. Fix: escape the replacement (`s_esc=$(printf '%s' "$v" | sed 's/[&|\\]/\\&/g')`) or do templating with the same `python3` one-liner approach already used at line 348.

### P2 — Hard-coded summary numbers vs. computed counts
`install.sh:400-405` prints a hard-coded list of "28 agents… 37 commands… 7 modes… 15 hooks" while `AGENT_COUNT`, `CMD_COUNT`, `MODE_COUNT`, `HOOK_COUNT` are computed above. The prose and the numbers will drift (and `AGENT_COUNT` at line 158 excludes QUICK_START/HANDOFF from the *count* but line 160 copies them anyway, so doctor's count differs again). Print only the computed values.

### P3 — Miscellany
- `install.sh:158` — SC2010 `ls | grep | wc`; use `find ... | wc -l` or a glob array.
- `install.sh:146` — banner prints *after* language detection/prompt output; cosmetic ordering.
- `install.sh:120` — kotlin detection: any `build.gradle.kts` mentioning "kotlin" (which nearly all do, being Kotlin DSL) classifies a Java project as kotlin.
- `install.sh:85` — `TARGET_DIR="$(cd "$TARGET_DIR" ... || echo "$TARGET_DIR")"` silently keeps a relative path if `cd` fails; the very next check catches nonexistence, but symlinked/`..` inputs pass through unresolved.
- No uninstall path, and no recorded manifest of what was installed (would make upgrade/idempotency tractable).

---

## 4. Ops filename convention — a repo-wide split brain (P1)

Three different components disagree about what an ops file is called:

| Component | Pattern |
|---|---|
| `.claude/plans/` (actual files) | `add-health-check-endpoint.ops.json` — `*.ops.json` |
| `pre-commit.sh:91`, Stop hook in settings.json | `find .claude/plans/ -name "ops-*.json"` |
| `ops-enforcement.sh:56` allowlist | `(^|/)ops(-[^/]+)?\.json$` |

Consequences:
1. `pre-commit.sh`'s ops validation and the Stop hook's ops check match **zero files** — silently validating nothing, forever.
2. `ops-enforcement.sh` **blocks the agent from writing the project's own plan files** (`foo.ops.json` matches neither the allow-regex nor `.claude/` if plans live elsewhere) while allowing `ops-anything.json`.

**Fix:** one shared pattern, e.g. `-name "*.ops.json" -o -name "ops*.json"` and regex `(^|/)([^/]+\.)?ops(-[^/]+)?\.json$`, defined once (a small `lib.sh` sourced by hooks).

---

## 5. `.claude/hooks/` scripts

### block-no-verify.sh
- **P0 (shared):** `exit 1` + stdout instead of `exit 2` + stderr — does not block (§2).
- **P2** `line 32`: `grep -qE '\-\-no-verify'` matches the substring anywhere — a commit *message* containing "--no-verify", `npm publish --no-verify`, or a `grep -- --no-verify` command all get blocked. Scope it: only act when the command is a git invocation (`grep -qE '(^|[;&|]\s*)git\s[^;&|]*--no-verify'`).
- **P3** `set -e` plus `TOOL_INPUT=$(cat)`: if stdin is closed early, `cat` failure kills the hook with a non-zero status that Claude interprets as hook error noise.

### commit-quality.sh
- **P2 portability** `line 60`: `${COMMIT_MSG,,}` is bash 4+. macOS ships bash 3.2 (`/bin/bash`); the hook shebang is `#!/bin/bash`, so on stock macOS this line throws "bad substitution" and the generic-message check never runs. Use `tr '[:upper:]' '[:lower:]'`.
- **P2** `line 44`: the `-m` extraction regex `-m\s+["']([^"']*)["']` silently returns empty for `git commit -m "don't break"` (apostrophe), `-m msg` (unquoted), `--message=...`, or heredoc commits — so length/generic checks silently skip. Parse with `shlex` in the already-invoked python.
- **P3** `line 77`: warning regex treats `console.error` as debug noise; many codebases legitimately keep it.

### config-protection.sh
- **P2** `line 19`: pattern `tsconfig.*\.json` — the unescaped `.` after `tsconfig` is fine but `checkstyle`, `spotbugs`, `detekt` (lines 28-30) are bare substrings matched against the basename: a file named `detekt_report.md`… is exempted by the doc-extension allow in the *security-reminder*, but here `my-checkstyle-notes.json` gets blocked. Anchor the patterns.
- **P2** pyproject special-case (line 77): only exempts pyproject.toml when it lacks `[tool.ruff|black|...]` — but a *Write* to a **new** pyproject.toml has no file on disk yet (`-f` fails) → falls through to BLOCK. Creating a brand-new pyproject.toml is blocked unconditionally.
- **P0 (shared):** exit 1 not 2.

### ops-enforcement.sh
- **P1:** naming mismatch blocks the repo's own `*.ops.json` (§4).
- **P3** `line 94`: the block message itself tells the agent the bypass ("use Bash cp/sed") — an enforcement hook that documents its own hole. Bash writes aren't gated by this hook at all, so the enforcement is advisory in practice.
- **P0 (shared):** exit 1 not 2.

### pre-commit.sh
- **P1** `line 91`: `find .claude/plans/ -name "ops-*.json"` matches nothing (§4) — the "validate ops configs" step has never validated a file.
- **P2** `lines 115-128`: secret patterns embed `\x27` inside `grep -E` character classes. POSIX ERE/GNU grep does **not** support `\xNN` escapes; inside `[..."\x27]` the class becomes the literal characters `" \ x 2 7`. Net effect: single-quoted secrets (`api_key = 'abcd1234...'`) are only "caught" if by luck, and the intent is silently broken. Fix: use `grep -P` where available or write the quote directly: `pattern="api_key\\s*[:=]\\s*[\"'][^\"']{8}"` (bash double-quoted string can contain a single quote via `"'"` concatenation, or build patterns in the python helper).
- **P2** `line 141`: runs the full pattern set with `git show :$file | grep` per file per pattern — O(files × patterns) subprocesses; a single `git diff --cached -U0 | grep -iE "$combined"` is one pass.
- **P3** suggests `git commit --no-verify` as the false-positive escape hatch (line 153) while a sibling hook exists specifically to block `--no-verify`. The two hooks are at war.

### pre-push.sh / post-implement.sh
- **P2**: `run_tests`/`run_lint`/`run_build` capture output and print only `tail -20` — on failure the actual root-cause error is often above the tail. At minimum write full output to a log file and say where it is.
- **P2** duplicate code: `log()`, `get_project_config()` are copy-pasted verbatim across 6 hooks (pre-commit, pre-push, pre-plan, post-implement, post-tool-use, and inline variants). One divergence has already happened (LOG vs LOG_FILE naming, `$SCRIPT_DIR` vs relative `.claude/hooks/...` — the relative variants break if cwd ≠ repo root). Extract `.claude/hooks/lib.sh`.
- **P3** `post-implement.sh:3` has `set -e` yet the design intends to run all three steps and summarize; any unguarded command failure (e.g. `date` in log) would abort the summary. It happens to guard the main calls, but `set -e` + "continue on failure" design is fragile.

### pre-plan.sh
- **P2** `line 81`: `[ "$similarity" -ge 70 ] 2>/dev/null` — if python3 is missing, `similarity` is "0" via fallback, fine; but the whole check spawns a python per existing plan file — O(n) interpreter startups. Batch into one python call.
- **P3**: only ever warns (`return 0` always) yet is registered via a UserPromptSubmit grep pipeline in settings.json that only fires on the literal phrase "plan <name>" — very low hit rate; effectively decorative.

### session-start.sh
- **P2** `line 77` (SC2046): `basename $(pwd)` unquoted — breaks on paths with spaces. `basename "$(pwd)"`.
- **P3**: `PM_INSTALL`/`PM_RUN` computed and never used (SC2034) — dead code.
- **P3**: prints previous-session context from `.claude/session-context.md` (head -20) straight into the transcript — content is unsanitized; a poisoned context file is a prompt-injection vector the prompt-injection-scanner never sees.

### suggest-compact.sh
- **P2** `lines 23-28`: mkdir-based mutex with **no stale-lock recovery** — if the subshell dies between `mkdir` and `rmdir` (kill, crash, reboot), every future invocation exits at line 27 and the counter freezes forever, silently. Add an age check: `find "$_lock_dir" -mmin +5 -exec rmdir {} \;` before giving up.
- **P2 portability** `line 34`: `date -r "$COUNTER_FILE"` is GNU-only for files; on macOS/BSD `-r` expects epoch *seconds*, so the command fails and the `||` fallback returns *today* → `FILE_DATE == TODAY` always → the daily counter reset **never happens on macOS**. Use `stat -f %Sm -t %Y-%m-%d` (BSD) / `date -r` (GNU) branch, or python3.
- **P3**: suggestion text is echoed from a backgrounded subshell after the hook exits — depending on Claude Code's capture semantics, it likely goes nowhere.

### cost-tracker.sh
- **P2**: entirely dependent on log lines that are never written (see §2 post-tool-use finding) — `TOOL_CALLS` always 0, summary dead. Also `SESSION_LOG` declared, never used (SC2034).
- **P3**: name promises cost, measures line counts — no token/cost data is available to it; rename or drop.

### format-typecheck.sh
- **P2** `lines 29-38`: reconstructs "files edited this session" by regex-scraping *bash command text* from `bash-commands.log`. Edit/Write tool operations never pass through that log, so the primary edit path is invisible; meanwhile `grep 'foo.ts'` in a command counts as an "edit". The data source is simply wrong for the goal. Track PostToolUse Edit/Write payloads instead.
- **P2** `line 42` (SC2207): `TS_FILES=($(printf ...|sort -u))` — word-splits paths with spaces.
- **P2** `line 84`: `grep -c "error TS" "$REPORT"` counts across the whole report including format output; and `TSC_ERRORS` may be `?` then compared/printed as a number.
- **P3**: `sleep 1` as a synchronization primitive (line 27), acknowledged in comments.

### security-reminder.sh, command-log-audit.sh, desktop-notify.sh
- security-reminder **P3**: `grep -qE '\bMD5\b|\bSHA1\b'` fires on comments/docs inside source; content truncated at 3000 chars means later code is unscanned (silent partial coverage).
- command-log-audit **P3**: `LOG_FILE`/`HOOK_NAME` unused (SC2034); audit log path is relative (`.claude/hooks/...`) while sibling uses `$SCRIPT_DIR` — writes to the wrong place when cwd ≠ root.
- desktop-notify: fine; nice escaping work. **P3**: WSL PowerShell block truncates but a `$` in the project name would still expand inside the double-quoted PS template — use single-quoted args or `-EncodedCommand`.

---

## 6. templates/hooks/

### auto-checkpoint.sh — P1: data-loss and wrong-stash pruning
1. `lines 144-150`: `git stash push --include-untracked` **removes** the working tree changes; the follow-up `git stash apply 2>/dev/null || true` **silently swallows failure** (conflicts, index states, hooks). If apply fails, the user's uncommitted work has just vanished into a stash while the hook logs success. At minimum: check apply's exit, and on failure loudly print recovery instructions (`git stash pop`).
2. `line 153`: records `stash_ref="stash@{0}"` in the registry. Stash refs are a **stack** — every subsequent stash shifts indices, so the registry's refs point at the wrong stashes almost immediately, and `prune_old_checkpoints` (line 103) then **drops the wrong stash** — potentially a checkpoint you wanted, or a user's manual stash. Record the stash **commit SHA** (`git rev-parse stash@{0}`) and drop by SHA.
3. **P2** `line 91`: prune math `checkpoints[:len-max+1]` mixes "keep max" and "make room for one more" — off-by-one wart; and registry read/modify/write has no locking against concurrent hooks.
4. **P2** `line 140`: `awk '{print $2}'` on `git status --porcelain` mangles renames (`R  old -> new`) and quoted paths with spaces.

### file-guard.sh
- **P2** `lines 94-97`: blocks every `*.key`, `*.crt`, `*.pem`, `*.cert` by extension — including `public.pem`, test fixtures, and `LICENSE.key`-style false positives, with no allowlist mechanism. Category 12 `*"customer"*"data"*` blocks `customer_data_schema.sql` in a migration. Needs an exceptions file.
- **P3**: not wired into `settings.json` at all (template-only), yet `config.schema.json` documents it as a hook with "195+ patterns" — the script has ~60. Docs overpromise.

### prompt-injection-scanner.sh
- **P2**: patterns like `"you are now"`, `"act as if"`, `"developer mode"` will fire constantly on legitimate prose/tests/docs (this repo's own agent .md files contain role-play phrasing). As a blocking hook it would be unusable; as unwired template it's dormant. Needs word-boundary anchoring + context (only scan *tool results from untrusted sources*).
- **P3** `line 62`: the escaper misses `]` and `\` in patterns (currently harmless as no pattern contains them).

### check-comment-replacement.sh
- **P2** `line 39`: `raise NotImplementedError` as a "suspicious placeholder" blocks perfectly legitimate abstract-method code. Should be a warn-pattern, not part of an exit-1 set.
- **P3**: `echo -e "$violations"` (line 98) will mangle backslashes present in code lines.

---

## 7. `.claude/operations/scripts/`

This is the strongest code in the repo — atomic writes, manifests, transactional rollback, signal handling. Remaining issues:

### execute-json-ops.py
- **P2** `line 68-72` `atomic_write`: good, but the temp file mode from `mkstemp` is 0600 and `os.replace` preserves it — an edited file that was 0644 becomes 0600 after an edit, silently changing permissions. Copy the original mode (`shutil.copystat` / `os.chmod` from `stat` of target) before replace.
- **P2** `line 101` `ExecutionLock.acquire`: on Windows (`_HAS_FCNTL` False) the "lock" is just an `O_CREAT|O_TRUNC` open that always succeeds — two executors run concurrently with interleaved backups. Use `O_CREAT|O_EXCL` there so at least creation is exclusive; and `release()` unlinks the lock file even if another process now holds it (unlink-after-flock race on Unix). Standard fix: keep the lock file permanent, or use `flock` on a stable path and don't unlink.
- **P2** `line 400-402`: an edit whose `find` pattern is missing prints a note and **continues**; only if *zero* edits apply does the op fail. A 9-of-10 partial application writes the file first (line 454) and *then* returns `False` → rollback restores it — correct, but the dry-run path (line 449) returns `False, "dry-run-partial"` while a real run with the same input writes then rolls back; validator + executor disagree because the validator checks patterns against the *original* file while the executor applies sequentially. Document or pre-validate against the progressively-modified content.
- **P3** `line 204` `normalize_config` is annotated `-> dict` but returns `None` on error (`Optional[dict]`).
- **P3** `line 549+`: `file_path` from `operation.get('path', 'unknown')` — the literal string `"unknown"` can flow into `txn.record_modified`.
- **P3**: `logging` is configured (line 43) but nearly all diagnostics go through `print()`; `--verbose` only changes the level of the one `logger.warning`.

### validate-config-json.py
- **P2**: TOCTOU by design — validation reads files, then the reviewer approves, then the executor re-reads; nothing pins content (a hash per file in the ops.json would close the gap between /review approval and /implement execution).
- **P2** `line 5` (docstring) says "26 guards", epilog says 29, guards 15/27/28 don't exist anywhere — numbering fiction that will mislead maintenance.
- **P3** `line 462`: `op['path']` KeyError-safe due to the `if 'path' in op` guard — fine — but legacy conversion at line 458 does `file_op['path']` unguarded: a legacy entry missing `path` raises KeyError inside `validate_backup_compatibility` (caught nowhere — this function isn't wrapped). Malformed legacy config → traceback instead of an error message.
- **P3**: `validate_file_operations` duplicates null-byte/traversal checks that `validate_modern_format` repeats 40 lines later for `code_edit` — one path-validation helper, called everywhere.

### restore-backup.py
- **P2** `line 30`: `sys.path.insert(0, os.path.dirname(__file__))` — needed hack; the sibling scripts rely on implicit script-dir on `sys.path`. All three would be cleaner as a package (`python3 -m operations.validate ...`).
- **P3**: mixes `os.path` everywhere with a single `PurePath` import; `restored_files`-printing block is copy-pasted five times (lines 189-236) — extract a `fail(msg)` helper.
- **P3** `line 286`: `sorted(backups, reverse=True)` sorts by *name*; works only because names embed timestamps — fragile coupling to executor naming, worth a comment or sort by manifest timestamp.

### shared.py
- **P3**: `PROTECTED_PATTERNS` includes `*.md` — so `file_delete` can never remove any markdown file, including scratch notes the ops system itself generated. Intentional? Deserves a comment; also `__all__` declared before the imports it doesn't include.

---

## 8. src/security/ — dead code with real bugs

### P1 — Nothing uses this package
`grep` across the repo: `CommandValidator`/`PathGuard` are imported **only by `tests/test_security.py`**. No hook, no CLI command, no operations script touches them. The bash hooks reimplement (differently) the same checks. This is security theater: tested, documented in ARCHITECTURE.md, and never executed in production paths. Either wire it (e.g. a `claudekit check-command` entry the Bash-matcher hook calls) or delete it.

### command_validator.py
- **P1** `line 94` — **reads the wrong config section**:
  ```python
  hooks_config = config.get("hooks", {})
  safe_mode = hooks_config.get("safeMode", True)
  ```
  `config.schema.json` (lines 120-135) defines `safeMode`, `allowedCommands`, `blockedCommands` under **`security`**, not `hooks`. Any user following the schema gets their settings silently ignored — validator runs on defaults forever. Fix: `config.get("security", {})` (and add a test that round-trips the schema example).
- **P1** `line 79-87` — **allowlist is self-defeating and chaining-blind**:
  - `bash` and `sh` are in `DEFAULT_ALLOWLIST` (line 16) → `bash -c 'rm -rf /'` passes every check (base cmd `bash` allowed; `rm` never inspected).
  - Only the *first* token is checked; `echo hi && rm -rf /` passes: `&&`/`||` chaining isn't in `DANGEROUS_PATTERNS` (only `;\s*rm` and `\|.*rm`), and `rm` after `&&` is never extracted.
  - Fix: split on `;`, `&&`, `||`, `|` and validate *each* segment's base command; drop `bash`/`sh`/`env`/`xargs` from the allowlist or recurse into `-c` payloads.
- **P2** `lines 31-43` pattern false positives: `r'\$\('` bans all command substitution (breaks `echo $(date)` in legitimate configured commands — while `pre-commit.sh` itself uses it constantly); `r'source\s'` matches "open source code" appearing in an echo; `r'exec\s'` matches `git exec-path`. Patterns need word/position anchoring.
- **P3** `line 56`: return type `-> tuple` — use `Tuple[bool, str]` (or a small frozen dataclass `ValidationResult`); `List` imported and unused.

### path_guard.py
- **P2** `line 70` — **relative symlink resolved against the wrong base**:
  ```python
  link_target = Path(os.readlink(file_path)).resolve()
  ```
  `readlink` of a relative symlink returns a path relative to the **link's directory**; resolving it against the process *cwd* gives the wrong target, so the escape check both misses real escapes and flags safe links whenever cwd ≠ link dir. Use `Path(file_path).parent / os.readlink(file_path)` then `.resolve()` — or drop the block entirely, since `Path(file_path).resolve()` at line 46 already followed symlinks and the `relative_to(project_root)` check at line 52 already catches escaping targets. As written it's redundant *and* wrong.
- **P2** `line 64` — substring matching on `PROTECTED_PATTERNS`: `".env" in rel_path` blocks `my.envelope.txt`, `assets/fonts.envmap`, and any path containing `.env` anywhere; `".ssh/" in rel_path` is reasonable but `".env"` needs component-level matching (`PurePath(rel_path).name == ".env"` or fnmatch per part).
- **P3** `lines 57-60` — dead code: the path was already proven inside `project_root` (line 52), so it can only be under a SYSTEM_PATH if the project root itself is — and the prefix check `startswith("/etc")` would also match `/etcetera`. Compare path components, or delete the block.
- **P3** `line 87`: magic number `20` for depth; make it a named class constant/parameter.

---

## 9. src/cli/main.py

Compiles clean; overall reasonable structure. Issues:

- **P1** `line 53` — the error message says `Set CLAUDEKIT_HOME or run from the repo`, but **`CLAUDEKIT_HOME` is never read** anywhere (`find_claudekit_root`, lines 31-41, checks only `__file__`-relative and `~/claudekit`, `~/.claudekit`). The advertised escape hatch doesn't exist. Fix:
  ```python
  env_home = os.environ.get("CLAUDEKIT_HOME")
  if env_home and (Path(env_home) / ".claude" / "agents").exists():
      return Path(env_home)
  ```
- **P2** `line 318` (`cmd_config`): `json.loads(config_path.read_text())` unguarded — a malformed config.json produces a raw traceback instead of the `err(...)` style the rest of the CLI uses. Same for `cmd_agents` `f.read_text()` on unreadable files.
- **P2** `lines 124-137` — doctor's magic thresholds (`>= 9` agents, `>= 8` commands, `>= 27` skills) are hard-coded and already disagree with install.sh's claims (28 agents, 37 commands). Every release will silently invalidate doctor. Derive expected counts from the source tree or a manifest.
- **P2** `lines 101, 109`: `subprocess.run(["bash","--version"], ...)` with no `timeout=` and no `check` — a wedged binary hangs doctor. Add `timeout=5`.
- **P3** `lines 7, 10`: `shutil` and `time` imported, never used — dead imports.
- **P3** `lines 262-265` (`cmd_rollback`): `elif args.list: append("--list") / else: append("--list")` — the branches are identical; collapse to `else: cmd.append("--list")`.
- **P3** `lines 81-91`: `check()`'s tri-state via `condition is True` / `== "warn"` — a stringly-typed enum; any truthy non-`True` value (an accidental non-bool) is counted as *failed*. Use an Enum or three functions.
- **P3** frontmatter "parser" (lines 290-304) splits on `line.startswith("name:")` — breaks on YAML lists/multiline descriptions; fine for now, but a `description: >` folds to empty. Note as a known limitation.
- **P3** ANSI colors unconditionally emitted — respect `NO_COLOR` / `not sys.stdout.isatty()`.
- **P3** `src/__init__.py`, `src/cli/__init__.py`, `src/security/__init__.py` are empty (no version, no docstring) — fine, but `__version__` living in `main.py` and diverging from pyproject (§1) should move to `claudekit/__init__.py` sourced from metadata.

---

## 10. config.schema.json

- **P1** — **The shipped default config violates its own schema.** Root has `"additionalProperties": false` (line 138) with properties `hooks|global|project|security`; the actual `.claude/hooks/config.json` begins with a top-level `"_note"` key → instance is invalid against the schema. Also `hooks.post-tool-use` in the real config carries a `"tools"` array the schema doesn't describe (allowed only because hook objects don't set `additionalProperties: false` — inconsistent strictness).
- **P1** — **Nothing validates against it.** `grep -rn config.schema` finds zero references in any script, hook, or CLI. `doctor` parses config.json but never applies the schema; the validator applies `operations-schema.json` (a different schema) to ops files only. Either wire it (`claudekit doctor` + `jsonschema`) or stop shipping it as if enforced.
- **P2** — Schema describes hooks (`file-guard`, `prompt-injection-scanner`, `auto-checkpoint`) that exist only as unwired templates, with the "195+ patterns" claim (line 58) that the actual script (~60 patterns) doesn't meet.
- **P3** — Schema is valid JSON and valid draft-07 (checked); the `security` section it defines is exactly the section `CommandValidator.from_config` fails to read (§8) — fixing that bug makes this schema meaningful.

`operations-schema.json`: well-constructed (oneOf per op type, `additionalProperties:false`, `const` discriminators). **P3**: `delete: {"type":"boolean","const":true}` plus edit-level `oneOf` means an edit with *two* actions (`replace` + `add_after`) is correctly rejected — good — but the executor's precedence order (add_after > add_before > replace > delete, execute-json-ops.py lines 404-427) would silently pick one if schema validation is skipped (no jsonschema installed). Executor should enforce single-action too.

---

## 11. Cross-cutting observations

- **Silent-failure culture in hooks:** nearly every python3 sub-call ends in `2>/dev/null` with a bare `except: print('')`. When the JSON protocol shifts (it already has — see §2), everything degrades to no-ops with zero diagnostics. At minimum log the exception line to hooks.log instead of `/dev/null`.
- **python3 spawn count:** a single Edit tool call triggers 3 PreToolUse hooks × ~2-3 `python3 -c` spawns each, plus PostToolUse — ~10 interpreter startups (~300-500 ms) per tool call. Consolidate to one python invocation per hook that extracts all fields at once (or use `jq` when present).
- **Copy-paste `log()`/`get_project_config()`/JSON-extractor blocks** across 10+ hooks — extract `.claude/hooks/lib.sh`.
- **Log paths inconsistent:** some hooks use `$SCRIPT_DIR/hooks.log`, others the cwd-relative `.claude/hooks/hooks.log` — with cwd ≠ root these are different files; cost-tracker greps one while other hooks write the other.
- **Version strings:** 5 locations, 4 values (§1).

---

## 12. Modernization recommendations

1. **Packaging (do first):** `build-backend = "setuptools.build_meta"`; rename package `src` → `claudekit` with proper src-layout; single-source the version. Without this nothing else is installable.
2. **argparse → Typer or Click?** The CLI is 7 flat subcommands with simple flags — argparse is honestly adequate and zero-dep. If you want richer UX (rich help, shell completion, colorized errors), **Typer** is the better fit here (type-hint-driven, function-per-command maps 1:1 onto the existing `cmd_*` functions). Click if you want to stay decorator-minimal without pydantic-ish typing. Tradeoff: both add a runtime dependency to a tool whose selling point is "drop into any repo" — a reasonable middle path is keeping argparse but adding `rich` only for doctor output. Recommendation: stay argparse until the package installs cleanly; then Typer.
3. **Type hints:** replace `-> tuple` with `-> Tuple[bool, str]` (or `tuple[bool, str]` once you drop 3.8 — note requires-python 3.8 EOL'd 2024-10; bump to `>=3.9`). Add `from __future__ import annotations`. Run mypy in CI.
4. **Dataclasses:** `ValidationResult(ok: bool, reason: str)`, `Operation`, `CheckpointEntry`, and doctor's `CheckResult` are all natural `@dataclass(frozen=True)` candidates replacing tuple-and-string plumbing.
5. **pathlib:** `restore-backup.py` and `validate-config-json.py` are os.path-heavy with pathlib imported but barely used; standardize on `Path` (also fixes several string-prefix path comparisons — `Path.is_relative_to()` exists on 3.9+, replacing the `startswith(cwd + os.sep)` idiom in three files).
6. **logging framework:** replace `print()` diagnostics in operations scripts with a module-level `logging` config (`--verbose` → DEBUG, default INFO, `-q` → WARNING); hooks should append structured lines via one shared helper instead of 12 hand-rolled `log()`s.
7. **Hook consolidation:** one dispatcher script (`hook-router.sh` or better a single python entry point) registered per event, reading the JSON once and fanning out — fixes the spawn-count, the stdin protocol drift, and the exit-code semantics in one place.
8. **CI:** add `shellcheck`, `bash -n`, `python -m build` (would have caught the P0), `pytest`, and a settings.json↔hooks-on-disk consistency check.

---

## Top Bugs (ranked)

| # | Sev | File:Line | Bug |
|---|-----|-----------|-----|
| 1 | P0 | pyproject.toml:3 | Build backend `setuptools.backends._legacy:_Backend` doesn't exist — `pip install` fails; package has never been installable |
| 2 | P0 | block-no-verify.sh:46, ops-enforcement.sh:96, config-protection.sh:91, commit-quality.sh:133 | "Blocking" hooks use `exit 1` + stdout; Claude Code only blocks on `exit 2` + stderr — no enforcement hook actually blocks |
| 3 | P1 | install.sh (absent) | `.claude/settings.json` never installed into target projects — all 15 hooks are copied but never registered/executed |
| 4 | P1 | install.sh:94-101 | ERR trap `rm -rf "$DEST"` deletes user's pre-existing `.claude/` on any mid-install failure, with no backup/restore |
| 5 | P1 | pre-commit.sh:91, settings.json Stop hook, ops-enforcement.sh:56 vs `.claude/plans/*.ops.json` | Ops filename split-brain: hooks search `ops-*.json`, repo ships `*.ops.json` — ops validation never runs; enforcement blocks the project's own plan files |
| 6 | P1 | settings.json PostToolUse; post-tool-use.sh:14 | Hook fed `$CLAUDE_TOOL_NAME/RESULT/ARGS` env vars that Claude Code never sets (protocol is stdin JSON) — tool tracking, ops revalidation, and cost-tracker are all dead |
| 7 | P1 | templates/hooks/auto-checkpoint.sh:144-153, 101 | `stash push` + silently-swallowed `stash apply` can wipe uncommitted work; `stash@{0}` refs recorded then drift → prune drops the wrong stashes |
| 8 | P1 | src/security/command_validator.py:94 | `from_config` reads `hooks.safeMode` but config.schema.json defines it under `security` — user security config silently ignored; plus `bash`/`sh` allowlisted and `&&` chaining unchecked defeat the validator entirely (and the whole module is dead code — nothing imports it) |
| 9 | P1 | pyproject.toml:29-40 | Installs top-level `src` package with `src.cli.main` entry points — global namespace collision |
| 10 | P1 | config.schema.json:138 vs .claude/hooks/config.json:2 | Shipped config violates shipped schema (`_note` vs `additionalProperties:false`); nothing anywhere validates against config.schema.json |
| 11 | P2 | pre-commit.sh:115-128 | `\x27` escapes inside `grep -E` classes are not ERE — single-quoted secrets silently not detected |
| 12 | P2 | commit-quality.sh:60 | `${VAR,,}` requires bash 4 — breaks on stock macOS `/bin/bash` 3.2 |
| 13 | P2 | src/security/path_guard.py:70 | Relative symlink targets resolved against cwd instead of link dir — wrong verdicts both ways |
| 14 | P2 | suggest-compact.sh:23-34 | No stale-lock recovery (counter freezes forever after one crash); `date -r FILE` is GNU-only → daily reset never fires on macOS |
| 15 | P2 | install.sh:306-337 | sed templating breaks (mid-install, triggering destructive trap #4) when commands contain `|` or `&` |
| 16 | P2 | src/cli/main.py:53 | Error text tells users to set `CLAUDEKIT_HOME`; the variable is never read |
| 17 | P2 | execute-json-ops.py:67-73 | atomic_write leaves edited files with mkstemp's 0600 mode — silent permission change on every edit |
| 18 | P2 | config-protection.sh:77 | Writing a *new* pyproject.toml always blocked (file-existence check precedes the lint-section exemption) |

## Top Refactors (ranked)

| # | Impact | Refactor |
|---|--------|----------|
| 1 | High | Fix packaging: `setuptools.build_meta`, rename `src` → `claudekit` (true src-layout), single version source, declare `jsonschema` extra — unblocks everything else |
| 2 | High | Single hook dispatcher: one entry per event reading stdin JSON once, correct exit-2 blocking semantics, shared logging — replaces 12 copy-pasted `log()`/`get_project_config()`/python3-extractor blocks and cuts ~10 interpreter spawns per tool call to 1 |
| 3 | High | Wire or delete `src/security/` — if kept: read the `security` config section, validate every command segment (`;`, `&&`, `||`, `|`), drop `bash`/`sh` from the allowlist, expose as `claudekit check-command` called from the Bash PreToolUse hook |
| 4 | High | install.sh: install/generate settings.json per mode; backup-and-restore rollback instead of `rm -rf`; explicit `CLAUDE_SRC` guard (curl\|bash message); `--yes` for non-interactive; clean-dir install for idempotency |
| 5 | Med | One canonical ops-file naming pattern (`*.ops.json`) defined in a shared lib and used by pre-commit, Stop hook, ops-enforcement, and docs |
| 6 | Med | Operations scripts → a package (`python3 -m claudekit.ops ...`): kills the `sys.path` hack, deduplicates path-validation logic between validator/executor, and lets the CLI import instead of shelling out |
| 7 | Med | Type hints + dataclasses across src/ (`Tuple[bool,str]` → `ValidationResult`), `Path.is_relative_to` instead of `startswith(cwd + os.sep)` (3 files), mypy in CI |
| 8 | Med | doctor: derive expected agent/command/skill counts from a generated manifest instead of magic numbers (9/8/27); validate config.json against config.schema.json here |
| 9 | Med | Replace `print`-based diagnostics in operations scripts with `logging`; hooks stop `2>/dev/null`-ing their python helpers and log parse failures |
| 10 | Low | CLI: optional Typer migration + `NO_COLOR`/TTY-aware colors; remove dead imports (`shutil`, `time`), collapse duplicate rollback branches |
| 11 | Low | Renumber/rename the "GUARD n" scheme (15/27/28 missing, counts wrong in three docstrings) or drop the numbering for named guards |
| 12 | Low | auto-checkpoint: record stash SHAs not `stash@{0}`, verify `stash apply`, lock the registry |

---

## Code Quality Score: 54 / 100

**Why not lower:** the operations scripts (execute/validate/restore) show genuine engineering care — atomic writes, manifests, transactional rollback, signal handling, thoughtful guard rails — and shell quoting/escaping discipline is above average (`bash -n` and ShellCheck come back nearly clean).

**Why not higher:** the package does not install (P0), the enforcement layer — the product's core promise — does not enforce (P0 exit-code semantics), the installer never wires the hooks it installs and can destroy user config on failure, the security module is dead code with real bypasses, and at least five features (ops validation, tool tracking, cost tracking, config-schema validation, post-tool-use) are silently non-functional due to wiring/naming drift. The pattern of `2>/dev/null` + bare `except` means every one of these failures was invisible.
