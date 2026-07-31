# Plan: Token-Waste Workflow Fixes (6 issues)

**Status:** Ready for review
**Created:** 2026-07-31
**Origin:** Transcript analysis of the 2026-07-30/31 session burn (80.3M billed context
tokens in one claudekit session, 381 API calls). This plan fixes the claudekit-side causes.
**Scope:** Prompt/command/hook changes in this repo only. Global settings (`opus[1m]`,
plugins) are handled by a separate effort — NOT part of this plan.

---

## Measured evidence (do not re-derive; verify spot-checks only)

Session `57e7399b` (~/.claude/projects/-Users-omarmokhtar-IdeaProjects-claudekit/):

| Finding | Number |
|---|---|
| Billed context tokens, whole session | 80.3M over 381 API calls |
| Write-tool inputs pinned in context | 122,746 chars (~31k tok) → 8.3M lifetime cost |
| Largest single Writes | ops-hardening-implementer-contract.json written at 42,665 chars, then REWRITTEN at 29,199 chars; ops-review-approval-binding.json 18,931 chars |
| Bash heredoc inputs (plans pasted into reviewer messages) | ~26k tok → 3.9M lifetime |
| Subagent preload (per existing task-009 measurement) | 16,120 lines of skills across 18 agents; coordinator alone ~27k tok |

Root pattern: the "stdout is the delivery contract" design routes full plan+ops.json
payloads through the MAIN session context 2–3 times per planning cycle, where they stay
pinned for every subsequent turn. The machinery to avoid this already exists
(`.claude/operations/scripts/extract-json-from-plan.py`, validators, reviewer has Read).

**New contract to enforce everywhere (the one-line summary of this plan):**
> Subagent handoffs pass FILE PATHS, never file bodies. Payloads live on disk; context
> carries pointers, summaries, and verdicts only.

---

## Issue 1 — `/plan` scripted path leaks the full plan via `tee`

**File:** `.claude/commands/plan.md` (line ~58)

**Problem:** `echo "$plan_output" | tee "$PLAN_FILE"` prints the entire plan+ops.json to
stdout, so the full payload lands in the main context as a Bash tool result — in the very
path designed to keep it out.

**Change:**
- Replace the `tee` with a silent write: `printf '%s\n' "$plan_output" > "$PLAN_FILE"`.
- Keep extract + validate in the SAME bash block (already the case, lines 63–66).
- Final stdout of the block must be ONLY: plan path, ops path, validation verdict,
  op count (parse with `python3 -c` from the ops file), and the plan's first 3 summary
  lines. Target ≤ 15 lines total.

**Acceptance:** running the scripted block on a dummy planner output produces a saved
plan file, a validated ops file, and ≤15 lines of stdout. No full plan text in stdout.

---

## Issue 2 — `/plan` interactive path makes the main agent re-type the plan

**File:** `.claude/commands/plan.md` (lines ~24–30, "Invocation — interactive")

**Problem:** Step 1 tells the planner to "Return the complete plan document and ops.json
in your final response" (→ full payload arrives as the Agent tool result, pinned). Step 2
tells the main agent to "Save the returned plan" (→ main agent re-types the full payload
through Write — the observed 42,665-char Write). The `.claude/**` sensitive-path gate that
justifies this contract is HEADLESS-ONLY; interactive Task-tool subagents share session
permissions, and `config-protection.sh` does not cover `.claude/plans/` (verified by grep).

**Change:** Rewrite the interactive invocation to:
1. Spawn planner via Task tool with Write access, instructing it to **write
   `.claude/plans/plan-<slug>.md` and `.claude/plans/ops-<slug>.json` itself**, run
   `python3 .claude/operations/scripts/validate-config-json.py` on the ops file, and
   return ONLY: both paths, validation verdict, op count, and a ≤10-line plan summary.
2. Main agent then runs one Bash call re-validating the ops file (trust but verify) and
   reports paths + verdict. It must NOT Read the plan back unless the user asks.

**Implementation note (verify first):** confirm an interactive Task-spawned agent can
Write into `.claude/plans/` in this repo with `ECC_HOOK_PROFILE=minimal`
(settings.local.json). If any hook blocks it, add a narrow allowlist for
`.claude/plans/*.{md,json}` to that hook instead of widening anything else — and record
which hook it was in the commit message. If it cannot be unblocked safely, fall back to:
planner returns payload, but the SAVE happens by redirecting the Task result through a
single `bash` heredoc written by a HAIKU-model subagent, never the main agent.

**Acceptance:** run `/plan` on a toy task in a scratch session: main-session transcript
contains no Write/tool-result block over 2,000 chars originating from plan content; plan
+ ops files exist on disk and validate.

---

## Issue 3 — `/refine` loop relies on shell variables that don't persist across Bash calls

**File:** `.claude/commands/refine.md` (whole Cycle A/B structure, lines ~95–170)

**Problem (two parts):**
- The loop stores the plan in `current_plan=$(...)` in one Bash call and consumes it in a
  LATER Bash call (`PLAN TO REVIEW: $current_plan`). Shell state does not persist between
  Bash tool calls, so the main agent pastes the entire plan into the reviewer message by
  hand — the observed ~26k tokens of Bash heredocs.
