---
description: "Cross-account/cross-tool pipeline with per-participant off-flags — degrades to the standard workflow"
argument-hint: "<task> [--no-brain] [--no-cursor] [--solo] [--status] [--dry-run]"
---

# XPipe Command

Run the multi-party workflow — Brain account plans, Hands account reviews +
implements, Cursor cross-reviews — with **any participant switchable off**.
With everything off (or nothing available) it IS the standard single-session
ClaudeKit pipeline: nothing external is ever required.

## Task

XPipe request: $ARGUMENTS

## Mandatory Skills

You MUST load and apply the following skills before proceeding:

- **using-superpowers** - Core agent capabilities and tool usage
- **cross-tool-collaboration** - Roles, account isolation, trust boundary

## Participants & Flags

| Participant | Role | Off flag | Auto-off when |
|---|---|---|---|
| brain | second Claude account (Team/Fable): plans, merge authority | `--no-brain` | `~/.claude-acct-b` missing/empty (not logged in) |
| cursor | cross-vendor reviewer (GPT via cursor-agent) | `--no-cursor` | cursor-agent not on PATH |
| hands | the CURRENT account: reviews + implements | (always on) | never |

`--solo` = all external participants off. Flags can only turn participants
OFF; an unavailable participant degrades automatically with an explanatory
note — the pipeline never fails because someone is missing.

## Execution

1. First resolve the mode:
   ```bash
   python3 .claude/operations/scripts/xpipe.py --status
   ```
2. **If mode is `solo`** (or the user passed `--solo`): do NOT run the script.
   Run the standard in-session pipeline yourself: `/plan` → `/review` (90/100
   gate) → `/implement` (or route through `/coordinator` for multi-part tasks).
3. **Otherwise** run the pipeline headless:
   ```bash
   python3 .claude/operations/scripts/xpipe.py "<task>" [flags]
   ```
   Stages execute with per-stage scoped `--allowedTools` (INVOCATION.md rules;
   `--dangerously-skip-permissions` is never used). Logs land in
   `.claude/reports/xpipe/`.
4. Exit 3 means a reviewer said REVISE — report the findings from the log and
   stop; do not retry without addressing them.
5. Implementation lands on an `agent/*` branch in a worktree. The merge stays
   with the merge authority (gitOps Multi-Agent Merge Protocol) — never
   auto-merge.

## Usage Examples

- `/xpipe add retry logic to the uploader` — full pipeline if both externals are up
- `/xpipe fix the flaky date test --no-cursor` — two Claude accounts only
- `/xpipe refactor the cache layer --solo` — plain single-session workflow
- `/xpipe --status` — who is available right now, and what mode would run

## Notes

- Trivial changes should NOT go through xpipe — the trivial fast-path
  (minimal ops.json, no planner/reviewer) stays cheaper and faster.
- Verifier remains user-gated: xpipe never auto-runs the verifier agent.
