# Implementation Plan: learning-loop-v2 — close the trigger gap

## Overview

ClaudeKit's learning loop has a working **store** layer (`knowledge-ledger.py`, per-agent
`.claude/agent-memory/`, the SessionStart injector) and a **dead trigger** layer: the only
write trigger is the Verifier PASS checkpoint (the verifier never auto-runs by policy), the
`continuous-learning` skill describes a Stop-hook extractor that does not exist, and
`/learn` points at `~/.claude/skills/learned/`, a directory that never existed. Result
across the 14-repo fleet: ledger issues in 2, proposals in 0, real memory in 3. This plan
adds the trigger: Stop demands memory **candidates** and a decision on each, `/learn`
becomes the human-gated promotion UI, and skill growth happens only through proposals a
human promotes.

## Design precheck (Phase 0)

**Ownership model.** The durable artifact is a per-agent memory entry plus its `MEMORY.md`
index line — a file Claude Code auto-injects into that agent's system prompt. So the only
actor allowed to create one is a human decision (`inbox --accept`, `/learn --promote`), and
the machine's role stops at *drafting a candidate*. Candidates and proposals are
machine-authored opinions, so they are gitignored; what is committed is what a human kept.
The files that carry the value: `.claude/agent-memory/<agent>/MEMORY.md` + entries (the
injected tier), `.claude/knowledge/issues/` (the receipts they are distilled from),
`.claude/knowledge/proposals/` (skill-level candidates). The trigger lives where a turn
actually ends — `reflection.duty_summary()`, read by `reflection-gate.py handle_stop()`.
Nothing in this plan writes into `.claude/skills/` (hard rule 5).

**Prior searches.** `review-record.py rejections search "memory learning stop hook"` →
exit 3, none recorded. `knowledge-ledger.py search` is the second search this plan itself
adds to Phase 0; run manually against `.claude/knowledge/issues/` it returns no entry about
Stop-triggered memory. Treated as unknown, not as evidence of safety. Planner memory does
record two validated priors that shape the design: *"A green check can measure nothing"*
(hence every test below asserts an exit code or a file, and the `--inbox` tests assert the
default path is unchanged) and *"ops add_after is literal concat"* (hence every `add_after`
payload here carries its own leading newline).

## Scope

- **In scope:** the Stop trigger and its duty text; `distill --inbox`; `inbox`
  accept/reject; `consolidate`; `propose --patch`; the `/learn` rewrite; the
  `continuous-learning` trigger section; the SessionStart over-budget message; planner
  Phase 0; `.gitignore`; CHANGELOG; behavioral tests.
- **Out of scope:** auto-merging memory entries (judgement, so `consolidate` lists and
  instructs); any automatic write into `.claude/skills/`; fleet propagation to the other
  13 repos; re-enabling the verifier auto-run; changing `MAX_ENTRIES`/`MAX_CHARS`.

## Prerequisites

- `.claude/settings.local.json` with `ECC_HOOK_PROFILE=minimal` present (this repo runs its
  own enforcement hooks on itself).
- Run from the `.ck-main` worktree on `feat/learning-loop`.

## Implementation Steps

### Step 1: `knowledge-ledger.py` — candidates, decisions, consolidation, patches
- **File:** `.claude/operations/scripts/knowledge-ledger.py`
- **Action:** Modify (7 edits, one operation)
- **Details:**
  - `cmd_distill` collects `cards` (slug, signature, rendered body) alongside `blocks`.
  - New `--inbox` flag: writes one candidate per group to
    `.claude/agent-memory/<agent>/_inbox/<slug>.md` and returns *before* the `.draft`
    path, so the default behaviour is untouched. Each candidate carries an `index:` line —
    the exact `MEMORY.md` row `accept` will append, so no code ever invents one.
  - New `inbox` subcommand: bare = list candidates + proposals; `--accept <name>` renames
    the file out of `_inbox/` into the agent directory and appends its `index:` line to
    `MEMORY.md`, refusing an ambiguous name, a missing `index:` line, or a result past the
    200-line truncation cliff; `--reject <name>` deletes it.
  - New `consolidate --agent <a>`: groups `MEMORY.md` index lines sharing 2+ signature
    tokens and prints what to merge. **Never rewrites the file** — merging two memories is
    a judgement about what is still true.
  - `propose --patch <skill> --section Pitfalls|Verification --text "..."`: writes
    `.claude/knowledge/proposals/patch-<skill>-<hash>.md` after redaction, refusing an
    unknown section, a missing skill, or text still carrying a secret/absolute path.
