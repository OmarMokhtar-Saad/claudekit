# ClaudeKit — Security Review (Security Engineer)

**Date:** 2026-07-05
**Scope:** `install.sh`, `src/security/*`, `.claude/hooks/`, `templates/hooks/`, `.claude/settings.json`, agents/skills/commands prompt surface, `SECURITY.md`, `.gitignore`, `templates/mcp/`, GitHub Actions.
**Method:** static read + live execution of hooks and installer, git history checks.
**Cross-refs:** `review/code-review.md` (P0 build backend, `\x27` secret-regex bug), `review/testing-review.md` (`src/security/*` is dead code, unbounded deletions).

## Threat model (who / what / how)

ClaudeKit is (a) a shell installer users are told to `git clone && ./install.sh` (README:44-48) and (b) a bundle of markdown prompts + bash hooks that run **with the user's full shell privileges** every time an agent uses a tool. The trust boundaries that matter:

1. **Installer → user's machine.** Arbitrary file writes into a target dir the user names, plus `.gitignore` mutation. No sudo, no network fetch (good), but destructive-overwrite and cleanup paths are risky.
2. **Agent tool-call → hooks.** Every `PreToolUse`/`PostToolUse`/`Stop` fires bash that shells out to `python3`, `git`, `grep`. Untrusted content (file paths, bash commands, tool output, git diffs) flows into these hooks.
3. **Untrusted repo content → agent.** Prompt-injection via files the agent reads, and the framework's own prompts telling the agent to run `--dangerously-skip-permissions`.
4. **Advertised security layer that does not run.** `src/security/command_validator.py` + `path_guard.py` are the marketed defense; nothing imports them.

Severity: **High** = exploitable / real damage or a security promise that is false. **Med** = weakens posture, needs a precondition. **Low** = hardening / hygiene.

---

## 1. The advertised security layer is dead code — High

`src/security/command_validator.py` (`CommandValidator`, allowlist/blocklist/`DANGEROUS_PATTERNS`) and `src/security/path_guard.py` (`PathGuard`, system-path + traversal + symlink checks) are **never imported by any running component**. Grep across `install.sh`, `.claude/hooks/*.sh`, `src/cli/main.py`, and settings returns zero references (confirmed in testing-review: referenced only by `test_security.py` and `docs/ARCHITECTURE.md`). `docs/ARCHITECTURE.md:535` even advertises a "Blocklist check → Block: rm -rf /, sudo rm, eval, curl|bash" pipeline that **does not execute**.

Impact: users reading the docs believe commands are validated against an allowlist and paths are sandboxed to the project root. Neither happens at runtime. This is the single most important finding: a **false security guarantee**.

Fix: either (a) wire a `PreToolUse` Bash hook that pipes the tool command through `CommandValidator.validate()` and a path hook through `PathGuard.validate_path()` and blocks on failure (`exit 1`), or (b) delete the modules and the doc claims. Do not ship marketed-but-inert security. If wiring it, note the bypasses below must be fixed first.

### 1a. `CommandValidator` bypasses (if it ever gets wired) — High (once live)

The validator's `DANGEROUS_PATTERNS`/blocklist are regex/token matches on a raw string and are trivially evaded:

- **Path/quote evasion of blocklist** (`command_validator.py:79`): `base_cmd = parts[0].split("/")[-1]` only inspects `argv[0]`. `bash -c "rm -rf ~"` passes (`bash` is allowlisted; `rm` never appears as `argv[0]`). `xargs rm`, `find . -delete`, `git` hooks, `python -c "import os;os.system('rm -rf x')"` all pass — `python`, `find`, `bash`, `sh` are on the allowlist.
- **Blocklist is namespace-blind:** `/bin/rm` → basename `rm` blocked, but `busybox rm`, `command rm`, `\rm`, `rm${IFS}-rf` are not.
- **`DANGEROUS_PATTERNS` false sense:** blocks `$(` and backticks but not `${var}` expansion, process substitution `<(...)`, here-docs, or newline-separated compound commands beyond the narrow `;\s*rm` regex. `printf ... | sh` is allowed (`printf` not blocked, `sh` allowlisted).
- **`curl`/`wget` blocked but `nc`, `python -c "urllib..."`, `git clone` (git allowlisted) exfiltrate/fetch freely.**

Conclusion: this is a **denylist-shaped speed bump, not a sandbox.** If wired, treat it as advisory only; real isolation needs an OS sandbox (seccomp/landlock/container) — not string matching.

---

## 2. install.sh — Med/High

