# Plan: Team coordination for concurrent sessions across accounts (rev 5)

**Date**: 2026-11-07 | **Requested by**: Omar ("make them all work like a team: one goal, shared bugs and work, know what happened, debug → plan → review before implement, handle every same-file case, keep token cost low"; "revise" after rev 1 review).
**Rev 5** addresses the rev 4 review (84 REVISE): guard template is `concurrency-guard.py` `blocking_enabled()` (not plan-gate.sh), no profile guard in Phase 1 hooks, dogfood note. **Rev 4** addresses the rev 3 Sonnet review (74 REJECTED): `src/claudekit/profiles.py` `GUARDED_HOOKS` entry for `team-edit-gate` (step 3.4, Files, P3), required `ECC_HOOK_PROFILE` guard in the gate (step 3.2), plus minors (three registry rows, matcher alias note, gen-docs rewrite instead of hand-fix, `--fmt` step, extra exit-8 and P4 tests). **Rev 3** addresses rev 2 review (82 REVISE): Rollback 4, exact gen-docs outputs, `land` mode required + dirty-main guard, enumerated registry rows, profile tests, one-path-per-line Files. **Rev 2** addressed rev 1 review (reviewer 58 REJECTED + design and readiness critics): adds Rollback, a parseable `Files:` header split by phase, dispatch-registry registration as an owner step, ordered steps, a stage transition table, a failure table, pinned choices, an Alternatives section and per-case behavioural tests.
**Research base**: Hermes house-ops (`house_touches.py`, `house_claimer.py`, `house_worktrees.py`, `house_merge_queue.py`, `house_lease.py`; ideas only, no code copied — Hermes is a different repo); Claude Code agent teams docs https://code.claude.com/docs/en/agent-teams ; Beads https://github.com/steveyegge/beads ; agentlocks https://github.com/simke9445/agentlocks .

Tier: 3 (new hooks; Phase 3 adds a blocking Edit/Write gate)

## Problem

Several interactive Claude sessions (two accounts → two config dirs) work one repo at once. They overwrite each other's edits, duplicate work, do not know what the others did or hold, and edit before debugging/planning/review.

What exists: `concurrency-guard.py` (blocks tree-wide git commands in a shared tree), `worktree-manager.py` + `.ai/CONCURRENCY.md` (one worktree per session, registry `.claude/state/worktrees.json`), plan-gate (Tier 3 plan before edit). Nothing shares a goal, tasks, bugs or history; nothing leases files; nothing ties work to stages across sessions.

## Non-goals

- Replacing Hermes cards / gatekeeper. house-ops merges stay on the Approvals card.
- Cross-machine sync. `.team/` is per machine.
- A sandbox. Every gate here is a speed bump against honest mistakes (hard rule 6). An agent that wants to bypass can; the design makes bypass visible, not impossible.
- Pushing. `team land` never pushes.

## Alternatives considered

| Option | Why not (alone) |
|---|---|
| Native agent teams | Task list + mailbox under the account config dir; one lead per team; no file locks (docs: same-file edits overwrite). Cross-account sharing is unverified → Step 0.1 tests it. If it works across accounts, Phase 2 shrinks to a thin adapter. |
| Beads (`bd`) | Good task/claim model, but alpha, external binary needed on both accounts, newer versions need Dolt; no file leases, no stage gate. Phase 2 schema stays Beads-compatible (id, status, claim) so a later swap is possible. |
| agentlocks | File locks via hooks only; no goal/tasks/bugs/log. Covers Phase 3 lease part only, adds an external dependency. |
| Locks only, no stages | Cheapest; solves overwrites but not duplicate debugging or unreviewed edits. Kept as the shape of Phases 1–3; Phase 4 stages are opt-in per repo (`.team/config.json` `stages: true`). |
| Do nothing beyond worktrees | Worktrees stop index/tree clobbering but not semantic duplication or late merge conflicts. |

## Pinned choices

