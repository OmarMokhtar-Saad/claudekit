# Plan: make the /review EGM panel actually run, stay zero-context, and converge

**Date**: 2026-11-11 | **Requested by**: Omar — "find bugs and gaps … do strong debug web search to find best solution the plan review implement to fix them all" (audit of the EGM panel shipped in c552012, session 9a2b13fa).
**Tier**: 3 (new blocking PreToolUse hook, new subagent-scoped hooks, CLI change in `flow.py`).
**Branch**: `feat/review-panel-fixes` off main 4164961.

## Evidence (audit of 335 critic runs, 3 accounts, 2026-11-05..11)

| # | Finding | Measured |
|---|---|---|
| F1 | `/review` never really starts the critics: one prose line (`review.md:23`), no step | 92/95 reviewer-only sessions spawned `reviewer` alone; `flow.py:178-220`, `coordinator.md:430`, `blueprint.md:78` skip the panel too |
| F2 | Critics think on CLI 2.1.322 | median 9.7k thinking / 16.7k output tokens / 64 s per run (2.1.319: 0 / 1.6k / 19 s, same final length) |
| F3 | Zero-context contract broken | 2/335 prompts were path-only; 118 (personal2) passed a coordinator `brief*.md`; tools `Read, Grep` unscoped |
| F4 | Context-cap hook (`auto-handoff.py`) splits the panel | 151 denials / 68 sessions; 10 sessions had only part of the panel denied; replays dropped critics |
| F5 | Format breaks | 62/335 no `PANEL:` line; 49 over 3,000 chars (parent "300 words" overrides); 2 API errors not marked incomplete |
| F6 | `test_review_panel.py:75` can never fail | matches `review-record.py write`, real text is `plan-write`; deleting `review.md:23` still passes |
| F7 | `--no-panel` never parsed; no on/off setting | review.md has no `$ARGUMENTS` handling |
| F8 | `=== PANEL ===` never printed (0/135 sessions) | no dedup against reviewer ISSUES ever happened |
| F9 | No calibration / stop rule | ~95% of runs report ≥1 Major; one plan was re-critiqued 6 times |
| F10 | Small: no EGM row in `THIRD-PARTY-LICENSES.md`; no critic line in `context-budget-gate.py` ROLE_BUDGETS (15M default); critics absent from `INVOCATION.md` tool table; critic text says "line range specified by the caller" / "standard provided by the orchestrator" |
| F11 | User-level `task-brief-guard.py` (agent-config) denies the critics' contract prompt: it demands 7 headings in every Agent prompt, so a path-only prompt can never launch | reproduced 2026-11-11: both `Plan: <path>. Review it.` launches denied "missing these headings"; reviewer (7 headings) allowed |

## Research (sources read 2026-11-11)

- Claude Code docs (code.claude.com/docs/en/sub-agents, /hooks, /skills): frontmatter has `effort` and `hooks` (non-plugin agents), no per-agent thinking key; subagent frontmatter `Stop` hooks run as `SubagentStop` for that agent; SubagentStop input carries `last_assistant_message`, `agent_type`, `stop_hook_active`, and `{"decision":"block","reason":…}` makes the subagent continue with `reason` as its next instruction; PreToolUse sees one call at a time (no batch view); no path-scoped Read in frontmatter — use a PreToolUse hook on `tool_input.file_path`/`path`; `$ARGUMENTS` is the raw string, no built-in flag parsing.
- google/elephant-goldfish-model `skills/egm-review-loop/SKILL.md`: reviewers get the verbatim prompt in a fresh context; if they cannot be created EGM *stops* rather than degrading; clean round = no Blocker/Major; stop after **two consecutive clean rounds**, cap **5**, at cap or churn list open findings and ask the user; one flat findings list with stable ids `<reviewer>-<round>-<n>`, settled findings are not reopened; zero findings is a valid result.
- Instructor re-ask pattern (python.useinstructor.com/concepts/reask_validation): validate output, re-ask once with the validation error.

## Design

### D1. One deterministic driver: `.claude/operations/scripts/review-panel.py` (stdlib, py3.9)

- `review-panel.py prompts [--no-panel] [PLAN]` — resolves the plan (`PLAN` arg, else newest `.claude/plans/plan-*.md` excluding `*.review.md`/`*.panel*.md`), decides panel on/off (off when `--no-panel` or env `CK_REVIEW_PANEL` ∈ {`0`,`off`,`false`}), appends one JSON row `{ts, plan, plan_sha256, panel: on|off, why}` to `.claude/hooks/.state/review-panel.jsonl`, and prints exactly:
  ```
  PLAN: <path>
  PANEL: on|off (<why>)
  CRITIC_PROMPT: Plan: <path>. Review it.
  ```
  `<path>` is always `os.path.realpath` of the plan (absolute, `/`-rooted), so it matches the D4 and D9 regex `^Plan: (/.+\.md)\. Review it\.$` (spaces allowed). `test_review_panel_script.py` asserts the CRITIC_PROMPT line matches that regex for a relative `PLAN` arg and for the newest-plan default.
  Exit 1 with `ERROR: no plan` when none is found.
