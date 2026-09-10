# Plan: Repo Hygiene Gates (generic, fleet-wide)

Status: REVISION 2 — round-1 review REJECTED (57/100); all 8 findings addressed (Golden Rule; no code until approved)
Author: session 01QseiamXDpuHdWf2jW696wz · 2026-09-09
Tier: 3 (hook/enforcement surface + fleet rollout) → planner + ops.json + reviewer

## 1. Problem (measured, not assumed)

Measured in `~/IdeaProjects/qa-agents` (private source) and
`~/IdeaProjects/qa-agent-pro` (public publish target), 2026-09-05..09:

| Signal | Measured | Intended |
|---|---|---|
| worktrees | 36 (25 in dead sessions' `/private/tmp/claude-501/*/scratchpad/`) | <= 5 |
| branches | 81, of which 75 already merged into main | merged => deleted |
| `.worktrees/` disk | 910 MB (vs 218 MB `.git`) | ~1 tree per active agent |
| commits / 4 days | 347 | n/a |
| unpushed on main | 3 | 0 |
| public repo CI | none (`.github/` absent) | build gate |
| public CHANGELOG version sections | 1 (heading renamed per release) | 1 per release |

Downstream damage this produced: `qa-agent-pro` v1.81.0 shipped a manifest
recording the wrong tree, was reverted 4h later in a PATCH release
(`06bd78ab`), silently withdrawing two shipped modules from users. The
committed `MANIFEST.sha256` still does not reproduce from its own tag
(`start.cmd` CRLF-vs-LF), so a clean rebuild fails its own integrity check.

## 2. Root cause — three enforcement gaps in ClaudeKit itself

ClaudeKit already ships the right machinery; nothing makes it binding.

- **G1 — the cap does not bind.** `worktree-manager.py:43` sets
  `MAX_WORKTREES = 5`, but `cmd_create` (line ~195) counts only entries in
  `.claude/state/worktrees.json`. A raw `git worktree add` never registers,
  so the cap is invisible to it. `command-guard.sh` contains no `git
  worktree` rule. Result: unbounded sprawl under a cap of 5.
- **G2 — nothing garbage-collects.** `finishing-a-development-branch` and
  `gitOps.md` *describe* deleting a merged branch; no hook or script
  enforces it at merge time. 75/81 branches are merged-but-alive.
- **G3 — the session is blind to sprawl.** `session-start.sh` reports project,
  package manager, build/test/lint. It does not report worktree count, branch
  count, or unpushed commits, so a session cannot see it is entering a repo
  with 36 trees, and adds one more.

Deliberately **out of scope**: code review. Review happens in the private
repo; the public repo is an export. These gates are deterministic and
token-free by design — no agent is invoked by any of them.

## 3. Design principles

- Language-agnostic: git + POSIX sh only. No Python/Node/Java assumptions.
- Advisory-by-default, blocking only where the user opts in. Fleet repos
  differ; a hard block that surprises a downstream repo is a regression.
- Bash 3.2 / macOS safe (hard rule 8). Blocking hooks: `exit 2` + stderr
  (hard rule 2).
- Extend existing assets; add no near-duplicates (task 008).

## 4. Phases

### Phase A — close the bypass (G1)

- A1. `worktree-manager.py`: count worktrees from `git worktree list`
  (ground truth), not from the registry, when enforcing `MAX_WORKTREES`.
  Registry stays the metadata store; git stays the source of truth.
- A2. `worktree-manager.py`: `prune` gains `--stale` to report (and with
  `--yes` remove) registered-or-unregistered worktrees whose path is outside
  the repo root — the `/private/tmp/.../scratchpad/` class. Never removes a
  dirty tree or one holding commits absent from base.
- A3. New `worktree-guard.sh`. Advisory by default (stderr note pointing at
  the manager); blocking when `CK_WORKTREE_GUARD=block`. Refuses outright when
  the target path escapes the repo root, is UNRESOLVABLE (contains `$`, a
  backtick, `~`, or a glob this guard cannot evaluate), or is combined with
  `-C`/`--git-dir`/`--work-tree`, which move the frame of reference the guard
  measures against.
  **Scope, stated honestly (hard rule 6).** This is a string-level speed bump,
  not a sandbox. It reads the literal command text; the shell that executes it
  expands what the guard cannot. Unresolvable targets are therefore refused for
  being unresolvable, NOT because they are known-bad. A symlink inside the repo
  pointing out of it is not reachable by string parsing at all.
- A4. Behavioural tests: raw `git worktree add` past the cap is caught; a
  scratchpad path is refused; a legitimate in-repo `create` still succeeds.

### Phase B — make cleanup part of finishing (G2)

- B1. New `.claude/operations/scripts/repo-hygiene.py` — read-only `report`
  plus opt-in `clean`. Reports: merged-but-undeleted branches, worktrees over
  cap, worktrees outside the repo, unpushed commits on the default branch,
  `.worktrees/` disk. `clean` acts only on what `report` listed and only with
  `--yes`; MAX_DELETIONS-style bound applies (hard rule 4).
- B2. Wire into `/worktree` (`.claude/commands/worktree.md`) as `report`/`clean`
  subcommands. No new command asset.
- B3. Tests (`tests/test_repo_hygiene.py`): report is read-only; `clean`
  without `--yes` mutates nothing; an unmerged branch is never deleted;
  `--max-deletions` refuses before mutating; `--oneline` is silent when healthy.
  Guard tests live in `tests/test_worktree_guard.py`, held with the guard.

### Phase C — make sprawl visible (G3)

- C1. `session-start.sh`: one extra line, printed only when a threshold trips
  (worktrees > 5, merged-undeleted branches > 10, unpushed > 0). Silent on a
  healthy repo — no context cost where there is no problem.
- C2. Budget: `check-context-floor.py` must still pass. Target <= 1 line.

### Phase D — release integrity (generic)

- D1. New skill `release-integrity` (`.claude/skills/release-integrity/SKILL.md`,
  docs-only, no runtime): the four
  deterministic gates any release repo should run in CI —
  (a) artifact rebuilds byte-identically from a clean checkout of the tag;
  (b) any file deleted since the previous tag that appeared in that tag's
      manifest is declared in the repo's removed-paths ledger;
  (c) CHANGELOG gained a NEW version section, not a renamed heading;
  (d) version is strictly monotonic vs the latest tag.
- D2. Ship a reference `.github/workflows/release-gate.yml` template under
  `templates/`, parameterised, not project-specific.

### Phase E — fleet rollout

- E1. Extend `fleet-verify.sh` FILES list with the assets A1-D2 touch; verify
  byte-identity against `origin/main` AND prove the hooks execute (exit 0)
  under the standard profile — the existing two-check pattern.
- E2. Roll out with `fleet-commit.sh` to kitted repos only. Surgical: never
  overwrite a downstream file carrying project-specific content; leave
  downstream changes uncommitted for owner review; never merge downstream
  back (established fleet rules).
- E3. Per-repo report: what changed, what was skipped and why.
- E4. `qa-agents` and `qa-agent-pro` are the pilot repos — they generated the
  evidence and are the acceptance test.

## 5. Acceptance

Replay the failure: in a scratch clone, 36 worktrees and 75 merged branches
cannot be reached — A3 refuses the scratchpad path, A1 refuses past the cap,
B1 lists the merged branches. Every ClaudeKit DoD command passes. Mutation
proof for each gate: break the shipped artifact, confirm the check goes red.

## 6. Rollback

Every operation is independently revertible; none migrates data or rewrites
history. `execute-json-ops.py` writes a backup directory per run (`RESULT-JSON`
names it), so `/rollback` restores the whole batch.

| Change | Undo |
|---|---|
| `worktree-guard.sh` fires wrongly | Delete its row from `dispatch-registry.json` — the hook is inert unregistered. Whole-repo escape hatch: `ECC_HOOK_PROFILE=minimal`. |
| Guard too strict for one session | `CK_WORKTREE_GUARD` is opt-IN; unset is advisory. No unset value blocks. |
| Cap change wrong | Revert the `worktree-manager.py` edit; the registry format is unchanged, so no state migration is needed either way. |
| Session-start line unwanted | Delete the block, or delete `repo-hygiene.py` — the block is guarded by `[ -f "$HYG_SCRIPT" ]` and goes silent. |
| `repo-hygiene.py clean` deleted something | Branch deletions use `-d` and are refused while the base has unpushed commits; a deleted branch tip is recoverable from `git reflog` and worktree removal never touches commits. |
| Skill/template unwanted | Delete both files; nothing references them at runtime. |

Order to unwind: registry row -> session-start block -> `worktree-manager.py`
edit -> new files. Nothing depends on anything created later in the list.

## 7. Risks

- A hard block on `git worktree add` could break a legitimate downstream
  workflow → advisory default, opt-in blocking.
- Fleet rollout touching 16 repos at once → E2 leaves changes uncommitted;
  owner reviews per repo.
- `qa-agents` cleanup deletes 75 branches / 25 worktrees → destructive; needs
  the explicit list approved before any removal, and runs only after Phase B
  exists to do it safely.
- **Cap semantics change (round-1 review finding).** `git worktree list`
  includes the PRIMARY checkout. Counting it would have cut the agent budget
  from 5 to 4 silently; the helper subtracts the primary, so 5 agent worktrees
  remain available exactly as before.
- **The guard cannot evaluate shell expansion.** It refuses what it cannot
  resolve rather than guessing. Cost: a legitimate `git worktree add "$DIR"`
  is refused and must be respelled literally or go through the manager. Judged
  acceptable — the manager is the intended path.

## 8. Decisions (owner-resolved 2026-09-09)

1. **Worktree guard: ADVISORY by default.** stderr note pointing at
   `worktree-manager.py`; hard block only under `CK_WORKTREE_GUARD=block`.
   A path escaping the repo root is refused outright regardless of mode.
2. **Rollout: PILOT on `qa-agents` + `qa-agent-pro` first.** Fleet-wide
   (16 kitted repos) follows only after the gates are proven on the repo
   that generated the evidence. Phase E2 is therefore two repos, not 16;
   E5 (fleet-wide) is a separate, later approval.
3. **Phase D ships in ClaudeKit.** `release-integrity` skill +
   parameterised `templates/release-gate.yml`, not a qa-agent-pro-local
   workflow.

## 9. Ops artifacts

- `.claude/plans/plan-repo-hygiene-gates.ops.json` — GENERATED, 9 operations
  (4 file_create, 4 code_edit, 1 run_command). Dry-run status: success.
- **A2 dropped.** `prune --stale` would have duplicated what `repo-hygiene.py`
  already reports and reclaims (outside-root worktrees). Task 008 — no new
  near-duplicate assets. Phase A is now A1/A3/A4.
- **Verification is NOT in the ops config.** The engine allowlists
  `run_command` to formatters only. Every other gate is listed under
  `post_execution_gate` in the ops.json and runs after execution as the DoD.
- **Pre-flight findings (measured while building, not assumed):**
  * the guard's first parser missed `git -C <dir> worktree add` entirely and
    read the BRANCH instead of the path for `add -b <br> <path>` — both were
    live bypasses of the escaping-path refusal, both fixed and re-tested
    against 9 command shapes;
  * `repo-hygiene.py report` reproduces the measured sprawl on `qa-agents`
    (35 worktrees / 76 merged branches / 6 unpushed) and correctly EXCLUDES
    3 dirty worktrees from reclaim;
  * `clean` refused 95 deletions against `--max-deletions 25` and mutated
    nothing — the bound proved itself before it ever ran for real;
  * ClaudeKit itself trips the gate: 13 merged-but-undeleted branches.
- Phase E (pilot rollout) is a separate ops config, generated only after
  A-D land and the DoD gate passes.
