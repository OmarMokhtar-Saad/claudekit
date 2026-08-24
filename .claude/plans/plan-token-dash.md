# Implementation Plan: the UNEXPLAINED intermittent was a dash in the token

**Status:** EXECUTED 2026-08-24. Tier 2 (one hook module, two test files, BACKLOG).
5 ops configs.

## The finding

`.ai/BACKLOG.md` has carried an **UNEXPLAINED intermittent** since 2026-08-21: one member
of the receipt-clears-checkpoint family fails in roughly one full-suite run in nine, passes
standalone, passes its whole file, and never reproduces. Three sightings, two of which had
their diagnostic destroyed — once by `/dev/null`, once by `tail -4` — and the entry says
outright that losing the evidence is the mistake it exists to prevent.

**Cause:** `secrets.token_urlsafe` draws from the base64url alphabet, which contains `-`.
Measured over 20 000 draws, **306 tokens (1.53%) begin with a dash**. Every caller passed
the token as `--session-token <value>`, and argparse reads a leading-dash value as the
**next option**, exiting 2 with:

    reflection.py receipt: error: argument --session-token: expected one argument

That is byte-for-byte the signature the entry recorded and could not explain. It never
reproduced because **the coin flip is inside the secret** — a re-run draws a new token.

## How it was caught, which is the transferable part

By keeping the whole suite output in a file instead of piping it through `tail`. The
capture (`receipt_diagnostic()`) had existed for days and had fired twice; both times the
harness around the run threw it away. This session repeated that mistake earlier in the
same day, recorded it, adopted the rule, and the very next full run produced a traceback
showing the token landing on argv immediately before `--inbox`.

**The entry's own conclusion was already correct and nobody followed it.** It said the
error "requires the token argument to have been absent or **option-shaped**", having ruled
out `None` and `""` by execution. Option-shaped was the answer; the alphabet was one step
further on.

## The fix, and where it belongs

**At generation, not at the call sites.** The token is printed to the user at session start
and pasted onto command lines by agents, so hardening the five known callers would have left
every future one exposed. `_new_token()` **redraws** until the token does not start with `-`
— redraw rather than strip, because stripping the first character shortens the secret and
replacing it biases that character. Length and entropy are unchanged (verified: all 5 000
sampled tokens are 32 chars).

Callers that pass a token **already on disk** — which the generator cannot reach — now use
`--session-token=<value>`, the form argparse parses whatever the value begins with.

## Testing

`tests/test_session_token_shape.py`:

- no leading dash in 5 000 draws (the old generator produced ~1.5%);
- the secret is not shortened to achieve that;
- **the premise is pinned** — a test asserting `token_urlsafe` really does emit leading
  dashes, so if the alphabet ever changes the guard cannot start passing vacuously while
  claiming to be a fix;
- the CLI trap reproduced deterministically in both forms: space-separated exits 2 with the
  recorded message, `=` does not.

Mutation-proven: reverting `_new_token` to a bare `token_urlsafe` call turns the first test
RED.

**One own-goal during the proof:** `git checkout -- .claude/hooks/reflection.py` was used to
undo the mutation, which also reverted the fix, because the fix was not committed yet.
Caught by re-grepping for the symbol instead of assuming the restore did what was intended,
and re-applied from the ops config.

## Definition of Done

Full gate list, plus the `.ai/BACKLOG.md` entry moved to diagnosed — with the original
record retained in full, since its value is five hypotheses and two lost captures.
