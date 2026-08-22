# Code-Review Triage — `review/code-review.md`

**Triaged:** 2026-08-20 · **Tree:** branch `perf/token-efficiency` @ `c167298` ·
**Original review:** 2026-07-05 (46 days and ~90 commits stale)

Every verdict below was produced by reading or executing the current tree. Line numbers in
the original review are stale and are not reproduced; the `Now` column is the current
`file:line`. The original stays untouched as the historical record.

---

## State in ten seconds

| | Count | Share |
|---|---:|---:|
| **Total findings** | **108** | 100% |
| **LIVE** — still reproducible today | **53** | 49% |
| **FIXED** — verified gone, with proof | **49** | 45% |
| **OBSOLETE** — the code no longer exists | **5** | 5% |
| **UNVERIFIABLE** | **1** | 1% |

Findings are the 103 discrete findings in §1–§10 of the review — the original uses
unnumbered bullets and prose, so the `F1`–`F103` identifiers are this triage's enumeration,
not the review's — plus the 5 cross-cutting observations in §11, enumerated `F104`–`F108`. §12 ("Modernization recommendations") and the Top Bugs / Top Refactors
tables are restatements of the same items and are not counted twice.

**Severity of what is still LIVE:** zero P0. One finding (`F57`) carries the original
review's P1 label, but that label rests on a "wipes uncommitted work" claim the current tree
does not support — see F57, where it is re-characterised as silent-success-on-failed-restore
with a conditional loss path. On the evidence, **every LIVE finding is P2/P3.** Every P0 and
every P1 from the 2026-07-05 review is fixed. What remains is the long tail — which is
exactly the tail that produced yesterday's executable-bit incident.

**The calibration case.** `F67` (`atomic_write` leaves 0600) was P2, documented with the fix
spelled out, and ignored for 46 days. On 2026-08-19 it stripped the exec bit from
`install.sh`, `.claude/hooks/ops-enforcement.sh` and `scripts/gen-docs.py`; two shipped in
`d878496` before an incidental `git log --diff-filter=M --summary` caught it. Repaired in
`7ac7ca6`, root-caused in `4c57198`. **A P2 with a written fix is not a low-risk finding.
It is an unexploded one.** Read the Priority column below with that in mind.

---

## Legend

- **Status:** `FIXED` · `LIVE` · `OBSOLETE` · `UNVERIFIABLE`
- **Class:** recurrence class per `.ai/REVIEW_GUIDE.md`. `NEW:` marks a class this triage adds.
- **Pri:** `P-now` (fix this round) · `P-next` (fix when the area is next touched) ·
  `P-log` (record, no action) · `P-decide` (owner decision, not an engineering call).
- **triv** in the Priority line means the fix is a one-or-two-line change. Per the
  workstream constraint, none of them were made here.

---

## §1 — `pyproject.toml` (4 findings: 4 FIXED)

| ID | Finding | Status | Now / Evidence |
|---|---|---|---|
| F1 | P0 build backend `setuptools.backends._legacy` does not exist | FIXED | `pyproject.toml:3` = `build-backend = "setuptools.build_meta"` |
| F2 | P1 installs top-level `src` package | FIXED | Tree is `src/claudekit/**`; `pyproject.toml:43-44` `where = ["src"]`; entry points `claudekit.cli.main:main` (`:32-34`) |
| F3 | P2 five version strings, four values; dead `setuptools-scm` | FIXED | `pyproject.toml:7`, `src/claudekit/__init__.py:8`, `.claude/operations/scripts/shared.py:3`, `install.sh:9` all `2.1.0`; no `setuptools-scm` in `requires` |
| F4 | P3 metadata polish (PEP 639 license, jsonschema extra, 3.13, dev extras) | FIXED | `pyproject.toml:10` `license = "MIT"` with no `License ::` classifier; `:22` 3.13; `:28-30` `validation` + `dev` extras |

---

## §2 — `.claude/settings.json` hook wiring (4 findings: 3 FIXED, 1 OBSOLETE)

| ID | Finding | Status | Now / Evidence |
|---|---|---|---|
| F5 | P0 blocking hooks `exit 1` + stdout, so nothing blocks | FIXED | `grep -n 'exit 1' .claude/hooks/*.sh` returns only the explanatory comment at `lib.sh:71`. Blocking goes through the shared `deny()` helper (exit 2 + stderr) |
| F6 | P1 `post-tool-use.sh` reads `$CLAUDE_TOOL_*` env vars Claude Code never sets | FIXED | `post-tool-use.sh:16` `TOOL_NAME=$(extract_json_field "$TOOL_INPUT" tool_name)` — stdin JSON. Cascade also closed: `:25` writes the `[INFO] Tool:` marker that `cost-tracker.sh:26` counts |
| F7 | P1 `ROOT` may be empty → hook paths become `/.claude/hooks/...` | FIXED | Every `settings.json` command now `ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null \|\| pwd)}"` |
| F8 | P2 Stop-hook inline unquoted `$(find ...)` loop | OBSOLETE | The inline ops loop no longer exists in `settings.json` `Stop` (now: reflection-gate, cost-tracker, desktop-notify, format-typecheck). The surviving ops scan moved to `pre-commit.sh:120`, which uses `done < <(find ...)` — no word splitting |

---

## §3 — `install.sh` (11 findings: 8 FIXED, 3 LIVE)

| ID | Finding | Status | Now / Evidence |
|---|---|---|---|
| F9 | P1 `settings.json` never installed → hooks never registered | FIXED | `install.sh:281-286` copies it; `:295-342` fails closed if `settings.json` wires a hook file that was not installed |
| F10 | P1 ERR trap `rm -rf "$DEST"` destroys pre-existing `.claude/` | FIXED | `install.sh:111-122`: writes to `STAGING="$TARGET_DIR/.claude.staging.$$"`, `mv "$STAGING" "$FINAL_DEST"` at `:518`, `trap - ERR` at `:520`. The trap can now only delete the staging dir |
| F11 | P2 `curl \| bash` fails unsafely | FIXED | `install.sh:14` guards `[[ ! -d "$CLAUDE_SRC" ]]`; `:50,80,94,126` add `--yes` and `[[ -t 0 ]]` TTY detection |
| F12 | P2 not idempotent with `--force`; stale files survive | FIXED | Staging-dir install (`:111-112`) is a clean tree by construction; `:506-509` deliberately carries `settings.local.json` forward |
| F13 | P2 sed templating breaks on `\|` or `&` | FIXED | Templating is python3, not sed: `:435` `CK_TPL_IN=... python3 -c`, `:489`, `:523`, `:556` |
| F14 | P2 hard-coded summary numbers vs computed counts | FIXED | `:636` prints `${AGENT_COUNT}` etc., computed at `:186` |
| F15 | P3 `ls \| grep \| wc` (SC2010) | **LIVE** | `install.sh:186` still `ls -1 ... \| grep -v -E ... \| wc -l`. ShellCheck 0.11 does not flag this variant (`shellcheck install.sh` is clean), so the lint gate will never catch it. **Class:** cosmetic. **Pri:** P-log, triv — works correctly; only fails on newlines in filenames, which cannot occur in `agents/*.md` |
| F16 | P3 banner prints after language detection | **LIVE** | `install.sh:170` `LANGUAGE=$(detect_language)` precedes `:174 print_banner`. **Class:** cosmetic. **Pri:** P-log, triv |
| F17 | P3 kotlin detection misclassifies Java projects using the Kotlin Gradle DSL | **LIVE** | `install.sh:146` still `[[ -f build.gradle.kts ]] && grep -q "kotlin" build.gradle.kts`. Every Kotlin-DSL file contains the string "kotlin"; a Java project using `build.gradle.kts` is installed as kotlin. **Class:** NEW `unanchored-pattern`. **Pri:** P-next — user-visible wrong config, but recoverable with `--language` |
| F18 | P3 `TARGET_DIR` silently keeps a relative path if `cd` fails | FIXED | `install.sh:103` now `... \|\| { print_err "Cannot access target directory"; exit 1; }` |
| F19 | P3 no uninstall path, no manifest | FIXED | Manifest written at `install.sh:523`; `ck uninstall` at `src/claudekit/cli/main.py:577-610` (backs up before removing) |

