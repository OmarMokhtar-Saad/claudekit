# Implementation Plan: Agent Memory + a Learning Loop That Produces Output

## Overview

ClaudeKit has four candidate memory surfaces and only one of them ever writes anything.
This plan gives the agents durable, native per-agent memory (`memory: project`), makes the
issue ledger's write path reachable from an automatic upstream (the reflection receipt),
gives the ledger an evidence-hash staleness rule borrowed from `ck memory` instead of a
clock, injects a scanned and capped slice of it at SessionStart, and makes the
continuous-learning skill propose candidate skills instead of claiming an extractor that
does not exist.

## Phase 0 — Design precheck: which store owns what

**There is no fifth store, and none is created here.** Four surfaces exist; this plan
assigns each one an owner and a direction of flow:

| Store | Owner | Contents | Durability |
|---|---|---|---|
| `.claude/memory/entries.jsonl` (`ck memory`) | `src/claudekit/memory.py` | Evidence-hashed *assertions* (decision / constraint / reference / observation). `freshness()` re-hashes cited files; STALE/MISSING is mechanical. | Durable. **Authoritative for claims about the tree.** |
| `.claude/knowledge/issues/*.md` (`knowledge-ledger.py`) | ops scripts | Per-issue *findings* with lifecycle (open/fixed/wontfix/regressed), keyword-searchable. | Durable. **Authoritative for findings.** |
| session reflection JSONL (`reflection.py`, `ledger_dir()`) | hook | Per-session receipts in a session-scoped temp dir. | **Ephemeral by design — it feeds the ledger (P4) and is never promoted to a store.** |
| `.claude/agent-memory/<agent>/MEMORY.md` | Claude Code (native) | Per-agent procedural notes, auto-loaded (first 200 lines / 25 KB). | Durable, committed, reviewed like code. |

The value of this change sits in `knowledge-ledger.py`, `reflection.py`,
`session-start.sh` and seven agent frontmatter blocks — all covered by operations below.
`ck memory` is **not modified**: P3 borrows its *rule* (evidence hash beats a clock) and
P5 borrows its *verdict* (`freshness()`), by importing it, never by copying it.

**Rejection-brief search (mandatory).** `review-record.py rejections search "agent memory
reflection ledger learning hook"` → exit 0, 9 matches. The validated match is
`.claude/knowledge/rejections/reflection-lifecycle-gates.md` (round -1, CONDITIONAL 88).
Its three live priors and what this plan does differently:

1. *"The escape hatch can be blocked by a sibling PreToolUse hook."* — This plan adds **no
   new PreToolUse hook and no new refusal**. The P4 bridge runs strictly **after**
   `record_receipt()` has already returned an accepted entry, inside `main()`, wrapped so
   that no exception it raises can change the return value.
2. *"`ECC_HOOK_PROFILE=minimal` suppresses blocking but keeps recording, diverging from the
   line-1 short-circuit every other hook uses."* — The new Stop-hook step (P6) and the new
   SessionStart helper (P5) are **non-blocking, exit-0-always** and therefore have no
   blocking behaviour to diverge on; P6 is wired as a background invocation like
   `cost-tracker.sh`.
3. *"Documented hook count becomes misleading."* — Re-verified, and the brief's premise is
   **stale**: `gen-docs.py:77` globs `("*.sh", "*.py")`, so the new
   `.claude/hooks/session-memory-context.py` **would** move the hook count.
   `_is_helper_module` (`gen-docs.py:110-126`) exempts a `.py` only when a sibling `.sh`
   names it with a literal `python3` on the **same line**, and `ck doctor --strict`
   (`cli/main.py:203`, `_HOOK_INVOKE_RE`) additionally requires a literal `$SCRIPT_DIR/` on
   that line. So `session-start.sh` invokes the helper as **one literal line** —
   `[ -f "$SCRIPT_DIR/session-memory-context.py" ] && _mem_text=$(python3
   "$SCRIPT_DIR/session-memory-context.py" ...)` — never through a variable, with the reason
   in a comment beside it. Both patterns were run against the generated line and match.
   `gen-docs.py --check` and `ck doctor --strict` remain gates.

