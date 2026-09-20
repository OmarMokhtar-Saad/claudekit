# Plan: bash-payload-gate — a ceiling on Bash command TEXT

**Tier 2** (several files, no security or schema surface). Parent-authored plan +
ops.json per the token policy; no planner, no reviewer chain.

## The gap

Every cap this kit ships measures tool **output**. `output_filter.py` bounds Bash
stdout, `read-window-guard.py` bounds a Read, `context-budget-gate.py` bounds the
window. Nothing bounds what the model **writes**.

Measured 2026-09-20 on a real session (251 Bash calls, 27.52M tokens billed):
`tool_use` parameters — the command text the agent itself authors — were **40.3% of
the transcript body, 65,883 tokens**, very nearly equal to all tool *results*
combined (73,542). 197,336 chars of command text, ~49,334 tokens.

That cost is not paid once. A token authored at request *k* is re-billed by every
request until the next compaction reset. The 48,464 tokens of oversized inline
payloads in that session carried **1.68M re-billed tokens — 6% of the bill** — for
text that existed only because a script was pasted into the command line instead of
written to a file and run by path.

## The threshold is measured, not guessed

Command length over those 251 calls is bimodal: p50 204, p75 475, p90 2,777, p95
3,954, max 11,507. Ordinary commands are two to five hundred characters; pasted
scripts are thousands. `THRESHOLD = 1500` sits in the empty region between p75 and
p90, so it separates the two populations rather than taxing normal work:

    1,500 -> refuses 39/251 calls (15.5%), trims 89,700 chars (~22,425 tokens)

3,000 halves the yield; 800 starts catching genuine one-liners. 1,500 is the knee.

## Not a sandbox (hard rule 6)

This is a budget, not a security control. It bounds the SIZE of a command, never its
meaning; `iron-law-gate.py` remains the thing that decides whether a Bash call may
write at all. A caller who wants the bytes through can split them across two calls.
The point is to make the cheap path the default one.

## Fail direction (hard rule 2)

A block is `exit 2` + reason on stderr. Everything else fails **open**: an
unparseable payload, a missing field, a foreign tool, or a bug in the hook must never
deny the main agent its Bash tool. The blast radius of a false positive is the whole
session; the cost of a false negative is a few thousand tokens.

Two documented hatches: commands whose length is inherent (`git commit|apply|am|tag`,
`gh pr|issue|release create|edit|comment`, `patch`) are exempt because the message IS
the payload; and `CK_RAW_INPUT=1` overrides for one process tree.

## Artifacts

| Path | Change |
|---|---|
| `.claude/hooks/bash-payload-gate.py` | **new** — the blocking PreToolUse hook (fail-open guard, anchored exemption, single stderr line, nothing on stdout) |
| `tests/test_bash_payload_gate.py` | **new** — 24 cases: ceiling boundary, `exit 2` shape, actionable refusal text, empty stdout on a block, 4 exempt payload-carriers, the anchored exemption not borrowable by a prefix trick, the override hatch, 6 malformed payloads failing open, 5 foreign tools invisible, and the registry row's tier/runner/matcher |
| `.claude/hooks/dispatch-registry.json` | register `bash-payload-gate` as a **blocking** PreToolUse handler matching `Bash`, directly after the `iron-law-gate` row it sits beside. No `command_matcher` — the registry invariant reserves that for `advisory` rows |
| `README.md` | shipped/reachable hook counts 31 -> 32 and 28 -> 29 (derived; `TestHookWiringIsHonest` pins them) |
| `docs/HOOKS.md` | the same two derived counts in the opening sentence |
| `CHANGELOG.md` | `[Unreleased]` entry — a user-visible new blocking hook with two documented hatches |

## Verification

`pytest tests/test_bash_payload_gate.py`, then the full DoD set: `pytest tests/ -q`,
`ruff check`, `mypy`, `gen-docs.py --check`, `gen-registry.py --check`,
`check-context-floor.py --check`, `check-plan-artifacts.py --check`,
`gen-plan-index.py --check`, `shellcheck`, `ck doctor --strict`.