**2.1 curl|bash / clone|bash trust — Med.** README instructs `git clone … && ./install.sh` (README:44-48). The installer itself makes **zero network calls** (`grep -c curl|wget|git clone install.sh` = 0) and uses no sudo — genuinely good. But there is **no checksum/signature verification** of the cloned tree, no pinned release, and no published hash in README. A tampered mirror or MITM'd clone yields silent code execution. Fix: publish signed release tarballs with SHA256SUMS, document `git verify-tag`, pin install docs to a tagged release.

**2.2 Destructive overwrite + `rm -rf` cleanup trap — High.** On failure, `_cleanup_on_failure` runs `rm -rf "$DEST"` where `DEST="$TARGET_DIR/.claude"` (install.sh:95-101). Combined with `--force` (line 104) which overwrites an existing `.claude` **without a backup**, a re-run or a mid-install error can destroy a user's hand-tuned `.claude/` (agents, local CONSTITUTION, session context) with no recovery. `TARGET_DIR` is `cd`'d then `pwd`'d (line 85) but falls back to the **raw string** if `cd` fails, so an odd path can leave `DEST` pointing somewhere unexpected before the `-d` check. Fix: back up existing `.claude` to `.claude.bak-<ts>` before overwrite; make cleanup only remove files it created this run (track a manifest), never a blanket `rm -rf $DEST`; abort if `$DEST` didn't exist before the run started but does now for reasons other than our own writes.

**2.3 No PATH manipulation — Low (good).** Installer does not touch shell rc files or PATH; console scripts come only via `pip` (which is broken anyway — see code-review P0). No finding beyond noting the `claudekit`/`ck` entry points never worked.

**2.4 `.gitignore` mutation appends `*.log` etc. into the user's repo — Low.** install.sh:363-384 appends ClaudeKit entries. Benign, but it edits a tracked file without asking; note in output.

**2.5 config.env parsing is safe — Low (good).** Lines 279-293 whitelist keys and `sed`-strip quotes rather than sourcing — correct choice; avoids arbitrary code execution from a template file.

---

## 3. Hooks — what auto-executes on every tool call — Med/High

`.claude/settings.json` wires **8 PreToolUse + 2 PostToolUse + UserPromptSubmit + SessionStart + 4 Stop + SubagentStop + PostToolUseFailure** hooks. Every `Write`/`Edit` triggers **3 bash→python3 hooks** (ops-enforcement, config-protection, security-reminder); every `Bash` call triggers **4** (pre-commit gate, commit-quality, pre-push gate, block-no-verify) plus the unconditional `suggest-compact`.

**3.1 Injection via file paths / commands into hooks — Med.** Hooks extract fields with `python3 -c` from JSON (safe parsing, good) but then **interpolate the extracted value straight into shell**: e.g. `config-protection.sh` and `security-reminder.sh` do `basename "$TARGET_PATH"` and `grep -qE "$pattern"` on attacker-influenced paths; `ops-enforcement.sh` runs `python3 -c "...realpath..." "$TARGET_PATH"`. Values are quoted, so classic `; rm` injection is mostly contained, but a **path used as a grep pattern** (config-protection matches `$FILENAME` against regex patterns) means a crafted filename could cause ReDoS or unexpected matches. Higher risk: `post-tool-use.sh` and hooks that `grep`/parse **untrusted tool output and git diffs** — a repo file containing shell-meta or huge lines can wedge or mislead the audit log. Fix: never use untrusted strings as regex patterns (`grep -F`), cap input length, and pass values via env/argv not string-concatenation.

