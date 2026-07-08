# Security Guide

Public policy: `SECURITY.md` (supported: 2.x; includes honest disclosures). This is the maintainer view.

## Threat model (honest version)

ClaudeKit defends against **accidents and casual misuse by an AI agent**: destructive commands, secret leakage, protected-file damage, runaway edits/deletes, prompt-injected instructions. It is explicitly **not a sandbox** against a determined adversary — a denylist "speed bump". Disclosures in SECURITY.md cover: the prompt-injection reality, hooks-are-bypassable-by-design (profile system), the historic skip-permissions and dead-layer eras. Never let docs oversell again — the marketing-vs-reality gap was the audit's single worst finding (Security 32/100).

## Defense layers

1. **Claude Code permissions** — the floor. Scoped `--allowedTools` per INVOCATION.md; CI `permission-gate` greps shipped assets for `--dangerously-skip-permissions`.
2. **PreToolUse hooks** ([HOOKS.md](HOOKS.md)) — fail-closed blockers: ops-enforcement, config-protection, file-guard-gate, command-guard, block-no-verify, commit-quality, pre-commit, pre-push.
3. **CommandValidator** (`src/claudekit/security/command_validator.py`, 205 lines) — BLOCKLIST + DANGEROUS_PATTERNS; splits on `; && || |` and validates **every segment**; extracts and validates `$(...)`/backtick payloads; allowlist excludes bash/sh/env/xargs (payload smuggling); detects `find -delete/-exec`, `${IFS}` evasion, python `os.system`/`subprocess`/`__import__` smuggling. `from_config` reads the `security` section (a silent `hooks`-section bug once ignored all user config). Entry points: `ck check-command`, `python3 -m claudekit.security`, `command-guard.sh`.
4. **PathGuard** (`path_guard.py`, 137 lines) — PROTECTED_PATTERNS matched **per path component** (`my.envelope.txt` ≠ `.env`); symlinks resolved against the link's directory; MAX_DIRECTORY_DEPTH; `ck check-path`.
5. **Ops guards** — protected-file deletion refusal, MAX_DELETIONS=3, null bytes, ambiguity rejection, schema strictness, backups + rollback.
6. **Secret hygiene** — pre-commit diff scan (api_key/password/secret/token/private_key/PEM, single-quote-safe), gitOps pre-stage scan, opensource-sanitizer for whole-repo audits.
7. **Supply chain** — SHA-pinned actions, Dependabot, zero runtime deps, wheel smoke test. Pending (task 014): SHA256SUMS, Sigstore, SLSA provenance, MCP server pinning.

## Rules for maintainers

- Blocking guards **fail closed** — a parse failure blocks. Never invert this.
- Never add shell interpreters/launchers to any allowlist.
- Every validator change adds bypass-corpus tests; coverage stays ≥85%.
- New "safety feature" claims require a wired, tested enforcement path *before* the doc claim (the anti-"dead code layer" rule).
- Logs must not enter git (hooks.log once leaked usernames/paths into history).
- Autonomous loops: iteration caps always; the hook-enforced block-list is still TODO (roadmap 19) — don't represent it as done.

## Vulnerability response

Private report per SECURITY.md → reproduce with a behavioral test → fix fail-closed → disclose in CHANGELOG Security section → extend the bypass corpus. For secrets committed to history: rotate, then `git filter-repo`, then force-push coordination with the owner.