- **Location**: `.team/` = `$(dirname $(realpath $(git rev-parse --git-common-dir)))/.team`, i.e. the main checkout's root; identical from every linked worktree. Bare repo or no git → `team` prints "not a git checkout" and exits 3; hooks no-op. Added to `.gitignore`.
- **Opt-in**: the system is active only when `.team/config.json` exists (`team init`). Absent → every hook exits 0 silently.
- **Session id**: `session_id` from the hook JSON payload; the CLI reads `$CLAUDE_SESSION_ID` if set, else the id written by the SessionStart hook to `.team/sessions/<worktree-hash>.current`. **Account**: basename of `$CLAUDE_CONFIG_DIR` (default `~/.claude`).
- **Liveness**: heartbeat only (no pid check — hook pids are short-lived shell children). Session stale after `stale_min` (default 20) minutes without a heartbeat; heartbeat is written by every PostToolUse, so only an idle or dead session goes stale.
- **Paths**: repo-relative to the session's worktree top level, `os.path.realpath` first (symlinks resolved), `/`-separated, compared with `str.casefold()` (APFS is case-insensitive by default). Lease file name = first 16 hex of sha256 of the normalized path.
- **Base branch**: `git symbolic-ref refs/remotes/origin/HEAD` → fallback `config.json` `base`, else `main`.
- **Bug fingerprint**: sha256 of `normalize(err) | relpath | func`, first 10 hex. `normalize` lowercases, replaces hex runs ≥6 with `H`, digit runs with `N`, absolute paths with their basename, collapses whitespace.
- **Locking**: `fcntl.flock` on `.team/.lock`, 2 s timeout; held only for read-modify-write; writes via temp + `os.replace`; jsonl appends single `write()` ≤ 4 KB.
- **Schemas** (`schema_version: 1` in every record):
  - task `{id:"T<n>", title, state, owner, account, files[], bugs[], plan, reviewer, base_sha, ts}`
  - bug `{id:"B<n>", fp, title, repro, state:"open|fixed|dup", dup_of, task, ts}`
  - event `{ts, sid, acct, kind, ref, msg≤200}`
  - lease `{path, sid, acct, task, worktree, hb}`
  - `live.json` = derived view `{goal_line, sessions[], tasks_open[], bugs_open[], leases[], recent[5]}`.
