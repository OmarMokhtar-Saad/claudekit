# Implementation Plan: task 008 batch 3, cluster 4 — `documenter` + `doc-updater` → one `docs` agent

**Status:** EXECUTED 2026-08-24. 9 ops configs. 25 → 24 agents.

## Scope

One `docs` agent with a mandatory `mode: create|update`, 613 lines, absorbing both
(378 + 224). The two were split by **tense, not capability**: same code reading, same
extraction rules, same quality bar, differing only in whether the target already existed.
Two agents meant two spawns, two contexts, two sets of drift — and `HANDOFF_PROTOCOL.md`
carried two near-identical Docs pipelines to route between them.

**The mode split is preserved, not erased.** `/docs` is create, `/doc-updater` is update,
and the coordinator table — which batch 4 had just split into `Docs (new)` / `Docs
(update)` — keeps both intents while collapsing the destination. Batch 4 shaped the table
for this cluster without either knowing about the other.

| # | Config | Effect |
| --- | --- | --- |
| 01 | `create` | `.claude/agents/docs.md` |
| 02 | `commands` | `/docs` → create, `/doc-updater` → update, plus a dangling `@`-path fix |
| 03 | `routing` | `agents/coordinator.md` (3 sites), `commands/coordinator.md` (2), `HANDOFF_PROTOCOL.md` |
| 04 | `consumers` | `QUICK_START`, `docs/AGENTS.md`, `model-policy.json` |
| 05 | `tests-existing` | 5 test files named the removed agents, including one of batch 4's own |
| 06 | `delete` | both agent files |
| 07 | `alias` | both names → `docs`, `kind: agent` |
| 08 | `doctor-command-names` | the alias scan could not tell a command from an agent |
| 09 | `tests` | `tests/test_008_b3c4_docs_merge.py` |

## What simulation caught that validation could not

**`ck doctor --strict` went red on two files that are both correct.** The alias scan
flagged `commands/doc-updater.md` and `commands/docs.md` for naming `doc-updater` — but
`/doc-updater` **the command survives**; only the agent it routes to moved. The scan had
no way to tell an agent reference from a slash-command of the same name. Two exemptions
were added, each exactly one shape wide: the command file whose own name is the alias key,
and `/<name>` occurrences, which are command references by construction. A bare or
backticked reference anywhere else is still flagged, and three tests hold that line —
including one asserting a same-named file *outside* `commands/` gets no pass.

**And one real defect underneath it:** `commands/docs.md:13` pointed at
`@.claude/agents/documenter.md`, a file this cluster deletes. That is a genuine dangling
path the doctor surfaced while producing the two false positives.

## Must be proven, not asserted

| # | Claim | Proof |
| --- | --- | --- |
| 1 | No operative rule lost | Token diff: 82 derived fragments + 8 headings, zero missing. Three justified absences — the two agents' display names. |
| 2 | The rule the sign-off named survived | `**Generate from code, don't manually write.**` verbatim, and asserted to sit **above** `# Mode: create` — it constrains both modes, so burying it inside one would have half-lost it. |
| 3 | Mode is never guessed | Choosing `create` for a file that exists overwrites human edits; `update` for one that does not diffs against nothing. Asserted present. |
| 4 | Both entry points still work | `/doc-updater` keeps its name **and its flags** (`--docstrings`, `--readme` asserted) — deleting the command would have been a user-visible removal the sign-off never authorised. |
| 5 | The two intents stay distinguishable | `Docs (new)` and `Docs (update)` both present; `DocUpdater` absent. |
| 6 | The doctor exemption stays narrow | Three fixtures: `/gone` exempt, same-named command file exempt, bare `gone` and a same-named file outside `commands/` both still flagged. |

## The risk this plan does NOT retire

**Routing is not demonstrated unchanged.** No cassettes. Two agents became one with a
mode parameter, which is the most behaviour-shaped merge in batch 3 so far: a caller that
omits the mode now depends on the agent inferring it from whether the file exists.
