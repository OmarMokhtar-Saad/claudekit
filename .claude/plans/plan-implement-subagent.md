# Plan: /implement hands the edits to a scoped implementer subagent

Status: v2, revised for round-2 delta review (round-1 reviewer + 2 critics, 13 fixes applied). Branch
`feat/implement-subagent` (worktree `/Users/omarmokhtar/IdeaProjects/claudekit-wt-implsub`, from origin/main ce09af05).
Owner OK on record: G-017 (`agent-config/decisions/G-017-subagent-implements-approved-plans.md`, 2026-11-27).
Next step: Step 1 (after this plan is APPROVED and recorded; STEP 0 of `/implement`).
Phases (each ends in its own commit so a phase can be reverted alone; every step is a `###` heading):
- A  code, tests, agent, command: Steps 1-6 (no owner gate)
- B  owner-gated rule docs (CLAUDE.md hard rule 1, AGENTS.md:40, .ai/KNOWLEDGE_BASE.md:95, .ai/MEMORY.md): Step 7, cites G-017
- C  other prose that states the old rule: Step 8
- D  regenerate, targeted gates, probe + dry-run gates: Step 9
- E  changelogs and state: Step 10
- F  live install, owner-run: Step 11
Phase 0 result (both prior searches done with Grep, the planner had no Bash): rejections store
`.claude/knowledge/rejections/{INDEX.jsonl,review-panel-fixes.md,e2e-lane-a.md,README.md}`: the only hit is a MINOR about
SubagentHandback documentation (INDEX.jsonl:17, review-panel-fixes.md:61), unrelated; NO prior rejection of an implementer
subagent. Knowledge ledger `.claude/knowledge/issues/*.md`: 0 matches for implementer|subagent|delegat. Prior plans naming the
implementer (origin of the rule, not rejections): plan-remove-ops-main-session.md:7, plan-implementer-no-git.md,
plan-ck-implement.md, plan-subagent-spend-wind-down.md. A miss is unknown, not proof: Risk R10 names what this plan does differently.

Tier: 3

Files:
- .claude/plans/plan-implement-subagent.md
- .claude/plans/INDEX.md
- .claude/commands/implement.md
- .claude/commands/plan.md
- .claude/commands/coordinator.md
- .claude/agents/plan-implementer.md
- .claude/agents/_shared/implementer-reference.md
- .claude/agents/_shared/planner-reference.md
- .claude/agents/_shared/INVOCATION.md
- .claude/agents/planner.md
- .claude/agents/coordinator.md
- .claude/agents/QUICK_START.md
- .claude/hooks/shell-write-gate.py
- .claude/hooks/context-budget-gate.py
- .claude/model-policy.json
- .claude/skills/skills-registry.json
- .claude/skills/subagent-driven-development/SKILL.md
- .claude/skills/writing-plans/SKILL.md
- .claude/skills/autonomous-loop/SKILL.md
- .agents/skills/autonomous-loop/SKILL.md
- .claude/local/CLAUDE.template.md
- CLAUDE.md
- AGENTS.md
- README.md
- docs/AGENTS.md
- docs/ARCHITECTURE.md
- docs/cli.md
- src/claudekit/cli/main.py
- src/claudekit/cli/flow.py
- tests/test_implement_subagent.py
- tests/test_model_policy.py
- tests/test_cli_flow.py
- .ai/KNOWLEDGE_BASE.md
- .ai/MEMORY.md
- .ai/SYSTEM_OVERVIEW.md
- .ai/TOKEN_MODEL_POLICY.md
- .ai/DOMAIN.md
- .ai/ARCHITECTURE.md
- .ai/AGENTS.md
- .ai/AGENTS_PIPELINE_1.md
- .ai/AGENTS_KNOWN_ISSUES.md
- .ai/AGENTS_INTERACTION_MODEL.md
- .ai/SESSION_STATE.md
- .ai/CHANGELOG_AI.md
- CHANGELOG.md