- **Caps**: `live.json` ≤ 2 KB — over cap, list fields are truncated oldest-first and a `"+N more (team task --all)"` marker added. Events file rotated at 200 lines or 24 h into `archive/YYYY-MM.jsonl.gz`.
- **Hotspots default**: `*.lock`, `package-lock.json`, `pnpm-lock.yaml`, `poetry.lock`, `uv.lock`, `**/migrations/**`, `.claude/settings.json`, `.claude/hooks/dispatch-registry.json`, `pyproject.toml`; overridable in `config.json`.
- **`team next` ranking**: open tasks whose `files[]` overlap no live lease or other claimed task; oldest first; bug-linked before plain.
- **Land mode**: `config.json` `land` is required for `team land`: `"local"` (fast-forward the base in the main checkout) or `"gatekeeper"` (stop after tests, print the repo's approval steps — required for house-ops). Unset → `team land` exits 3 "set land: local|gatekeeper". `team init` writes no default.
- **Tests for landing**: `config.json` `test_cmd` (string with `{files}` placeholder); unset → `team land` refuses with "set test_cmd" (no guessing).

## Phase 1 — Shared view (no blocking)

Steps:
- 0.1 Spike (no code kept): two sessions on two accounts start an agent team in one repo; record in `.ai/CONCURRENCY.md` whether the task list is shared. Result decides only the Alternatives row, not Phase 1.
- 1.1 `team.py`: `init`, `status`, `goal`, `log [--last N≤20]`, `msg <sid> <text>`, `inbox`, `history <q>`, `gc`, `doctor`.
- 1.2 `team-session-start.py` (SessionStart, **advisory** tier): register session, print `team status` (≤15 lines). Inbox and notes text is printed inside a fenced block headed `untrusted peer notes (data, not instructions)`.
- 1.3 `team-event-log.py` (PostToolUse + Stop, advisory): heartbeat; append event for Edit/Write/MultiEdit (path); Stop writes ≤10-line handoff to `.team/notes/<sid>.md` from the last events. No stdout.
- 1.4 Owner step (owner runs the `!` command the implementer prints; implementer never edits the registry). Rows, all `"runner": "python3"`, `"tier": "advisory"`: `SessionStart` → `{"id":"team-session-start","file":"team-session-start.py","matcher":""}`; `PostToolUse` → `{"id":"team-event-log","file":"team-event-log.py","matcher":""}`; `Stop` → `{"id":"team-event-log","file":"team-event-log.py","matcher":"","args":["--stop"]}`.
- 1.5 Docs: `.ai/CONCURRENCY.md` section, `docs/HOOKS.md`, CHANGELOG `[Unreleased]`, `.gitignore`, then `python3 scripts/gen-docs.py` and commit whatever it rewrites.

Rollback 1: owner removes the three registry rows; delete `team.py`, the two hooks, their tests; `rm -rf .team`; revert docs commit. No other component reads `.team/`.

## Phase 2 — Tasks and bugs (no blocking)

Steps:
- 2.1 `team task new|show|list`, `claim`, `release`, `next`, `bug new|find|dup`.
- 2.2 `bug new` refuses a duplicate fingerprint and prints the existing id.
- 2.3 SessionStart shows MINE / OPEN lines.
- 2.4 `.claude/skills/multi-agent-coordination/SKILL.md` + its mirror `.agents/skills/multi-agent-coordination/SKILL.md`: point to `team`. Edit the SKILL.md body only (frontmatter `name`/`description` unchanged) so `skills-registry.json` stays valid; run `python3 scripts/gen-registry.py --check` and, if it reports drift, stop and report it.

Rollback 2: `git revert` the Phase 2 commit; existing `tasks.jsonl`/`bugs.jsonl` are inert data.

## Phase 3 — Leases and the edit gate (blocking)

Steps:
- 3.1 `team lease|unlease|who`, `team plan <T> --files a,b [--plan .claude/plans/x.md]` — with `--plan`, files are read from that plan's `Files:` (reuses plan-gate's list; no second list to maintain). Overlap with another claimed task or a live lease → refuse, task `blocked`, print the holder.
- 3.2 `team-edit-gate.py` (PreToolUse `Edit|Write|MultiEdit|NotebookEdit`, **blocking**; the alias tool names `str_replace_based_edit_tool|write_file` are deliberately excluded: the gate is a speed bump, not a sandbox): see Gate rules and Failure table. The hook MUST carry the guard in exactly the form of `concurrency-guard.py:244` `blocking_enabled()` (a function of that name returning `os.environ.get("ECC_HOOK_PROFILE", ...) != "minimal"`): under `minimal` the decision is still computed and logged as WOULD-BLOCK but the hook exits 0. Any other shape is rejected by `profiles.py:_scan_python` and fails `test_minimal_declaration_equals_the_minimal_guard[team-edit-gate]`, `check_declarations` and `ck doctor`. `plan-gate.sh` is NOT the template (it deliberately has no guard). The `minimal` declaration is `"advisory"`.
- 3.3 `team land <T>`: see Landing.
- 1.2/1.3 note: `team-session-start.py` and `team-event-log.py` must NOT mention `ECC_HOOK_PROFILE` (`test_no_unlisted_hook_carries_a_profile_guard` fails any unlisted hook that does).
- 3.4 Code step (implementer): add `"team-edit-gate": "team-edit-gate.py"` to `GUARDED_HOOKS` in `src/claudekit/profiles.py` (line ~58); without it `profiles.py:193` raises `ProfileError` and `tests/test_profiles.py` fails. Owner step: `PreToolUse` row `{"id":"team-edit-gate","file":"team-edit-gate.py","runner":"python3","tier":"blocking","matcher":"Edit|Write|MultiEdit|NotebookEdit"}` in `dispatch-registry.json`, and `"team-edit-gate": "advisory"` in `.claude/profiles/minimal/profile.json` (minimal profile → gate never blocks).