- `echo "$current_plan"` after each planner spawn dumps the full plan into context again,
  and iteration 2+ asks the planner to "Produce the complete revised plan and a new
  ops.json" — full re-emission every iteration (observed: same ops file written at 42k
  then 29k chars).

**Change:** restructure `/refine` around files:
1. **Single-script option (preferred):** the entire refine loop (plan → save → review →
   revise → re-score, up to MAX_ITER) becomes ONE self-contained bash script executed in
   ONE Bash call. Plans/ops live on disk; each `claude -p` spawn reads/writes files; the
   script's stdout is only the per-iteration scoreboard (iteration, score, decision,
   critical/major count) and final file paths. The existing anti-anchoring rule (fresh
   reviewer context, no prior-history leakage) is preserved automatically because each
   spawn only receives the file path, not conversation history.
2. Reviewer message becomes: "Review the implementation plan at `<PLAN_FILE>` and ops
   config at `<OPS_FILE>`. Read them yourself." — reviewer `--allowedTools` already
   includes Read; add the two paths to the message, delete the `$current_plan`
   interpolation entirely.
3. Revision message becomes: "Revise the plan at `<PLAN_FILE>` addressing the issues
   below. EDIT the existing files in place (or rewrite on disk); do not print their
   contents. Return a ≤10-line change summary." Grant the headless planner spawn write
   access to the two files via `--allowedTools "Read,Grep,Glob,Write,Bash(python3
   .claude/operations/scripts/validate-config-json.py *)"` — if the headless
   sensitive-path gate blocks Write into `.claude/plans/`, have the spawn write to
   `.claude/plans/tmp/` (gate-exempt? verify) or a scratch dir, and let the SCRIPT move
   the file into place. The script, not the model, moves bytes.
4. Keep the existing loop-state HARD RULES (fresh score each iteration) — they are
   compatible with this change and must not be weakened.

**Acceptance:** a full 2-iteration `/refine` run on a toy task adds < 3k tokens of
tool-result/tool-input content to the main session (scoreboard + paths only). Reviewer
scores appear each iteration. Plan/ops files on disk validate.

---

## Issue 4 — Codify the path-not-payload contract in the shared docs

**Files:** `.claude/agents/_shared/INVOCATION.md`, `.claude/agents/HANDOFF_PROTOCOL.md`,
`.claude/agents/planner.md`, plus the other ops.json-flow commands:
`.claude/commands/implement.md`, `review.md`, `migrate.md`, `rollback.md`.

**Problem:** the leak pattern is prescribed in the shared contracts, so fixing /plan and
/refine alone leaves /implement, /review, /migrate to regress the same way.

**Change:**
- INVOCATION.md: add a "Delivery contract" section stating the rule verbatim: handoffs
  pass file paths + ≤10-line summaries; full file bodies in a subagent response, an Agent
  tool result, or a Bash echo are a contract violation; interactive spawns write files
  themselves; headless spawns deliver via stdout ONLY when a wrapper script immediately
  redirects to disk without teeing.
- HANDOFF_PROTOCOL.md: same rule in its handoff checklist.
- planner.md: delivery section (~lines 193–201) rewritten: interactive → write both files,
  return paths + summary; headless → emit payload knowing the wrapper captures it; NEVER
  instruct "return the complete plan" for interactive spawns. Revision requests edit
  in place.
- implement.md / review.md / migrate.md / rollback.md: audit each for `tee`, `echo "$..."`
  of captured payloads, "return the complete …" phrasing, and "PLAN TO REVIEW: $var"
  interpolation; apply the same path-based pattern. (Reviewer of this plan: treat this as
  a checklist item per file, not optional.)

**Acceptance:** `grep -rn 'tee \|echo "\$' .claude/commands/*.md` shows no remaining case
where a captured subagent payload is re-printed; every "Review/implement the following"
message passes paths.

---

## Issue 5 — `suggest-compact.sh` output never reaches the model

**Files:** `.claude/hooks/suggest-compact.sh`, `.claude/settings.json` (PreToolUse entry
with empty matcher, lines ~85–93).

**Problem (two independent bugs):**
1. It is registered as PreToolUse — PreToolUse stdout is never shown to the model.
2. The script emits its tip from a backgrounded subshell (`{ ... } &`, line 13/60) and the
   settings entry ALSO appends `&` — stdout is detached and lost regardless of event type.
The one hook meant to fight context bloat has been a no-op, while sessions sat at 300k+.

**Change:**
- Move the settings entry from PreToolUse to **PostToolUse** (matcher `""` or
  `Edit|Write|Bash`), WITHOUT the trailing `&`.
- Restructure the script: counter increment/lock logic may stay backgrounded, but compute
  the count synchronously first and emit the CONTEXT TIP from the FOREGROUND path so
  PostToolUse captures stdout. Keep total runtime < 100ms (it is file-touch only).
