# Handoff: finish the backup-history branch

Repo: `/Users/omarmokhtar/IdeaProjects/claudekit`. Branch: `fix/backup-history-ordering`
(2 commits: `aebd260`, `db8ac09`, both on top of `d8b1e16`).

Read `CLAUDE.md` first. Session gotcha: if Edit/Write is blocked by `ops-enforcement`, the
gitignored `.claude/settings.local.json` with `ECC_HOOK_PROFILE=minimal` is missing —
restore it per CONTRIBUTING.md, never bypass hooks another way.

## What the work is

`.claude/operations/scripts/restore-backup.py --list` claimed "most recent first" and
sorted directory NAMES, which orders by plan slug before time — so anyone reaching for the
latest backup to restore got the alphabetically-last plan. Fixed to sort by the parsed
`timestamp` inside each manifest. `--list` also now reports plan/counts/`Complete:`, and a
new `--list --json` emits the rows bannerless for machine consumers.

Two review rounds ran. Round 1: 75/REVISE (found a regression the fix itself introduced).
Round 2: 92/APPROVED, zero blocking, one MINOR — which is already fixed in the working
tree but NOT yet committed. **The review floor is met. Do not run a round 3.**

## State right now

Committed: `aebd260` (the fix), `db8ac09` (round-1 findings).

**Uncommitted in the working tree — this is your first task.** The round-2 MINOR fix:
`--list --json` was still emitting raw non-list `files`/`created_files` with
`"readable": true, "error": null`, so a consumer doing `len()` hit a TypeError and
`"files": "a.py"` silently reported four files. Both output modes now go through one
`manifest_file_list`, and `manifest_field_faults` names a dropped field in `error` rather
than silently substituting `[]`. Applied via ops config, already archived at
`.claude/plans/archive/ops-backup-history-json/` with a README row.

Files that are YOURS to commit (staged or not):
- `.claude/operations/scripts/restore-backup.py`
- `tests/test_backup_history.py`
- `.claude/plans/archive/README.md`
- `.claude/plans/archive/ops-backup-history-json/` (untracked)

Verified already: 32 tests pass; 3 new mutants killed (emit the raw value / suppress the
faults / force an error); ruff clean; mypy clean; delivery-contract gate 7 passed.

A full `python3 -m pytest tests/ -q` was RUNNING when this handoff was written and had not
reported. **Re-run it and read the result before committing — do not take my word for it.**

## Tasks, in order

1. **Verify the suite.** `python3 -m pytest tests/ -q` (~17 min). Expect exactly ONE
   failure: `tests/test_request_shaping.py::test_plan_index_gate_still_passes`, caused by
   another session's UNTRACKED `.claude/plans/plan-agent-memory-learning.md`. Confirm the
   cause yourself with `python3 scripts/gen-plan-index.py --check`. **Do NOT regenerate
   INDEX.md to clear it** — writing a row for an uncommitted file makes every local gate
   go green and CI go red on a row it cannot see (the trap is documented in
   `.claude/plans/archive/README.md`). Any OTHER failure is real and is yours to fix.

2. **Commit the hardening** as a third commit. Conventional commit, one concern,
   `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.
   Stage ONLY the four paths listed above — see the concurrency warning below.

3. **Re-run the secret self-scan AFTER committing** (committing is what makes the files
   tracked and visible to it):
   `python3 -m pytest tests/test_day_one_blockers.py -q -k "no_committed_file_matches"`
   Expect 13 passed.

4. **Ask the owner about merge/PR.** Do not push to `main` or open a PR without being
   asked. If asked, `gh` is available.

5. **Ask the owner before switching branches back** to `feat/agent-memory-learning`.

## Concurrency — read this before any git command

Another Claude session is ACTIVELY working in this same working directory and has been
writing throughout. Its files (do not stage, do not modify, do not clean up):
`.claude/plans/plan-agent-memory-learning.md`, `.claude/plans/plan-agent-memory-learning.ops.json`,
`.claude/reports/research/agent-memory-selflearning-2026-09-06.md`,
`.claude/reports/reviews/agent-memory-learning.json`,
`.claude/knowledge/rejections/agent-memory-learning.md`, and modifications to
`.claude/knowledge/rejections/INDEX.jsonl`.

`.claude/reports/research/llm-wiki-net.md` is a research cache from this session; it is
untracked and deliberately uncommitted. Leave it.

Re-check `git branch --show-current` and `git log --oneline -1` immediately before and
after every git operation — the branch has already moved under this session once tonight.
Never `git checkout`, `reset`, `stash`, or `clean` without asking the owner first.

## Rules that bind you here

- **Iron Law**: every code change flows through an ops.json executed by
  `.claude/operations/scripts/execute-json-ops.py`. Never hand-edit source. Sequence:
  write config -> `validate-config-json.py <config>` -> `--dry-run` -> execute
  (`--no-approval` is correct for Tier 1). Then move the spent config to
  `.claude/plans/archive/<dir>/` and add a row to `.claude/plans/archive/README.md`, or
  `test_queued_ops_configs_validate_against_head` fails.
- **Golden Rule**: no code changes without explicit owner approval. Task 1-3 are already
  approved. Anything beyond them is not.
- **Verify by executing, never by reading.** If a subagent or a document tells you
  something is true, reproduce it before acting. Round 1's findings were all reproduced
  before being accepted, and one of my own "proofs" had already passed for the wrong
  reason.
- Don't claim done without pasted command output.

## Deliberately NOT in scope

Rewiring the queued-ops and archive gates onto `--list --json` — the payoff for this
work, but it needs its own plan and its own session, and it is owner-gated.

## Context worth having

The mutation lesson from round 1, because it will bite you the same way: a two-fixture
ordering test can only catch a mutation that INVERTS two rows, not the absence of ordering
— deleting the sort entirely left the headline test green on filesystem enumeration luck.
The test now uses three fixtures whose time order is a rotation of any enumeration order.
When you add a test here, mutate the shipped code and prove it reds for the reason you
think it does.