Gate rules (Phase 3 without stages): allow iff (a) path ∉ `.team/` (all direct edits of `.team/` blocked; use `team`), and (b) the path is leased by this session, or is free and inside the session's claimed task `files[]` (auto-lease). Otherwise exit 2 with ≤3 lines naming the holder and the fix command. Session with no claimed task and a free, non-hotspot path → allow + advisory note (keeps Tier 1 one-line fixes fast). Hotspot → always needs a lease.

Rollback 3: owner removes the gate row from `dispatch-registry.json` (instantly restores pre-gate behaviour) and the `team-edit-gate` row from `profiles/minimal/profile.json`; `team unlease --all`; revert commit.

## Phase 4 — Stages (blocking, opt-in `stages: true`)

Transition table:

| From → To | Command | Precondition | On failure |
|---|---|---|---|
| open → claimed | `team claim T` | not claimed by a live session | exit 4, prints owner |
| claimed → debugging | `team debug T` | — | — |
| debugging → planned | `team plan T --files … [--plan p]` | `repro` text or linked bug; files non-empty; no overlap | exit 4, task `blocked` |
| planned → reviewed | `team review T --approve` | reviewer sid ≠ planner sid (honest-mistake guard, spoofable) | exit 4 |
| planned → planned | `team review T --reject "<why>"` | — | rejection logged |
| reviewed → implementing | `team start T` | worktree HEAD contains current base (`merge-base --is-ancestor`) | exit 4 "rebase first" |
| implementing → verifying | `team verify T` | `test_cmd` exit 0 | stays implementing |
| verifying → landed | `team land T` | see Landing | stays verifying |
| any → orphaned | `team gc` | owner session stale | — |
| orphaned → claimed | `team claim T` | — | handoff note printed |
| blocked → planned | `team unblock T` | blocking task landed/released, or owner `--force` | exit 4 |

With stages on, the gate also requires state `implementing`. Tier 1 escape: `team quick "<title>" --file f` creates, claims and moves a one-file task straight to `implementing` (logged as `quick`; refused for hotspots).

Rollback 4: set `"stages": false` in `.team/config.json` (takes effect on the next tool call; the gate stops reading task state and Phase 3 rules apply); then `git revert` the P4 commit. Tasks left in `debugging|planned|reviewed|implementing|verifying` are inert data: Phase 3 treats any claimed task's `files[]` the same regardless of state, and `team task list` still shows them; `team release T` frees each.

## Same-file cases

| # | Case | Behaviour | Where enforced |
|---|---|---|---|
| 1 | Two plans list the same file | second `team plan` refused, `blocked` | CLI (P3) |
| 2 | Same file, different functions | one owner, no split | gate (P3) |
| 3 | Hotspot | lease always required; one task at a time | gate + CLI (P3) |
| 4 | Edit outside plan | blocked; `team plan T --add-file f` re-checks overlap | gate (P3) |
| 5 | File held by other session | blocked with holder + `team msg` hint | gate (P3) |
| 6 | Owner crashed/compacted/closed | stale after 20 min no heartbeat → `gc` frees leases, task `orphaned`, branch kept | CLI gc (P3) |
| 7 | Edit via Bash/sed/script | not prevented; `team land` refuses any changed path not in task files | land (P3) |
| 8 | Formatter/codegen | run inside `team land --fmt` on task files only | land (P3) |
| 9 | Two sessions in one tree | SessionStart warns when another live session has the same worktree; `concurrency-guard.py` stays on | advisory (P1) |
| 10 | Rebase conflict at land | `team land` aborts rebase, leaves tree clean, prints conflicted files and their owners | land (P3) |
| 11 | Stale base | `team start` refuses | CLI (P4) |
| 12 | Two lands at once | `.team/land.lock` flock, second waits ≤2 s then exits 4 "queue busy" | land (P3) |
| 13 | Same bug twice | fingerprint dedupe | CLI (P2) |
| 14 | Two accounts | state in repo `.team/`, not config dir | design (P1) |

## Landing (`team land T`)