- `review-panel.py merge PLAN --reviewer REF [--critic NAME=REF]...` — `REF` is a Task agentId (transcript found with `review-record.py`'s `_task_transcript`, imported via `importlib` from the same directory) or a file path. For each critic: the reply is **valid** iff its last non-empty line matches `^PANEL: (\d+) blocker, (\d+) major\s*$` or `^PANEL: incomplete\b`, and it is ≤ 3,000 chars; an API-error reply (`API Error`/empty) or invalid format prints `<critic>: incomplete (<reason>)` — never retried here (SubagentStop already retried once, D3). Findings are parsed from lines starting with `[Blocker]`/`[Major]`/`**Blocker**`/`**Major**` (severity token + text). **Dedup rule (deterministic):** a critic finding is *covered* when any reviewer `ISSUES:` line shares ≥ 1 path-like token (`[\w./-]+\.(md|py|sh|json|ts|js|yml|yaml)` or `§\S+`) AND ≥ 3 lower-cased content words of ≥ 5 letters with it; otherwise *uncovered*. Ids `<critic>-r<round>-<n>`.
  Prints:
  ```
  === PANEL ===
  <id> <critic>: [Blocker|Major] <text>
  PANEL: <n> blocker, <n> major (uncovered); round <k>; <stop line>
  === END PANEL ===
  ```
  **Stop rule (EGM):** rounds are kept per plan path in `.claude/hooks/.state/review-panel-rounds.json` (`{plan: [{sha, blockers:[normalized text], majors:n, ts}]}`), a round is appended only when `plan_sha256` differs from the last recorded round (re-running merge on the same bytes does not add a round). Clean = 0 uncovered Blocker and 0 uncovered Major. Stop line is one of: `STOP: 2 consecutive clean rounds`; `STOP: round <k> raised no new Blocker — stop re-reviewing; carry remaining Majors as follow-ups` (k ≥ 2, every uncovered Blocker text already present in round k-1); `CAP: round 5 — list open findings and ask the owner`; else `CONTINUE: fix uncovered Blockers, then re-run /review`. Exit 0 always (advisory) except usage errors (exit 2).

### D2. `/review` command (`.claude/commands/review.md`) rewritten as numbered steps

0. Parse `$ARGUMENTS`: pass it verbatim to step 1 (`review-panel.py prompts $ARGUMENTS`), which accepts `--no-panel` and an optional plan path; nothing else is parsed by the model.
1. Bash: `python3 .claude/operations/scripts/review-panel.py prompts $ARGUMENTS`.
2. **In ONE message**, spawn `reviewer` (existing REVIEWER_MSG) and, when `PANEL: on`, `plan-design-critic` and `plan-readiness-critic`, each with the `CRITIC_PROMPT` line **verbatim and nothing else** (the D4 guard denies anything else).
3. Record reviewer (existing `review-record.py plan-write … --from-task <reviewer agentId>`; unchanged).
4. Bash: `review-panel.py merge <PLAN> --reviewer <id> --critic plan-design-critic=<id> --critic plan-readiness-critic=<id>`; print its output verbatim.
5. Suggestions keyed on reviewer DECISION **and** the stop line (advisory; gate unchanged).
- If any spawn in step 2 is denied (context cap, D6): do not run the remaining steps; the handoff carries the whole panel duty.
- Scripted `claude -p` block: after the reviewer call, run both critics with `claude -p --agent <critic> --allowedTools "Read,Grep"` using the CRITIC_PROMPT, save each to `.claude/plans/<slug>.panel-<critic>.md`, then `merge … --critic <name>=<file>`.
- `_shared/REVIEW_PANEL.md` is updated to describe this flow, the dedup and stop rules, and `CK_REVIEW_PANEL`.

### D3. Critic frontmatter (both critics)

- `effort: low` via `.claude/model-policy.json` role override `"effort": "low"` on both critic roles, projected by `scripts/gen-model-policy.py --write` (never hand-edited). Acceptance is measured (Validation V5); if median thinking stays > 3k tokens, STOP and report — no further lever exists per docs (no per-agent thinking key).
- `maxTurns: 8` (was 15; median run used ≤ 5 tool calls).
- `hooks:` in frontmatter:
  - `Stop` → `python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/panel-format-check.py"`: reads stdin JSON; if `stop_hook_active` is true → exit 0 (one retry max). Else if `last_assistant_message` is ≤ 3,000 chars and its last non-empty line matches the D1 PANEL regex → exit 0. Else print `{"decision":"block","reason":"Reformat: at most 8 findings, under 3,000 chars, last line exactly `PANEL: <n> blocker, <n> major` (or `PANEL: incomplete - <reason>`). Do not call tools."}`. Any parse error → exit 0 (fail-open: advisory panel).
  - `PreToolUse` matcher `Read|Grep|Glob` → `python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/critic-read-scope.py"`: target = `tool_input.file_path` or `tool_input.path` (Grep/Glob with no path = cwd = allowed). Deny (exit 2, stderr reason) when the resolved real path is outside `$CLAUDE_PROJECT_DIR`, or matches any of: `.claude/plans/*.review.md`, `.claude/plans/*.panel-*.md`, `.claude/hooks/.state/**`, `.claude/reports/**`, `**/brief*.md`, `**/session-context.md`, `**/handoffs/**`. Missing/odd input → exit 0.
- Body text fixes: "Audit the target document file and line range specified by the caller" → "Audit the plan file named in the caller's one-line prompt"; "standard provided by the orchestrator" → "the Target Standard inlined below". Run contract gains: "Zero Blocker/Major is a valid and expected result for a sound plan; report a Major only when you can name the concrete failure it causes."

### D4. Blocking guard `.claude/hooks/panel-guard.py` (PreToolUse `Agent|Task`, registry tier `blocking`)

- `subagent_type` ∈ {`plan-design-critic`, `plan-readiness-critic`}: allow only when `prompt.strip()` matches `^Plan: (/.+\.md)\. Review it\.$` (absolute path, same regex as D9) and `os.path.isfile` of it; else exit 2 with `panel-guard: critics take exactly "Plan: <path>. Review it." — no history, briefs or word limits (zero-context contract). Run review-panel.py prompts for the line.`
- `subagent_type == "reviewer"` and prompt names a `.claude/plans/plan-*.md`: exit 0 with JSON `{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":…}}` (best-effort nudge; the /review steps carry the duty) carrying `panel-guard: /review panel — spawn plan-design-critic and plan-readiness-critic in this same message with "Plan: <path>. Review it." unless the panel is off.` when `CK_REVIEW_PANEL` is not off.
- Other types, unparseable payload → exit 0. stdlib, py3.9, no state.
- Registered in `.claude/hooks/dispatch-registry.json` PreToolUse after `review-round-cap`.

### D5. Other reviewer entry points

- `src/claudekit/cli/flow.py`: `AGENTS` gains both critics (`("sonnet", "Read,Grep")`); after the reviewer phase and record, unless `CK_REVIEW_PANEL` is off, run each critic with `critic_prompt(plan_md)` = `f"Plan: {plan_md}. Review it."`, save to `.claude/plans/plan-<slug>.panel-<critic>.md`, run `review-panel.py merge` and append its stdout to `out`. Critic failures never change the flow exit code (advisory). `PHASE_ORDER` gains `"plan-design-critic", "plan-readiness-critic", "panel"`.
- `coordinator.md:430`: "Spawn reviewer agents…" → "Run each completed plan's review per `/review` steps 1-4 (reviewer + both critics in one message, `review-panel.py` prompts/merge)."
- `blueprint.md:78`: Step 5 adds "then run `/review <plan>` so the critic panel also sees it".

### D6. Context-cap hook: whole panel together (outside this repo — agent-config, both account copies)

Edits: `~/IdeaProjects/agent-config/accounts/personal/hooks/auto-handoff.py` and `…/sehhaty/hooks/auto-handoff.py` (identical today; edit both identically).
- `PANEL = {"reviewer", "plan-design-critic", "plan-readiness-critic"}`.
- `on_agent_launch`: before denying a PANEL type past the cutoff, if the ledger (`track().rows(session)`) has a non-denied `launch` row of a PANEL type within the last 120 s, return (allow) — a panel whose first member got in finishes together. Never applies once `finished(rows)` (IDLE path unchanged) or when ctx ≥ `CK_CONTEXT_BLOCK`.
- `append_denied`: if any denied item is a PANEL type, drop those items and write one item instead: `- Panel review (review)` with body `Run /review <plan path from the denied prompt, else "latest plan">: reviewer + plan-design-critic + plan-readiness-critic in one message (review-panel.py prompts/merge).`
- Tests in `~/IdeaProjects/agent-config/tests/test_auto_handoff.py`: sibling allowed within 120 s; denied after 120 s; non-panel type unaffected; replay collapses to one panel item.

### D7. Tests (kit)

- `tests/test_review_panel.py` rewritten:
  - recording-line check asserts **≥ 1** line contains `review-record.py plan-write` (fixes F6) and none names a critic;
  - review.md has numbered steps calling `review-panel.py prompts` and `review-panel.py merge`, and the step-2 text "In ONE message";
  - critic frontmatter: `effort: low`, `maxTurns: 8`, `hooks:` with `panel-format-check.py` and `critic-read-scope.py`; old "line range specified by the caller" / "provided by the orchestrator" strings absent.
- `tests/test_review_panel_script.py` (subprocess on a tmp repo): prompts on/off (flag and env) and the jsonl row; no plan → exit 1; merge: valid critic file, missing PANEL line → incomplete, `API Error` → incomplete, >3,000 chars → incomplete; dedup covered/uncovered by the rule; stop rule: same sha twice = one round, two clean rounds → STOP, round 2 same Blocker → STOP no-new-blocker, 5 rounds → CAP.
- `tests/test_panel_guard.py`: exact critic prompt allowed; prompt with extra text / history / missing file → exit 2; reviewer → exit 0 + note; other types/garbage → exit 0.
- `tests/test_panel_format_check.py` and `tests/test_critic_read_scope.py`: each branch above.
- Mutation proof (V3): deleting the step-2 critic spawn text, or reverting the regex in `panel-format-check.py`, must turn a test red.

### D8. Small items

- `THIRD-PARTY-LICENSES.md`: row for google/elephant-goldfish-model @0dfb5bf, Apache-2.0, files = both critics + `_shared/EGM-*`.
- `context-budget-gate.py` `ROLE_BUDGETS`: `"plan-design-critic": 1500000, "plan-readiness-critic": 1500000` (2.1.319 runs ≈ 0.3-0.6M; the cap catches the thinking blow-up tail).
- `_shared/INVOCATION.md`: both critics in the tool tables (`Read,Grep`; read-only, plan-scoped by hook).
- `CHANGELOG.md` entry (records the V5 live result: critic thinking median, frontmatter hooks fired yes/no); `gen-docs.py`/`gen-registry.py` outputs refreshed if their `--check` fails.

### D9. Brief guard exempts the exact critic prompt (outside this repo — agent-config, both account copies)

Edits: `~/IdeaProjects/agent-config/accounts/personal/hooks/task-brief-guard.py` and `…/sehhaty/hooks/task-brief-guard.py` (identical today; edit both identically), `~/IdeaProjects/agent-config/tests/test_task_brief.py`.
- Add `import re` to the imports (lines 17-20 have none; a NameError would fail the whole guard open via `main()`).
- In `decide()`, after the `not isinstance(body, str)` check and before `tb.skip_used`: if `ti.get("subagent_type")` ∈ `{"plan-design-critic", "plan-readiness-critic"}` and `re.fullmatch(r"Plan: (/.+\.md)\. Review it\.", body.strip())` and `os.path.isfile(group 1)` → `tb.log(sd, HOOK, "panel-critic", sid, len(body))`; `return allow()`.
- Anything else for those types (extra text, history, a brief file, missing or relative path) falls through to the normal 7-heading check and is denied, which also enforces F3 at user level. Other types unchanged. Kit `panel-guard.py` (D4) stays the repo-level check.
- Why safe: critics have `Read, Grep` only, plan-scoped by `critic-read-scope.py` (D3); the prompt carries nothing but the path.
- Tests in `tests/test_task_brief.py` (helper `e.agent(prompt, **ti)` already forwards `subagent_type=`): exact prompt + existing file (incl. a path with a space) → allow (no deny output, streak reset); same prompt with `subagent_type: reviewer` → deny headings; extra line / nonexistent path / relative path → deny headings.

## Files:
Files:
  `.claude/operations/scripts/review-panel.py` (new)
  `.claude/hooks/panel-guard.py` (new)
  `.claude/hooks/panel-format-check.py` (new)
  `.claude/hooks/critic-read-scope.py` (new)
  `.claude/hooks/dispatch-registry.json`
  `.claude/commands/review.md`
  `.claude/commands/blueprint.md`
  `.claude/agents/_shared/REVIEW_PANEL.md`
  `.claude/agents/_shared/INVOCATION.md`
  `.claude/agents/plan-design-critic.md`
  `.claude/agents/plan-readiness-critic.md`
  `.claude/agents/coordinator.md`
  `.claude/model-policy.json`
  `.claude/hooks/context-budget-gate.py`
  `src/claudekit/cli/flow.py`
  `THIRD-PARTY-LICENSES.md`
  `CHANGELOG.md`
  `tests/test_review_panel.py`
  `tests/test_review_panel_script.py` (new)
  `tests/test_panel_guard.py` (new)
  `tests/test_panel_format_check.py` (new)
  `tests/test_critic_read_scope.py` (new)
  `AGENTS.md`, `docs/AGENTS.md`, `docs/ARCHITECTURE.md`, `.claude/skills/skills-registry.json`, `.claude/hooks/README.md` (generator outputs, only if --check fails)

Outside this repo (agent-config, own commit there): accounts/personal/hooks/auto-handoff.py, accounts/sehhaty/hooks/auto-handoff.py, tests/test_auto_handoff.py, accounts/personal/hooks/task-brief-guard.py, accounts/sehhaty/hooks/task-brief-guard.py, tests/test_task_brief.py, accounts/personal/settings.json (context limits 100k/112k, already edited).

## Validation commands

```bash
cd ~/.claude-kit
PY=/usr/local/bin/python3   # system py3.14 has no pytest
# V1 unit tests for everything touched
$PY -m pytest -q tests/test_review_panel.py tests/test_review_panel_script.py tests/test_panel_guard.py \
  tests/test_panel_format_check.py tests/test_critic_read_scope.py tests/test_review_round_cap.py \
  tests/test_registry.py tests/test_registry_drift.py tests/test_dispatch_merge.py tests/test_model_policy.py \
  tests/test_agent_frontmatter.py tests/test_structure.py $(ls tests/test_flow*.py 2>/dev/null)
# V2 generators and lint
$PY scripts/gen-model-policy.py --check && $PY scripts/gen-docs.py --check && $PY scripts/gen-registry.py --check
ruff check tests/ .claude/operations/scripts/review-panel.py .claude/hooks/panel-*.py .claude/hooks/critic-read-scope.py src/claudekit/cli/flow.py
# V3 mutation: each mutant must make V1 fail (run on a scratch copy, never the tree)
S=$(mktemp -d); git archive HEAD | tar -x -C "$S"   # after commit; before commit: rsync -a --exclude .git ./ "$S"/
sed -i '' '/In ONE message/d' "$S/.claude/commands/review.md" && ! (cd "$S" && $PY -m pytest -q tests/test_review_panel.py) && echo MUTANT1-KILLED
# (restore, then) break the PANEL regex in panel-format-check.py → test_panel_format_check.py must fail → MUTANT2-KILLED
# V4 agent-config
cd ~/IdeaProjects/agent-config && $PY -m pytest -q tests/test_auto_handoff.py tests/test_task_brief.py && cmp accounts/personal/hooks/auto-handoff.py accounts/sehhaty/hooks/auto-handoff.py && cmp accounts/personal/hooks/task-brief-guard.py accounts/sehhaty/hooks/task-brief-guard.py
# V5 live (manual, owner-visible): one real /review on this plan; read both critic transcripts:
#   thinking tokens per critic (sum of thinking block lengths/4) median ≤ 3000, PANEL line present,
#   ≤ 3,000 chars, `=== PANEL ===` printed by merge, frontmatter hooks fired (critic-read-scope deny on a probe is not required).
```

## Risks / rollback

- Frontmatter `hooks:` need folder trust and may not fire under `claude -p --agent`: then D3 hooks are no-ops there and `merge` still marks bad output `incomplete` (format is validated twice). V5 checks the interactive path.
- The critics are user-level (symlinked into `~/.claude/agents`), so `$CLAUDE_PROJECT_DIR/.claude/hooks/*.py` may not exist: python's exit 2 would block every critic Read. The hook commands fall back to `~/.claude-kit` and then exit 0 (fail open); `test_critic_hooks_fail_open_and_fall_back_to_kit` pins it.
- `panel-guard` is blocking: a false deny only blocks a critic (advisory); reviewer is never denied. Owner off-switch: `CK_REVIEW_PANEL=off`.
- D6 lets ≤ 2 extra subagents past the cutoff within 120 s; bounded by `CK_CONTEXT_BLOCK`.
- Rollback: `git revert` the kit commit; `git revert` the agent-config commit. No data migration; state files under `.claude/hooks/.state/` are disposable.

## Out of scope

The Air's copies of claudekit/agent-config (not synced; owner pulls); the other 5 EGM personas; making the panel gate `/implement`; Hermes reviewer paths; prp-*/ship (they spawn no reviewer).