Also verified against the current tree (not assumed):
- `is_protected_file` is enforced for **`file_delete` only** (`validate-config-json.py:122`,
  `execute-json-ops.py:612`), so `code_edit` on `CHANGELOG.md` / `.gitignore` /
  `README.md` is permitted. This plan performs **zero deletions**.
- `ALLOWED_RUN_COMMANDS` (`shared.py:71`) contains formatters only — **no `python3`**. Every
  gate command below is therefore a manual verification step, not a `run_command` op. This
  config contains **zero `run_command` operations**.

## Scope

- **In scope:** P1 agent memory frontmatter + policy; P2 skill-listing budget + a CI
  ratchet + the continuous-learning honesty fix; P3 evidence-hash staleness on the ledger;
  P4 receipt→ledger bridge; P5 SessionStart retrieval; P6 propose-only skill proposals;
  CHANGELOG / docs / `.ai` updates.
- **Out of scope:** any change to `src/claudekit/memory.py` or the `ck memory` CLI; any
  change to the reflection blocking contract; any write into `.claude/skills/`; fleet sync
  to the other 14 kitted repos; enabling `record --verified` to auto-run (the Verifier gate
  stays user-gated per CLAUDE.md).
- **Files another session owns — NOT touched by any operation:**
  `.claude/operations/scripts/restore-backup.py`, the existing unstaged `CHANGELOG.md`
  hunk (this plan **appends a new hunk above it**, anchored on `## [Unreleased]`),
  `.claude/plans/plan-backup-history.md`, `.claude/plans/ops-backup-history/`.

## Prerequisites

- Branch `feat/agent-memory-learning` (already checked out).
- `.claude/settings.local.json` with `ECC_HOOK_PROFILE=minimal` present, or Edit/Write is
  blocked by this repo's own `ops-enforcement` (CONTRIBUTING.md).
- Claude Code auto-memory enabled for `memory:` frontmatter to take effect. When it is
  disabled the frontmatter key is inert — a degradation, never an error.

---

## Implementation Steps

### P1 — Agent memory

Verified facts driving the design:
- `templates/*/` contain only `CLAUDE.md` + `config.env` — **no agent files** — so there is
  nothing to mirror there. `templates/` is untouched.
- `scripts/gen-registry.py:66-88` reads named frontmatter fields (`description`, etc.) and
  `scripts/gen-model-policy.py:27` matches only `^model:`. Neither enumerates or rejects
  unknown keys, so `memory:` needs no generator change. Confirmed by running both `--check`
  gates after execution.
- **`src/claudekit/context_floor.py:104` charges the FULL FILE TEXT of `planner.md`,
  `reviewer.md`, `implementer.md` against `pipeline agent bodies` (42,930 / 43,000 — 70
  chars of headroom).** So `planner.md` and `reviewer.md` receive the 16-char frontmatter
  line and **no body text** (42,930 + 32 = 42,962, 38 chars spare). The recording policy
  for those two lives in `.claude/agent-memory/README.md`, which Claude Code's own injected
  read/write instructions point the agent at.

#### Step 1.1 — `memory: project` + recording policy (5 non-pipeline agents)
- **Files:** `.claude/agents/code-reviewer.md`, `.claude/agents/debugger.md`,
  `.claude/agents/explore.md`, `.claude/agents/verifier.md`,
  `.claude/agents/security-scanner.md`
- **Action:** Modify (one `code_edit` op per file, two edits each)
- **Details:** add `memory: project` after the `color:` frontmatter line; add a 3-line
  **Durable memory** block after the `# <Name> Agent` heading naming what to record
  (recurring patterns, project conventions, confirmed false positives) and what never to
  (secrets, absolute paths, one-off facts, anything a directive could ride in on).

#### Step 1.2 — `memory: project` only (2 pipeline agents)
- **Files:** `.claude/agents/planner.md`, `.claude/agents/reviewer.md`
- **Action:** Modify — frontmatter line only, for the context-floor reason above.

