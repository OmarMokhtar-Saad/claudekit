# Plan — the context-floor gate must be able to fail

**Tier:** 2 (three files; a DoD gate's honesty, no schema or public API surface)
**Base:** `34a4140`
**Ops config:** `.claude/plans/ops-floor-gate-exit-code.json` (3 ops)

## The defect

`scripts/check-context-floor.py:88` was `return 1 if (check and not ok) else 0` in the
`--json` branch and `return 1 if check else 0` in the text branch. So the bare invocation
printed `FAIL: context floor over budget` on stderr and **exited 0** — and `CLAUDE.md`'s
command block prescribes exactly the bare form, which means the documented way to run this
gate was the one way it could not fail. A gate that reports failure and returns success is
the class this repo ratchets against. CI is unaffected: it passes `--check` (`ci.yml:90`).

Found as a follow-up of Phase 1b, filed rather than folded in — one concern per commit.

## The change

- `scripts/check-context-floor.py` — the exit code follows the measurement, never the flag,
  in **both** branches. `--check` is still accepted, for symmetry with the other generator
  gates, and is now ignored.
- `CLAUDE.md` — the command block gains `--check` so the documented invocation matches the
  other four generator gates. Comment alignment is dropped to one space rather than padded,
  because `CLAUDE.md` is weighted ×4 in the floor and had **44 characters of headroom**
  (30956/31000). Measured cost of the shorter form: **12** weighted characters (3 raw ×4),
  leaving 32 — which is 8 raw characters of `CLAUDE.md`. Recorded plainly because that is
  tight: the review that passed this change argued the edit should be dropped entirely,
  since op 1 alone makes the previously-misleading bare form correct. It is kept on owner
  instruction, for symmetry with the other four generator gates.
- `tests/test_context_floor.py` — three tests, all asserted WITHOUT `--check` so
  reintroducing the flag gate reddens them.

## Must be proven by mutation, not asserted

1. **The bare form fails when over budget.** Restore `return 1 if check else 0` and
   `test_the_bare_invocation_fails_when_over_budget` must go RED. This is the defect.
2. **The bare form still succeeds within budget** — a misplaced `return 1` would make the
   gate fail unconditionally, which is worse than the bug.
3. **`--json` has the same fix**, proven the same way in its own branch.
4. The repo's own floor stays green under both invocations.

## Definition of Done

All nine gates, run AFTER committing. Archive the spent config first.
