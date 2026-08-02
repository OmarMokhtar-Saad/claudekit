# Plan: Work-loss protection (concurrent-session wipe incident)

## Context

Incident in a kitted project: during multi-round ops work (Phase 1, 3a, 3b, 3d, R1, R2),
a concurrent session's external `git checkout`/`restore` reset one file
(`agents/test_scenario_agent.py`) to clean HEAD, silently wiping five rounds of
accumulated work. Discovery came late (31 test failures during R3), and recovery
required manual replay of archived ops configs.

Gap analysis against current kit defenses:
1. Command guard has **zero screening of destructive git commands** (`git checkout --`,
   `git restore`, `git reset --hard`, `git clean -f`, `git stash drop/clear`).
2. ops.json carries **no baseline binding** — the executor cannot detect "target file
   changed since this plan was authored"; only anchor-miss failures surface it.
3. Backups are **pre-execution only** (rollback), so recovery from external wipes is
   replay archaeology, not restore.
4. No concurrent-session awareness.

User approved all four protections (A+B+C+D).

## Changes

### A. Destructive-git screening — `src/claudekit/security/command_validator.py`
Add DANGEROUS_PATTERNS entries (block, exit per existing guard flow):
- `git reset --hard` (any position of flag)
- `git clean` with `-f`/`-fd`/`--force`
- `git checkout -- <path>` and `git checkout .`
- `git restore` EXCEPT pure `--staged` usage (worktree restore destroys; unstaging doesn't)
- `git stash drop` / `git stash clear`
Message: destroys uncommitted work — commit/stash first or the user runs it manually.
Benign forms stay allowed: `git checkout <branch>`, `git checkout -b`, `git restore --staged <p>`.
Tests in the existing validator test file, both directions.

### B. Baseline binding — ops engine
- `validate-config-json.py --stamp-baseline`: after successful validation, compute
  sha256 of every existing target file (code_edit/file_delete) and write
  `baseline: {"<path>": "sha256:..."}` into the config file.
- `execute-json-ops.py`: if `baseline` present, verify all hashes BEFORE any write;
  mismatch → abort (no partial work), report per-file drift ("changed since plan was
  stamped — re-validate or re-plan"). Absent baseline → warn once, proceed (back-compat).
- `operations-schema.json`: optional top-level `baseline` object.

### C. Post-execution checkpoints — ops engine + restore
- `execute-json-ops.py`: on success, snapshot final state of all touched/created files
  under `<backup_dir>/post/` and set `post_state: true` in manifest.json.
- `restore-backup.py --post`: restore from post/ (forward recovery after external wipe),
  same traversal guards as the existing restore path.

### D. Concurrent-session warning — `session-start.sh`
- Per-pid lock files `.claude/locks/session-<pid>` (bash 3.2-safe), prune dead pids
  (`kill -0`), warn when other live session pids exist: "another session is active —
  coordinate file ownership". Warning only, never blocks. `.claude/locks/` gitignored.

## Verification
- New/extended behavioral tests: validator (destructive vs benign git), stamp+verify+
  drift-abort, post-checkpoint + `--post` restore, lock warn/prune.
- Full DoD gate; then fleet rollout (16 projects, settings.local.json preservation loop).

## Out of scope
- Hard mutual exclusion between sessions (locking writes) — warning only in v1.
- Auto-commit/WIP-branch checkpoints (touches user git history; owner-gated).
