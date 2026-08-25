# Plan — Rejection Retro Loop (self-learning review flow)

**Slug:** `rejection-retro-loop` · **Tier:** 3 · **Status:** DRAFT — awaiting owner sign-off (hard rule 5)
**Evidence:** `.claude/reports/research/self-learning-agent-loops.md` (prior-art review, 2026-08-24)

## Problem

A plan can be rejected repeatedly and the repo keeps no durable record of *why*.
Measured on the live corpus (2026-08-24): **80 review records, 80 APPROVED, 1 CONDITIONAL,
79 of 80 single-round.** Not because review always passes — because only the round that
passed is ever written. The rejection signal is produced and discarded.

## Decisions (owner, 2026-08-24)

- Trigger = any non-APPROVED verdict (REJECTED, REVISE, or score < 90); brief on the 2nd
  for one ops slug.
- Analyst runs on demand and **proposes** only. Never self-applies. No cron in this change.

## Phase 0 — PREREQUISITE: record the rejections (nothing else works without this)

The corpus above proves the trigger would never fire today. Before any retro machinery:

1. `reviewer.md` / `code-reviewer.md` emit the anchored `=== REVIEW ===` block on **every**
   round, rejections included — not only when approving.
2. The pipeline calls `review-record.py write` on rejecting rounds, so `rounds[]`
   accumulates real history.
3. Backfill: the 166 session transcripts are currently the ONLY place rejection history
   exists. `transcript-miner.py` is therefore not a convenience — it is the sole source
   for any pre-Phase-0 data.

Ship Phase 0 + capture first. The analyst is built against that history, not against an
empty store.

## Design

### 1. Trigger (one writer, no new hook)

Every verdict passes through `review-record.py cmd_write`. After the `rounds` fold, count
non-approving rounds (current + history); at exactly 2, write/refresh the brief.
Idempotent: key = ops_slug + round number, so re-running `write` never duplicates.

### 2. Brief — durable, project-local, safe to commit

- `.claude/knowledge/rejections/<ops-slug>.md` (appended per round)
- `.claude/knowledge/rejections/INDEX.jsonl` (one line per brief)

Storage shape is **confirmed by the research**: markdown brief + append-only JSONL sidecar
index. At dozens-to-low-hundreds of records the queries are filter-and-aggregate, not
fuzzy similarity — exactly where JSONL beats a vector store. Keyword-grep-over-markdown is
defensible below ~1000 records; revisit only past that. (LangMem's "procedural memory" is
this same pattern renamed.)

Index fields: plan slug, `session_id`, per-round scores/decisions, ODC type + trigger tags
(§5), **prompt version** (needed to attribute an improvement to an edit at all).

**Why raw session UUID, not a hash.** The brief's value is that a later agent can open the
session that produced the rejection. Transcripts live at
`~/.claude*/projects/<project-slug>/<session-uuid>.jsonl` (77 + 89 present today), so a
hashed ref is unresolvable and root-cause analysis dies. A UUID is a local filename, not a
credential. NEVER in a brief: the absolute transcript path (trips `_safe_text` and the
secret self-scan) and the SessionStart reflection token. All free text through
`reflection.py _safe_text`.

### 3. `transcript-miner.py` — deterministic reduction, NOT an agent

`transcript-miner.py <session-uuid> --around <ops-slug>` globs both project roots and
slices to: the reviewer verdict block, the planner output that earned it, and tool failures
in that window. Returns hundreds of lines from a file of tens of MB.