- **Validation:** `python3 -m pytest tests/test_learning_loop_v2.py tests/test_knowledge_ledger.py -q`

### Step 2: `reflection.py` — the Stop duty
- **File:** `.claude/hooks/reflection.py`
- **Action:** Modify (3 edits)
- **Details:** new `memory_inbox_pending()` (globs `*/_inbox/*.md` under
  `.claude/agent-memory/`; the files ARE the state, so nothing can go stale);
  `duty_summary()` appends a `MEMORY INBOX` duty naming each pending candidate and both
  decision commands; the existing LEARNING LOOP duty now names
  `distill --agent <agent> --inbox` as the way to produce candidates.
  `reflection-gate.py` is **not** touched: `handle_stop()` already blocks on any unmet duty
  and already honours `stop_hook_active`, so interrupt-once semantics come for free.
- **Validation:** `python3 -m pytest tests/test_reflection_gate.py tests/test_learning_loop_v2.py -q`

### Step 3: SessionStart injection stops truncating
- **File:** `.claude/hooks/session-memory-context.py`
- **Action:** Modify (1 edit, `render()` tail)
- **Details:** pack whole lines up to `MAX_CHARS`, then append one
  `MEMORY OVER BUDGET (n of m chars shown): run knowledge-ledger.py consolidate --agent
  <agent>` line. A half-sentence memory the reader believes is whole is worse than a
  short list plus a named fix.
- **Validation:** `python3 -m pytest tests/test_session_memory_context.py tests/test_memory_injection_contract.py -q`

### Step 4: `.gitignore` — candidates are local
- **File:** `.gitignore`
- **Action:** Modify (1 edit) — ignore `.claude/agent-memory/*/_inbox/`, with the reason
  written next to the existing proposals rule.

### Step 5: `/learn` rewrite
- **File:** `.claude/commands/learn.md`
- **Action:** Modify (2 edits: frontmatter, then the whole body)
- **Details:** `--list` → `inbox`; `--show <name>` → print the file verbatim;
  `--promote <name>` → three branches (memory candidate = `inbox --accept`; skill proposal
  = `ck skill new` **only after an in-chat yes**; patch proposal = build and run an
  ops.json, never a direct SKILL.md edit); `--reject <name>`. Every
  `~/.claude/skills/learned/` reference removed. New body is ~130 lines, under the 154-line
  `ck lint` ratchet recorded in `.claude/lint-baseline.json`.

### Step 6: `continuous-learning/SKILL.md` — describe what exists
- **File:** `.claude/skills/continuous-learning/SKILL.md`
- **Action:** Modify (14 edits)
- **Details:** trigger B is rewritten as the real Stop-gate/inbox flow; a trigger D
  (proposals and patch proposals) is named; the `~/.claude/skills/learned/` "Store As"
  table and every other reference to that directory are replaced with paths that exist.
  Frontmatter (`disable-model-invocation: true`, description) is untouched, so the skill
  description budget does not move.

### Step 7: proposals README + planner Phase 0
- **Files:** `.claude/knowledge/proposals/README.md`, `.claude/agents/planner.md`
- **Action:** Modify (1 edit each)
- **Details:** README gains a "Patch proposals" section. Planner Phase 0 now runs
  `knowledge-ledger.py search` beside the rejections search; the replacement paragraph is
  **23 bytes shorter** than the one it replaces, so the pipeline-agent floor moves from
  42980 to 42957 of 43000.