---

## §4 — Ops filename split-brain (1 finding: 1 FIXED)

| ID | Finding | Status | Now / Evidence |
|---|---|---|---|
| F20 | P1 three components disagree on `ops-*.json` vs `*.ops.json` | FIXED | Single definition in `.claude/hooks/lib.sh:26-28`: `OPS_FIND_EXPR=('(' -name '*.ops.json' -o -name 'ops-*.json' ')')` and `OPS_REGEX='(^\|/)([^/]+\.ops\.json\|ops(-[^/]+)?\.json)$'`. Consumed by `pre-commit.sh:120` and `ops-enforcement.sh:90` |

---

## §5 — `.claude/hooks/` (36 findings: 18 FIXED, 15 LIVE, 3 OBSOLETE)

### FIXED (18) — verified

| ID | Finding | Now / Evidence |
|---|---|---|
| F21 | block-no-verify `exit 1` | uses shared `deny()`; no `exit 1` in file |
| F22 | block-no-verify substring match on `--no-verify` | `block-no-verify.sh:28` anchored: `(^\|[;&\|]\|[[:space:]])git[[:space:]][^;&\|]*--no-verify`; `:24` documents the commit-message case |
| F24 | commit-quality `${VAR,,}` is bash 4+ | `commit-quality.sh:58` `\| tr '[:upper:]' '[:lower:]' \|` |
| F25 | commit-quality `-m` regex misses apostrophes/`--message=`/heredoc | `commit-quality.sh:37-38` extracts via python3, not regex |
| F28 | config-protection blocks creating a new `pyproject.toml` | `config-protection.sh:43-46` explicitly exempts a brand-new file with no tool sections |
| F29 | config-protection `exit 1` | shared `deny()` |
| F30 | ops-enforcement blocks the repo's own `*.ops.json` | `ops-enforcement.sh:90` uses `OPS_REGEX` (F20) |
| F32 | ops-enforcement `exit 1` | shared `deny()` |
| F33 | pre-commit ops scan matched zero files | `pre-commit.sh:120` uses `OPS_FIND_EXPR` |
| F34 | pre-commit `\x27` inside `grep -E` classes is not ERE | `pre-commit.sh:145` carries the fix and a comment naming the old bug |
| F36 | pre-commit suggests `--no-verify` while a sibling hook blocks it | `pre-commit.sh:188` now says "do NOT bypass with --no-verify (block-no-verify blocks it)" |
| F42 | session-start `basename $(pwd)` unquoted | `session-start.sh:77` `basename "$(pwd)"` |
| F43 | session-start `PM_INSTALL`/`PM_RUN` dead (SC2034) | 18 references in the file; no longer dead |
| F45 | suggest-compact mkdir mutex with no stale-lock recovery | `suggest-compact.sh:28` `find "$_lock_dir" -maxdepth 0 -mmin +1 -exec rmdir {} \;` before giving up |
| F46 | suggest-compact `date -r FILE` is GNU-only → daily reset never fires on macOS | `suggest-compact.sh:38` comment + date stored *inside* the counter file (`:14` writes `"$TODAY $COUNT"`), removing the mtime dependency entirely |
| F48 | cost-tracker `TOOL_CALLS` always 0 | fixed as a cascade of F6; `post-tool-use.sh:25` writes the marker `cost-tracker.sh:26` greps |
| F50 | format-typecheck scrapes bash command text for "edited files" | `format-typecheck.sh:13-14,26` now reads `.claude/hooks/edited-files.log`, appended by `post-tool-use.sh` on PostToolUse Edit/Write |
| F56 | desktop-notify `$` expands inside the WSL PowerShell template | `desktop-notify.sh:54-60`: values sanitised with `tr -d "'"`, interpolated into PowerShell **single-quoted** strings (which do not expand), and `$` in the PS template is backslash-escaped from bash |

### OBSOLETE (3)

| ID | Finding | Evidence |
|---|---|---|
| F23 | block-no-verify `set -e` + `TOOL_INPUT=$(cat)` kills the hook on early stdin close | `grep -n '^set ' .claude/hooks/block-no-verify.sh` returns nothing — the script no longer sets `-e` |
| F26 | commit-quality warns on `console.error` | `grep -n 'console\.' commit-quality.sh` → only `:71` (comment) and `:82` (message), both scoped to `console.log`/`debugger`. `console.error` is not in the pattern set |
| F31 | ops-enforcement's block message documents its own bypass ("use Bash cp/sed") | `grep -n 'cp \|sed \|bypass' ops-enforcement.sh` returns nothing in the deny text. Note the *substance* survives: Bash writes are still ungated by this hook — that is now an accepted design property (open decision 21), not an unfixed finding |

### LIVE (15)

**F27 — config-protection: unanchored basename substrings** · `config-protection.sh:17-19`
`PROTECTED_PATTERNS` still contains the bare substrings `'checkstyle' 'spotbugs' 'detekt'`
alongside anchored siblings like `'\.eslintrc'`. `my-checkstyle-notes.json` is blocked;
so is any file whose name merely contains `detekt`.
**Class:** NEW `unanchored-pattern`. **Pri:** P-next, triv — false-positive blocks on a
blocking hook are the worst kind of friction, but the affected names are rare.

**F35 — pre-commit secret scan is O(files x patterns) subprocesses** · `pre-commit.sh:174`
`for pattern in "${patterns[@]}"` inside a per-staged-file loop (`:134` collects the files).
One `git diff --cached -U0 \| grep -iE "$combined"` would be a single pass.
**Class:** cosmetic/perf. **Pri:** P-next — pure latency on the commit path.

**F37 — `tail -20` hides the root cause** · `post-implement.sh:98,130`, `pre-push.sh:150,183,216`
Five sites still print only the last 20 lines of captured tool output; compiler and test
errors are usually above the tail, and the full output is not written anywhere.
**Class:** NEW `silent-failure`. **Pri:** P-now, triv — this is a diagnosability bug in the
exact hooks a developer consults when something fails. Cheapest high-value item in this list.

**F38 — `log()`/`get_project_config()` duplication only half-migrated** · `.claude/hooks/`
`lib.sh` exists (the fix landed), but only **9 of 19 consumer hooks** source it.
`grep -l 'lib\.sh' .claude/hooks/*.sh` returns 10 paths, one of which is `lib.sh` itself; of
the 20 `.sh` files in the directory, 19 are potential consumers. The other 10 still carry
their own `log()` / `get_project_config()` copies, so a divergence can reappear.
**Class:** `duplicate-asset`. **Pri:** P-next — half a refactor is a trap: the next
maintainer will assume `lib.sh` is authoritative.

**F39 — `post-implement.sh:3` `set -e` fights the "run all three steps" design** · confirmed
`grep -n '^set ' post-implement.sh` → `3:set -e`. Any unguarded command failure aborts the
summary the hook exists to print.
**Class:** NEW `silent-failure`. **Pri:** P-next, triv.

**F40 — pre-plan spawns a python3 per existing plan file** · `pre-plan.sh:69`
The similarity call is inside the per-plan loop. With ~40 plans in `.claude/plans/` that is
40 interpreter startups on a UserPromptSubmit hook.
**Class:** cosmetic/perf. **Pri:** P-next.

**F41 — pre-plan can never fail** · `pre-plan.sh:81-86`
Warns and returns 0 unconditionally, and is triggered by a `settings.json` grep on the
literal phrase "plan <name>". A gate that cannot fail is not a gate.
**Class:** `vacuous-check`. **Pri:** P-decide — either give it teeth or delete it; keeping a
decorative gate is what the review guide's `vacuous-check` row exists to stop.

