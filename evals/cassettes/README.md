# Eval cassettes

A cassette is one recorded `claude -p --output-format json` response, plus the
fingerprint of everything the model saw when it was recorded.

Empty by design: recordings cost real API money, so they are the owner's to make.
Until then `--replay` fails closed with the exact command to record — never a
vacuous pass.

```bash
python3 scripts/run-evals.py --record                  # LIVE, writes cassettes here
python3 scripts/run-evals.py --record --only <eval-id> # re-record just one
python3 scripts/run-evals.py --replay                  # free, keyless, no network
```

## Why the fingerprint is the whole point

Caching is easy; invalidation is the reason this exists. These evals test the
**prompt corpus**, so the agent's own `.md` file and the skills the registry says
it loads are part of the question being asked. A cassette recorded against an
older `planner.md` answers a question nobody asked any more, and a green CI run
off a superseded recording is worse than no CI run at all.

`prompt_surface()` therefore folds in everything the model sees:

| In the fingerprint | Why |
|---|---|
| agent prompt file digest | it *is* the system prompt — the subject under test |
| digests of the skills the registry maps to that agent | loaded into the same context |
| resolved model | a different model is a different answer |
| `allowed_tools` | changes what the agent can do, so what it will say |
| `prompt`, `fixture` tree digest, `setup_files` | the rest of the input |

Deliberately **excluded**, because the model never sees them and re-recording is
expensive: `max_cost_usd`, `description`, and the eval's own `checks`. Tighten a
check without paying to re-record.

Any mismatch is refused with the field that moved named in the message
(`skills(writing-plans)`, `agent_prompt`, …), so a stale cassette is actionable
rather than a wall.

## Not wired into CI

Deliberate, and the same call `scripts/check-silent-failure.py` made: the
mechanism ships, the gate waits on ownership. With no cassettes recorded,
`--replay` in CI would fail every run. Wire it up in the same change that lands
the first recordings — `.ai/BACKLOG.md` tracks it.

## Proving the checks bind

Recording a passing response proves nothing on its own; checks that never fail
are decorative. Fault injection needs no API key and no cassettes:

```bash
python3 scripts/run-evals.py --inject refusal            # exits 0 iff EVERY eval fails
python3 scripts/run-evals.py --inject truncation
python3 scripts/run-evals.py --inject malformed_tool_call
python3 scripts/run-evals.py --inject timeout
```

`--list` is the one mode that makes no pass/fail claim at all: it enumerates definitions and
exits 0 even when there are none. Every other mode treats an empty set as an error.

The exit code is inverted on purpose. Green means every eval **rejected** a
deliberately broken response. An eval that passes one of these is reported by
name as `PASSED DESPITE FAULT`.

Truncation is the sharpest of the four: the output *starts* correct, so any
check that matches a prefix — or only asserts a pattern is absent — sails
through it.
