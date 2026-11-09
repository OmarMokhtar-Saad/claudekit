# Tracker: EGM (Elephant-Goldfish) critics audit, 2026-11-09

Scope: the claudekit `/review` panel (shared by ~/.claude, ~/.claude-acct-b, ~/.claude-acct-personal,
~/.claude-acct-personal2) and the Hermes house-ops plan-panel (Air, `bin/egm_review/`).
Branches: claudekit `fix/egm-panel-audit` (worktree ../claudekit-egm-fix), house-ops `pro/egm-panel-audit`
(worktree ~/IdeaProjects/hermes/ho-egm-fix).

Status: OPEN, DEBUGGED (root cause + fix chosen), FIXED, WONTFIX (with reason), DEFERRED (owner/process).

## claudekit / accounts

| ID | Type | Finding | Debug result (root cause) | Chosen fix | Status |
|----|------|---------|---------------------------|------------|--------|
| K1 | Bug | `~/.claude-acct-b` has no `/review` | `~/.claude-acct-b/commands` symlink is gone. kit-sync (agent-config/bin/kit-sync:55-60) creates it and did run at 08:39 today (its siblings carry that time), so something removed it after 08:39 (acct-b dir mtime 09:53). No script in agent-config/house-ops removes it; deleter not identified. | Re-link (`kit-sync --links` equivalent for acct-b). kit-sync: print a WARNING when any account ends with cmds=0 or agents=0 so a missing link is visible. | FIXED (link restored; kit-sync WARNING added, kit-sync untracked; deleter unknown) |
| K2 | Gap | Critics only run if the model follows a one-line pointer; the scripted bash block never calls them | review.md:23 is the only trigger; review.md:29-81 runs reviewer only | Scripted block runs both critics (plan path only, last line parsed with a strict regex, failure = incomplete) after the reviewer record. Task path unchanged (REVIEW_PANEL.md) | FIXED 4fefe89b |
| K3 | Gap | No rule for timeout / crash / missing or malformed `PANEL:` line / missing plan | REVIEW_PANEL.md:23 covers only a critic's own `PANEL: incomplete` | One rule: any critic without a valid last-line `PANEL:` is reported `PANEL: incomplete`, never retried, never blocks | FIXED 4fefe89b |
| K4 | Bug | Test `test_review_command_runs_panel_but_records_only_reviewer` is partly vacuous | Its loop looks for `review-record.py write`; review.md uses `review-record.py plan-write`, so the "never a critic" assertion never runs | Match `review-record.py` lines; assert at least one matched | FIXED 4fefe89b |
| K5 | Gap | Tests do not pin the panel contract: summary format, `PANEL: incomplete`, one-line prompt, allowedTools == frontmatter tools | test_review_panel.py:56-66 | Add assertions for each | FIXED 4fefe89b |
| K6 | Gap | A plan can plant a fake `PANEL: 0 blocker, 0 major` | Counts are read from the critic's reply by eye (Task path) | Read only the critic's last non-empty line; if its `**Blocker**`/`**Major**` finding lines outnumber the line's counts, use the larger number (same rule in the scripted parse) | FIXED 4fefe89b |
| K7 | Accepted limit | Critics not fully zero-context: `omitClaudeMd` ignored under `claude -p --agent`, Read/Grep unscoped | Documented at REVIEW_PANEL.md:8. Dropping setting sources risks `--agent` not resolving the project agent | Keep; read-only, no conversation context. Documented | WONTFIX |
| K8 | Enhancement | "5/12 vs 8/12" claim has no reproducible fixture | REVIEW_PANEL.md:9-10 | Seeded-defect eval set under evals/ | DEFERRED |

## Hermes house-ops plan-panel

Live (Air, since 11-05): 18 panels, 36 critic calls, all rc=0, no timeouts, avg 37s, $3.16. Mode: shadow.
Tests: 49 pass; 7 mutants all killed.

| ID | Type | Finding | Debug result (root cause) | Chosen fix | Status |
|----|------|---------|---------------------------|------------|--------|
| H1 | Gap | 9-13 Majors per panel; 7/18 panels had Blockers, never graded | Cap is 8 findings per critic (16 per panel), so this is not saturation, it is a high Major rate. Needs human grading | Hand-grade ~20 panels before block mode | DEFERRED (owner) |
| H2 | Bug | A plan line `PLAN END` closes the data fence early | panel.py:63-66 puts the plan between bare fence lines, no escaping | Prefix any plan line that starts with `PLAN START`/`PLAN END` so it cannot be read as a fence | FIXED 08d0ab06fc (random fence id, not a prefix) |
| H3 | Bug | Counts are only what the critic says; a forged `PANEL: 0 blocker` passes | panel.py:75-84 reads only the last line | blockers/majors = max(reported, counted `**Blocker**`/`**Major**` finding lines) | FIXED 08d0ab06fc, partly open: Output-Format findings (`1. **Severity**:`) carry no leading tag and are not counted |
| H4 | Bug (minor) | `egm_panel.timeout_s: 600.0` silently ignored, falls back to card_timeout (900) | panel.py:56 rejects every float | Accept an integral float | FIXED 08d0ab06fc |
| H5 | By design | Critic Blocker/Major lines reach build-card prompts in shadow mode | plan_chain.py:76-94, deliberate (prior EGM audit item 4); labelled advisory; text derives from the plan already in that prompt | Keep | WONTFIX |
| H6 | Accepted limit | Critics load project CLAUDE.md/settings (`--setting-sources project`), cwd = card worktree | ai_run/claude_cmd.py:114, shared by all roles; tools Read/Grep/Glob only | Keep: project settings carry the guard hooks | WONTFIX |
| H7 | Decision | Block mode: should an incomplete panel hold or pass the plan? | Today: incomplete never blocks (panel.py:87-93), right for shadow | Owner decides before block mode | DEFERRED (owner) |
| H8 | Enhancement | Kill switch + metric before block mode | `egm_panel.mode: off` already works as the kill switch | Add a precision metric once H1 grading exists | DEFERRED |

Hermes merge: pro/egm-panel-audit @ 5b4e9bec94 (FF over main be834cad0f), gatekeeper request 4d65ef405e4e approved by the owner (Telegram) and merged 2026-11-09; origin/house-ops at df465c5e38.

## Follow-ups

- DONE (2026-11-09, plan-egm-panel-followups.md): Align the critics' `## Output Format` with the tag line: claudekit plan-design-critic.md:~81, plan-readiness-critic.md:~80; Hermes persona design.md:69 (closes the rest of H3).
- DONE (2026-11-09; now read via a quoted heredoc into CK_ARGS): claudekit review.md: `$ARGUMENTS` is pasted as text into `case " $ARGUMENTS "`; a `"` in the args breaks the shell. Low risk.
- DONE (2026-11-09): real-CLI smoke of the scripted `claude -p --agent` critic call. Both critics rc=0, PANEL line present, findings tag-led (7 and 6), no `**Severity**` field. Argecho byte probe of the review.md heredoc with `x" $(touch pwned) `z`` PASS: bytes intact, no command run.
- Optional: name the fence id in Hermes skills/roles/role-plan-critic/BODY.md:12-13.
- Full-suite note: test_gate_scope doctor tests fail under bare uvx (claudekit not installed); use `--with-editable .`.