**F44 — session-start pipes unsanitised `.claude/session-context.md` into the transcript** ·
`session-start.sh:133,151` (`head -20 "$CONTEXT_FILE" \| sed 's/^/  /'`). A poisoned context
file is injected at session start, before any scanner sees it; `injection-scan-gate.sh` runs
on tool results, not on this path.
**Class:** NEW `unwired-artifact` (a scanner exists but does not cover this surface).
**Pri:** P-now — this is the only LIVE finding with a security shape. Low likelihood
(requires local write access), but the mitigation already exists and is simply not applied here.

**F47 — suggest-compact's suggestion is echoed from a backgrounded subshell after exit** ·
`suggest-compact.sh` (background `&` in the `settings.json` Stop entry)
Output written after the hook returns is very likely discarded by Claude Code.
**Class:** `vacuous-check`. **Pri:** P-log — UNVERIFIED in the strict sense: confirming it
needs a live Claude Code session capturing hook stdout timing, which this triage did not run.

**F49 — `cost-tracker.sh` measures line counts, not cost** · `cost-tracker.sh:26-40`
It now works (F48), but it counts hook-log lines. No token or cost data is available to it.
The name promises something it structurally cannot deliver.
**Class:** cosmetic/naming. **Pri:** P-decide — rename to `session-tracker` or drop.

**F51 — format-typecheck word-splits paths (SC2207)** · `format-typecheck.sh:45`
`IFS=$'\n' TS_FILES=($(printf '%s\n' "${TS_FILES[@]}" \| sort -u))`. `IFS=$'\n'` makes this
newline-safe in practice, so the space case is handled — but it is still an unquoted command
substitution into an array and breaks the moment `IFS` handling is edited.
**Class:** NEW `unsafe-word-split`. **Pri:** P-log, triv — currently correct by accident.

**F52 — `grep -c "error TS"` counts the whole report; `TSC_ERRORS` may be `"?"`** ·
`format-typecheck.sh:88` `TSC_ERRORS=$(grep -c "error TS" "$REPORT" 2>/dev/null \|\| echo "?")`,
then interpolated into `TSC_RESULT="fail:${TSC_ERRORS}_errors"`. The report also contains
formatter output, so the count is over-broad, and `"?"` flows into a numeric-looking field.
**Class:** NEW `silent-failure`. **Pri:** P-next, triv.

**F53 — `sleep 1` as a synchronisation primitive** · `format-typecheck.sh:30`
Acknowledged in the file's own comment. Racy under load, and adds a fixed second to every Stop.
**Class:** cosmetic. **Pri:** P-log.

**F54 — security-reminder: unanchored crypto keywords + silent 3000-char truncation** ·
`security-reminder.sh:55` (`print(inp[key][:3000])`) and `:81`
(`grep -qE '\bMD5\b\|\bSHA1\b\|\bRC4\b'`). Two distinct problems in one hook: the keyword
fires on comments and documentation, and anything past 3000 characters is never scanned at
all, with no indication that coverage was partial.
**Class:** NEW `unanchored-pattern` + NEW `silent-failure` (the truncation is the more
serious half). **Pri:** P-now for the truncation — a scanner that silently stops scanning is
the "coverage that isn't" failure mode this whole triage exists to surface.

**F55 — command-log-audit writes to a cwd-relative path** · `command-log-audit.sh:10`
`AUDIT_LOG=".claude/hooks/bash-commands.log"` while `:9` correctly uses
`LOG_FILE="$SCRIPT_DIR/hooks.log"`. When cwd is not the repo root the audit trail is written
somewhere else, or nowhere. (The SC2034 half of the finding is fixed: `LOG_FILE` and
`HOOK_NAME` are both used now.)
**Class:** NEW `silent-failure`. **Pri:** P-now, triv — an audit log that lands in the wrong
directory is the same class of "looks like coverage" liability as the review file itself.

---

## §6 — `templates/hooks/` (10 findings: 1 FIXED, 8 LIVE, 1 UNVERIFIABLE)

**Wiring changed since the review.** `file-guard.sh` and `prompt-injection-scanner.sh` are
no longer dormant: `.claude/hooks/file-guard-gate.sh` and `.claude/hooks/injection-scan-gate.sh`
wrap them and are registered in `settings.json` (2 references). Both gates are advisory
(`exit 0` always) and gated to `ECC_HOOK_PROFILE=strict`. This **raises** the priority of the
false-positive findings below, because the patterns now run against real input.

| ID | Finding | Status | Now / Evidence · Class · Pri |
|---|---|---|---|
| F57 | P1 (original label) `git stash push` then silently-swallowed `git stash apply` | **LIVE, severity corrected** | `templates/hooks/auto-checkpoint.sh:165` is still `git stash apply 2>/dev/null \|\| true`, and `:153` has already cleared the working tree. If apply fails, the hook logs success while the tree is unexpectedly clean. **The original review's "can wipe uncommitted work" framing is NOT supported by the current tree:** the stash created at `:153` still exists, its SHA is captured at `:162` and recorded in the registry, so the work is recoverable via `git stash list` / `git stash pop`. This is silent-success-on-failed-restore, not data loss. **Class:** NEW `silent-failure` (not a data-loss class). **Pri:** **P-now on diagnosability grounds** — a user whose tree silently empties has no signal telling them to look in the stash, and the hook's own log says it succeeded. **Conditional escalation:** a genuine loss path exists only if the un-applied stash is later pruned before the user notices — `prune_old_checkpoints` (`:65-91`) drops the oldest entries once `MAX_CHECKPOINTS` is reached and resolves by SHA (`:107`), so an unrecovered checkpoint CAN be dropped. That path requires `MAX_CHECKPOINTS` further checkpoints between the failed apply and the user noticing. It is real but conditional, and is argued here rather than asserted |
| F58 | P1 `stash@{0}` recorded, refs drift, prune drops the wrong stash | FIXED | `auto-checkpoint.sh:160-168`: `stash_sha=$(git rev-parse "stash@{0}")` captured immediately, `stash_ref="$stash_sha"`; `:107` resolves the SHA back to a position at prune time. The comment at `:159-161` names the original bug |
| F59 | P2 prune off-by-one + unlocked registry read/modify/write | **LIVE** | `auto-checkpoint.sh:~91`: `pruned = checkpoints[:len(checkpoints) - max_cp + 1]` still mixes "keep max" with "make room for one more"; `grep -n 'flock\|lock' auto-checkpoint.sh` finds no locking. **Class:** cosmetic (off-by-one) + NEW `silent-failure` (lost update). **Pri:** P-next |
| F60 | P2 `awk '{print $2}'` on `git status --porcelain` mangles renames and quoted paths | **LIVE** | `auto-checkpoint.sh:149`. `R  old -> new` yields `old`; quoted paths with spaces truncate. Display-only (feeds `files_list`), so no data impact. **Class:** NEW `unsafe-word-split`. **Pri:** P-log |
| F61 | P2 file-guard blocks by extension with no exception mechanism | **LIVE** | `templates/hooks/file-guard.sh:95` `cert\|crt\|pem\|key\|p12\|pfx)` matches `public.pem` and test fixtures; `:125` `*"customer"*"data"*` matches `customer_data_schema.sql`. **Class:** NEW `unanchored-pattern`. **Pri:** P-next — now advisory-wired (see above), so it produces noise rather than blocks |
| F62 | P3 not wired, yet documented as a hook with "195+ patterns" | **LIVE (half)** | Wiring half is FIXED (`file-guard-gate.sh`, registered). Doc half stands: `config.schema.json:58,64` still claim "195+ patterns" and the script has nowhere near that. **Class:** NEW `unwired-artifact` / doc overpromise. **Pri:** P-next, triv |
| F63 | P2 injection-scanner phrases fire on legitimate prose | **LIVE** | `prompt-injection-scanner.sh:34,42,50` — `"you are now"`, `"developer mode"`, `"act as if"` unanchored. This repo's own agent `.md` files contain exactly this phrasing. Now reachable via `injection-scan-gate.sh`. **Class:** NEW `unanchored-pattern`. **Pri:** P-next |
| F64 | P3 pattern escaper misses `]` and `\` | **UNVERIFIABLE** | The claim is conditional ("currently harmless as no pattern contains them"). Confirming or refuting requires enumerating the escaper's behaviour against a pattern containing `]`/`\`, which none currently do — so the bug is latent by construction and cannot be observed without first adding such a pattern. **To verify:** add a `]`-containing pattern to the array and run the scanner against a matching payload. **Pri:** P-log |
| F65 | P2 `raise NotImplementedError` treated as a suspicious placeholder | **LIVE** | `check-comment-replacement.sh:39` `'^\+.*raise\s+NotImplementedError'` is in the exit-1 set. Abstract methods are legitimate. **Class:** NEW `unanchored-pattern`. **Pri:** P-next — template-only, unwired, so contained |
| F66 | P3 `echo -e "$violations"` mangles backslashes in code lines | **LIVE** | `check-comment-replacement.sh:98`. **Class:** cosmetic. **Pri:** P-log, triv |

---

## §7 — `.claude/operations/scripts/` (14 findings: 2 FIXED, 12 LIVE)

This section contains the highest-value LIVE findings in the document.

### F67 — `atomic_write` mode preservation · **FIXED** (the calibration case)

`execute-json-ops.py:106-122`. `atomic_write` now takes an explicit `mode`, falls back to
`current_mode(file_path)`, then `DEFAULT_CREATE_MODE` for new files, and re-applies
`stat.S_IMODE` (including setuid/setgid/sticky) to the temp file before `os.replace`. The
docstring at `:110-115` states the invariant and justifies preserving the high bits.

Commit `4c57198` "fix(ops): preserve file modes across every engine write path" — the message
names the three damaged files and the two commits that shipped the damage (`d878496`, repaired
in `7ac7ca6`), and the fix covers *every* write path, not just the one line the review cited.

**This is what a closed finding looks like:** a commit that names the finding, the mechanism,
the observed damage, the blast radius, and the invariant now enforced.

### F68 — `ExecutionLock` is a no-op on Windows and unlinks other holders' locks · **LIVE**

`execute-json-ops.py:161-172` and `:183-186`.

```
self._fd = os.open(self.lock_path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC)
if _HAS_FCNTL:
    fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