A script, not a prompt, for the same reason `reflection-gate.py` is Python — deterministic
state reduction is not a prompt's job — and it keeps whole transcripts out of every context
window. **Research constraint:** never feed raw transcripts to the analyst; summarise into
structured briefs first, and treat that text as evidence to verify, never as instruction
(matches this repo's existing retrieved-text rule). Missing transcript => exit 3; the
analyst degrades to brief-only rather than failing.

### 4. `/flow-retro` + `flow-analyst` — ExpeL-shaped

Closest prior art is **ExpeL (arXiv:2308.10144)**: offline pooling of trajectories, batch
extraction of natural-language insights with explicit **ADD / EDIT / UPVOTE / DOWNVOTE**
operations over a maintained insight list. We adopt that operation set directly — it is
what stops the checklist from growing monotonically forever.

**Reflexion (2303.11366) is deliberately NOT the model here**: it is online, per-episode,
and needs a verifiable reward. Its analogue in our system is the round-2 retry that already
exists, not weekly learning.

Root cause separates three causes needing opposite fixes, indistinguishable from the brief
alone: (a) planner produced a weak plan, (b) reviewer rubric is miscalibrated and rejecting
sound plans, (c) task underspecified upstream. Then context7 for best practice on the weak
dimension (never delegated — `web-researcher` has no MCP). Output:
`.claude/reports/retro/<date>.md` + paired ops.json. Owner approves; implementer applies.

**SWE-agent's (2405.15793) empirical lesson**, and the analyst is prompted for it
explicitly: durable wins came from fixing the agent's *interface and task spec*, not from
adding checklist rules. "Add a rule" is the weakest available fix and must be argued for
against an interface fix.

### 5. Defect taxonomy — ODC, adapted

Chillarege et al., IEEE TSE 1992. Transferable part is the **two orthogonal axes**: defect
**type** (missing ops.json, file-ownership error, uncovered security surface, scope
overflow) and **trigger** (the rubric line that caught it) — plus the core claim that the
**distribution shift over time** is the process signal, never any individual defect. Do not
copy IBM's literal code-defect list. (Its "10x faster root cause" figure is a vendor claim.)
From blameless postmortems (Google SRE ch.15) we steal one thing: **owned, trackable action
items**. 5-whys is a fine brief template, weak as a clustering method.

### 6. Guardrails — the part the first draft was missing

- **External anchor metric (non-negotiable).** "LLMs Cannot Self-Correct Reasoning Yet"
  (arXiv:2310.01798, ICLR 2024) shows self-correction gains largely came from oracle labels
  and performance often *degrades* without them. Sources genuinely conflict (Self-Refine,
  Reflexion report gains); the reconciliation is that gains survive when feedback is
  external and verifiable. **Our reviewer score is not an oracle.** So every retro tracks at
  least one metric outside the judge: did ops execute, did tests pass, did the human accept.
- **Goodhart.** Optimising planners against a 90-point rubric is textbook criteria-gaming;
  LLM judges carry verbosity/position/self-preference bias (2306.05685, 2404.13076).
- **Never tune planner and reviewer in the same cycle** — keep one as control. Generator/
  reviewer co-drift is widely feared but essentially unmeasured; no citation exists. Treated
  as hypothesis, guarded anyway because the guard is cheap.
- **Held-out validation.** DSPy/MIPROv2 (2406.11695) and TextGrad (2406.07496): propose
  candidates, score on a frozen set, keep the best. A prompt edit ships only on no
  regression against a frozen plan set.
- **Bounded edits + versioned prompts + rollback.** Cap edit budget per cycle; forbid
  monotonic checklist growth (this is what DOWNVOTE/EDIT are for).
- **Sample-size gate.** Act only on >=5 briefs spanning >=3 distinct sessions.
  **Honest framing: the literature does not answer this.** Prompt optimisers use 40-300
  examples; SPC wants ~20-25 subgroups. Our gate is engineering judgement, not a cited
  result, and is labelled as such wherever it appears.
- **Cadence.** Generative Agents (2304.03442) contributes importance-triggered reflection:
  fire when accumulated weight crosses a threshold, not on a calendar. `/flow-retro` stays
  on demand; the threshold is advisory only.

### 7. Loop closure — what makes it *learning*

`review-record.py rejections search "<keywords>"` (mirrors `knowledge-ledger search`,
exit 3 = no match). `planner.md` Phase 0 gains a mandatory call, exactly as `debugger.md:215`
does for the issue ledger. Without this the briefs are an archive, not a feedback loop.

## Agent budget

**One** new agent. Root-cause and best-solution are phases inside `flow-analyst`, not
separate agents; transcript slicing is a script. Every agent costs a model-policy row, a
registry entry, a docs count, and permanent context-floor budget.

## Files

| File | Change |
|---|---|
| `.claude/agents/reviewer.md`, `code-reviewer.md` | Phase 0: emit verdict block on every round |
| `.claude/operations/scripts/review-record.py` | brief emission in `cmd_write`; `rejections` subcommand |
| `.claude/operations/scripts/transcript-miner.py` | new: session-transcript slicer |
| `.claude/knowledge/rejections/` | new store (briefs ARE tracked) |
| `.claude/agents/flow-analyst.md` | new agent — the ONLY one |
| `.claude/commands/flow-retro.md` | new command |
| `.claude/agents/planner.md` | Phase 0 mandatory `rejections search` |
| `.claude/model-policy.json` | row for `flow-analyst` |
| `tests/test_rejection_briefs.py` | new behavioural tests |
| `docs/`, `CHANGELOG.md`, `.ai/SESSION_STATE.md` | counts via gen-docs only (hard rule 8) |

## Tests (behavioural)

1. Two REVISE rounds on one slug -> brief + exactly one INDEX line per round.
2. One REVISE then APPROVED -> no brief.
3. Finding with an absolute path / credential-shaped token -> refused or digested.
4. Raw session token never in brief or INDEX; session UUID present and resolvable.
5. Re-running `write` for the same round -> no duplicate INDEX line.
6. `rejections search` -> exit 3 no match, 0 on hit.
7. `transcript-miner.py` on a fixture -> returns the verdict window; missing UUID -> exit 3
   and `/flow-retro` still reports.
8. Corrupt `INDEX.jsonl` line -> skipped with a note, never crashes `write`.
9. Reviewer rejection round -> a record IS written (the Phase 0 regression).

## Risks

- **`cmd_write` is on the approval path.** Brief emission must be fail-soft: on any error,
  warn to stderr and still record the verdict. A retro feature must never block execution
  approval.
- Tracked briefs redden the secret self-scan once committed — re-run gates AFTER committing.
- Transcript layout is Claude Code's, not ours: versions change, transcripts get pruned.
  Both are normal (exit 3), never errors.
- Context floor: one new agent + one command must still pass `check-context-floor.py --check`.

## DoD

pytest · ruff · mypy · gen-docs --check · gen-registry --check · gen-model-policy --check ·
check-context-floor --check · shellcheck · `ck doctor --strict` · CHANGELOG · conventional commit.
