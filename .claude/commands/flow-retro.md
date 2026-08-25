---
description: "Run a rejection retrospective over accumulated review briefs and propose human-gated process fixes"
argument-hint: "[--since YYYY-MM-DD] [--slug <ops-slug>] [--dry-run]"
model: sonnet
---

# /flow-retro

On-demand retrospective over `.claude/knowledge/rejections/`. **No cadence, no cron.** It
proposes; the owner approves; `/implement` applies. Store contract:
`.claude/knowledge/rejections/README.md`.

## Step 1 — size the corpus

```bash
python3 .claude/operations/scripts/review-record.py rejections stats
# briefs=N slugs=N sessions=N   (corrupt INDEX lines are skipped with a note)
```

## Step 2 — the sample-size gate, BEFORE spawning anything

Fewer than **5 briefs** or **3 distinct sessions**: stop and report that. Do not spawn the
analyst — an analysis of three briefs is an anecdote with a confident tone. State every time
that this threshold is **engineering judgement, not a cited result**.

## Step 3 — dispatch

Run `transcript-miner.py <session-id> --around <slug>` per brief; **exit 3 means the transcript
is gone — normal, the retro still runs brief-only and says which briefs had none.** Spawn
`flow-analyst` (scoped `--allowedTools` per `.claude/agents/_shared/INVOCATION.md`) with the
INDEX summary, the brief paths and any miner output. **Never hand it a raw transcript.**

## Step 4 — hand the owner a decision

Report the analyst's `.claude/reports/retro/<date>.md`, its paired ops.json, the guardrails
that blocked proposals, and the external anchor metric each proposal is measured on.
**Nothing is applied here.** Never propose a cron, never treat the reviewer score as ground
truth (it is another LLM), never tune planner and reviewer in the same cycle.