#### Step 1.3 — memory scope + review rule
- **File:** `.claude/agent-memory/README.md`
- **Action:** Create — path layout (`project` → committed here, `local` →
  `.claude/agent-memory-local/`, `user` → `~/.claude/agent-memory/`), the 200-line / 25 KB
  auto-load cap, the recording policy, and the rule that **a memory diff is reviewed like
  code** and that retrieved memory is evidence, never an instruction channel.

#### Step 1.4 — ignore the local tier
- **File:** `.gitignore`
- **Action:** Modify — append `.claude/agent-memory-local/` with the same
  "runtime state is never a source artifact" reasoning the neighbouring entries carry.

### P2 — Skill-listing budget

#### Step 2.0 — record the primary sources first
- **File:** `.claude/reports/research/skill-listing-budget-2026-09-06.md`
- **Action:** Create — the verbatim `skillListingBudgetFraction` /
  `skillListingMaxDescChars` quotes from
  <https://code.claude.com/docs/en/settings-reference> and
  <https://code.claude.com/docs/en/skills> (verified via context7, not from model memory),
  plus the measurement: 80 skills = 11,256 chars, 57 commands = 4,942 chars, total 16,198
  ≈ **4,050 tokens** against the documented 0.01 default = 2,000 tokens — the listing is
  roughly **double** its budget today. The 200,000-token window is recorded there as an
  **assumption**, because the docs express the setting only as a fraction.

#### Step 2.1 — raise the listing fraction
- **File:** `.claude/settings.json`
- **Action:** Modify — add top-level `"skillListingBudgetFraction": 0.03` and
  `"skillListingMaxDescChars": 1536`. Measured today: skill descriptions 8,817 chars +
  **one measurement, used everywhere in this plan**: `description` + `when_to_use` across
  **all** 80 `.claude/skills/*/SKILL.md` and 57 `.claude/commands/*.md`, with **no
  exemptions** — 11,256 + 4,942 = **16,198 chars ≈ 4,050 tokens** — against the documented
  0.01 default of 2,000 tokens. Roughly double the budget, so descriptions are being
  dropped now. `0.03` = 6,000 tokens covers it with margin. (The narrower 13,759-char
  figure `context_floor.BUDGETS` gates on excludes `disable-model-invocation` skills and
  `when_to_use`; it answers a different question and is not used here.) (Same op also wires P6; see Step 6.2.)

#### Step 2.2 — the ratchet
- **File:** `tests/test_skill_listing_budget.py`
- **Action:** Create — measure `description` + `when_to_use` **from the files**, across
  `.claude/skills/*/SKILL.md` and `.claude/commands/*.md`, and assert the total fits
  `fraction × CONTEXT_WINDOW_TOKENS`. It deliberately does **not** borrow
  `context_floor.BUDGETS`: those budgets exempt `disable-model-invocation` skills and
  ignore `when_to_use`, so they answer a different question (already gated by
  `check-context-floor.py`). `CONTEXT_WINDOW_TOKENS = 200_000` is a **named constant
  carrying a comment that it is an assumption** — the docs give a fraction, never a token
  count. A fourth test pins the per-entry 1,536-char cap. Today: 0 of 80 skills declare
  `when_to_use`; the test reads it anyway so the first one that does is charged for it.

#### Step 2.3 — `continuous-learning`: keep the flag, fix the lie
- **File:** `.claude/skills/continuous-learning/SKILL.md`
- **Action:** Modify
- **Also edited, so all three copies of the claim agree:**
  `.claude/skills/skills-registry.json` (line ~634, `"Auto-extract reusable patterns from
  sessions and save as skills at session end"`) and
  `.agents/skills/continuous-learning/SKILL.md` (the portable copy, carrying the identical
  description line). Fixing one copy and leaving two is not an honesty fix.
