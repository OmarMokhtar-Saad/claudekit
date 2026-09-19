---
description: "Write plan.md + ops.json inline; --deep spawns the planner agent"
argument-hint: "[--deep] [task description]"
model: sonnet
---

# Planner Command

**Default: no spawn.** You — the parent session — write `.claude/plans/plan-<slug>.md` and
`.claude/plans/ops-<slug>.json` yourself, from the context you already hold. A planner spawn
pays a second full corpus load: measured 2026-09-19, 98 turns average (worst 572 / 895 K) and
19 % of two days' token spend, mostly re-reading files the parent had already read.

| Mode | What runs | When |
|---|---|---|
| default | you write plan + ops.json inline, then validate | you can name the files the change touches (Tier 1/2) |
| `--deep` | spawns the `planner` agent | the change spans unfamiliar subsystems, or you cannot name those files |

## Task

Create implementation plan for: $ARGUMENTS

If `$ARGUMENTS` begins with `--deep`, strip that flag from the task description and follow
the `--deep` sections below. Otherwise write both files yourself, as follows.

## Default (no `--deep`) — you write both files

1. Name every file the change touches. If you cannot, stop and re-run with `--deep`.
2. Write `.claude/plans/plan-<slug>.md`: overview, scope naming **every path the ops config
   writes** (`scripts/check-plan-artifacts.py` enforces this), implementation steps, a
   `## Validation commands` fenced block, rollback plan, risk assessment.
3. Write `.claude/plans/ops-<slug>.json`. The Iron Law binds the parent too: a plan with no
   ops config is not a plan.
4. `python3 .claude/operations/scripts/validate-config-json.py <ops-file> --stamp-baseline`
5. Report both paths, the verdict and the op count — never the plan body; you just wrote it.

`ck implement <ops-file>` then runs validate -> dry-run -> execute -> the plan's own
validation commands.

## `--deep` — spawn the planner agent

Two mechanisms, both verified (see `.claude/agents/_shared/INVOCATION.md`, single source of
truth). Either way the delivery contract is PATHS + A SHORT SUMMARY, never file bodies.

### `--deep` mechanism A — interactive Task tool (preferred)

No cold boot; shares the session's MCP servers and permission gating. No hook of this session
blocks `.claude/plans/` (`ops-enforcement.sh` allows all of `.claude/**`; `config-protection.sh`
matches only linter/formatter names; `file-guard-gate.sh` is advisory, `strict`-gated — all
three read 2026-07-31), so the planner writes its own files.

1. Spawn with `subagent_type: "planner"` (model: opus) and the task/exploration instructions
   of `PLANNER_MSG` below, plus: "Write the plan to `.claude/plans/plan-<slug>.md` and the
   ops config to `.claude/plans/ops-<slug>.json` yourself using the Write tool. Return ONLY:
   both paths, the op count and a ≤10-line summary — never the plan body or ops.json."
2. Main agent runs `python3 .claude/operations/scripts/validate-config-json.py <ops-file>`
   (the planner has no Bash) and reports paths + verdict. Do NOT Read either file back into
   context unless the user asks to see it.

### `--deep` mechanism B — scripted (claude -p)

Pays ~13s cold boot per spawn. The headless planner cannot write into `.claude/**` (platform
sensitive-path gate, verified 2026-07-08), so its stdout is the delivery contract: the block
below stays SILENT except for the final summary — no `tee`, no echo of `plan_output`.

```bash
PLAN_FILE=".claude/plans/plan-$(date +%Y%m%d-%H%M%S).md"
mkdir -p .claude/plans

PLANNER_MSG="Create a complete implementation plan for the following task.

Task: $ARGUMENTS

Explore with BATCHED parallel Read/Grep/Glob calls — fire all independent searches in ONE
message. Open the plan with a 3-line summary: goal, approach, riskiest step.

IRON LAW: The plan MUST include a valid ops.json."

plan_output=$(echo "$PLANNER_MSG" | claude -p --agent planner --model opus --allowedTools "Read,Grep,Glob,Write")
EXIT_CODE=$?
[ $EXIT_CODE -ne 0 ] && { echo "ERROR: planner failed (exit $EXIT_CODE) — check .claude/agents/planner.md"; exit 1; }

printf '%s\n' "$plan_output" > "$PLAN_FILE"

OPS_FILE="${PLAN_FILE%.md}.ops.json"
python3 .claude/operations/scripts/extract-json-from-plan.py "$PLAN_FILE" --output "$OPS_FILE" \
  && python3 .claude/operations/scripts/validate-config-json.py "$OPS_FILE" > /tmp/plan-validate.$$ 2>&1 \
  || { echo "ERROR: no valid ops.json in planner output — IRON LAW violated, re-run /plan"; exit 1; }

OP_COUNT=$(python3 -c "import json; print(len(json.load(open('$OPS_FILE')).get('operations', [])))" 2>/dev/null || echo "?")
VERDICT=$(grep -m1 '^-> ' /tmp/plan-validate.$$ 2>/dev/null | sed 's/^-> //')
[ -z "$VERDICT" ] && VERDICT="validated"
rm -f /tmp/plan-validate.$$

printf '\nPlan saved to: %s\nOps config:    %s (%s, %s ops)\n\nSummary:\n' \
  "$PLAN_FILE" "$OPS_FILE" "$VERDICT" "$OP_COUNT"
grep -v '^$' "$PLAN_FILE" | head -3
```

Final stdout ≤15 lines: paths, op count, verdict, the plan's first 3 non-blank lines.

After output, suggest:
- `/review` — single-pass review (auto-detects the saved plan file); once APPROVED, run `/implement` from a compacted or fresh context whose only input is the plan path