- Lower the nudge cadence from every 50 calls to every 40, and strengthen the message:
  "run /compact now unless mid-edit" (the message text is the only compaction lever this
  repo controls; the model decides).
- Keep `exit 0` always (non-blocking; a broken counter must never block tools).

**Acceptance:** in a test session, after 40 tracked tool calls the CONTEXT TIP visibly
arrives as hook output attached to a PostToolUse event (check the session transcript
jsonl, not the terminal). `shellcheck` passes. Hook adds no user-visible latency.

---

## Issue 6 — Implement task 009: lazy skill loading (existing plan)

**STATUS: ALREADY SHIPPED — no work needed.** Verified 2026-07-31 during Phase 6 of this
plan's implementation: `git log` shows task 009 landed in commit `fe7396e`
("feat(corpus): lazy skill loading — 59% preload cut, generated registry", 2026-07-08),
three weeks before this plan's Phase 6 was written. That commit already did everything
this section calls for:
- ≤3 mandatory skills per agent, everything else on-demand with an explicit trigger
  (mandatory preload 16,120 → 6,649 lines, -59%; worst agent 559 lines).
- `scripts/gen-registry.py` derives `agentMapping` from the agent files with a `--check`
  drift gate (18 honest entries, down from 30 with 10 sectionless ghosts + 2 command keys).
- `AGENT_TEMPLATE.md`'s Skill Loading Protocol documents mandatory-vs-on-demand semantics.
- `TestContextBudget` (in `tests/test_behavior_spec.py`) gates all of the above: max-3-
  mandatory, on-demand-entries-declare-triggers, registry-matches-agent-files — all three
  pass as of this verification (`pytest -k ContextBudget`, 3 passed).

**File:** existing design in `.claude/plans/plan-context-budget-lazy-skills.md` — its "Not
in scope" follow-ups (splitting large SKILL.md bodies, usedBy semantics, command-file skill
trimming) remain open but are explicitly out of scope for both that plan and this one.

**Acceptance:** already met — confirmed by the passing `TestContextBudget` suite; no new
commit required for this issue.

---

## Implementation order

| Phase | Issues | Why this order |
|---|---|---|
| 1 | 5 | Smallest, isolated, immediately reduces ongoing burn in every session |
| 2 | 1, 2 | /plan is the entry point of every planning cycle |
| 3 | 3 | /refine builds on the fixed /plan contract |
| 4 | 4 | Codify + sweep remaining commands once the pattern is proven in 1–3 |
| 5 | 6 | ~~Largest; independent of 1–4, do last~~ — already shipped (`fe7396e`, 2026-07-08); no commit needed for this phase |

Each phase = one conventional commit (`fix(commands): …`, `fix(hooks): …`,
`refactor(agents): …`). No phase depends on an unmerged later phase.

## Verification (repo DoD — all must pass per phase)

```bash
python3 -m pytest tests/ -q               # 516 tests, all green
ruff check src/ tests/ scripts/
mypy
python3 scripts/gen-docs.py --check
python3 scripts/gen-registry.py --check
shellcheck install.sh .claude/hooks/*.sh
```

Plus the per-issue acceptance checks above, plus: CHANGELOG `[Unreleased]` entry per
phase; update `.ai/SESSION_STATE.md` + `.ai/CHANGELOG_AI.md` at the end.

**End-to-end smoke test (after phase 3):** run `/plan` then `/refine` on a toy task in a
scratch session; measure with the transcript jsonl that total plan-content bytes entering
the main context are < 3k tokens (was ~90k chars).

## Hard-rule compliance notes (for the reviewer)

- Iron Law preserved: ops.json still gates all implementation; only its TRANSPORT changes
  (disk instead of context). The implementer still never gets Edit/Write.
- Blocking hooks unchanged: suggest-compact is and stays non-blocking exit-0.
- No `--dangerously-skip-permissions` introduced anywhere.
- Protected files untouched; any hook allowlist change is narrow (`.claude/plans/*` only)
  and must be named in the commit message.
- Component counts: only via `gen-docs.py` if any assets are added/renamed (none planned).

## Risks

- **Headless Write gate (issues 2, 3):** the sensitive-path gate's exact scope must be
  verified empirically before committing to the "subagent writes directly" path; both
  issues include a fallback. Do the verification FIRST in phase 2.
- **PostToolUse hook output size:** the CONTEXT TIP itself enters context (~40 tokens
  every 40 calls) — negligible vs. what it saves, but keep the message ≤3 lines.
- **009 regressions:** behavior changes if an agent needed a now-on-demand skill and its
  trigger never fires. Mitigation is in the 009 spec (triggers + behavioral tests); do not
  skip its budget-gate test.

## Out of scope

- Global `~/.claude/settings.json` changes (`opus[1m]`, effortLevel, plugin prune) —
  separate effort, already delegated.
- qa-agents repo CLAUDE.md trim — same separate effort.
- Splitting large SKILL.md bodies (74 skills) — recorded follow-up in the 009 plan.
- `.ai/AGENTS.md` (100KB) split — recommend filing as a new backlog task, not done here.