- **Decision (with reasoning): `disable-model-invocation: true` STAYS.** Two reasons, both
  measured. (a) Cost: `skill descriptions` is at 8,817 / 9,000; `model_invisible()`
  (`context_floor.py:59`) exempts this skill, so flipping it charges its 129-char
  description against 183 chars of headroom — spending 70% of the remaining always-on floor
  on one skill. (b) Fit: after this plan the skill is *invoked by name* from the ledger
  README, the proposals README and the SessionStart block; it is an operator runbook, not a
  skill a model should autoselect. What is genuinely broken is the **description**, which
  claims "Stop hook that learns reusable patterns and saves them as skills" — no such Stop
  hook exists and P6 deliberately never writes into `.claude/skills/`. The description is
  rewritten to the truth (propose-only), and the body documents the P3/P4/P6 loop. Rewriting
  the description while keeping the flag costs **zero** floor.

### P3 — A reachable write gate, staled by evidence and not by a clock

- **File:** `.claude/operations/scripts/knowledge-ledger.py`
- **Action:** Modify
- **Details:**
  - `record --verified` is unchanged and remains the **promotion** path (`status: fixed`,
    `verified: true`, rubric threshold intact). `open` becomes the **documented automatic**
    path; it is already ungated.
  - `close` and `record` carry the `evidence:` line through (`render_closed`,
    `render_fixed`, and `cmd_record` passing the prior entry's stamps), so promoting or
    retiring a finding does not drop its provenance.
  - `open` gains `--evidence PATH` (repeatable, repo-relative), stamped at write time into a
    new `evidence: [path@sha256:<hex>, ...]` frontmatter line rendered through the existing
    `render_entry_text` contract and parsed back by the existing `split_files()`. The same
    `FORBIDDEN_FILE_CHARS` refusal applies, so the one-line `key: value` contract cannot be
    broken. Hashing is `hashlib.sha256` — stdlib, no import of `src/`.
  - `prune` gains an **evidence-supersession** rule: an `open`/`regressed` entry whose every
    cited evidence file has a *different* hash than the one stamped (or is gone) is reported
    as `SUPERSEDED` — the code the finding was about has moved on. **Archived only under
    `--apply --supersede`.** Default behaviour is byte-for-byte unchanged: the existing
    invariant "prune never archives an unfixed finding" holds unless an operator opts in.
    `fixed` and `wontfix` entries are never touched by this rule.
  - `--ttl-days N` (default 90) is the **fallback only**, applied solely to `open` entries
    that cite **no** evidence — a clock is what you use when you have nothing to re-derive.
    Same `--supersede` opt-in to archive.
- **Files:** `.claude/knowledge/issues/README.md` — document `--evidence`, the supersession
  rule, the TTL fallback, and **amend the "Never auto-injected" bullet**, which P5 makes
  false: the ledger is now injected at SessionStart, but only as ≤5 open-status one-line
  summaries, capped at 600 tokens, and only after passing `prompt-injection-scanner.sh`.
- **Files:** `tests/test_knowledge_ledger.py` — appended regression tests.

### P4 — Receipt → ledger bridge

- **File:** `.claude/hooks/reflection.py`
- **Action:** Modify
- **Details:** a new `bridge_receipt_to_ledger(entry)` helper plus one call in `main()`
  **after** `record_receipt()` returns and **before** `_emit(entry)`.
  - **Blocking contract untouched:** `record_receipt()` is not modified. The bridge is
    wrapped in `except Exception: pass` and returns nothing; no failure it can produce
    changes `main()`'s return value or writes to stderr. `exit 2` + stderr on refusal is
    reached before the bridge is ever called.
  - **No-op** when `.claude/knowledge/issues/` does not exist (checked first), when
    `knowledge-ledger.py` is absent, or when the subprocess times out.
  - **Sanitized fields only, and the bridge re-applies the boundary itself.**
    `record_receipt()` already ran `_safe_text` over `failedAssumption`, but a boundary
    that holds only when the caller remembered to hold it is not a boundary —
    `bridge_receipt_to_ledger` is a public function a future caller will reach with a raw
    dict. It re-runs `_safe_text(..., required=False)` and returns `False` on `ValueError`,
    so a path-shaped or credential-shaped signature is **refused, not written** (pinned by
    a test using two samples verified today to be rejected). It passes that value as
    `--signature`, `origin=workflow`, and a slug of `reflection-<12 hex of the signature>`
    which satisfies `SLUG_RE`. Nothing raw from the caller's payload is forwarded, and no
    file path is forwarded at all. Invoked as an **argv list, never a shell string**.
  - Duplicate signatures are refused by `cmd_open` (exit 1) and that refusal is ignored —
    idempotence for free.
- **File:** `tests/test_reflection_ledger.py` — appended behavioral test: run
  `reflection.py receipt` in a tmp repo with a tmp ledger dir, assert a `.md` entry appears,
  assert it contains no absolute path and no credential-shaped token, and assert the exit
  code is unchanged.

### P5 — SessionStart retrieval

- **File:** `.claude/hooks/session-memory-context.py` — **Create**. Prints a compact block:
  up to 5 `status: open` ledger entries (one line each, via the ledger's own parser, imported
  by path — never re-implemented) and the **FRESH** entries from `ck memory`
  (`claudekit.memory.check`, imported inside a `try/except ImportError` so a project without
  the package simply gets the ledger half). **STALE and MISSING memories are excluded** —
  current files outrank memories, so a memory that no longer matches the tree must never be
  injected. Hard cap 2,400 chars (≈600 tokens), truncated with an explicit marker. Prints
  **nothing** and exits 0 when both sources are empty. Never raises.
- **File:** `.claude/hooks/session-start.sh` — **Modify**. Capture the helper's stdout, pipe
  it through `$SCRIPT_DIR/prompt-injection-scanner.sh` and print only on rc 0 — the exact
  pattern the neighbouring session-context block already uses — including a one-line
  `(not shown: …)` message on **both** non-zero branches (pattern matched vs scanner
  failed), so a withheld slice is never silent — for the exact reason stated there (retrieved text is evidence, never an instruction channel; this text is written by
  agents). Withhold with a named reason on rc 1 and distinguish scanner failure from
  detection, as that block does. bash-3.2 safe: no `${VAR,,}`, no process substitution.
- **File:** `tests/test_session_memory_context.py` — **Create**. Empty ledger → empty stdout,
  exit 0. Populated ledger → ≤5 lines, ≤2,400 chars. A ledger entry carrying an injection
  phrase → withheld by the scanner (assert it is absent from `session-start.sh` output).

### P6 — Propose-only skill proposals

- **File:** `.claude/operations/scripts/knowledge-ledger.py` — a `propose` subcommand
  (same op as P3). Clusters `open`/`regressed` entries by shared normalized signature
  tokens; when a cluster reaches **≥3** entries it writes
  `.claude/knowledge/proposals/<slug>.md` describing a *candidate* skill: the shared tokens,
  the member slugs, and the manual next step. The slug carries a short hash of the **member
  set**, because two different clusters can share their top three tokens and the second
  would otherwise be skipped as "already proposed". Note the design constraint that forced
  clustering rather than counting: `cmd_open` **refuses a duplicate signature**
  (`knowledge-ledger.py:405-411`), so "the same signature 3 times" is unreachable by
  construction; shared-token clustering is the reachable equivalent. It **never** writes into
  `.claude/skills/` and never runs a generator — hard rule 5, no code change without user
  approval.
- **File:** `.claude/settings.json` — wire `propose` as a **backgrounded, non-blocking**
  Stop-hook step alongside `cost-tracker.sh` (same op as Step 2.1), gated with
  `[ "$ECC_HOOK_PROFILE" = minimal ] && exit 0;` — the same line-1 short-circuit every
  other recording hook uses, which is exactly the divergence a prior reviewer named in
  `rejections/reflection-lifecycle-gates.md`.
- **File:** `.claude/knowledge/proposals/README.md` — **Create**. States that these are
  proposals a human promotes with `ck skill new`, that nothing here is loaded into context,
  that promotion is owner-gated, and that **proposals stay local until promoted**.
- **File:** `.gitignore` (same op as Step 1.4) — ignore
  `.claude/knowledge/proposals/*.md` with a `!.claude/knowledge/proposals/README.md`
  negation. A proposal is a machine's opinion about a cluster of findings, not a reviewed
  artifact; committing every one would put unreviewed prose in the tree. What gets
  committed is what a human decided to make of it.

### Docs

- `CHANGELOG.md` — a **new** hunk inserted directly under `## [Unreleased]`, above the
  existing unstaged `restore-backup.py` entry, which is left byte-for-byte alone.
- `docs/LEARNING_LOOP.md` — **Create**. The user-facing page: the four stores and who owns
  which, the receipt → ledger → proposal flow, the SessionStart injection and its cap, and
  how to turn each piece off. No component counts appear on this page.
- `.ai/SESSION_STATE.md`, `.ai/CHANGELOG_AI.md` — session entries.
- **Counts are never hand-edited**; `python3 scripts/gen-docs.py --check` is a gate below.

---

## Testing Strategy

Per phase, run exactly:

| Phase | Commands |
|---|---|
| P1 | `python3 scripts/gen-registry.py --check` · `python3 scripts/gen-model-policy.py --check` · `python3 scripts/check-context-floor.py` (must stay under `pipeline agent bodies` 43,000) · `python3 -m pytest tests/test_agent_tool_grant_drift.py tests/test_structure.py -q` |
| P2 | `python3 -m pytest tests/test_skill_listing_budget.py tests/test_context_floor.py tests/test_skill_loading_contract.py -q` · `python3 -c "import json;json.load(open('.claude/settings.json'))"` |
| P3 | `python3 -m pytest tests/test_knowledge_ledger.py -q` · `ruff check .claude/operations/scripts/` |
| P4 | `python3 -m pytest tests/test_reflection_ledger.py tests/test_reflection_gate.py -q` (the gate suite proves the blocking contract is unchanged) |
| P5 | `python3 -m pytest tests/test_session_memory_context.py tests/test_session_context_scan.py -q` · `shellcheck install.sh .claude/hooks/*.sh` · `python3 scripts/check-context-floor.py` |
| P6 | `python3 -m pytest tests/test_knowledge_ledger.py tests/test_hook_delivery.py -q` |
| All | `python3 -m pytest tests/ -q` · `ruff check src/ tests/ scripts/ .claude/operations/scripts/` · `mypy` · `python3 scripts/gen-docs.py --check` · `python3 scripts/check-plan-artifacts.py --check` · `ck doctor --strict` |

Behavioral over structural throughout: every new test runs the real script or hook in a
subprocess against a tmp tree and asserts files and exit codes, per this repo's convention.

## Rollback Plan

- The executor backs up every touched file; `python3 .claude/operations/scripts/restore-backup.py --list` then restore by plan slug. (That script is owned by another session — **read it, do not edit it**.)
- Or `git checkout -- <path>` per file; the branch is `feat/agent-memory-learning` and no
  operation deletes anything.
- Partial rollback by phase: P1 is 8 independent files; P2 is `.claude/settings.json` +
  one new test; P4 is a single helper plus one call site; P5/P6 are additive.
- Behavioral kill switches without a revert: remove `memory:` lines (P1), drop the
  `skillListing*` keys (P2), delete the Stop entry (P6), delete `session-memory-context.py`
  — `session-start.sh` degrades to silence when the helper is missing (P5).

## Risk Assessment

**High**
- *Context floor breach on the pipeline agents.* `pipeline agent bodies` has 70 chars of
  headroom; this plan spends 32 and forbids body edits to `planner.md`/`reviewer.md`
  precisely because of it. If `check-context-floor.py` fails after P1, the `memory:` line on
  those two is the thing to drop — not a budget raise (budgets need owner sign-off).
- *Memory poisoning.* `.claude/agent-memory/*/MEMORY.md` is auto-injected into an agent's
  system prompt and is writable by any agent run. Mitigations: the file is **committed and
  diff-reviewed like code** (README states it as the rule), the recording policy forbids
  secrets and absolute paths, and the SessionStart path (P5) — the only *automatic*
  injection this plan adds — is scanned by `prompt-injection-scanner.sh` and capped.
  `reflection.py::_safe_text` remains the trust boundary on the P4 path.

**Medium**
- *`prune` archiving a live finding.* The exact failure a prior reviewer named. Mitigated by
  making supersession **opt-in** (`--supersede`): default `prune` output and exit codes are
  unchanged, and `tests/test_knowledge_ledger.py` pins that.
- *`session-memory-context.py` mutates `sys.path`.* It inserts the repo's `src/` to reach
  `claudekit.memory` and removes it again in a `finally`, so no later import in that
  process silently resolves differently.
- *Blast radius of `knowledge-ledger.py`.* It is edited by both P3 and P6 in a single
  `code_edit` op with independent anchors; `.claude/project-graph.json` is gitignored and
  absent, so no hub query was possible (`project-graph.py` exits 3) — recorded here rather
  than claimed. Boundary-crossing files touched: `.claude/settings.json` (hook wiring) and
  `.claude/hooks/reflection.py` (blocking hook) → routed to the reviewer.
- *SessionStart latency.* One `parse_entry` pass over a small directory plus an in-process
  `claudekit.memory.check`; no subprocess. Bounded by the 600 s default hook timeout with
  enormous margin, and the helper never raises.

**Low**
- `memory:` frontmatter is inert when auto-memory is disabled — degradation, not breakage.
- `skillListing*` keys are additive settings; a JSON parse test guards the edit.
- The docs page and the two `.ai` files carry no counts, so `gen-docs.py --check` is
  unaffected by them.

---

## Operations

Config: `.claude/plans/plan-agent-memory-learning.ops.json` — **28 operations, 0 deletions,
0 `run_command`** (no `python3` in `ALLOWED_RUN_COMMANDS`, so every gate above is a manual
verification step). Every path it writes is named in this document.

## Post-review corrections (Tier 1, executed after the APPROVED 94 record)

Two follow-up configs fixed defects found by execution and by the `code-reviewer` diff pass.
They write only paths already named above plus one new test:

- `plan-agent-memory-learning-splice-fix.ops.json` — five `add_after` insertions in
  `.claude/hooks/reflection.py` and `.claude/operations/scripts/knowledge-ledger.py` lacked a
  leading newline (the executor concatenates verbatim); restored with `find`/`replace`.
- `plan-agent-memory-learning-review-fixes.ops.json` / `-2.ops.json` — the same splice in the
  `memory: project` frontmatter of all seven agents and in `.claude/settings.json`; a read-side
  `_safe_text` boundary in `.claude/hooks/session-memory-context.py`; a poisoning regression in
  `tests/test_session_memory_context.py`; a scanner-honesty note in `docs/LEARNING_LOOP.md`; and
  the new structural ratchet `tests/test_agent_frontmatter.py` (every agent frontmatter line must
  parse; the seven documented agents must declare `memory: project`).
- `plan-agent-memory-learning-gate-fixes.ops.json` — the full-suite gates the review did not
  run: `tests/test_behavior_spec.py` (KNOWN_KEYS gains `memory`); the `propose` Stop entry
  moves out of `.claude/settings.json` into a guarded block in `.claude/hooks/cost-tracker.sh`
  (every wired command must be a counted hook); `.claude/hooks/session-memory-context.py`
  names its one swallowed failure on stderr; `tests/test_doctor_gate.py` expects the second
  invoked helper; `docs/LEARNING_LOOP.md` off-switch row updated; and this section of
  `.claude/plans/plan-agent-memory-learning.md` itself (so does `-plan-note.ops.json`).
- `plan-agent-memory-learning-changelog-splice.ops.json` — restores the newline between
  `## [Unreleased]` and its first bullet in `CHANGELOG.md`; removes the undeclared
  `ECC_HOOK_PROFILE` guard from the `propose` block in `.claude/hooks/cost-tracker.sh`
  (`cost-tracker` is not a `GUARDED_HOOK`); updates the row in
  `.claude/plans/archive/README.md` and this list.
