# Plan — Rejection Retro Loop (self-learning review flow)

**Slug:** `rejection-retro-loop` · **Tier:** 3 (enforcement script + new agent/command + planner change)
**Status:** DRAFT — awaiting owner sign-off (hard rule 5)

## Problem

A plan can be rejected repeatedly and the repo keeps no durable record of *why*.
`review-record.py` already folds prior verdicts into `rounds[]`, but nothing reads
them across plans. `reflection.py`'s ledger is session-scoped, temp-dir, and
deliberately never committed — so it cannot answer "what did review reject this
week". The rejection signal exists and is discarded.

## Decisions (owner, 2026-08-24)

- Trigger = **any non-APPROVED verdict** (REJECTED, REVISE, or score < 90); brief
  fires on the **2nd** such round for one ops slug.
- Analyst runs **on demand only** and **proposes** edits (report + ops.json);
  never self-applies. No cron in this change.

## Design

### 1. Trigger (one writer, no new hook)

Every verdict already passes through `review-record.py cmd_write`. After the
`rounds` fold, count non-approving rounds (current + history). At exactly 2,
write/refresh the brief. Idempotent: re-running `write` for the same round must
not duplicate an INDEX line (key = ops_slug + round number).

### 2. Brief — durable, project-local, safe to commit

- `.claude/knowledge/rejections/<ops-slug>.md` (one file per slug, appended per round)
- `.claude/knowledge/rejections/INDEX.jsonl` (one line per brief; cheap aggregation)

Fields: `session_ref` (**hashed** — reuse `reflection.py bounded_token`; a raw
session id must never enter a tracked file), plan path, ops path, ops_sha256,
each round's score/decision, findings verbatim, authoring agent, tier, UTC time.
All free text through `reflection.py _safe_text` (rejects rather than digests) so
absolute paths and credential-shaped strings cannot be committed.

### 3. `/flow-retro [--since 7d]` + `flow-analyst` agent

Reads `INDEX.jsonl` and the `rounds[]` in `.claude/reports/reviews/*.json`; clusters
findings by dimension (missing ops.json, security, schema, test coverage, plan
quality); computes rejection rate per dimension and per authoring agent, plus a
rounds-to-clean trend. Calls **context7 itself** for best practice on the weakest
dimension (token policy: `web-researcher` has no MCP access, so context7 is never
delegated). Emits `.claude/reports/retro/<date>.md` + a paired ops.json proposing
concrete checklist edits to `planner.md` / `reviewer.md`. Owner approves; the
implementer applies via the ops engine (Iron Law).

### 4. Loop closure — the part that makes it *learning*

`review-record.py rejections search "<keywords>"` (mirrors `knowledge-ledger search`,
including exit 3 = no match). `planner.md` Phase 0 gains a mandatory call, exactly as
`debugger.md:215` does for the issue ledger. Without this the briefs are an archive,
not a feedback loop.

## Files

| File | Change |
|---|---|
| `.claude/operations/scripts/review-record.py` | brief emission in `cmd_write`; new `rejections` subcommand |
| `.claude/knowledge/rejections/` | new store (+ `.gitignore` review: briefs ARE tracked) |
| `.claude/agents/flow-analyst.md` | new agent (Read/Grep/Glob/Bash + context7) |
| `.claude/commands/flow-retro.md` | new command |
| `.claude/agents/planner.md` | Phase 0 mandatory `rejections search` |
| `tests/test_rejection_briefs.py` | new behavioural tests |
| `docs/`, `CHANGELOG.md`, `.ai/SESSION_STATE.md` | counts via gen-docs only (hard rule 8) |

## Tests (behavioural, not structural)

1. Two REVISE rounds on one slug → brief file + exactly one INDEX line per round.
2. One REVISE then APPROVED → **no** brief (threshold respected).
3. A finding containing an absolute path / credential-shaped token → refused or
   digested, never written verbatim to the tracked brief.
4. Raw session id never appears in brief or INDEX.
5. Re-running `write` for the same round → no duplicate INDEX line.
6. `rejections search` → exit 3 on no match, 0 with a hit.
7. Corrupt `INDEX.jsonl` line → skipped with a note, never crashes `write`
   (a broken index must not be able to block review recording).

## Risks

- **`cmd_write` is on the approval path.** Brief emission must be fail-soft:
  any error writes a stderr note and still records the verdict. A retro feature
  must never be able to block execution approval.
- Tracked briefs redden the secret self-scan once committed — re-run gates AFTER
  committing (known trap).
- Model-policy gate: `flow-analyst` needs a `.claude/model-policy.json` row or
  `gen-model-policy.py --check` fails.

## DoD

pytest · ruff · mypy · gen-docs --check · gen-registry --check · gen-model-policy --check ·
check-context-floor --check · shellcheck · `ck doctor --strict` · CHANGELOG · conventional commit.