```

Two distinct defects, both exactly as the review described:

1. **Windows (`_HAS_FCNTL` False):** the open is `O_CREAT|O_WRONLY|O_TRUNC`, not `O_EXCL`.
   It always succeeds. `acquire()` returns True for every caller, so two executors run
   concurrently and interleave their backup directories — the transactional-rollback promise
   silently does not hold.
2. **Unix:** `release()` (`:183-186`) calls `os.unlink(self.lock_path)` unconditionally after
   dropping the flock. A second process that has already opened the same path and is waiting
   on / holds the flock ends up holding a lock on an unlinked inode; a third process creates a
   fresh file and acquires "the" lock. Classic unlink-after-flock race.

**Class:** NEW `platform-divergence` (defect 1) + NEW `silent-failure` (defect 2).
**Pri:** **P-now** for defect 1 — `O_EXCL` on the non-fcntl branch is a one-line change that
restores mutual exclusion. Defect 2 needs a design decision (keep the lock file permanent, or
verify inode identity before unlinking) → **P-decide**.

### F69 — Validator and executor disagree about what a valid config is · **LIVE (partly fixed)**

The review reported this as "the dry-run path returns `dry-run-partial` while a real run
writes then rolls back; validator and executor disagree because the validator checks patterns
against the *original* file while the executor applies sequentially."

**The half that is FIXED:**
- Partial application is gone. `execute-json-ops.py:686-697` now fails fast: `occurrences == 0`
  → `return False, "pattern-not-found"`; `occurrences > 1` → `return False, "ambiguous-pattern"`.
  No more 9-of-10 writes.
- Sequential simulation landed. `validate-config-json.py:270-329` threads a `sim` variable
  through the edit list and re-applies each edit to the simulated content
  (`:318-327`), so GUARD 10 and GUARD 11 see the progressively-modified text. The specific
  original/sequential mismatch the review named is closed.

**The half that is LIVE, and is now larger than the review realised.** The two components
still disagree — just at different seams. Confirmed by execution, not by reading:

**Instance 1 — unknown edit fields.** `operations-schema.json:173` sets
`additionalProperties: false` on the edit object. The executor's edit loop
(`execute-json-ops.py:678-729`) tests only for known keys and ignores everything else.

```
$ cat ops-unk.json
{"plan":"x","operations":[{"type":"code_edit","path":"f.txt",
  "edits":[{"find":"hello","replace":"HI","bogus_field":"z"}]}]}

$ validate-config-json.py ops-unk.json
-> REJECTED
$ execute-json-ops.py ops-unk.json --dry-run
  Edit 1: Replaced pattern with 2 chars
RESULT-JSON: {... "status": "success" ...}
```

**Instance 2 — multi-action edits.** The schema's edit-level `oneOf` rejects an edit carrying
both `replace` and `add_after`. The executor's `if/elif` chain
(`execute-json-ops.py:699-722`) silently picks by precedence — `add_after` wins, `replace` is
discarded with no warning.

```
$ cat ops-multi.json
{"plan":"x","operations":[{"type":"code_edit","path":"f.txt",
  "edits":[{"find":"hello","replace":"HI","add_after":"XX"}]}]}

$ validate-config-json.py ops-multi.json
- Schema validation failed: ... is valid under each of
  {'required': ['replace']}, {'required': ['add_after']}
-> REJECTED
$ execute-json-ops.py ops-multi.json --dry-run
RESULT-JSON: {... "status": "success" ...}
```

**Amplifier (not a third seam) — the two seams above become undetectable when `jsonschema`
is absent.** `jsonschema` is an *optional* extra (`pyproject.toml:28`).
`validate-config-json.py`'s `validate_against_schema` returns `True, []` when it is missing,
and instances 1 and 2 are caught **only** by the schema. So on a machine without the extra,
the validator approves a config it would otherwise reject.

The validator **does** warn. `validate-config-json.py:864-866` prints it, and the full,
unedited transcript is:

```
$ PYTHONPATH=./shim validate-config-json.py ops-multi.json   # shim makes `import jsonschema` fail
Warning: jsonschema library not installed - schema validation skipped
Install with: pip install jsonschema

Validating: ops-multi.json

  JSON syntax valid
  All required fields present
  All file paths valid
  All find patterns exist in files

-> APPROVED

