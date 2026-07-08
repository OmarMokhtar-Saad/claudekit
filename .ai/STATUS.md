# Project Status Snapshot

**Date:** 2026-07-08 · **Version:** 2.1.0 (`[Unreleased]` in CHANGELOG) · **Branch:** main (Phase 1 merged via PR #1) · **Tests:** 516 passing · **Audit baseline:** 49/100 (2026-07-05, pre-Phase-1)

## Completed

- **Phase 1 "Fix What's Broken"** (audit tasks 001–006, 011) — all landed and merged 2026-07-06:
  - 001 Packaging: build backend fixed, true src-layout, single version source, wheel bundles assets, `pip install` self-contained.
  - 002 Security: CommandValidator/PathGuard wired for real (`command-guard.sh`, `ck check-command/check-path`), chained-command + substitution validation, allowlist hardening.
  - 003 Hooks: all blocking hooks exit 2 + stderr + fail closed; `lib.sh` extracted; ops filename split-brain unified; telemetry reads stdin JSON; macOS bash-3.2 fixes; `\x27` secret-regex fixed.
  - 004 Permissions: all 5 `--dangerously-skip-permissions` removed; `_shared/INVOCATION.md` single source of truth; CI `permission-gate`.
  - 005 Installer: staging + backup + atomic swap (no more `rm -rf $DEST` trap), settings.json installed, manifest written, curl|bash guard, `--yes`, honest epilogue, sed escaping; `settings.local.json` preserved across reinstall.
  - 006 Version/docs: CHANGELOG renumbered (1.3.0→2.1.0), phantom agents removed, canonical slug everywhere, counts corrected via `gen-docs.py`, docs/HOOKS.md rewritten around settings.json, SECURITY.md covers 2.x with honest disclosures.
  - 011 CI: honest full-suite matrix (ubuntu+macos), coverage gate (security ≥85%), lint, docs-drift, dangling-hooks, package-smoke, install-integration, SHA-pinned actions, Dependabot.
- Post-merge fix: `0c9223b` (setuptools missing on py3.12+ broke test_packaging).
- CLI lifecycle commands: `ck diff` / `update` / `uninstall` on the install manifest; `ck doctor --strict` (19 checks); `CLAUDEKIT_HOME` honored.
- MAX_DELETIONS guard (GUARD 26) in the ops validator; planner schema drift fixed (references `generate-operations-config`); `execute-operations-config` skill rewritten script-only.

## Not done / open

| Item | Ref | State |
|------|-----|-------|
| Tag v2.1.0 + PyPI publish | roadmap §1.1 | **User-gated.** Mechanics ready (release.yml + Trusted Publishing). |
| Claude Code plugin packaging | task 007 | Not started. Strategic bet for v3.0. |
| Corpus consolidation (agents 28→~20, skills 73→~60, delete templates/skills dupes) | task 008 | Not started. Needs owner sign-off on merge list. |
| Context-budget reduction (≤2 mandatory skills/agent, one hook dispatcher/event) | task 009 | Not started. |
| Eval framework (`ck eval`, golden ops.json fixtures, calibrated gates) | task 010 | Not started. The 90/100 gate remains prompt-side only. |
| Test-suite behavioral upgrade (kill remaining existence-theater tests) | task 012 | Partially improved (test_hooks_behavioral, security bypass corpus); systematic pass pending. |
| OSS community health (CoC, CODEOWNERS, labels, demo GIF) | task 013 | Not started. |
| Supply-chain hardening (signed releases, SHA256SUMS, SLSA, MCP pinning) | task 014 | Partially (SHA-pinned actions, Dependabot); release-signing pending. |

## Known bugs

None currently tracked as open. The audit's P0/P1 defect list was the Phase-1 scope and is closed. Fragile spots worth watching: manifest-hash sensitivity in `ck update`, language detection edge cases (JS-vs-TS, nested csproj, kotlin false positives — partially fixed in `dca9a19`), symlinked project roots.

## Concerns

- **Architecture:** four-layer prompt duplication (command ↔ agent ↔ skill ↔ registry) until task 008/009 land; `hooks/config.json` (project commands) vs `settings.json` (wiring) split is documented but still confuses users.
- **Security:** guard is a denylist speed bump; autonomous-loop block-list still narration-enforced (roadmap item 19); MCP templates still reference unpinned `npx` servers (item 20).
- **Performance:** 9–15 hook spawns per tool call; ~12.4K-token routing tax.
- **Testing:** CLI in-process coverage still thin; eval coverage of prompts = 0 until task 010.
- **Docs:** `docs/AGENTS.md` covers the 13 core agents in depth; the 15 specialists have frontmatter-level docs only. `.ai/` (this folder) now fills the maintainer gap.

## Highest-priority next work

1. Get the user decision, then tag + publish v2.1.0 ([PLAYBOOK.md](PLAYBOOK.md) → Release).
2. Task 008 consolidation (biggest quality-per-effort win; shrinks the token tax too).
3. Task 010 eval framework (turns quality claims into data).

See [ROADMAP.md](ROADMAP.md), [BACKLOG.md](BACKLOG.md), [TECH_DEBT.md](TECH_DEBT.md).
