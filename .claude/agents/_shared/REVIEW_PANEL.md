# /review panel (default; `--no-panel` or `CK_REVIEW_PANEL=off` skips it)

Two zero-context critics run beside `reviewer`, in the SAME message as the reviewer spawn so all
three run in parallel: `plan-design-critic` (contradictions, unmitigated risks, security, scope) and
`plan-readiness-critic` (choices left to the implementer, failure paths, missing files/tests). Each
gets only `Plan: <absolute plan path>. Review it.` — no conversation context, no reviewer output, no
plan-writer prose summary. Measured (2026-11-05, 12 seeded defects): reviewer alone 5/12, reviewer +
both critics 8/12.

## Flow (`/review` steps 1-4; `.claude/operations/scripts/review-panel.py`)

1. `review-panel.py prompts $ARGUMENTS` prints `PLAN:`, `PANEL: on|off (<why>)` and the exact
   `CRITIC_PROMPT:` line (realpath of the plan). Off when `--no-panel`, or env `CK_REVIEW_PANEL` is
   `0`, `off` or `false`. Each call logs one row to `.claude/hooks/.state/review-panel.jsonl`.
2. Spawn reviewer + both critics in one message; critics get `CRITIC_PROMPT` verbatim.
3. Record reviewer only (`review-record.py plan-write … --from-task <reviewer agentId>`).
4. `review-panel.py merge <PLAN> --reviewer <id> --critic <name>=<id>...` prints the panel block.

Scripted path: `claude -p --agent <critic> --allowedTools "Read,Grep"` with the same one-line
prompt, run after the reviewer call, saved to `.claude/plans/<slug>.panel-<critic>.md` and merged
with `--critic <name>=<file>` (there `omitClaudeMd` is ignored, so CLAUDE.md still loads).

## Enforcement

- `panel-guard.py` (PreToolUse, blocking): a critic spawn whose prompt is not exactly
  `Plan: <abs path>.md. Review it.` naming an existing file is denied. A reviewer spawn on a plan
  gets a one-line nudge to spawn both critics in the same message.
- Critic frontmatter `hooks:` — `critic-read-scope.py` (PreToolUse Read|Grep|Glob) denies reads
  outside the project and of review/panel siblings, hook state, reports, briefs, session context
  and handoffs; `panel-format-check.py` (Stop → SubagentStop) re-asks once when the reply is over
  3,000 chars or lacks the final `PANEL:` line.

## Output and dedup

The panel is ADVISORY. Only `reviewer`'s `=== REVIEW ===` block is recorded (step 3), so the
`/implement` gate is unchanged; never paste critic text into that block. `merge` prints:

```
=== PANEL ===
<critic>-r<round>-<n> <critic>: [Blocker|Major] <finding>   (only findings reviewer's ISSUES do not cover)
PANEL: <n> blocker, <n> major (uncovered)[, <n> covered]; round <k>; <stop line>
=== END PANEL ===
```

A critic finding is *covered* when one reviewer `ISSUES:` line shares at least one path-like token
(`*.md|py|sh|json|ts|js|yml|yaml` or `§…`) AND at least 3 lower-cased content words of 5+ letters
with it. A critic reply that is empty, an API error, over 3,000 chars or without a final
`PANEL: <n> blocker, <n> major` line is printed as `<critic>: incomplete (<reason>)` and never
retried in the same round (the Stop hook already re-asked once). `PANEL: incomplete` from the
critic is reported as such. `, <n> covered` is added when n > 0 covered findings were hidden.

## Stop rule (EGM)

Rounds are kept per plan in `.claude/hooks/.state/review-panel-rounds.json`; a round is added only
when the plan bytes changed (re-running `merge` on the same plan updates that round). A clean round
has 0 Blocker and 0 Major from valid critics, covered or not: dedup only decides what is printed,
never the stop line (a covered Blocker still blocks "clean" and counts for "no new Blocker"). The stop line is one of:

- `STOP: 2 consecutive clean rounds`
- `STOP: round <k> raised no new Blocker — stop re-reviewing; carry remaining Majors as follow-ups`
- `CAP: round 5 — list open findings and ask the owner`
- `CONTINUE: fix uncovered Blockers, then re-run /review`

If the panel has any uncovered Blocker and the line says CONTINUE: fix it in the plan and re-run
`/review` before `/implement`, whatever reviewer scored (advisory — the gate does not enforce it; say so).
