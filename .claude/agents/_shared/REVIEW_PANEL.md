# /review panel (default; `--no-panel` skips it)

Two zero-context critics run beside `reviewer`, in the SAME message as the reviewer spawn so all
three run in parallel: `plan-design-critic` (contradictions, unmitigated risks, security, scope) and
`plan-readiness-critic` (choices left to the implementer, failure paths, missing files/tests). Each
gets only `Plan: <plan path>. Review it.` — no conversation context, no reviewer output, no plan-writer prose
summary. Scripted path: `claude -p --agent <critic> --allowedTools "Read,Grep"` with the same
one-line prompt, run after the reviewer call (there `omitClaudeMd` is ignored, so CLAUDE.md
still loads). Measured (2026-11-05, 12 seeded defects): reviewer alone
5/12, reviewer + both critics 8/12.

The panel is ADVISORY. Only `reviewer`'s `=== REVIEW ===` block is recorded (step 2), so the
`/implement` gate is unchanged; never paste critic text into that block. After the reviewer output,
print:

```
=== PANEL ===
<critic>: [Blocker|Major] <finding> — <scope>     (only findings reviewer's ISSUES do not already cover)
PANEL: <n> blocker, <n> major (uncovered)
=== END PANEL ===
```

Read only each critic's last non-empty line. `PANEL: <n> blocker, <n> major` is valid; anything else (timeout, crash, missing plan, no or malformed line, the critic's own `PANEL: incomplete - <reason>`) is reported `PANEL: incomplete`, never retried in the same round, never blocks. A `PANEL:` line anywhere but last is ignored. If the reply has more `**Blocker**`/`**Major**` finding lines than that line counts, the larger number is the critic's total; the uncovered counts in the summary are drawn from that total (deduplication can only lower them).

After the output, if the panel has any uncovered Blocker: fix it in the plan and re-run `/review` before `/implement`, whatever reviewer scored (advisory — the gate does not enforce it; say so).
