# Plan: /xpipe — cross-account/cross-tool pipeline with per-participant off-flags

**Date**: 2026-08-09 | **Requested by**: Omar ("flow has flag can off account of them or all and just use the workflow now") — explicit approval, immediate implementation ordered; additive change, no review loop (owner urgency; blast radius = 2 new files + docs).

## Goal

One entry point for the multi-party workflow (Brain account = Team/Fable plans+merges, Hands account = personal Max implements, Cursor = cross-reviewer) where every external participant can be switched off — individually or all at once — and the flow degrades to the standard single-session ClaudeKit pipeline. Must work TODAY (account B not yet logged in) via auto-detection.

## Design

- `.claude/operations/scripts/xpipe.py` (stdlib-only):
  - Roles: **brain** (default `CLAUDE_CONFIG_DIR=~/.claude-acct-b`, override `--brain-dir` / `XPIPE_BRAIN_DIR`) and **cursor** (`cursor-agent` on PATH). **hands** = the default account (no config dir).
  - Flags: `--no-brain`, `--no-cursor`, `--solo` (both off), `--status` (report availability + resolved mode), `--dry-run` (print exact stage commands, execute nothing).
  - **Auto-degrade**: brain unavailable (dir missing/empty = not logged in) or cursor not installed → stage silently skipped with a warning line; flags can only turn OFF, never force an unavailable participant on.
  - Modes: `full` (brain plans → hands reviews → cursor cross-reviews → hands implements), `no-brain` (current account plans, cursor still cross-reviews), `no-cursor` (two-account only), `solo` (exit 0 with instruction: run the standard in-session pipeline — /plan → /review → /implement or coordinator).
  - Stage execution: headless `claude -p` / `cursor-agent -p` subprocesses with per-stage scoped `--allowedTools` (per INVOCATION.md; NEVER --dangerously-skip-permissions), logs to `.claude/reports/xpipe/`, REVISE verdict stops the chain (exit 3).
- `.claude/commands/xpipe.md`: command front-end; on `solo` mode the session itself runs the standard pipeline.
- Tests `tests/test_xpipe.py` (subprocess, `--status`/`--dry-run` only — no real model calls): degradation matrix (full/no-brain/no-cursor/solo/auto-degrade), banned-flag guard (output never contains dangerously-skip-permissions), exit codes.
- Docs: counts 42 commands (gen-docs + prose lines), CHANGELOG, PARALLEL_AGENTS.md section, fleet sync of the 2 new files.

## Out of scope
Verifier auto-run (stays user-gated); MCP bus; scheduling.
