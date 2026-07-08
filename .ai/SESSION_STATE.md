# Session State

> Update this file at the end of every significant AI working session. It is the resume point.

**Last updated:** 2026-07-08 · **By:** Claude (Fable 5) — AI-handover documentation session

## Current project state

- v2.1.0 complete on `main`; 516 tests passing; all CI gates green as of `0c9223b`.
- Release to PyPI **pending user decision** (tag push triggers release.yml / Trusted Publishing).
- The 2026-07-05 audit (`review/`) is the work queue: tasks 001–006+011 done; 007–010, 012–014 open.

## Recent changes (this session)

- Added the self-adaptation capability: `/adapt` command + `project-adaptation` skill (registered; counts now 40 commands / 74 skills across README, docs, .ai). First product change after Phase 1 — needs a conventional commit.
- Created the `.ai/` AI operating system (36 documents) from a full-repository analysis.
- Created the root `CLAUDE.md` (the repo previously had none — only templates for user projects).

## Important files for orientation

`.claude/plans/phase-1-HANDOFF.md` (the previous handoff, still accurate for Phase-1 detail) · `review/FINAL-REPORT.md` + `review/roadmap.md` (audit + plan of record) · `.claude/settings.json` (enforcement truth) · `scripts/gen-docs.py` (count gate) · `src/claudekit/cli/main.py` (CLI) · `.claude/hooks/lib.sh` (hook helpers).

## Pending work (priority order)

1. **User-gated:** tag `v2.1.0`, publish to PyPI, announce. Recipe: [PLAYBOOK.md](PLAYBOOK.md) §Release.
2. Task 008 — corpus consolidation (merge candidates listed in [BACKLOG.md](BACKLOG.md); get owner sign-off first).
3. Task 010 — eval framework (`evals/` fixtures + `ck eval`).
4. Task 009 — context-budget reduction (hook dispatcher consolidation, ≤2 mandatory skills/agent).
5. Tasks 012/013/014 — behavioral tests, OSS health files, supply-chain signing.

## Blocked / waiting

- PyPI publish → owner go-ahead.
- Plugin packaging (007) and consolidation deletions (008) → owner sign-off (user-visible surface changes).

## Known risks

- First real release.yml run is untested end-to-end (Trusted Publishing config could need iteration).
- `ck update` three-way behavior is warn-and-overwrite-with-backup, not a true merge — user data loss is guarded but UX is rough (roadmap §2.2).
- Docs drift risk is CI-gated for counts only; prose claims can still rot — sweep during release prep.

## Suggested first task for a fresh session

Run the DoD gate (see [MODEL_ONBOARDING.md](MODEL_ONBOARDING.md) §5) to confirm the tree is green, then pick up the top unblocked pending item.