$ echo $?
0
```

**Correction of record.** An earlier draft of this triage asserted the validator "prints no
indication that schema validation was skipped" and showed a transcript with the warning
absent. That transcript was produced by a `tail -8` that cut the warning off, and the prose
around it was wrong. The tree could not have produced it. The claim is retracted here and the
full output is shown above. A document written because the original review was trusted
without verification cannot itself contain evidence the tree does not reproduce.

**The real defect is sharper: the warning is cosmetic.** It goes to stdout ahead of the
verdict and changes nothing downstream. The verdict text (`:896`) is still the bare
`-> APPROVED` and the exit code (`:897`) is still `0`. Every machine consumer — the reviewer
agent parsing the verdict line, a hook or CI job branching on `$?`, `pre-commit.sh:120`'s ops
scan — sees an unqualified pass on a config the schema forbids. The human-readable warning is
the only thing carrying the degradation, and it is the one channel nothing reads.

**Class:** `vacuous-check` (the guard set silently shrinks while the verdict stays green).
**Pri:** **P-now.** Reflect the degraded state where it is consumed: emit
`-> APPROVED (DEGRADED: schema guards skipped)` and either exit non-zero or gate the degraded
path behind an explicit opt-in flag, so a caller cannot mistake a partial run for a full one.
Do **not** re-add a warning `print` — that work is already done.

**Seam count.** Instances 1 and 2 are genuine, distinct divergences between two independently
maintained rule sets. The `jsonschema` case is not a third seam; it is what makes the first
two invisible. `validator-executor-divergence` therefore stands at **2 confirmed seams — one
short of the ratchet threshold.** The remedy below is warranted anyway on severity grounds
(a config the validator rejects executes successfully), but it is being recommended by
judgement, not earned by the ratchet, and this document should not pad a count to pretend
otherwise.

**Remedy.** Make the executor enforce single-action edits and reject unknown edit keys, so the
two components agree by construction rather than by two rule sets that must be kept in sync
by hand.

### Remaining §7 findings

| ID | Finding | Status | Now / Evidence · Class · Pri |
|---|---|---|---|
| F70 | P3 `normalize_config` annotated `-> dict`, returns `None` on error | **LIVE** | `execute-json-ops.py:272` `def normalize_config(config: dict) -> dict:` with `None` returns; `:914` handles `config-normalize-failed`, so the caller knows — the annotation lies. `mypy` covers only `src/claudekit` (`pyproject.toml:57` — `:56` is `ignore_missing_imports`), so ops scripts are untyped territory. **Class:** NEW `type-contract-drift`. **Pri:** P-next, triv |
| F71 | P3 literal `"unknown"` path can flow into `txn.record_modified` | **LIVE** | `execute-json-ops.py:1053` `file_path = operation.get('path', 'unknown')`. A sentinel string in a path slot. **Class:** NEW `type-contract-drift`. **Pri:** P-next, triv |
| F72 | P3 `logging` configured but diagnostics go through `print()` | **LIVE** | `logging.basicConfig` at `:53`, `--verbose` at `:1203`; 117 `print(` calls vs 5 `logger.` calls (`:684,691,696,729`). `--verbose` changes almost nothing. **Class:** cosmetic. **Pri:** P-log |
| F73 | P2 validator TOCTOU: nothing pins file content between /review and /implement | FIXED | `validate-config-json.py:746-780` records `sha256:` of every existing target into a `baseline` block; `--record-baseline` at `:855`; the executor checks drift and reports `MISSING (was <hash>...)` at `execute-json-ops.py:332`. Note it is **opt-in**, not automatic — if the pipeline never passes `--record-baseline`, the gap is open. Worth an owner decision on making it default (**P-decide**) |
| F74 | P2 guard-numbering fiction: docstring says 26, epilog says 29, guards 15/27/28 absent | **LIVE (half)** | Count half FIXED: docstring `:12` says 31 and exactly 31 distinct `GUARD n` tokens exist. Gap half LIVE: the numbering runs 1-14, 16-26, 29-34 — 15, 27 and 28 are still missing, so "GUARD 34" implies 34 guards. Nothing checks this. **Class:** `hardcoded-count`. **Pri:** P-next, triv — either renumber densely or drop numbers for names |
| F75 | P3 legacy-format conversion does `file_op['path']` unguarded → traceback | **LIVE** | `validate-config-json.py:487`, `:647`, `:771` all index `file_op['path']` with no `KeyError` guard; `validate_backup_compatibility` is called at `:880` outside any try. A malformed legacy config produces a traceback instead of an error message. **Class:** NEW `silent-failure` (inverted — fails loudly with a traceback instead of an error message; same class as F91, and counted in it). **Pri:** P-next, triv |
| F76 | P3 null-byte/traversal path checks duplicated between `validate_file_operations` and `validate_modern_format` | **LIVE** | Confirmed by reading both paths; GUARD 26 null-byte logic appears in the edit loop (`:291-296`) and again for file ops. **Class:** `duplicate-asset`. **Pri:** P-next |
| F77 | P2 `sys.path.insert(0, dirname(__file__))` hack | **LIVE** | `restore-backup.py:30`. All three ops scripts still rely on implicit script-dir imports of `shared`. Reproduced incidentally during this triage: `exec()`-ing the validator from another cwd fails with `ModuleNotFoundError: No module named 'shared'`. **Class:** cosmetic/architecture. **Pri:** P-next — blocked behind the "ops scripts become a package" refactor (Top Refactor #6) |
| F78 | P3 `restored_files`-printing block copy-pasted five times | **LIVE** | 12 occurrences of `restored_files` in `restore-backup.py`. **Class:** `duplicate-asset`. **Pri:** P-log |
| F79 | P3 `sorted(backups, reverse=True)` sorts by name, coupling to executor naming | **LIVE** | `restore-backup.py:306`. Works only because names embed timestamps; no comment records the coupling. **Class:** cosmetic. **Pri:** P-log, triv (add the comment or sort by manifest timestamp) |
| F80 | P3 `PROTECTED_PATTERNS` includes `*.md`, so `file_delete` can never remove a markdown file | **LIVE** | `shared.py:16`. Still undocumented as intentional — the comment at `:12-13` is generic ("Add project-specific patterns as needed"). Consequence: the ops engine cannot delete scratch notes it generated itself. **Class:** N/A. **Pri:** **P-decide** — this is a policy question (hard rule 4 protects protected files), not a bug. Whatever the answer, it deserves one sentence in the file |

---

## §8 — `src/claudekit/security/` (9 findings: 9 FIXED)

The review's harshest section is now its cleanest. Every finding is closed.

| ID | Finding | Status | Now / Evidence |
|---|---|---|---|
| F81 | P1 nothing imports the package — security theatre | FIXED | Wired three ways: `.claude/hooks/command-guard.sh:49-57` (Bash PreToolUse), `.claude/hooks/pre-push.sh:47-53`, and the `ck check-command` / `ck check-path` CLI (`src/claudekit/cli/main.py:704,710,810-811,841`). `python3 -m claudekit.security` fallback exists for uninstalled trees |
| F82 | P1 `from_config` reads `hooks.safeMode`; schema defines it under `security` | FIXED | `command_validator.py:228-229` `sec = config.get("security", {}) or {}` / `sec.get("safeMode", True)`; docstring `:225-226` names the section; round-tripped by `tests/test_security.py:50` |
| F83 | P1 `bash`/`sh` allowlisted and `&&` chaining unchecked | FIXED | `DEFAULT_ALLOWLIST` (`:18-26`) contains no shell interpreter or launcher. `_SEPARATORS` (`:89`) covers `; && \|\| \| & \|& \n`; `_split_segments` (`:157`) validates each segment (`:140-141`); `-c` payloads are recursed into (`:126`). Matches hard rule "no allowlist additions of shell interpreters" |
| F84 | P2 dangerous-pattern false positives (`$(`, `source\s`, `exec\s`) | FIXED | `DANGEROUS_PATTERNS` (`:47-61`) is now position-anchored: `(?:^\|[\s;&\|(])eval\b`, `(?:^\|[\s;&\|(])exec\b`. Blanket `\$\(` and bare `source\s` are gone; redirects are targeted at device/system paths |
| F85 | P3 `-> tuple` bare annotation, unused `List` import | FIXED | `command_validator.py:104` `-> Tuple[bool, str]`, `:188` likewise; `List` is used by `_split_segments` (`:157`) |
| F86 | P2 relative symlink target resolved against cwd | FIXED | `path_guard.py:87-91`: `raw_target = os.readlink(...)`, absolute → `Path(raw_target).resolve()`, relative → `(Path(file_path).parent / raw_target).resolve()`. Comment at `:84-86` names the original bug |
| F87 | P2 substring matching on `PROTECTED_PATTERNS` (`.env` matches `my.envelope.txt`) | FIXED | `path_guard.py:79-81` delegates to `self._matches_protected(pattern, rel_path)`; comment at `:78` says "at component granularity" |
| F88 | P3 dead SYSTEM_PATH block; `startswith("/etc")` matches `/etcetera` | FIXED | `path_guard.py:73-74` `resolved_str == sys_path or resolved_str.startswith(sys_path + os.sep)` — separator-anchored, so `/etcetera` no longer matches. Comment at `:71` says "component-anchored" |
| F89 | P3 magic number `20` for depth | FIXED | `path_guard.py:14` `MAX_DIRECTORY_DEPTH = 20` |

---

## §9 — `src/claudekit/cli/main.py` (9 findings: 2 FIXED, 7 LIVE)

| ID | Finding | Status | Now / Evidence · Class · Pri |
|---|---|---|---|
| F90 | P1 error text names `CLAUDEKIT_HOME`, which is never read | FIXED | `main.py:55-60`: `env_home = os.environ.get("CLAUDEKIT_HOME")` is now first in the resolution order; docstring `:55` documents it |
| F91 | P2 unguarded `json.loads(config_path.read_text())` in `cmd_config` | **LIVE** | `main.py:722`. A malformed `config.json` produces a raw traceback instead of the `err(...)` style used everywhere else. **Class:** NEW `silent-failure` (inverted). **Pri:** P-next, triv |
| F92 | P2 doctor's magic thresholds `>= 9` / `>= 8` / `>= 27` | **LIVE** | `main.py:202,208,215`. The repo now ships 29 agents, 42 commands, 75 skills (`CLAUDE.md:7`), so a doctor run passes with a third of the tree missing. `scripts/gen-docs.py --check` regenerates counts in *docs* but does not touch `main.py`, so the drift gate does not cover this. **Class:** `hardcoded-count`. **Pri:** **P-now** — this is `hardcoded-count` living in the one place the `hardcoded-count` gate does not look, and `ck doctor --strict` is a Definition-of-Done command |
| F93 | P2 `subprocess.run` with no `timeout=` | **LIVE** | `main.py:172` (`bash --version`), `:187` (`git --version`). A wedged binary hangs doctor indefinitely. **Class:** NEW `silent-failure`. **Pri:** P-next, triv (`timeout=5`) |
| F94 | P3 dead `shutil` / `time` imports | FIXED | `shutil` is used (1 call site); no `import time` / `time.` usage remains — timestamps go through `datetime` (`:605`) |
| F95 | P3 identical `elif args.list` / `else` branches in `cmd_rollback` | **LIVE** | `main.py:370-372` — both append `--list`. **Class:** cosmetic. **Pri:** P-log, triv |
| F96 | P3 `check()` stringly-typed tri-state | **LIVE** | `main.py:152-162`: `if condition is True` / `elif condition == "warn"` / `else`. Any truthy non-`True` value is silently counted as a *failure* — a doctor check returning `1` or a non-empty list reports red. **Class:** NEW `type-contract-drift`. **Pri:** P-next — a latent false-negative generator inside the health command |
| F97 | P3 frontmatter "parser" splits on `line.startswith("name:")` | **LIVE** | `main.py:~290-304` unchanged in shape. `description: >` folded blocks yield empty. **Class:** cosmetic. **Pri:** P-log — acceptable, but the limitation should be a comment |
| F98 | P3 ANSI colours emitted unconditionally | **LIVE** | `grep -n 'NO_COLOR\|isatty' main.py` returns nothing. Piping `ck doctor` into a file or CI log embeds escape codes. **Class:** cosmetic. **Pri:** P-next, triv — CI log readability |

---

## §10 — `config.schema.json` (5 findings: 4 LIVE, 1 OBSOLETE)

### F99 — The shipped default config violates the shipped schema · **LIVE**, proven

```
$ python3 -c "import json,jsonschema; jsonschema.validate(
      json.load(open('.claude/hooks/config.json')),
      json.load(open('config.schema.json')))"
INVALID: Additional properties are not allowed ('_note' was unexpected)
```

`config.schema.json` root sets `additionalProperties: false` with properties
`['hooks','global','project','security']`; `.claude/hooks/config.json:2` opens with `_note`.
**Class:** NEW `unwired-artifact`. **Pri:** **P-now, triv** — either add `_note` to the schema
or drop the key. Shipping a config that fails its own schema is a five-second fix that has
been LIVE for 46 days precisely because nothing runs the check (F100).

### F100 — Nothing validates against `config.schema.json` · **LIVE**

```
$ grep -rn 'config.schema' --include='*.py' --include='*.sh' .
setup.py:4                                  # packaging comment
setup.py:54                                 # ships it in the wheel
tests/test_security.py:50                   # comment only
src/claudekit/security/command_validator.py:226   # docstring only
```

Zero executable references. The schema is shipped, documented, and enforced by nothing —
which is why F99 survived. `ck doctor` parses `config.json` but never applies the schema.
**Class:** `vacuous-check` + NEW `unwired-artifact`. **Pri:** **P-now** — this is the single
highest-leverage LIVE finding in the document, because fixing it (validate in `ck doctor`,
`jsonschema` already an optional extra) mechanically closes F99 and F101 as well.

### Remaining §10 findings

| ID | Finding | Status | Now / Evidence · Class · Pri |
|---|---|---|---|
| F101 | P2 schema describes template-only hooks and claims "195+ patterns" | **LIVE** | `config.schema.json:58,64` both still say "195+ patterns"; `templates/hooks/file-guard.sh` has roughly 60. The wiring half improved (F62): `file-guard` and `prompt-injection-scanner` now run advisory via gates, `auto-checkpoint` remains template-only. **Class:** `hardcoded-count` + doc overpromise. **Pri:** P-next, triv — replace the number with a description, or generate it |
| F102 | P3 the `security` section the schema defines is the one `CommandValidator` fails to read | OBSOLETE | The premise is gone: `command_validator.py:228` reads `security` correctly (F82). What remains of the observation is F100 (the schema is still unwired), already counted |
| F103 | P3 executor should enforce single-action edits, since schema validation can be skipped | **LIVE** | Confirmed by execution — this is F69 Instance 2 seen from the schema side, not a separate seam. `execute-json-ops.py:699-722` precedence chain picks `add_after` over `replace` with no warning. **Class:** NEW `validator-executor-divergence` (instance 2 of 2). **Pri:** **P-now** |

---

## §11 — Cross-cutting observations (5: 1 FIXED, 4 LIVE)

| ID | Observation | Status | Now / Evidence · Class · Pri |
|---|---|---|---|
| F104 | Silent-failure culture: `2>/dev/null` + bare `except` everywhere | **LIVE** | `grep -c '2>/dev/null' .claude/hooks/*.sh`: `pre-commit.sh` 10, `session-start.sh` 10, `format-typecheck.sh` 8, `suggest-compact.sh` 6, `cost-tracker.sh` 6, `pre-push.sh` 6, `desktop-notify.sh` 6, `pre-plan.sh` 5, and so on — 89 across 20 hooks. Encouragingly, the blocking hooks are the cleanest (`block-no-verify.sh` 0, `file-guard-gate.sh` 0, `injection-scan-gate.sh` 0). **Class:** NEW `silent-failure`. **Pri:** **P-now for the scoped version** — not "remove all 89", but "no `2>/dev/null` on a call whose failure changes the hook's verdict." F52, F55, F57 and F93 are all instances |
| F105 | ~10 python3 interpreter startups per tool call | **LIVE** | Reduced but not solved: `lib.sh` provides a shared `extract_json_field`, so each hook extracts fields in fewer spawns, but three PreToolUse hooks still each spawn at least one python3, plus PostToolUse. **Class:** cosmetic/perf. **Pri:** P-next — subsumed by Top Refactor #2 (single dispatcher) |
| F106 | `log()` / `get_project_config()` copy-pasted across 10+ hooks | **LIVE** | Same evidence as F38: `lib.sh` exists, 9 of 19 consumer hooks source it (the 10th `grep -l` hit is `lib.sh` itself). **Class:** `duplicate-asset`. **Pri:** P-next — finish the migration or the divergence returns |
| F107 | Log paths inconsistent (`$SCRIPT_DIR/hooks.log` vs cwd-relative) | **LIVE** | `grep -h 'LOG_FILE=' .claude/hooks/*.sh \| sort -u` → two forms: `"$SCRIPT_DIR/hooks.log"` (7 hooks) and `"${LOG_FILE:-$ROOT/.claude/hooks/hooks.log}"` (2 hooks, via `lib.sh`). These resolve to the same file in a normal install; they diverge if the hooks directory is symlinked or relocated. The genuinely broken case is `command-log-audit.sh:10` (F55), whose `AUDIT_LOG` is cwd-relative. **Class:** `duplicate-asset`. **Pri:** P-next |
| F108 | Version strings: 5 locations, 4 values | FIXED | Same evidence as F3. Hard rule 7's three locations plus `install.sh:9` all read `2.1.0` |

---

## Recurrence classes

Counted over **LIVE findings only** — a fixed finding does not justify a gate.

| Class | LIVE | Status against the ratchet | Instances |
|---|---:|---|---|
Every count below is the length of its own Instances list. A finding may appear in two
classes where it genuinely has two defects (F54, F100); those are noted, not hidden.

| Class | LIVE | Status against the ratchet | Instances |
|---|---:|---|---|
| **NEW** `silent-failure` | **12** | **THRESHOLD CROSSED** | F37, F39, F52, F54, F55, F57, F59, F68, F75, F91, F93, F104 |
| **NEW** `unanchored-pattern` | **6** | **THRESHOLD CROSSED** | F17, F27, F54, F61, F63, F65 |
| `duplicate-asset` (existing) | **5** | **THRESHOLD CROSSED** (again) | F38, F76, F78, F106, F107 |
| **NEW** `unwired-artifact` | **4** | **THRESHOLD CROSSED** | F44, F62, F99, F100 |
| `vacuous-check` (existing) | **3** | **THRESHOLD CROSSED** (again) | F41, F47, F100 |
| **NEW** `type-contract-drift` | **3** | **THRESHOLD CROSSED** | F70, F71, F96 |
| `hardcoded-count` (existing) | **3** | **THRESHOLD CROSSED** — see note | F74, F92, F101 |
| **NEW** `validator-executor-divergence` | 2 | **below threshold** — see note | F69 instance 1 (unknown edit fields), F69 instance 2 / F103 (multi-action edits) |
| **NEW** `unsafe-word-split` | 2 | below threshold | F51, F60 |
| **NEW** `platform-divergence` | 1 | below threshold *now* — see note | F68. Historically 3 (F24 bash-4, F46 `date -r`, F68); two are fixed |
| cosmetic (no class) | 14 | n/a | F15, F16, F35, F40, F49, F53, F66, F72, F77, F79, F95, F97, F98, F105 |

**Seven classes cross the three-entry threshold** — `silent-failure`, `unanchored-pattern`,
`duplicate-asset`, `unwired-artifact`, `vacuous-check`, `type-contract-drift`,
`hardcoded-count`. Per `.ai/REVIEW_GUIDE.md`, each owes either a mechanical check or a written
"cannot be mechanised, and here is why". That is the next section.

> **`hardcoded-count` — verdict: threshold crossed, check owed.** All three instances are
> LIVE. F74 is "LIVE (half)": the count half is fixed (the docstring now says 31 and 31 guard
> tokens exist), but the *numbering-gap* half stands — the sequence runs 1-14, 16-26, 29-34,
> so 15, 27 and 28 are absent and "GUARD 34" implies 34 guards. A half-fixed finding whose
> remaining half is independently reproducible counts as LIVE, so the class stands at 3.
> What makes this row unusual is that the class already *has* a mechanical check
> (`scripts/gen-docs.py --check`) and recurred anyway: `gen-docs.py:28-34` limits `DRIFT_FILES`
> to five docs files and never scans `src/claudekit/cli/main.py:202,208,215`,
> `config.schema.json:58,64`, or the validator's guard numbering. The check is not weak, its
> *scope* is narrow. Widening it is cheaper than building a new gate.

> **`validator-executor-divergence` — verdict: below threshold, remedy recommended anyway.**
> An earlier draft counted three instances by treating the missing-`jsonschema` case as a
> third seam. It is not: it is the condition under which seams 1 and 2 become undetectable,
> and it is already classed as `vacuous-check` in its own right. Counting it twice would have
> manufactured a ratchet trigger. The honest count is 2. The remedy in F69 is still
> recommended — a config the validator rejects executing successfully is severe on its own
> merits — but it is recommended by judgement, and this row does not claim the ratchet
> compelled it.

> **`platform-divergence` — verdict: below threshold on LIVE count, check still owed.**
> Judging it by LIVE count alone would retire a class
> that has produced three real bugs. Two of them (macOS bash 3.2, BSD `date -r`) are now
> covered by CI running on macOS; the third (F68, Windows `fcntl`) is covered by nothing,
> because CI has no Windows runner. That asymmetry is the finding.

---

## What should have caught this

For every LIVE finding: the gate that could have caught it mechanically, or an honest
statement that it could not. **This section is the input to the next round of work.**

**How to read the two tables.** "Widen an existing gate" and "build a new gate" are very
different pieces of work, and conflating them is how an earlier draft of this document
inflated its own headline number. They are separated here, and each row's finding IDs are
disjoint so the totals can be checked by counting.

### A. Existing gate, scope change only — **13 LIVE findings**

Findings: **F38, F51, F60, F69, F70, F71, F74, F92, F99, F100, F101, F106, F107.**

| Gate | Would catch | Change required |
|---|---|---|
| **`ck doctor` (+ the already-optional `jsonschema`)** | **F99, F100, F101** | Validate `.claude/hooks/config.json` against `config.schema.json` in `cmd_doctor`. The highest-leverage single change in the document: it closes three LIVE findings and turns a shipped-but-inert schema into a gate. `jsonschema` is already declared under the `validation` extra, so this adds no dependency |
| **`scripts/gen-docs.py --check` (widen `DRIFT_FILES`)** | **F92, F74** | `gen-docs.py:28-34` lists five docs files and nothing else, so `src/claudekit/cli/main.py:202,208,215` and the validator's guard numbering are outside its reach. Extend it to fail on any hand-typed component count in the tree, doctor thresholds included |
| **`validate-config-json.py` (verdict + exit code)** | **F69** (the `jsonschema`-absent amplifier) | The warning already exists at `:864-866`; what is missing is propagation. Make `:896` emit `-> APPROVED (DEGRADED: schema guards skipped)` and `:897` exit non-zero or require an explicit opt-in flag, so callers parsing the verdict or `$?` cannot mistake a partial run for a full one |
| **`mypy` (widen `files`)** | **F70, F71** | `pyproject.toml:57` sets `files = ["src/claudekit"]`. The operations engine — the most consequential code in the repo — is untyped territory. Adding `.claude/operations/scripts/` would catch `-> dict` returning `None` immediately |
| **`shellcheck` (raise severity / add directives)** | **F51, F60** | Both are word-splitting issues that shellcheck 0.11 does not flag in their current form. `shellcheck -S style` plus explicit `# shellcheck disable` justifications where the pattern is intentional |
| **`ck doctor --strict` self-check** | **F38, F106, F107** | Assert every `.claude/hooks/*.sh` sources `lib.sh`. Currently 9 of 19 consumers do. A one-line check that makes the half-finished refactor visible instead of leaving it as a trap |

### B. New gate required — **8 LIVE findings**

Findings: **F37, F52, F55, F57, F68, F93, F103, F104.**

| Proposed gate | Would catch | Notes |
|---|---|---|
| **CI job: `hook-diagnosability`** | **F37, F52, F55, F93, F104** | Grep-level and genuinely new: fail if a hook writes to a cwd-relative log path (F55), if `2>/dev/null` appears on a command whose exit status feeds a conditional (F104, F52), if output is truncated with `tail -N` and not also written to a log (F37), or if `subprocess.run` in `src/` omits `timeout=` (F93). Crude, but all five are syntactically detectable |
| **`tests/test_ops_parity.py` (differential test)** | **F103** (and F69 seams 1-2) | For a corpus of configs, assert `validator_verdict == executor_would_apply`. The durable fix is to delete the second rule set — both components importing one `edit_is_valid(edit)` helper — but until then this is the cheapest thing that makes the class mechanical |
| **`_HAS_FCNTL=False` unit test** | **F68** | Monkeypatch `_HAS_FCNTL` to False and assert two `ExecutionLock.acquire()` calls cannot both return True. Cheaper than a Windows CI runner and catches the same defect |
| **Behavioural test for `auto-checkpoint`** | **F57** | Force `git stash apply` to fail (dirty index / conflicting change) and assert the hook reports failure rather than logging success. A standard regression test that does not exist for no reason other than that nobody wrote it |
| **CI job: mode-change audit** | *(no LIVE finding — recurrence guard for F67)* | The `git log --diff-filter=M --summary` audit that caught the exec-bit incident ran **incidentally, once, by hand**. Make it a job: fail if a commit changes a file's mode without the diff touching that file's content. This gates the recurrence of the finding that commissioned this workstream |

### Not mechanisable — and why

| Finding | Why no gate can catch it |
|---|---|
| **F41** (pre-plan can never fail), **F47** (output from a backgrounded subshell), **F49** (cost-tracker measures the wrong thing) | These are *purpose* mismatches, not defects. Each script does exactly what its code says; the problem is that what it says is not worth doing. No static or dynamic check can distinguish "a gate that correctly always passes" from "a gate that is broken open" without knowing the intent. **These need an owner decision, not a gate.** Judgement is the mechanism |
| **F61, F63, F65, F27, F17, F54** (unanchored patterns) | A checker cannot know that `detekt_report.md` is not a detekt config, or that `"act as if"` in an agent prompt is legitimate. The false-positive *rate* is measurable, though: a corpus test — run every classifier over this repo's own tree and assert zero hits on known-good files — converts an unmeasurable judgement into a measurable regression. That is the mechanisable half, and it is worth building because `unanchored-pattern` is the largest LIVE class |
| **F80** (`*.md` in `PROTECTED_PATTERNS`) | A policy choice colliding with hard rule 4. There is no correct answer a check could enforce; there is only a decision that should be written down |
| **F73** (baseline hashing is opt-in) | Whether content-pinning should default to on is a pipeline design decision. Once decided, it is trivially enforceable |
| **F64** | Latent by construction — the bug cannot manifest until a pattern containing `]` or `\` is added. A check would have to predict a future edit |
| **F97, F98, F95, F15, F16, F53, F66, F72, F79** (cosmetic) | Mechanisable in principle (linters exist for most), but the cost of the gate exceeds the cost of the defect. Recorded, not gated. This is a deliberate call, not an oversight |

### The meta-finding

Of the 53 LIVE findings, **21 are mechanically catchable** — and the split matters more than
the total:

- **13** need only a **scope change to a gate that already exists**: F38, F51, F60, F69, F70,
  F71, F74, F92, F99, F100, F101, F106, F107.
- **8** need a **new gate**: F37, F52, F55, F57, F68, F93, F103, F104.
- The remaining **32** are judgement calls, cosmetic, or policy decisions — see the
  not-mechanisable table above.

An earlier draft of this section claimed "at least 31 catchable by a gate that already
exists". That figure was not supported by its own table: it summed both categories and then
rounded up. The corrected figure is 13, and the ID list above is what produces it.

The substance survives the correction, and it is the most useful thing in this document.
Five existing gates each stop one directory short of the defects they were built to catch:
`gen-docs.py:28-34` lists five docs files and never scans `main.py`; `pyproject.toml:57`
scopes `mypy` to `src/claudekit` and leaves the operations engine untyped; `ck doctor` never
applies the schema it ships; `shellcheck` runs at default severity; and the mode-preservation
audit that caught the incident behind this workstream has never been run twice.

**Widening the scope of five existing gates closes 13 of the 53 LIVE findings — more than any
new tooling on the list, at a fraction of the cost.** That is the recommendation.

And the finding behind the finding: the reason F67 sat for 46 days is that nothing in this
repo tracked whether a review finding had been actioned. This file is the first artifact that
does. It is only worth writing if it is re-run — the triage should be regenerated (or its
LIVE set re-verified) whenever `review/code-review.md` is superseded, otherwise it becomes the
same liability the original became: coverage-shaped, and stale.

---

## Appendix — verification method and sampling disclosure

**Disclosure of method, per finding class.** This triage had shell access and used it. Of the
108 verdicts:

- **9 rest on EXECUTION** — a command was run and its output is quoted: F69 (3 config runs,
  plus the `jsonschema`-shim run), F99, F103, F15/F51/F60 (via `shellcheck`), F77
  (`ModuleNotFoundError` reproduced incidentally).
- **~30 rest on COMMAND OUTPUT that is not a full behavioural reproduction** — `grep -n`,
  `grep -c`, `sed -n` and `git log`/`git show`. These confirm that a line is present or absent
  in the current tree; they do **not** prove the surrounding runtime behaviour. Every FIXED
  verdict in §5 and §8 is of this kind.
- **The remainder rest on READING** the current source of the cited file.
- **2 are not verified at all** and say so: F64 and the runtime half of F47.

**The distinction matters and is not cosmetic.** A `grep` proving `tr '[:upper:]' '[:lower:]'`
is present at `commit-quality.sh:58` is strong evidence that F24 is fixed, but it is not the
same as running the hook on macOS bash 3.2. Where a verdict would change if the runtime
behaviour differed from what the source implies, it is marked LIVE rather than FIXED. A
maintainer acting on a FIXED verdict in §5 or §8 should expect to re-verify behaviourally
before removing any compensating control.

**What was NOT done:** no test suite was run; no hook was executed end-to-end under Claude
Code; no installer run was performed against a real target directory. Verdicts touching
installer behaviour (F9-F19) are source-reading verdicts.

Every FIXED verdict cites a current `file:line` or a commit. Every LIVE verdict was
reproduced by reading the current file or by executing the code:

- **Executed:** `validate-config-json.py` and `execute-json-ops.py` against three
  purpose-built configs (unknown field, multi-action edit, and both under a shimmed
  `ImportError` for `jsonschema`) — the F69/F103 evidence.
- **Executed:** `jsonschema.validate(config.json, config.schema.json)` — the F99 evidence.
- **Executed:** `shellcheck install.sh .claude/hooks/*.sh templates/hooks/*.sh` — clean on
  `.claude/hooks/`, two SC2155 in templates, nothing on `install.sh`. This is what
  established that F15, F51 and F60 are LIVE but *invisible to the lint gate*.
- **Executed:** `grep -c`/`grep -n` counts for every claim of the form "still present in N
  places".
- **Read:** the current source of every file named in a finding; no verdict rests on the
  original review's prose.

Not verified, and stated as such: **F64** (latent by construction) and the runtime half of
**F47** (needs a live Claude Code session to observe hook-stdout capture timing).

**Corrections applied after review.** Four defects were found in this document's synthesis
layer and are fixed above, each in place rather than silently: a fabricated transcript for the
`jsonschema`-absent case (F69 — the validator does warn, at `:864-866`; the earlier transcript
was a `tail -8` artifact and the surrounding prose was wrong); an inflated meta-count (31 →
13 existing-gate findings, with the ID list that produces it); a self-contradicting
`hardcoded-count` row (now 3 LIVE, threshold crossed, stated once); and an inflated F57
severity (data loss → silent-success-on-failed-restore, with the conditional loss path argued
explicitly). The classification layer was independently sampled at 20 findings across
LIVE/FIXED/OBSOLETE and returned 20/20 correct; the defects were confined to synthesis. That
asymmetry is itself worth recording: per-finding verification held up, and the errors entered
where individual findings were aggregated into counts and claims.
