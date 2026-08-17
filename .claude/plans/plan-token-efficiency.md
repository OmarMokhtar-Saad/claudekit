# Plan: Token Efficiency Program (verified 2026-08-17)

**Status:** DRAFT — awaiting owner approval (Golden Rule). No code changed yet.
**Goal:** high quality, less tokens, faster pipeline — for ClaudeKit itself and kitted projects (e.g. AppiumLens).
**Evidence:** all numbers below measured on this filesystem, not estimated. Research cache: `.claude/reports/research/multi-agent-token-efficiency-2026.md`.

## Measured baselines

- Always-on floor: ~12k tokens/session (agent descriptions 22,046 chars — 70% of that is `<example>` blocks: 15,568 chars ≈ 3,890 tok; skill descriptions ~2.9k tok; CLAUDE.md ~1.8k tok).
- Per-pipeline floor: ~15k tokens (planner.md + reviewer.md + implementer.md = 38,334 chars; CLAUDE.md re-injected into 3 subagents = 21,117 chars).
- ops.json payload is paid ~3x (opus writes it; reviewer and implementer each re-read it whole). Largest archived: ops-task-014.json = 52.6 KB ≈ 13.1k tok, of which 58% was a hand-transcribed pip lockfile.
- 48 archived code_edit ops target 737 KB of source ≈ 184k tokens if fully Read for anchor extraction. CHANGELOG.md (44.5 KB) targeted in 6/6 plans.
- Find-anchors are only 12% of payload — the ops.json *format* is efficient; the leaks are elsewhere. Do NOT replace the format.

## Ranked changes

### 1. Planner anchor extraction via grep (HIGH, prompt-only, no contract change)
Edit `.claude/agents/planner.md`: instruct the planner to locate find/replace anchors
with `grep -n -C3 <pattern> <file>` instead of Reading whole files; full Read only when
file <200 lines or the change is structural. Add explicit CHANGELOG guidance (append-entry
ops never need a full Read). Est. saving: tens of thousands of tokens on large-file plans.

### 2. Strip agent-description `<example>` blocks (HIGH, ~3.9k tok off every context)
Remove `<example>` blocks from agent frontmatter descriptions for all agents except the
genuinely confusable pairs (keep ≤1 example each): reviewer vs code-reviewer,
doc-updater vs documenter, planner vs Plan. First line of each description already routes.
Touches ~29 files in `.claude/agents/`; run gen-docs/gen-registry checks after.

### 3. Add `run_command` op type (MEDIUM saving, MEDIUM risk — needs its own plan + owner sign-off)
`validate-config-json.py:414` allows only file_create/file_delete/code_edit — generated
content (lockfiles, formatter output, codegen) must be hand-transcribed by opus.
Add allowlisted `run_command` (pip-compile, formatters, codegen only; denylist + Iron Law
review; hooks must gate it). The task-014 lockfile alone was ~7.6k opus output tokens.

### 4. Blast-radius fast-path tiering (MEDIUM, CLAUDE.md edit)
Replace "≤2 lines OR purely cosmetic" with:
- Tier 1: single file, no public API/security/schema surface → minimal ops.json, validate, execute (no planner/reviewer).
- Tier 2: multi-file, no security/schema → planner + ops.json; reviewer only if architecture touched.
- Tier 3: security/migrations/>15 ops/>2 phases → full pipeline.

### 5. Reviewer reads op manifest, not content bytes (MEDIUM)
Edit `.claude/agents/reviewer.md`: score against a manifest (op id/type/path/description
+ anchors) rather than re-reading full ops.json content; spot-check ≤3 ops' bodies.
Saves ~1 full payload per pipeline.

### 6. CI floor gate (makes 1–5 permanent)
`scripts/check-context-floor.py --check` printing the always-on floor table and failing
above a budget — same pattern as gen-docs drift gate. Slots into task 010.

### Dropped
- Plan/ops duplication validator: measured only 10/257 anchors duplicated (4%), false-positive risk inverts cost/benefit.
- CLAUDE.md split by consumer: defer; hard rules must stay global, realistic saving ~half the claim.

## Order of execution
1 → 2 (independent, low-risk, prompt/frontmatter only) → 4 → 5 → 6 → 3 (own plan).

## Verification per DoD
pytest -q · ruff · mypy · gen-docs --check · gen-registry --check · shellcheck · ck doctor --strict.
For #2: registry drift gate is the main risk. For #1/#5: archive a before/after pipeline token count.