### Step 8: CHANGELOG + tests
- **Files:** `CHANGELOG.md` (1 edit), `tests/test_learning_loop_v2.py` (new)
- **Details:** `[Unreleased]` gains four user-visible entries. The test file is behavioral
  throughout: real hook subprocess with a real JSON payload on stdin, real script
  subprocess against a temp project root, `ECC_HOOK_PROFILE` forced explicitly.

## Testing Strategy

`tests/test_learning_loop_v2.py` (new), all subprocess-level:

| # | Claim under test | Assertion |
|---|---|---|
| a | Stop blocks once on an undecided candidate | exit 2 + `MEMORY INBOX` in stderr; retry with `stop_hook_active` exits 0 |
| a2 | no candidate ⇒ no duty; the loop duty names the command | exit 0 / `distill --agent ... --inbox` in stderr |
| b | `distill --inbox` writes candidates | one `_inbox/*.md` per group, carrying `index: - [` |
| b2 | the default path is unchanged | no `--inbox` ⇒ no `_inbox/`, `.draft` still written |
| c | over-budget injection | `MEMORY OVER BUDGET` + `consolidate --agent` present, old truncation string gone, every rendered entry line whole |
| d | `inbox --accept` | file moved out of `_inbox/`, the exact index line appended, prior MEMORY.md content preserved; `--reject` writes no memory; no `index:` ⇒ exit 4 |
| e | `propose --patch` | `patch-<skill>-<hash>.md` names skill, section and text; SKILL.md byte-identical afterwards; bad section ⇒ exit 2; missing skill ⇒ exit 3 |
| f | `consolidate` | prints merge groups, MEMORY.md byte-identical afterwards; missing file ⇒ exit 3, nothing created |

Full DoD afterwards: `pytest -q`, `ruff check`, `mypy`, `gen-docs.py --check`,
`gen-registry.py --check`, `check-context-floor.py --check`, `ck lint`.

## Rollback Plan

Every change is additive or a prose replacement in a single commit: `git revert` restores
the previous behaviour. Partial rollback: dropping the `reflection.py` operation alone
disarms the new duty (the ledger subcommands become unused but harmless); dropping the
`knowledge-ledger.py` operation alone leaves the duty naming a flag that does not exist, so
these two operations must be reverted together. Candidate files are gitignored and can be
deleted by hand; no data written by this plan is load-bearing for any other gate.

## Risk Assessment

- **Low:** `.gitignore`, CHANGELOG, proposals README, the new test file.
- **Low:** planner Phase 0 — measured at −23 bytes against a 20-byte headroom, so the
  context floor moves the safe direction.
- **Medium:** `/learn` and `continuous-learning` rewrites are prose; the `ck lint` line
  ratchet (154 for `learn.md`) and the skill-description budget both gate them. Frontmatter
  is untouched in the skill, and the new `learn.md` body is ~130 lines.
- **Medium:** `session-memory-context.render()` runs on every SessionStart. The function
  is already wrapped so any exception prints nothing and exits 0; the new branch only
  executes over budget, and a test pins the under-budget path as unchanged.
- **High:** the Stop duty can interrupt every turn of every session in this repo and, once
  synced, the fleet. Mitigations: it is interrupt-once (`stop_hook_active` allows the
  retry, tested); `ECC_HOOK_PROFILE=minimal` still suppresses blocking; the duty is
  self-clearing (rejecting a candidate is one command and a valid outcome); and it only
  appears at all once someone runs `distill --inbox`, so an agent that never distills is
  exactly as interrupted as it is today.
- **UNVERIFIED:** whether `ruff` requires two blank lines around the inserted
  `knowledge-ledger.py` block on this config — the payload supplies them, but the first
  post-execution `ruff check` is the proof.

## Review round 1 (2026-09-16)
reviewer: 92/100 APPROVED, 1 MAJOR — inbox duty was agent-unscoped and would interrupt subagents that cannot resolve it. Fixed in the config before execution: `duty_summary(session_id, include_inbox=...)`, the Stop handler passes `include_inbox=not subagent`; new test `test_a_subagent_stop_never_carries_the_inbox_duty`. Informational call sites (SessionStart carry-over, PreCompact note) keep the default and merely list it.
