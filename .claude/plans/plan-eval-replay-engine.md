# Plan: the eval engine — record once, replay many, and prove the checks bind

Slug: `eval-replay-engine`. Wave-2 **Phase 2.1** (handoff `handoff-2-policy-and-eval.md`).
Blast radius: **Tier 3** — new module surface in the eval harness plus the definition schema.

## Problem

`scripts/run-evals.py` spawns real agents at $0.2–1.5 per eval. An eval suite whose fixtures
require live paid API calls cannot run in CI, so **it runs never** — which is exactly why task 010
is still open. Three concrete defects today:

1. **No replay path.** Every run costs money and needs a key. `tests/test_evals.py` covers only
   definition loading and workspace building; nothing exercises an agent response.
2. **Nothing proves the checks bind.** A suite of `regex_absent` checks would pass against an
   empty string. Recording a *passing* response would not fix this — checks that never fail are
   decorative regardless of what they are pointed at.
3. **Definitions are an unaudited vendor-name surface.** They carry `"model": "opus"`, which the
   Phase 1 `callsite_overrides` audit does not scan. Worse, measured: `implementer-no-fabrication`
   ran on **sonnet** while `implementer` ships on haiku, and `reviewer-refutes-and-formats` ran on
   **opus** while `reviewer` ships on sonnet. **Two of four evals were not testing the shipped
   agent at all.**

## Approach

**Caching is easy; invalidation is the design.** These evals test the *prompt corpus*, so the
agent's own `.md` and the skills the registry maps to it are part of the question being asked.
`prompt_surface()` folds every input the model sees into one fingerprint — agent prompt digest,
per-skill digests, **a digest of `.claude/operations/scripts/`**, resolved model, `allowed_tools`,
prompt, fixture tree digest, `setup_files` —
and replay refuses on any mismatch, naming the field that moved (`skills(writing-plans)`,
`agent_prompt`, …).

Equally deliberate is what is **excluded**: `max_cost_usd`, `description`, and the eval's own
`checks`. Re-recording costs money, so a hair-trigger fingerprint would make tightening a check
expensive. The model never sees those, so they may change freely.

**Fault injection is mutation testing for the eval suite**, and needs no key and no cassettes.
Four shapes a real model actually produces — `timeout`, `truncation`, `malformed_tool_call`,
`refusal` — with `--inject`'s **exit code inverted**: green means every eval *rejected* the broken
response. Any eval that passes one is reported by name as `PASSED DESPITE FAULT`. Truncation is the
sharpest: the output *starts* correct, so prefix-matching checks sail through it.

Definitions now name a `tier` resolved through `.claude/model-policy.json`, and `load_definitions`
**rejects** a `model` key outright — closing the surface Phase 1 missed and fixing the two evals
that tested the wrong agent.

## Operations (7)

| # | Type | Path | Why |
|---|------|------|-----|
| 1 | code_edit | `scripts/run-evals.py` | cassettes, fingerprint, faults, tier resolution, mode dispatch |
| 2 | file_create | `tests/test_eval_replay.py` | 24 keyless behavioural tests |
| 3 | file_create | `evals/cassettes/README.md` | format, fingerprint contract, why CI wiring waits |
| 4–7 | code_edit | `evals/definitions/*.json` | `model` → `tier` (4 files) |

## Evidence already gathered

Payloads were executed against a staged tree, then reverted — not reasoned about:

- **26 tests pass in ~4s**, and the existing `tests/test_evals.py` (5 tests) still passes.
- **Mutation 1** — delete the staleness check: **6 tests fail**.
- **Mutation 2** — drop `agent_prompt` from the surface: **exactly 1 test fails**, the agent-prompt
  one. Surgical, so each dimension is independently pinned.
- **Mutation 3** — make `apply_checks` return `[]`: the **fault-injection tests** fail, confirming
  they are the harness that would catch decorative checks.
- **Mutation 4** (added after round 1) — replace the operations-scripts digest with a constant:
  **exactly 1 test fails**, the new one.
- **Mutation 5** (added after round 1) — delete the empty-definitions guard: the harness prints
  `0/0 passed` and exits **0**, and the new test fails. Verified by running the command directly,
  because a first `-k` filter selected the wrong test and appeared to show the guard was
  unnecessary.

## Tests

`tests/test_eval_replay.py`, all keyless: round-trip through the real replay path; six staleness
dimensions each naming what moved; the negative case (a cost/description/checks edit must **not**
invalidate); missing and corrupt cassettes as errors rather than passes; all four faults rejected;
`--inject`'s inverted exit code; `--replay` against an empty store failing rather than passing
vacuously; and a definition carrying `model` being refused.

## Out of scope, deliberately

**Phase 2.2** (the `disable-model-invocation` corpus audit) is a separate plan,
`plan-skill-loading-contract`, and is not attempted here. The two halves share a principle —
"a sentence in the entrypoint is not a load" — but touch disjoint files and fail independently.

## Deliberate non-delivery: no cassettes are recorded, and CI is not wired

Recording costs real API money and is the owner's call, so `evals/cassettes/` ships **empty**.
Wiring `--replay` into CI now would fail every run. This is the same call
`scripts/check-silent-failure.py` made in this repo — ship the mechanism, gate on ownership — and
`--inject` gives CI-safe value today with no recordings at all. Tracked in `.ai/BACKLOG.md`.

## Risks

- **The operations scripts are model input, not inert files** — review round 1 rejected this plan
  for missing that. `planner-delivers-artifacts` grants
  `Bash(python3 .claude/operations/scripts/validate-config-json.py *)` and tells the agent to
  self-validate; `implementer-no-fabrication` grants the whole directory and tells the agent to
  dry-run. Those scripts therefore **run during generation** and their stdout is read by the model
  before it answers, so changing one changes the response a fresh run would produce. Excluding the
  tree left a live false-PASS path of exactly the kind this design exists to prevent. Now
  fingerprinted, and pinned by
  `test_editing_an_operations_script_the_agent_can_run_invalidates_it`.
- **`0/0 passed` is not a pass.** With an empty definition set the result loop never ran, the
  failure count stayed zero, and the harness exited 0 — a green run that verified nothing. This was
  inherited from the pre-existing `main()`, not introduced here, but it is fixed rather than
  carried: zero matching definitions now exits 2.

- **A fingerprint that is too broad makes re-recording constant.** Mitigated by the explicit
  exclusion set, pinned by `test_changing_something_the_model_never_sees_does_NOT_invalidate_it`.
- **Skill digests come from the registry mapping**, so a skill loaded at runtime but not mapped is
  outside the fingerprint. `gen-registry.py --check` keeps the mapping honest; noted as the known
  edge.
- **The tier conversion changes which models two evals run on.** That is the fix, not a regression
  — they now exercise the shipped agents — but it means recorded costs will differ from the
  historical `max_cost_usd` figures. Budgets left untouched; revisit at first recording.

## Rollback

`git revert`, or `/rollback` against the engine backup. Ops 1 and 4–7 are whole-file replacements
(`find` = current content) that fail closed on drift; ops 2–3 are new files with no importers, so
deletion is clean. Reverting restores the live-only harness; **no product or runtime behaviour is
affected** — this surface is developer tooling that pytest exercises and CI does not yet run.