1. `land.lock` (exit 4 if busy). 2. Record `pre_base = rev-parse <base>`. 3. In the task worktree: `git rebase <base>`; conflict → `git rebase --abort`, exit 5 with conflict list. 4. `git diff --name-only <base>...HEAD` ⊆ task files, else exit 6 listing extras. 5. `test_cmd` → non-zero exits 7. `team land --fmt` runs the project formatter on task files only, after step 3 and before step 4, and commits the result in the task worktree. `land: gatekeeper` stops here (exit 0) and prints the gatekeeper steps. 6. `land: local` only: refuse (exit 8) if the main checkout is dirty (`git status --porcelain` non-empty) or not on `<base>`, or if any live session other than this one is registered with the main checkout as its worktree or holds a lease there. Then `git merge --ff-only <branch>` in the main checkout; refuses if base moved since step 2 (exit 4, retry). 7. Append `landed` event, compact task to one line, archive details (idempotent; `team land --resume T` redoes 7–8 only). 8. Release leases, unlock. Never pushes. Steps 1–5 change nothing on base. Step 6 is a fast-forward of a clean checkout; if bookkeeping after the merge (step 7) fails, `team land` **prints** the undo (`git -C <main> reset --hard <pre_base>`) and does not run it.

## Failure table

| Condition | Phase 1–2 hooks (advisory) | Edit gate (P3+) | CLI |
|---|---|---|---|
| no `.team/config.json` | exit 0 silent | exit 0 silent | exit 3 "run team init" |
| lock timeout (2 s) | skip, exit 0 | **exit 2** "team busy, retry" | exit 4 |
| corrupt json / unknown schema | skip line, note once | **exit 2** "run team doctor" | `doctor` rebuilds `live.json` from jsonl, quarantines bad lines to `.team/corrupt/` |
| unexpected exception | exit 0 + hooks.log | **exit 2** + hooks.log (hard rule 2: fail closed) | exit 1 + traceback to hooks.log |
| override | — | `.team/gate.off` (owner creates with `! touch`); gate blocks Edit/Write of that path; every `status` shows `GATE OFF` in line 1 and SessionStart appends a `gate.off` event with the file's mtime | — |

`TEAM_GATE` env var removed (rev 1 finding: self-settable).

## Token budget

SessionStart ≤15 lines (~300 tokens); PostToolUse prints nothing; gate refusal ≤3 lines; CLI reads ≤20 lines; history only via `team history`; events ≤200 chars, long text to `.team/notes/`; plan ≤40 lines; handoff ≤10 lines. A PreToolUse advisory on Read of `.team/*.jsonl` nudges toward the CLI (documented as a nudge; `cat` bypasses it).

Files:
  `.claude/operations/scripts/team.py`
  `.claude/hooks/team-session-start.py`
  `.claude/hooks/team-event-log.py`
  `.claude/hooks/team-edit-gate.py`
  `.claude/hooks/dispatch-registry.json`
  `.claude/profiles/minimal/profile.json`
  `src/claudekit/profiles.py`
  `.claude/skills/multi-agent-coordination/SKILL.md`
  `.agents/skills/multi-agent-coordination/SKILL.md`
  `.ai/CONCURRENCY.md`
  `docs/HOOKS.md`
  `README.md`
  `CHANGELOG.md`
  `.gitignore`
  `tests/test_team_cli.py`
  `tests/test_team_hooks.py`
  `tests/test_team_edit_gate.py`
  `tests/test_team_land.py`
  `tests/test_team_concurrency.py`
  `AGENTS.md`