Generator-owned (written only by the named script, never by hand): `.claude/skills/skills-registry.json`
(`scripts/gen-registry.py`), the count lines in `README.md`, `AGENTS.md`, `docs/AGENTS.md`, `docs/ARCHITECTURE.md` and the
`# BEGIN GENERATED:counts` block in `src/claudekit/cli/main.py` (`scripts/gen-docs.py`; `docs/AGENTS.md:3` "23 specialized
agents" becomes 24), the `model:` line of the new agent (`scripts/gen-model-policy.py`), `.claude/plans/INDEX.md`
(`scripts/gen-plan-index.py`, post-commit). `.agents/skills/` is a membership-parity mirror only
(`scripts/gen-agents-mirror.py:2,:21,:71`); content is hand-edited per file, so each mirrored file is edited on its own merits.

Not touched on purpose (exclusions, with reason):
- `.agents/skills/subagent-driven-development/SKILL.md`: a different, older 171-line text that already says "Dispatch Implementer".
- `.agents/skills/writing-plans/SKILL.md`: has no such sentence (only `.claude/skills/writing-plans/SKILL.md:76` does).
- `.claude/agents/reviewer.md:22` ("before the main session edits anything") and `.claude/commands/rollback.md:3`: neutral, still true.
- `.claude/agents/coordinator.md:419` "FAST-PATH (Tier 1): the main session edits directly": Tier 1 stays inline, still true.
- `CLAUDE.md:69` Token & Model Policy region and `templates/*/CLAUDE.md` ("the parent edits" stays true; policy v8, pinned by
  `tests/test_adapt.py:43`): follow-up for the owner, Risk R6.
- `.claude/skills/skills-registry.json` `removedAgents.implementer` (:939-941): historical tombstone of the ops-era agent,
  generator-owned, pinned by a test; the new agent has a different name.
- `src/claudekit/enforcement/spill.py:19`, `main.py:2047`, decision-ledger / whitebox skills ("never edited" is unrelated).
- History files: `CHANGELOG*` old entries, `.claude/plans/*` other plans, `.claude/reports`, `.ai/CHANGELOG_AI.md:874`.
- `.ai/DECISIONS.md`: has no text stating the old rule.
- `.claude/lint-baseline.json`: never touched (Step 6 stays inside the ratchet; `--update-baseline` is forbidden).

## Overview

`/implement` today (`.claude/commands/implement.md:8-10`, :74): "Execute ... in the main session with Edit/Write. No ops.json,
no executor script, no implementer agent. Subagents explore, review, test and verify; they never edit." and Phase 2 step 3 "Do
not delegate edits to a subagent." Every edit and test output lands in the main context, which pushes the session to an
auto-handoff (owner audit; CHANGELOG.md:613-617 measured 51k -> 301k in 317 turns).

Change: add a scoped agent `plan-implementer` (tools Read/Grep/Glob/Edit/Write/Bash, no `memory:`, no git), and let `/implement`
delegate the edits of an approved plan to it in the plan's worktree. The main session keeps: the approval proof (STEP 0), the
file-set check, reading the diff, and running the targeted tests. The owner has agreed to the rule change (G-017); Phase B edits
the owner-gated text citing it.

### Phase 0 design precheck
Ownership model: plan-gate / checkpoint-gate / review records are keyed on the file PATH and the approved plan, not on which
agent calls the tool. The value of this change sits in (1) the new agent contract, enforced by `context-budget-gate.py` (reads
`agent_type`), (2) one role-keyed hook addition for "never git" in `shell-write-gate.py`, (3) the `/implement` command text plus
its companion reference file, and (4) ~30 prose/doc files that state the old rule. All of them are in `Files:`; no ownership
model is violated. The one place where value depends on something the model does not cover is the role signal itself (does the
PreToolUse payload carry `agent_type` for a spawned plan-implementer): that is closed by the live probe gate in Step 4, not assumed.

## (a) Why the rule was made, and how each reason is handled now

Evidence read in this worktree (file:line). The rule came with the removal of the ops.json pipeline
(`.claude/plans/plan-remove-ops-main-session.md:7`, CHANGELOG.md:99-114); no single "why" paragraph exists, the reasons are
spread over these records:

| # | Reason (source) | Handled now by |
|---|---|---|
| 1 | ops.json friction: every prompt edit needed an ops.json, ~635 files mention ops (plan-remove-ops-main-session.md:87; BACKLOG.md:15) | No ops.json. The brief is plan path + step line ranges. |
| 2 | Iron Law bypass: the old implementer held unscoped Bash; a frontmatter `Bash(...)` specifier is NOT applied (CHANGELOG.md:2787-2795; tests/test_agent_tool_grant_drift.py:3-18); `iron-law-gate` needed 3 review rounds | The mechanical gate is now path-based (plan-gate.sh) and applies to any caller (see (b)). Bash writes stay a documented speed bump (same as the main session); compensating control = Phase 2c file-set and git-state check. |
| 3 | `memory:` made the harness grant Write+Edit (planner 64 Edits, SESSION_STATE.md:129-132; context-budget-gate.py:174-177) | `plan-implementer` declares NO `memory:` and an explicit `tools:`; `context-budget-gate` enforces the contract (`_subagent_verdict`, context-budget-gate.py:604-652); tests/test_agent_frontmatter.py:54 keeps memory out. |
| 4 | Cost: 44 turns / 1.4M tokens to run three scripts (plan-ck-implement.md:8, plan-implementer-no-git.md:13). But implementer was 1.4% of spend; coordination agents were 98.6% (SESSION_STATE.md:128-129) | No scripts to run. `maxTurns: 60`, `ROLE_BUDGETS["plan-implementer"]` 6M line with wind-down advice (context-budget-gate.py:148-161). |
| 5 | False completion and baseline mutation: reported COMPLETE while the suite ran; ran `ck lint --update-baseline` (CHANGELOG.md:621-624) | Agent body forbids both; hook (Step 4) refuses `--update-baseline` / `--no-verify` for this role; the MAIN session re-runs the targeted tests and quotes exit codes (existing Phase 3 rule kept). |
| 6 | Implementer ran git; parent owns branch and commits (plan-implementer-no-git.md:3-15) | Hook (Step 4) refuses git from `plan-implementer` (tokenised check, honest limits stated there); the brief says the same; Phase 2c compares git state before and after the spawn. |
| 7 | Identity: subagents resolve to the PARENT session; author-vs-reviewer only attestable by role (CHANGELOG.md:780-785) | Unchanged: the implementer never writes review records; plan-gate denies Edit/Write under `.claude/reports/reviews/` for every caller (`pg_is_denied_path`, plan-lib.sh:50-56). |
| 8 | Reviewer verdicts are STATIC-ONLY; execution-capable check before Tier 3 runs (CHANGELOG.md:618-620) | Unchanged (STEP 0 and `/code-review` untouched). |
| 9 | Main-context bloat / stage handoff (CHANGELOG.md:613-617) | This change is the fix; the stage-handoff rule stays. |

Result: no safety reason found that cannot be kept with a subagent implementer, so no Blocker. The owner gate (`.ai/KNOWLEDGE_BASE.md:95`
"Things future models must NEVER change" #1 and CLAUDE.md hard rule 1) is satisfied by G-017; the owner-gated edits sit in their own
Phase B, after Phase A has proven the code, so they can be reverted alone.

## (b) Which guards apply to subagent tool calls (evidence)

Hooks fire inside subagents: settings.json PreToolUse has `"matcher": ""` -> `dispatch.sh PreToolUse`; the payload then carries
`agent_id` (and `agent_type`, "confirmed present in the payload on both spawn paths", CHANGELOG.md:3097) -
`context-budget-gate.py:30-31, 239-249, 444-460` (`payload.get("agent_type")`, fallback `agent-<id>.meta.json` `agentType`). Hooks
that skip subagents say so explicitly (`delegate-nudge.py:205`, `memory-first.py:126`, both advisory). Grep for
`agent_id|agent_type|subagent` in `plan-gate.sh`, `checkpoint-gate.sh`, `shell-write-gate.py`, `config-protection.sh`,
`team-edit-gate.py`, `dispatch.sh`, `bash-payload-gate.py`, `command-guard.sh`, `block-no-verify.sh`, `commit-quality.sh` = 0 hits,
so none of them exempts a subagent.

| Guard | Applies to subagent? | Evidence |
|---|---|---|
| plan-gate (Edit/Write, T3 path must be in an approved plan's `Files:`) | YES (keyed on tool_name + path only) | plan-gate.sh:22-34, :55-63; dispatch-registry.json:58 |
| checkpoint-gate (tag before first edit) | YES | dispatch-registry.json:59 |
| `.claude/reports/reviews/`, settings, plan-gate.globs deny | YES | plan-lib.sh:50-56 |
| shell-write-gate (shell writes to protected paths, T3 deletes) | YES (Bash) | dispatch-registry.json:55 |
| command-guard, block-no-verify, commit-quality, bash-payload-gate | YES (Bash) | dispatch-registry.json:52-57 |
| context-budget-gate contract + spend line | YES, only for roles with a `.claude/agents/<type>.md`; the built-in `general-purpose` agent is BLOCKED outright unless `CK_ALLOW_GENERAL_PURPOSE=1` (context-budget-gate.py:655-667, :721-728) | so a scoped agent is required |
| golden-rule | NO hook; it is a skill, applies only if the agent body loads it | `plan-implementer.md` lists it; plan approval IS the Golden Rule approval |
| review-record `plan-check` | Run by plan-gate for every Edit/Write (plan-lib.sh:58-95), so it binds the subagent indirectly; STEP 0 still runs it in main | |
| delegate-nudge, memory-first | NO (explicit skip) | advisory only |

Gaps and the steps that close them:
1. Root resolution: `resolve_root` = `git rev-parse --show-toplevel` of the HOOK's cwd (lib.sh:14-21); an Edit whose path is outside
   that root exits 0 ("other projects are not this gate's business", plan-gate.sh:47-51). If the session sits in the main checkout and
   the subagent edits the worktree by absolute path, plan-gate does NOT bind. Step 6 therefore delegates ONLY when
   `git rev-parse --show-toplevel` of the main session equals the plan's worktree path; otherwise STOP.
2. "Never git" for a subagent has no hook (iron-law-gate was deleted in Phase 2). Step 4 adds a role-keyed, tokenised check; it is a
   speed bump (limits stated in Step 4), backed by the Phase 2c before/after git snapshot compare.
3. Bash writes to source bypass plan-gate for ANY caller (shell-write-gate protects only review records, settings, globs and T3
   deletes). Phase 2c adds a mechanical post-run check against the batch's own file list, including ignored files.
4. Prove binding: Step 5 tests run the REAL plan-gate.sh with `agent_id`/`agent_type` in the payload.
5. The role signal itself may be absent for a spawned agent in the current harness: Step 4 has a required live probe with two
   explicit outcome branches (a)/(b).

## (c) When /implement delegates (exact rule)

`/implement <plan> [--delegate | --inline]`:
- `--inline`: main session edits (today's behaviour, unchanged text kept as "Phase 2b: Inline").
- `--delegate`: always spawn `plan-implementer`.
- default (neither flag) = auto. Definitions: a "file" is a `Files:` entry other than the plan file itself and
  `.claude/plans/INDEX.md`; a "step" is a `### Step N` heading under `## Implementation Steps`. Delegate when files >= 3 OR
  steps >= 3, else inline. Worked examples: this plan = 44 files, 11 steps -> delegate (but implemented inline, because the agent
  does not exist until Step 1 lands); a 2-file 2-step plan -> inline; a 1-file 4-step plan -> delegate.
- Never delegate (STOP, say why, offer `--inline`): the main session root is not the plan's worktree (gap 1); STEP 0 failed; the
  `Agent` spawn is blocked by a hook (report the BLOCKED text, no retry loop); the live probe (Step 4) ended in branch (b) and
  `--delegate` was not given explicitly.
- Large plans: batches of at most 5 steps or 10 files per spawn, run sequentially (edits never parallel); main verifies each batch
  (Phase 2c) before the next.
- This plan itself is implemented inline (the agent does not exist until Step 1 lands).
- The rule text lives in `.claude/agents/_shared/implementer-reference.md` (Step 6), not in `implement.md`, to stay inside the
  lint ratchet; there is no code helper for the count, so it is guarded by a structural test (Step 5 test 8).

## (d) Subagent brief template (lives in `.claude/agents/_shared/implementer-reference.md`, Step 6)

Headings follow the owner's brief guard (7 headings, each on its own line):

```
## Objective
Implement steps <S>-<T> of the approved plan <PLAN_ABS_PATH> in the worktree <WT_ABS_PATH> (branch <BRANCH>).
## Done when
Each step's "Done when" holds. These pass (the main session re-runs them): <TARGETED_TEST_COMMANDS>.
## Scope
Work only under <WT_ABS_PATH>, absolute paths. Read the plan's status block, then only lines <a>-<b> per step.
Edit only: <FILES_FOR_THESE_STEPS>. Never: any git command (commit, push, branch, stash, checkout, add),
--no-verify, `ck lint --update-baseline`, edits to .claude/reports/reviews/, settings files, the plan file,
plan-gate.globs, deleting a file not marked (delete). Anything outside the plan is a plan change: stop.
## Verify
Run only the commands above with quiet flags; quote exit code and counts verbatim. Never report COMPLETE
while a command is still running.
## Stop and ask
Ambiguous step, file not in Files:, a hook BLOCKED message, an edit that fails twice: stop, return BLOCKED
with the exact message and file:line. Do not work around a hook.
## Report
At most 300 words: COMPLETE/PARTIAL/BLOCKED; per file one line of what changed; command outputs
(exit code, counts); deviations. Do not paste diffs. Detail beyond 300 words goes to a scratch file; reply with its path.
## Original request
<the user's /implement message, whole and exact>
```

## Implementation Steps

Order is by dependency. Line numbers are from this worktree at ce09af05; re-find with `grep -n` before editing.

### Step 1 (Phase A): New agent `.claude/agents/plan-implementer.md`
File: `.claude/agents/plan-implementer.md` (create). Name is NOT `implementer`: `skills-registry.json:939-941` carries
`removedAgents.implementer`, and a same-named file would collide with the removal marker.
Details: layout template is `.claude/agents/tester.md` (frontmatter order name, `description: |`, blank line, model, effort, color,
tools as a JSON list; test_agent_frontmatter.py:38 requires every line to be a key line, KEY_LINE allows camelCase such as
`maxTurns`). Frontmatter: `name: plan-implementer`, `description: |` ONE sentence, <= 150 chars, no `<example>` (context-floor
description budget is 10000 chars, ~5.5k used, scripts/check-context-floor.py), `model: sonnet`, `effort: medium`, `color: green`,
`maxTurns: 60`, `tools: ["Read", "Grep", "Glob", "Edit", "Write", "Bash"]`. No `memory:`.
Body, same layout as tester.md:12-28: `## Skill Loading` with **bold** skill ids (scripts/gen-registry.py derives agent->skills from
this section, SKILL_RE line 27): Mandatory **using-superpowers**, **verification-before-completion**; On demand **golden-rule**
(satisfied by the approved plan) and **clean-architecture** (when edits cross modules); all four are visible skills. Rules: edit
only the `Files:` of the brief; one step at a time in plan order; read each file window before editing; never git; never repair a
red gate (report it); never `--update-baseline` / `--no-verify`; report format = the brief's Report section; ends with
`SubagentHandback` (<= 3000 chars, context-budget-gate.py:171).
Done when: file exists; `python3 -m pytest tests/test_agent_frontmatter.py tests/test_skill_loading_contract.py tests/test_agent_prompt_size.py -q` passes.

### Step 2 (Phase A): Model policy role
Files: `.claude/model-policy.json`, `tests/test_model_policy.py`.
Edit: add `"plan-implementer": {"accountable_for": "Applies the edits of an approved plan inside the plan's worktree; never runs git.", "tier": "balanced", "effort": "medium"}`
in alphabetical position between `"loop-operator"` and the next role (roles are sorted; model-policy.json:62-99). In
`tests/test_model_policy.py` `SHIPPED_MODELS` (:114-135) add `"plan-implementer": "sonnet",` with a comment naming this plan (the
dict is pinned as literals on purpose, :109-113). Then `python3 scripts/gen-model-policy.py` and `--check`.
Done when: `python3 -m pytest tests/test_model_policy.py -q` and `python3 scripts/gen-model-policy.py --check` exit 0.

### Step 3 (Phase A): Spend line and message in context-budget-gate
File: `.claude/hooks/context-budget-gate.py`. Exactly two edits; nothing else in the file changes.
Edit 1: in `ROLE_BUDGETS` (:148-155) add `"plan-implementer": 6000000,` and extend the comment above (:144-147): "plan-implementer:
no measured p90 yet; set at the code-reviewer line (6M); old implementer ran 1.4M for 44 turns (plan-ck-implement.md:8). Recalibrate
after 10 runs." No test pins the ROLE_BUDGETS keys.
Edit 2: the string at lines 626-627 `"Changes are made by the main session after an approved plan, never as this "` / `"agent's edits."`
-> `"Changes are made by the main session or the plan-implementer subagent after an approved plan, never as this "` /
`"agent's edits."` (still the same two-line string concatenation). This is the only phrase stating the old rule.
Must NOT change: lines 6, 54, 230, 240, 704 ("main session" there means main-vs-subagent context measurement, not who edits). The
hook docstring (:90-110) was grepped: it has no "main session edits" wording, so no docstring edit.
Done when: `python3 -m pytest tests/ -q -k "context_budget"` exits 0; `git diff` of the file shows exactly the ROLE_BUDGETS entry, its
comment, and the one message string.

### Step 4 (Phase A): Hook: `plan-implementer` never runs git, never mutates baselines
File: `.claude/hooks/shell-write-gate.py` (docstring :1-30 plus `main()` :278-308).
Design. Only the role check is on the hot path: the helper runs ONLY when the role is `plan-implementer`, so a bug cannot affect
the main session or other roles (shell-write-gate runs on every Bash call under all profiles; the role check comes first and
nothing else in `main()` changes).
1. `_agent_role(payload) -> str`: `payload["agent_type"]` when a non-empty str; else the `agentType` of the agent's own meta file.
   Copy BOTH sources from context-budget-gate.py, do not import (hooks are standalone): own path = `os.path.splitext(transcript_path)[0]`
   + `/subagents/agent-<agent_id>.jsonl` (`_caller_transcript`, :236-251; `agent_id` must be `isalnum`), meta = that stem + `.meta.json`
   (`_agent_type`, :444-460). Any read error -> "" (no role).
2. Module constant `_IMPLEMENTER = "plan-implementer"`. In `main()` after the command string is parsed and before `_violates`: if
   `_agent_role(payload) == _IMPLEMENTER`, `reason = _git_forbidden(command)`; if `reason` -> stderr `BLOCKED shell-write-gate:
   plan-implementer must not run git or mutate baselines (<reason>); the main session owns git. Report what you need and stop.`
   and `return 2`. An exception inside the helper for this role also returns 2 (fail closed). The existing fail-closed parse path
   is unchanged.
3. `_git_forbidden(command) -> str` (reason or ""), replacing the v1 regex (which matched the bare word and missed `$(git ...)`
   and `env git`):
   - If `re.search(r"--update-baseline|--no-verify", command)`: return "baseline/no-verify flag".
   - Normalise: replace `$(`, backtick, `(`, `)`, `{`, `}` with `;`, then split on `[;&|\n]+` into segments.
   - For each segment: `tokens = shlex.split(seg)` (on ValueError fall back to `seg.split()`); drop leading tokens that are `VAR=value`
     assignments or wrappers in {env, command, sudo, nohup, time, exec, xargs, nice, builtin} (also skip any following tokens that
     start with `-` after a wrapper); if the first remaining token's basename == `git` return "git"; if it is in {sh, bash, zsh} and
     `-c` is in the tokens, recurse into the token after `-c`.
   - Expected table, pinned parametrised in Step 5 test 9 (role = plan-implementer): `git status` BLOCK; `cd x && git status` BLOCK;
     `/usr/bin/git log` BLOCK; `env git status` BLOCK; `$(git rev-parse HEAD)` BLOCK; `GIT_DIR=x git log` BLOCK; `xargs git rm`
     BLOCK; `bash -c "git status"` BLOCK; `ck lint --update-baseline` BLOCK; `git commit --no-verify` BLOCK; `echo "git"` ALLOW;
     `grep git f` ALLOW; `pytest tests/test_git.py` ALLOW; `gitleaks detect` ALLOW; `python3 -m pytest tests/x -q` ALLOW;
     `echo "a; git status"` BLOCK (documented false positive: separators inside quotes are split first, fail-closed direction).
     The same commands with `agent_type` `explore` or no `agent_type`: exit 0 (existing behaviour; `git status` stays allowed for the
     main session).
4. Honest limits (state in the hook docstring, "speed bump, not a sandbox"): `python -c`, scripts, `os.system` / `subprocess`,
   `find -exec git`, a renamed or copied git binary, and `eval` of built strings are NOT caught. Compensating controls: the Phase 2c
   git-state snapshot compare (HEAD, current branch, `git stash list`, `git tag -l`, `git for-each-ref`, index via
   `git status --porcelain --ignored`) and the live probe below.
5. REQUIRED GATE, live probe, before this step counts as done. Setup: a throwaway worktree of the kit (or a tmp repo with the kit's
   `.claude/` hooks and agents copied) opened as the project of a fresh session (UNVERIFIED: whether a running session can spawn an
   agent file created mid-session; if not, restart the session in the throwaway worktree, owner-run `! claude`). Spawn
   `plan-implementer` with a brief whose only task is "run `git status` then report". Expected: the Bash call returns `BLOCKED
   shell-write-gate`. Record the transcript excerpt (command, BLOCKED text) in the PR description. Two explicit outcome branches:
   - (a) Hook got a role signal (`agent_type` or meta.json present): PASS, delegation default stays auto (section (c)).
   - (b) No role signal (the git command ran): `disallowedTools: ["Bash(git:*)"]` in the agent frontmatter is tried ONLY if a second
     probe shows the harness honours it; the default assumption is NOT honoured (CHANGELOG.md:2787-2795: a frontmatter `Bash(...)`
     specifier is not applied). If it is not honoured: Blocker for default delegation. Then `/implement` default becomes inline,
     `--delegate` is an explicit opt-in, Phase 2c snapshot compare is the only git control, and Step 6 / Step 8 wording follows
     branch (b); this plan is amended and re-reviewed before Step 6 proceeds (the `Files:` list does not change).
   The branch taken is written in the PR description and in `.ai/SESSION_STATE.md` (Step 10).
Done when: Step 5 tests 3, 7, 9 pass; `ruff check .claude/hooks/shell-write-gate.py` exits 0; the probe is recorded with branch (a) or (b).

### Step 5 (Phase A): Behavioral tests `tests/test_implement_subagent.py` (new)
Fixtures are copied into the new file (tests are not a package; do not import): from `tests/test_plan_gate_hooks.py` copy `proj(tmp_path)`
(:25-46: git init, config user, mkdir `.claude/{plans,hooks,operations/scripts}`, copy lib.sh, plan-lib.sh, plan-gate.sh,
checkpoint-gate.sh, shell-write-gate.py, review-record.py, write `app.py` 'a = 1\nb = 2\n', add, commit), `_hook(proj, name, payload,
profile)` (:49-56: strips ECC_*, sets ECC_HOOK_PROFILE, runs py via sys.executable else bash, cwd=proj, timeout 60), `_approve(proj,
files)` (:69-75: plan text with `**Files:** \`app.py\``, `**Tier:** 3`, then `review-record.py plan-write --score 95 --decision APPROVED
--owner-approved`), `PROFILES=[None, 'minimal']`. From `tests/test_context_budget_gate.py` copy `usage_line(total)` (:71-84),
`run_hook` (:150-182, sets CLAUDE_PROJECT_DIR=tmp, cwd=tmp, pops HATCHES env), `spawned()` (:675-688: parent transcript
`tmp/parent.jsonl` usage 450000, subagent transcript `tmp/parent/subagents/agent-<id>.jsonl` usage 10000, optional
`agent-<id>.meta.json` = {"agentType": T, "model": "opus"}, payload extras `agent_id`, optional `agent_type`) and `contract()`
(writes `tmp/.claude/agents/<agent>.md`). Force `ECC_HOOK_PROFILE` explicitly (unset and `minimal`).
Tests:
1. `test_plan_gate_binds_a_subagent_payload`: real `plan-gate.sh`, payload `{"tool_name":"Edit","tool_input":{"file_path":<T3 file>},"agent_id":"abc123","agent_type":"plan-implementer"}`: no approved plan -> exit 2; approved plan listing the file -> exit 0; file not listed -> exit 2.
2. `test_review_records_denied_to_a_subagent`: same payload targeting `.claude/reports/reviews/x.json` -> exit 2.
3. `test_shell_write_gate_refuses_git_for_plan_implementer`: payload `{"tool_name":"Bash","tool_input":{"command":"git commit -am x"},"agent_type":"plan-implementer"}` -> exit 2, stderr contains `plan-implementer`; same command with `agent_type` `explore` or absent -> exit 0; `python3 -m pytest tests/x -q` -> exit 0 for the role. The existing allow-test at test_plan_gate_hooks.py:181-187 (`git status`, no agent_type, exit 0) must stay green.
4. `test_context_budget_gate_scopes_plan_implementer`: copy the SHIPPED `.claude/agents/plan-implementer.md` into `tmp/.claude/agents/`; subagent payload (agent_type `plan-implementer`, tool `Edit`) -> exit 0; agent_type `explore` with a contract whose tools are Read,Grep,Glob (via `contract()`), tool `Edit` -> exit 2. A fallback-by-meta variant follows `test_agent_type_falls_back_to_the_meta_file` (:757-766).
5. `test_agent_file_contract`: frontmatter of `plan-implementer.md` has `tools` containing Edit and Write, no `memory`, `maxTurns` <= 60; `skills-registry.json` lists it; `removedAgents` still has `implementer` and no `implementer.md` exists.
6. `test_implement_command_documents_the_delegation` (STRUCTURAL GUARD, it proves the text exists, not that the model obeys it): `implement.md` contains `plan-implementer`, `--inline`, `--delegate`, the pointer to `_shared/implementer-reference.md`, and no longer contains `Do not delegate edits`; `implementer-reference.md` contains the seven brief headings and the Phase 2c commands `plan-check`, `status --porcelain --ignored`, `rev-parse HEAD`, `stash list`, `tag -l`, and the worktree precondition `rev-parse --show-toplevel`.
7. `test_role_from_meta_file_fallback`: layout `tmp/parent.jsonl`, `tmp/parent/subagents/agent-abc123.meta.json` = {"agentType":"plan-implementer"}, payload `{"tool_name":"Bash","tool_input":{"command":"git status"},"agent_id":"abc123","transcript_path":"<tmp>/parent.jsonl"}` with NO `agent_type` -> exit 2; same with meta type `explore` -> exit 0.
8. `test_auto_delegate_rule_is_documented` (STRUCTURAL GUARD, there is no code helper): `implementer-reference.md` contains the exact sentence "Delegate when files >= 3 OR steps >= 3, else inline" and the three worked examples of section (c).
9. `test_git_forbidden_table`: parametrised over the exact BLOCK/ALLOW table of Step 4 point 3, run through the real hook with role `plan-implementer`, plus the same commands under `explore` / no role -> exit 0.
Mutation control (repo rule, KNOWLEDGE_BASE "prove it can fail"): make `_git_forbidden` return "" and confirm tests 3, 7, 9 fail; make `_agent_role` return "" and confirm test 7 fails; record both in the commit message.
Done when: `python3 -m pytest tests/test_implement_subagent.py -q` exits 0 and both mutation runs exit non-zero.

### Step 6 (Phase A): Rewrite `/implement` and add its companion reference
Files: `.claude/commands/implement.md` (133 lines now), `.claude/agents/_shared/implementer-reference.md` (create).
Budget: `.claude/lint-baseline.json:29` pins `implement.md` at 148 lines (ratchet: it may not grow past 148; `--update-baseline` is forbidden and the
file is not in `Files:`). So `implement.md` gets only short pointers and stays <= 145 lines; Mode rules, the brief template and the Phase 2c
check list go to `.claude/agents/_shared/implementer-reference.md` (the installer globs `agents/_shared/*.md`, install.sh:238). Trim
redundant prose in `implement.md` as needed.
`implement.md` edits:
- Frontmatter :2 description -> `"Execute an approved plan: delegate the edits to plan-implementer or edit inline"`.
- :8-10 -> "Execute an approved `plan.md`. Edits are made by the `plan-implementer` subagent in the plan's worktree (default for plans of >= 3 files or >= 3 steps, see reference) or inline by the main session (`--inline`). No ops.json, no executor script. Other subagents explore, review, test and verify; they never edit. A subagent never runs git." plus one line: "Read `.claude/agents/_shared/implementer-reference.md` once before Phase 2a."
- STEP 0: keep items 1-4 unchanged; add item 5 (delegation only): `[ "$(git rev-parse --show-toplevel)" = "<plan worktree>" ]` and `git -C <wt> status --porcelain` empty or listing only the plan file; else STOP.
- Phase 1 unchanged. Phase 2 -> `### Phase 2a: Delegated` (spawn `Agent(subagent_type="plan-implementer", model per policy)` with the reference brief; one batch at a time) and `### Phase 2b: Inline` (existing lines 70-73 verbatim). Replace :74 "Do not delegate edits to a subagent" by "Delegate searches and test runs in 2b; edits only to `plan-implementer` in 2a."
- New `### Phase 2c: Check the delegated diff` (main session, small outputs only): one pointer line to the reference (the full list is there).
- Phase 3: add "targeted tests only, quiet (`-q`, output tailed to 20 lines); the full suite is the owner's rule: one run on the Pro."; keep the no-estimate / no-baseline-mutation text. Safety Rules: add "NEVER let a subagent commit, push, or run git". Output block: add `Mode: inline | delegated (batches N)` and `Subagent report: COMPLETE/PARTIAL/BLOCKED`.
`implementer-reference.md` contents:
- Mode rules = section (c) verbatim (flags, the exact auto rule with definitions and worked examples, never-delegate conditions, batches of <= 5 steps or <= 10 files), written for the branch chosen by the Step 4 probe.
- Brief template = section (d) verbatim.
- Phase 2c check list (small outputs only): (1) Snapshot BEFORE and AFTER the spawn, each run as `git -C <wt> rev-parse HEAD`, `git -C <wt> symbolic-ref --short HEAD`, `git -C <wt> stash list`, `git -C <wt> tag -l`, `git -C <wt> for-each-ref`; any difference = deviation -> `/rollback`. (2) File set: per-batch list = the `Files:` entries of the steps in this batch (not the whole `Files:`); run `git -C <wt> status --porcelain --ignored`; every reported path must be in the batch list (or be the plan file untouched); Tier 3: `python3 .claude/operations/scripts/review-record.py plan-check "$PLAN" --path "$p"` exit 0 per path; an extra path = deviation. (3) `git -C <wt> diff --stat` and `git -C <wt> diff --check`. (4) read the diff in windows of <= 150 lines only for security- or hook-related files; never paste diffs into the reply. (5) one repair round: re-spawn with the findings; a second failure -> `/rollback` and report, or the user chooses `--inline`.
Done when: Step 5 tests 6 and 8 pass; `python3 -m claudekit.cli.main lint .` exits 0 WITHOUT `--update-baseline` (cmd_lint main.py:2852; rules command-budget, skill-agent-costume, duplicate-triggers) and `wc -l .claude/commands/implement.md` <= 145.

### Step 7 (Phase B, owner-gated by G-017): Rule text in CLAUDE.md, AGENTS.md, KNOWLEDGE_BASE, MEMORY
Entry gate: G-017 is the owner's recorded OK; cite it in the commit message. Files: `CLAUDE.md`, `AGENTS.md`, `.ai/KNOWLEDGE_BASE.md`, `.ai/MEMORY.md`.
- `CLAUDE.md:44` (hard rule 1) and `AGENTS.md:40` (identical): tail "the main session edits directly, subagents only explore, review, test and verify." -> "the main session or `plan-implementer` edits; other subagents never edit." (68 chars vs 81: length-neutral or shorter for the context floor, where CLAUDE.md counts x4, limit 31000, src/claudekit/context_floor.py:39-45).
- `.ai/KNOWLEDGE_BASE.md:95` invariant 1: same wording. `.ai/MEMORY.md:14` (long line): replace only the clause "...subagents never edit)" with the same qualifier.
Done when: `python3 scripts/check-context-floor.py --check` exits 0; `python3 -m pytest tests/test_context_floor.py -q` exits 0.

### Step 8 (Phase C): Other prose that states the old rule
Each edit replaces only the quoted phrase; re-find the line first.
- `.claude/agents/_shared/planner-reference.md:78` "The main session edits directly after approval;" -> "The main session or the `plan-implementer` subagent edits after approval (`/implement` decides);".
- `.claude/agents/_shared/INVOCATION.md:58` ("main session now edits directly, so there is no implement phase to bill") -> a delegated run bills one `plan-implementer` spawn; `:189` same phrase -> add `plan-implementer`. Prose only: do NOT touch the grants table (:192-208); `test_documented_grants_match_frontmatter` checks only documented rows against frontmatter (test_agent_tool_grant_drift.py:99-115) and tester is not in the table either, so no row is added.
- `.claude/agents/planner.md:16` "The main session implements it directly after review and approval" -> "`/implement` executes it after review and approval" (shorter: planner.md has a 10000-byte ceiling, tests/test_agent_prompt_size.py:26).
- `.claude/agents/coordinator.md:408` "NEVER let the main session edit a Tier 2/3 task without a plan" -> "NEVER let the main session or an implementer subagent edit ..."; `:420` "main session edits" -> "main session or plan-implementer edits". Leave :419 (Tier 1 fast path).
- `.claude/commands/coordinator.md:59` "code edits stay in the main session" -> "code edits stay in the main session or plan-implementer". `:97` table "main session (/implement...)" stays.
- `.claude/commands/plan.md:19` "the **main session implements the plan directly** (`/implement`)" -> "`/implement` implements the plan (inline, or via the `plan-implementer` subagent)".
- `.claude/agents/QUICK_START.md:52` and `:58` "Main session edits" in the pipeline arrows -> "Main session / plan-implementer edits".
- `.claude/local/CLAUDE.template.md:62` "Execute approved plan (main session edits)" -> "Execute approved plan (inline or plan-implementer)".
- `.claude/skills/subagent-driven-development/SKILL.md` (the `.agents/` copy is a different text and is NOT edited): description :3, Core Principle :10-13, Stage 1 :61-64 -> "Stage 1: Implement (main session inline OR plan-implementer subagent; see /implement Mode)", :99, :119, Rework Protocol :125 ("Apply the reviewer's specific findings yourself") -> "main session or the implementer, re-briefed with the findings". Read-only reviewers stay read-only.
- `.claude/skills/writing-plans/SKILL.md:76` "The main session then implements the approved plan directly; there is no ops.json." -> "`/implement` then executes the approved plan (inline or via `plan-implementer`); there is no ops.json."
- `.claude/skills/autonomous-loop/SKILL.md:77` "- Phase 3 edits run in the main session" and `.agents/skills/autonomous-loop/SKILL.md:196` "- Phase 3: the main session edits directly per the approved plan" -> add "or plan-implementer".
- `docs/cli.md:212-213` "the main session then edits directly." -> "`/implement` then makes the edits (inline or via `plan-implementer`)."
- `.ai/DOMAIN.md:36` "main session edits directly -> verifier"; `.ai/ARCHITECTURE.md:10` "the main session edits. No overlap." and `:62` "main session edits directly"; `.ai/AGENTS.md:80` "main session<br/>edits directly after plan-gate"; `.ai/AGENTS_PIPELINE_1.md:56` "the main session implements the approved plan directly" and `:105` "then main-session edits" (leave :64: it mirrors planner.md description :4, still true); `.ai/AGENTS_KNOWN_ISSUES.md:26` "and the main session edits directly."; `.ai/AGENTS_INTERACTION_MODEL.md:52` clause "plan-gate allows edits, main session edits;" (long line, replace only that clause): each gets "or plan-implementer" / "(inline or via plan-implementer)".
- `.ai/SYSTEM_OVERVIEW.md:17` "the main session edits directly" -> "the main session or `plan-implementer` edits"; `.ai/TOKEN_MODEL_POLICY.md:24, :53` "the main session edits" / "main-session edits" -> add "or plan-implementer".
- `README.md:193, :200`, `docs/AGENTS.md:51` ("The main session edits only those files after approval." -> "The main session or plan-implementer edits only those files after approval."), `docs/ARCHITECTURE.md:307`: "main session edits" -> "main session (inline) or `plan-implementer` (delegated, `/implement` default for >= 3 files or steps)". In `docs/AGENTS.md` add the table row after the Tester line (:19): `| Plan Implementer | \`plan-implementer.md\` | Green | Sonnet | READ, WRITE, EXECUTE (no git) |`; the count line :3 is generator-owned (Step 9).
- `src/claudekit/cli/flow.py:13` docstring "the main session then edits directly" -> "the chain ends; run `/implement` next"; `:256` message "...; the main session implements it" -> "...; run /implement on it". `ck flow` itself is unchanged and must still never mention `implementer`.
- `tests/test_cli_flow.py:75` comment only: "the flow never edits: /implement does that after approval". Lines 79 (`assertNotIn("implementer", out)`) and 128 (bad roles `cook`, `implementer`) stay true; do NOT add `plan-implementer` to flow roles. No test asserts the old sentences (`tests/test_adapt.py:43` is a comment pin on the untouched policy version).
Done when: `grep -rnE "edits directly|main session edits|main-session edits|never edit|no implementer|subagents only explore|Do not delegate edits|implements (it|the plan|the approved plan) directly" docs .ai .agents .claude CLAUDE.md AGENTS.md README.md src` (excluding `.claude/plans`, `.claude/reports`, `.claude/knowledge`, `CHANGELOG*`) returns only hits that mention `plan-implementer` or are in the "Not touched on purpose" list above; each remaining hit is named in the commit message.

### Step 9 (Phase D): Regenerate, targeted gates, probe and dry-run gates (outputs piped to `tail -n 20`)
Commands: `python3 scripts/gen-registry.py` then `--check`; `python3 scripts/gen-docs.py` then `--check` (rewrites the count lines and the generated block in
`src/claudekit/cli/main.py`); `python3 scripts/gen-model-policy.py --check`; `python3 scripts/check-context-floor.py --check` (if it exits 1 shorten the
agent description first; budget changes are owner-only); `python3 -m claudekit.cli.main lint .` (no `--update-baseline`); `ruff check src/ tests/ scripts/ .claude/operations/scripts/`;
`python3 -m pytest tests/test_implement_subagent.py tests/test_model_policy.py tests/test_cli_flow.py tests/test_agent_frontmatter.py tests/test_agent_tool_grant_drift.py tests/test_skill_loading_contract.py tests/test_agent_prompt_size.py tests/test_lint.py tests/test_context_floor.py -q`.
Compare `git status --short` with `Files:`; any generated file outside the list = amend the plan and re-review, never extra edits.
REQUIRED GATE, `--delegate` dry run (also re-confirms the Step 4 probe with the final files): in a throwaway worktree, a 3-file toy plan, run
`/implement <toy plan> --delegate`. Expected: (1) the spawn is NOT blocked as `general-purpose`; (2) a `git status` attempt by the agent is BLOCKED (branch (a)); (3) an
off-list edit is caught by Phase 2c (file-set check) and a created tag or branch by the snapshot compare. Paste command, expected and actual into the PR description.
Done when: every command exits 0 (quote the output) and the dry-run evidence is in the PR description. The full suite is NOT run here: owner rule = one run on the Pro; the
plan's final gate is that single run, started by the owner.

### Step 10 (Phase E): Changelogs and state
`CHANGELOG.md` `[Unreleased]`: "Changed: /implement delegates the edits of a plan of >= 3 files or steps to the new `plan-implementer` agent in the plan's worktree (`--inline` keeps the old behaviour); the main session checks the file set and git state and diff and runs the targeted tests. Added: `plan-implementer` agent; `shell-write-gate` refuses git / baseline flags for that role (tokenised check, speed bump)." Plus `.ai/SESSION_STATE.md` (include the Step 4 probe branch, (a) or (b), and the dry-run result) and `.ai/CHANGELOG_AI.md` entries (CLAUDE.md "Docs" rule).
Done when: entries present; `python3 scripts/gen-plan-index.py` run after commit and `--check` exits 0.

### Step 11 (Phase F): Reach the live install (owner-run, after merge)
Verified install shape: `~/.claude/commands` is a symlink to `~/.claude-kit/.claude/commands`; `~/.claude-kit` is a claudekit checkout on main at 342a682 (behind origin);
`~/.claude/agents` is a symlink to `/Users/omarmokhtar/IdeaProjects/agent-config/accounts/personal/agents/`, a DIFFERENT repo, whose entries are per-file symlinks into
`/Users/omarmokhtar/.claude-kit/.claude/agents/` (e.g. planner.md, reviewer.md).
1. After the claudekit merge: `git -C ~/.claude-kit pull --ff-only`. Commands and `_shared/*.md` go live through the symlink (hooks too if `~/.claude/hooks` also points into the kit; UNVERIFIED, owner checks `ls -l ~/.claude/hooks`). No `settings.json` change: no hook is added or re-registered, so no owner-only `! ` edit.
2. A new agent file is NOT live until agent-config has its own symlink. Owner follow-up F1: an agent-config PR adding `accounts/personal/agents/plan-implementer.md -> /Users/omarmokhtar/.claude-kit/.claude/agents/plan-implementer.md`. Same follow-up on the Air (its own checkout drifts: pull there, add the same symlink).
3. Until F1 lands, `/implement` cannot spawn the agent (unknown agent, and context-budget-gate blocks a `general-purpose` stand-in): per section (c) it STOPs and offers `--inline`; nothing breaks.
4. Then `ck doctor --strict` in the live tree; restart sessions (running sessions keep old commands and agents).
Done when: `~/.claude/commands/implement.md` contains `plan-implementer` and `~/.claude/agents/plan-implementer.md` resolves to the kit file (read both).

## Testing Strategy
Behavioral tests in Step 5 run the real hooks with `agent_id`/`agent_type` payloads and the meta-file fallback; negative controls (other roles, absent role) prove no
regression; two mutation runs prove tests 3, 7, 9 can fail; tests 6 and 8 are labelled structural guards (they prove the text exists, not model behaviour). The two live gates
(Step 4 probe, Step 9 dry run) cover what tests cannot: that the harness really delivers the role signal and that Phase 2c catches off-list edits. Targeted pytest only until
the owner's single full run on the Pro.
Validation commands (all must exit 0): `python3 -m claudekit.cli.main lint .`; `python3 scripts/gen-registry.py --check`; `python3 scripts/gen-docs.py --check`;
`python3 scripts/gen-model-policy.py --check`; `python3 scripts/check-context-floor.py --check`; `ruff check src/ tests/ scripts/ .claude/operations/scripts/`; targeted pytest
(Step 9 list, including `tests/test_agent_prompt_size.py` and `tests/test_lint.py`); `python3 scripts/gen-plan-index.py --check` after commit.

## Alternatives considered
1. `general-purpose` + `CK_ALLOW_GENERAL_PURPOSE=1` (what the owner's note suggests): rejected, the gate blocks it because frontmatter caps cannot reach it (56 turns / 246K measured, context-budget-gate.py:724-728).
2. Re-create an agent named `implementer`: rejected, collides with `removedAgents.implementer` (skills-registry.json:939-941) and the old pipeline's history.
3. Reuse `refactor-cleaner` / `tester` / `build-error-resolver` (they have Edit): rejected, their prompts are for other jobs (dead code, tests, build errors).
4. `ck implement` CLI that runs `claude -p --agent ...` (like `ck flow`): rejected for now, heavier, a second delivery path, and it loses the interactive hook context.
5. Subagent returns a patch, main applies it: rejected, doubles the diff in main context and the subagent's edits would not run through plan-gate.
6. Keep main-session-only and rely on `/compact` and stage handoff: this stays as `--inline`; it did not stop the handoff restarts.
7. Also edit the policy region of CLAUDE.md and the templates to say "the parent edits": deferred (R6).
8. Keep a regex for the git ban (v1): rejected, it missed `$(git ...)`, `env git`, `xargs git` and matched the bare word; replaced by the tokenised helper (Step 4).

## Rollback
Each phase is its own commit, so a phase reverts alone.
- Before merge: from the main checkout, owner-run: `git worktree remove /Users/omarmokhtar/IdeaProjects/claudekit-wt-implsub` then `git branch -D feat/implement-subagent` (nothing was installed live).
- After merge: `git revert -m 1 <merge sha>` (additive change: one agent, one reference file, one role-keyed hook rule, text). Revert only Phase B (`git revert <phase B sha>`) to restore the old owner-gated rule text while keeping the code.
- Fastest runtime rollback, no revert: `/implement --inline` (the old behaviour is kept verbatim as Phase 2b); or delete the symlink below so delegation STOPs.
- Live: `git -C ~/.claude-kit pull --ff-only` after the revert lands; revert the agent-config PR from Step 11 F1 (removes the `plan-implementer.md` symlink); same on the Air; then `ck doctor --strict` and restart sessions.
- Generated files after a revert: re-run `scripts/gen-registry.py`, `scripts/gen-docs.py`, `scripts/gen-model-policy.py`, `scripts/gen-plan-index.py` and their `--check`.

## Risk Assessment
- R1 cwd/root (gap 1 in (b)): plan-gate does not bind an edit outside the hook's root. Likelihood medium, impact high (an ungated edit). Mitigation: Step 6 STEP 0 item 5 precondition + Phase 2c file-set check; STOP otherwise.
- R2 Bash writes bypass plan-gate for any caller. Likelihood low, impact medium. Mitigation: only Phase 2c (per-batch file list, `status --porcelain --ignored`, `plan-check` per path); stated honestly as a speed bump.
- R3 Role signal absent for a spawned agent (the git ban silently does not fire). Likelihood unknown, impact medium. The gate already relies on `agent_type` with the meta.json fallback (context-budget-gate.py:444-460) and Step 4 copies both sources. Mitigation: the required live probe with explicit branches (a)/(b); branch (b) makes default delegation a Blocker and keeps `/implement` inline by default.
- R4 `check-context-floor.py` budget may tip over: agent description <= 150 chars (~5.5k of 10000 used); CLAUDE.md/AGENTS.md replacement is shorter than the old text; budget raise is owner-only.
- R5 Generated-file fan-out: counts live in README.md, AGENTS.md, docs/AGENTS.md, docs/ARCHITECTURE.md, main.py block; if `gen-docs.py` touches another file, amend `Files:` and re-review (the list is frozen after approval).
- R6 The CLAUDE.md "Token & Model Policy" v8 region and `templates/*/CLAUDE.md` say "the parent edits": still true for `--inline`; left alone to avoid a v9 bump across the templates + `ck adapt` + tests/test_adapt.py:43. Owner follow-up.
- R7 The tokenised git check misses indirect git (python -c, os.system, `find -exec git`, renamed binary, eval). Mitigation: Phase 2c snapshot compare (HEAD, branch, stash, tags, refs, index) + probe; documented as a speed bump, not a sandbox (hard rule 6).
- R8 Blast radius of the hook edits: `shell-write-gate.py` runs on every Bash call under all profiles and `context-budget-gate.py` on every tool call (gate hubs; no `project-graph` query was run, so the fan-in is unmeasured). Mitigation: the new code runs only when the role == `plan-implementer`, the context-budget-gate diff is two lines, the existing allow-tests stay green, and `git diff` is checked in Step 3.
- R9 plan-gate globs: `.claude/plan-gate.globs` classifies `.claude/hooks/` as T3 for the kit (plan-remove-ops-main-session.md:37), so every hook/agent edit needs this plan APPROVED first (`review-record.py plan-check` exit 0): STEP 0 of this plan's own implementation. A `Files:` omission found later means amend and re-review.
- R10 Prior-art match (Phase 0): the only related history is the ops-era `implementer` (plan-remove-ops-main-session.md:7, plan-implementer-no-git.md, plan-ck-implement.md), removed for unscoped Bash, `memory:` Write grants, git use and cost, not rejected by a reviewer. This plan differs: no ops.json, explicit `tools:` and no `memory:`, a role-keyed git ban, a post-run Phase 2c compare, the cost cap (`maxTurns: 60`, 6M line), a different name, and the owner's G-017 consent. A silent miss in the stores is unknown, not proof.
- R11 Live install lag: the agent is not spawnable until the agent-config symlink (Step 11 F1) lands on each Mac; `/implement` then STOPs and offers `--inline`. Impact low.
- R12 lint ratchet: `implement.md` may not exceed 148 lines; mitigated by moving Mode/brief/Phase 2c into the reference file and keeping `implement.md` <= 145; the baseline is never edited.
- R13 Open: whether a running session can spawn an agent file created mid-session (UNVERIFIED, Step 4 point 5); fallback is a fresh session in the throwaway worktree.

## Code Quality
Minimal diffs; Python stdlib-only in the hook and py3.9-safe (mypy target); ruff line length 100; `_git_forbidden` and `_agent_role` are small pure functions (<= ~40 lines each) covered by a
parametrised table; one role-keyed rule, not a new hook (no `settings.json` or dispatch-registry change); bash-3.2 untouched; no near-duplicate asset (the reference file consolidates Mode, brief
and Phase 2c, `implement.md` only points at it); behavioral tests with mutation controls, structural guards labelled as such; counts only via generators; `lint-baseline.json` never touched;
every prose edit replaces only the quoted phrase with a qualifier, never a rewrite.
