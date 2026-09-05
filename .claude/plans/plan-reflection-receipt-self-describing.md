# Plan: make the reflection receipt demand self-describing

**Tier 2** (multi-file: `reflection.py`, `reflection-gate.py`, two test files, CHANGELOG; no
security or schema surface). Executed with `--no-approval`, disclosed here.

## Why

A qa-agents session on 2026-09-05 needed FOUR Write+run cycles to clear one reflection
checkpoint: the demand said `inbox-<session-key>.json` without saying the key is a hash of
the session id; the validator said "trigger is not a supported enum value" without naming
the enum or the one value the pending checkpoint required; and the fingerprint check named
neither the expected list nor the supplied one. Each omission cost a round. The same
transcript then ran into Claude Code's built-in `/goal` loop re-firing ~25 times on a task
whose remaining step was human-only, until the 9-block cap overrode it -- nothing in the
kit implements `/goal` and `reflection-gate` already honours `stop_hook_active`, so that
part is not ours to fix, but the Stop demand can say what to do about it.

## Changes

1. `reflection.receipt_instructions(session_id=None)`: with a session id, print the EXACT
   inbox path, the exact `--session-id` value, the exact `trigger` the pending checkpoint
   requires (or `learning-loop`), the exact `failureFingerprints` list, and the
   `durableDisposition` enum.
2. Validators name the expected value in every refusal (trigger enum, checkpoint trigger,
   fingerprints expected vs supplied, disposition enum).
3. `reflection-gate.py` passes the session id at all three call sites; the Stop demand adds
   one line: if a `/goal` is set and the remaining step is human-only, `/goal clear`.
4. Tests: `tests/test_reflection_gate.py` asserts the Stop demand contains the exact
   filename, trigger and fingerprints; `tests/test_reflection_ledger.py` asserts each
   validator refusal names the expected value. Mutation proof recorded in the archive row.
5. `CHANGELOG.md`: an `[Unreleased]` entry for the user-visible change (the demand text
   every blocked session reads is user-visible), and `.claude/plans/INDEX.md` +
   `.claude/plans/archive/README.md` for the plan lifecycle.