Per phase: P1 = `team.py`, `team-session-start.py`, `team-event-log.py`, `dispatch-registry.json` (owner), `.ai/CONCURRENCY.md`, `CHANGELOG.md`, `.gitignore`, hook-count prose (`README.md` "41 hooks"/"38 are reachable"/"41 workflow hooks", `docs/HOOKS.md` lines 3–4, `AGENTS.md` line 7 — run `python3 scripts/gen-docs.py` and commit its in-place rewrite of these lines, per hard rule 8; never hand-edit counts), `test_team_cli.py`, `test_team_hooks.py`. P2 = `team.py`, both `SKILL.md`, `test_team_cli.py`, `test_team_concurrency.py`. P3 = `team.py`, `team-edit-gate.py`, `src/claudekit/profiles.py`, `dispatch-registry.json` + `profile.json` (owner), hook-count prose (same three files), `test_team_edit_gate.py`, `test_team_land.py`. P4 = `team.py`, `team-edit-gate.py`, `test_team_edit_gate.py`, `test_team_cli.py`, `test_team_land.py`. `gen-docs.py` scans only its DRIFT_FILES (`README.md`, `src/claudekit/cli/main.py`, `AGENTS.md`, `docs/AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/SKILLS.md`, `docs/HOOKS.md`); of these only the three listed carry hook counts, and `main.py`'s generated block excludes hooks. `dispatch-registry.json` and `profile.json` are edited only by the owner (`!` command); they are listed so plan-gate covers them.

## Verification (per phase, targeted tests only)

- P1: `pytest tests/test_team_cli.py tests/test_team_hooks.py -q`; no-op without `config.json` (asserted: empty stdout, exit 0); SessionStart output ≤15 lines against a **full** fixture (200 tasks, 50 bugs, 10 leases, 200 events); inbox text rendered inside the untrusted block; gc rotates at 200 lines; latency benchmark: 50 runs of each hook on the full fixture, p95 < 150 ms.
- P2: dup fingerprint refused (normalization cases: different line numbers/addresses → same fp); `test_team_concurrency.py`: 8 processes race `team claim T1` → exactly one exit 0.
- P3: one gate test per case 1–5, 9, 14 asserting exit code + stderr; mutation check: patching the gate to always allow makes those tests fail. `test_team_land.py` in a temp repo: case 7 (sed-edited extra file → exit 6), case 10 (conflict → exit 5, tree clean, base unchanged), case 12 (second land → exit 4), base moved → exit 4, `--resume` idempotent. Failure table rows: corrupt json → exit 2; lock held → exit 2; exception injected → exit 2; `gate.off` → allow + `GATE OFF` in status. Gate tests set `ECC_HOOK_PROFILE=standard` explicitly; one test sets `minimal` and asserts the gate never exits 2. `test_team_land.py` adds: `land` unset → exit 3; dirty main checkout → exit 8, base unchanged; `land: gatekeeper` → base unchanged, steps printed; undo printed, not run.
- P3 also: two more exit-8 tests (main checkout not on base; live peer session registered on main); `team land --fmt` touches only task files; gate with `ECC_HOOK_PROFILE=minimal` never blocks; `pytest tests/test_profiles.py` passes with the new `GUARDED_HOOKS` entry.
- P4: gate refuses a `planned` task's file with stages on (mutation check: patched to allow, test fails); transition table rows, each failure exit code; `team quick` refused on hotspot; stale-base refusal. `stages: false` after tasks reached `implementing` → gate applies Phase 3 rules only (Rollback 4).
- Every phase: `ruff check .claude/operations/scripts/team.py .claude/hooks/team-*.py tests/test_team_*.py`; `python3 scripts/gen-docs.py --check`; `python3 scripts/gen-registry.py --check`; `python3 scripts/check-context-floor.py --check`; `ck doctor --strict`; `pytest tests/test_profiles.py tests/test_hook_delivery.py -q` (P1, P3: registry/profile rows).

## Risks

- Dogfood: this repo develops with `ECC_HOOK_PROFILE=minimal`, so the Phase 3 gate is advisory (WOULD-BLOCK logged) here, the same posture as `concurrency-guard`. Real enforcement needs a non-minimal profile; the gate tests use `standard`.

- Gate blocks real work → `gate.off` owner override, `team quick`, one-line refusal with fix command.
- Hook latency → flock held only for writes; p95 test.
- Peer notes as injection channel → untrusted fencing; never auto-executed.
- Interaction with plan-gate → `team plan --plan` reuses its `Files:`; the two gates check different things (plan reviewed vs file owned) and both must pass.
- Scope: four phases; each lands and is used before the next starts; Phase 4 starts only if Phases 1–3 are in daily use.