**3.2 Silent non-functionality = false protection — High.** Multiple safety hooks are effectively no-ops (corroborated by code-review):
- `commit-quality.sh` / secret scan relies on the `\x27`-in-`grep -E` bug (code-review P2) — single-quoted secrets slip through. The "blocks staged secrets" promise is unreliable.
- `block-no-verify.sh` matches `--no-verify` textually; `git -c core.hooksPath=/dev/null commit`, `git commit --no-verif\` line-continuations, or env `GIT_...` bypass it.
- `config-protection`/`security-reminder` depend on `tool_name`/`tool_input` JSON shapes; if Claude Code's payload keys differ from the guessed `d.get('tool_name', d.get('name'))`, the hook silently `exit 0`s (allow). A guard that fails **open** on parse mismatch is worse than none because it's advertised.
Fix: fail-closed on parse failure for **blocking** guards (config-protection, ops-enforcement, secret scan); add a self-test that feeds a known-bad payload and asserts `exit 1`.

**3.3 `templates/hooks/*` are shipped but never installed/wired — Med.** `file-guard.sh` (blocks 13 sensitive-file categories) and `prompt-injection-scanner.sh` are the strongest defenses in the repo, yet `install.sh` copies `templates/hooks/*.sh` into `.claude/hooks/` (line 213) **but `.claude/settings.json` never references them** — no matcher runs file-guard before a Read/Write of `.env`/`id_rsa`, and nothing pipes prompts/tool-output through the injection scanner. So the anti-secret-exfiltration and anti-injection layers exist as inert files. Fix: add PreToolUse matchers that run `file-guard.sh` on Read/Write/Bash targets (fail-closed) and run `prompt-injection-scanner.sh` on `UserPromptSubmit` and on tool output.

**3.4 `prompt-injection-scanner.sh` is a keyword denylist — Low/Med.** Patterns like "ignore previous instructions" catch only naive English attacks; trivially bypassed by base64, homoglyphs, translation, or novel phrasings, and prone to false positives on legitimate security docs. Useful as defense-in-depth, not a control. Document it as best-effort.

**3.5 Backgrounded hooks (`&`) drop exit codes — Low.** `suggest-compact`, `command-log-audit`, `cost-tracker`, `desktop-notify`, `format-typecheck` run with `&` (settings.json). A backgrounded blocking guard can never block; fine for these (all advisory) but ensure no security-relevant hook is ever backgrounded.

---

## 4. Prompt-injection & dangerous-instruction surface — High

**4.1 The framework instructs the agent to run `--dangerously-skip-permissions` — High.** `.claude/commands/plan.md:30`, `review.md:55`, and `refine.md:96,112,150` all pipe into `claude -p --agent … --dangerously-skip-permissions`. This is ClaudeKit's own default workflow disabling the human-in-the-loop permission prompt for sub-agent invocations (planner/reviewer). Because these sub-agents read repo files and untrusted plan text, a prompt-injection in a source file or a plan can now drive an agent that has been **explicitly stripped of permission gating**. This is the highest-impact design flaw: the toolkit markets safety hooks while its core commands opt out of the platform's primary safety mechanism. Fix: remove `--dangerously-skip-permissions` from all shipped commands; if non-interactive runs are required, scope them and document the risk loudly, or gate behind an opt-in env var that defaults off.

**4.2 Autonomous-loop skills — Med (mitigated but unsandboxed).** `.claude/skills/autonomous-loops/SKILL.md` and `commands/loop-start.md` run an agent iteratively until convergence. They **do** define a `BLOCKED_IN_LOOPS`/emergency-stop list (`rm -rf`, `git reset --hard`, `DROP TABLE`, `git push --force`) and stagnation checks — good design. But enforcement is **prompt-level**, not a sandbox: the loop-operator is asked to detect and stop, with no OS-level guarantee, and the block list is a small literal-string set (same evasions as §1a). An autonomous loop with shell access + skipped permissions (§4.1) is the worst-case combination. Fix: enforce the loop block-list through an actual `PreToolUse` hook (wire `command_validator`), not narration; require the loop to run under the file-guard hook; keep permissions ON inside loops.

**4.3 No indication that skills/agents themselves are treated as untrusted.** Good news: grep found no `auto-approve: true`, no `rm -rf /`, no unconditional force-push in agents — the destructive terms appear only in **defensive** contexts (block-lists, "NEVER force push"). `continuous-learning/SKILL.md` even ships `"auto_approve": false`. So the prompt library's *intent* is safety-positive; the gap is that enforcement is advisory and undermined by §4.1.

---

## 5. Secrets & committed artifacts — Med

**5.1 Committed runtime logs — Med.** `.claude/hooks/hooks.log` (159 KB) and `.claude/hooks/cost-tracker.log` (8 KB) and `compact-counter.txt` exist in the working tree; `cost-tracker.sh` is git-tracked. `.gitignore` has `*.log` and `.claude/hooks/hooks.log` (installer adds the latter), so they *should* be ignored, but the repo already contains a populated `hooks.log` with `pwd`, `whoami`, timestamps, and tool/target history (session-start logs `user=$(whoami)` and full paths). If any of these logs were ever committed they leak local usernames, project paths, and activity. Fix: `git rm --cached` any tracked log; confirm `.gitignore` covers `.claude/hooks/*.log`, `*.txt` counters, `session.log`; scrub before publishing a release.

**5.2 Hardcoded email — Low.** `pyproject.toml:13` `omar@claudekit.dev`; `SECURITY.md` `security@claudekit.dev` (unverifiable domain, flagged in documentation-review). Not a secret, but ties releases to an unowned-looking domain. No API keys/tokens found (the only `api_key = "test-key-12345"` is an intentional *bad-example* inside `insecure-defaults/SKILL.md`). Good.

**5.3 Repo-slug inconsistency is a supply-chain footgun — Med.** README/badges use `omarmokhtar/claudekit`; pyproject/schema use `OmarMokhtar-Saad/claudekit` (see documentation-review D-7). A user who clones the wrong (possibly unclaimed) slug could fetch attacker-controlled code. Fix: canonicalize the slug everywhere and claim/redirect the other.

---

## 6. Supply chain — Med

- **No lockfile, no pinned deps.** `pyproject.toml` has no runtime deps pinned; `tests/requirements.txt` pulls `jsonschema` unpinned. No hash-pinning. Fix: pin with hashes (`pip-compile --generate-hashes`) or a lockfile.
- **GitHub Actions use mutable major tags** — `actions/checkout@v4`, `actions/setup-python@v5`, `softprops/action-gh-release@v2`, `actions/upload-artifact@v4` (`.github/workflows/*`). `@v4` is a moving ref; a compromised action release runs in CI with repo token. Fix: pin to full commit SHAs and enable Dependabot for actions.
- **`templates/mcp/mcp-settings.json` runs `npx -y @pkg@latest` for 5 servers** including `server-filesystem --allow-write .` — `npx -y` fetches and executes the **latest** published package with no version pin and no integrity check, and the filesystem server is granted write to the CWD. This is remote-code-execution-by-design on `--with-mcp` installs. Fix: pin exact versions, drop `@latest`, document that `--allow-write` grants the agent disk write, and consider scoping the filesystem root.
- **`pip install .` is currently impossible** (code-review P0: invalid `build-backend`), which paradoxically limits the console-script attack surface — but fix the backend and the above pins become load-bearing.

---

## 7. SECURITY.md adequacy — Low/Med

`SECURITY.md` supported-versions table lists only **`1.x`** while the product is **`2.0.0`** (install.sh VERSION, pyproject) — the current version is documented as *unsupported*. It correctly warns "review hooks before enabling" and "review ops with `--dry-run`", but omits: the `--dangerously-skip-permissions` default (§4.1), that `src/security/*` is inert (§1), that `--with-mcp` runs `npx @latest` (§6), and the curl/clone-trust guidance (§2.1). Fix: bump the table to `2.x`, add these disclosures, and add a "the hooks are advisory, not a sandbox" statement.

---

## Prioritized hardening checklist

| # | Severity | Fix |
|---|----------|-----|
| 1 | High | Remove `--dangerously-skip-permissions` from `plan.md`/`review.md`/`refine.md`; keep human/permission gating on, especially in autonomous loops. |
| 2 | High | Resolve the dead `src/security/*` layer: either wire it as a fail-closed `PreToolUse` guard (after fixing §1a bypasses) or delete it and its doc claims. Stop advertising a control that doesn't run. |
| 3 | High | Make blocking hooks **fail-closed** on JSON-parse mismatch; add self-tests that feed known-bad payloads and assert `exit 1` (config-protection, ops-enforcement, secret scan). |
| 4 | High | install.sh: back up existing `.claude` before overwrite; scope cleanup to a per-run manifest instead of `rm -rf $DEST`; don't fall back to raw `TARGET_DIR` on `cd` failure. |
| 5 | Med | Wire the shipped-but-inert `file-guard.sh` (Read/Write/Bash) and `prompt-injection-scanner.sh` (UserPromptSubmit + tool output); document both as best-effort. |
| 6 | Med | MCP template: pin exact versions (drop `@latest`), warn about `--allow-write .`, scope filesystem root. |
| 7 | Med | Fix the `\x27` secret-regex bug (code-review P2) so single-quoted secrets are actually caught. |
| 8 | Med | Pin GitHub Actions to commit SHAs; add Dependabot; pin/lock Python deps with hashes. |
| 9 | Med | Canonicalize repo slug across README/badges/pyproject/schema; claim the alternate. |
| 10 | Med | `git rm --cached` all runtime logs; ensure `.gitignore` covers `.claude/hooks/*.log`, counters, `session.log`; scrub before release. |
| 11 | Low | Publish signed release tarballs + SHA256SUMS; pin install docs to a tag; document `git verify-tag`. |
| 12 | Low | SECURITY.md: update supported version to `2.x`; disclose skip-permissions, inert security layer, MCP `npx @latest`, hooks-are-advisory. |
| 13 | Low | Hardening in hooks: use `grep -F` on untrusted values, cap input length (ReDoS), never background a blocking guard. |

**Bottom line:** ClaudeKit's *stated* security posture (allowlist validator, path sandbox, secret blocking, injection scanning) is largely **aspirational** — the strongest controls are either not wired (`src/security/*`, `templates/hooks/*`), fail open on mismatch, or are string-matching speed bumps, while the core commands **actively disable** permission prompting. The installer is refreshingly network-free and non-sudo, but its overwrite/cleanup path can destroy user config. Nothing here is catastrophic-by-default (no bundled malware, no committed keys), but the gap between marketed and actual safety is the real risk.
