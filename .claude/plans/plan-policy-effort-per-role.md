# Plan: policy-effort-per-role

## Phase 0 — Design precheck (ownership / data model)

`.claude/model-policy.json` already owns "how much intelligence a role earns" (tier -> model).
Reasoning **effort** is the same kind of fact — a per-role budget dial — so it belongs in the
same table, resolved by the same projector, gated by the same `--check`. The value of this
change lives in three places: the policy table (the decision), `scripts/gen-model-policy.py`
(the projection + drift gate), and the 22 `.claude/agents/*.md` frontmatters (the effect). The
model covers all three, but only the first two are reachable by ops: the 22 frontmatter lines
are **generated output**, and `ALLOWED_RUN_COMMANDS` excludes `python3`, so the regeneration is
an explicit post-execution command, not an op. Until it runs, `gen-model-policy.py --check` is
RED by design (every agent is missing its `effort:` line). That red window is the correctness
proof that the gate actually binds on effort.

Prior art searched (both mandatory): `review-record.py rejections search "effort model policy
frontmatter"` -> 1 hit, `e2e-lane-a` (CONDITIONAL 87; findings are about mutation-proof
overclaim and an untested executor lock — matched on the bare word "frontmatter", no relation
to model policy; re-read, not a match for this change). `knowledge-ledger.py search "effort"`
-> exit 3, no hits. Silence is NOT evidence; the effort-inheritance behaviour below rests on
the caller's fetched Claude Code docs, not on a repo artifact.

## Overview

Claude Code subagent frontmatter supports `effort: low|medium|high|xhigh|max`; with no key the
subagent **inherits the session's effort**, which makes a cheap role expensive whenever the
owner runs a deep session, and a deep role cheap whenever they do not. Effort scales *all*
output tokens (thinking + text + tool calls), so today every agent's cost profile is an
accident of the parent session. This plan makes effort a policy fact: each capability tier
carries a default, a role may override it, and `gen-model-policy.py` projects and gates it
exactly as it does `model:`.

## Scope

In scope: `.claude/model-policy.json` (tier defaults + 4 role overrides + `_readme`),
`scripts/gen-model-policy.py` (validate / resolve / write / `--check`),
`tests/test_model_policy.py` (4 behavioural tests), `tests/test_behavior_spec.py`
(`KNOWN_KEYS`), `.claude/agents/reviewer.md` (byte trim), `CHANGELOG.md`.

Out of scope: the 22 agent frontmatter edits (generated — see Step 7), any change to model
routing, `tests/test_agent_frontmatter.py` (`KEY_LINE` is `^[a-z][A-Za-z0-9_-]*:(\s|$)` and
already accepts `effort:` — verified at tests/test_agent_frontmatter.py:19; no edit needed).

## Prerequisites

Clean tree for the six touched files; `python3 -m pytest tests/test_model_policy.py
tests/test_behavior_spec.py -q` green before starting.

## Byte arithmetic (prompt-size ceilings)

`tests/test_agent_prompt_size.py` SPLIT: `planner.md` 10000, `reviewer.md` 12400. Measured now
(`wc -c`): planner **9976**, reviewer **12397**. The inserted line is `effort: high\n` = 13 bytes.

- planner: 9976 + 13 = **9989 <= 10000**. **It fits** — the caller's premise that planner
  overflows is incorrect, and a compensating trim there would be diff for its own sake. Left
  untouched, with 11 bytes of headroom recorded here so the next editor knows the margin.
- reviewer: 12397 + 13 = **12410 > 12400**. Overflows by 10 bytes. Step 5 deletes the
  rationale line `Cost is turns x context: every turn re-reads the whole conversation.` plus
  its trailing blank line (70 bytes) under `## Output & Turn Discipline`. That is prose, not a
  rule: the rule it motivates (`**Hard ceiling: ~20 tool calls per review.**`, `**Never
  re-read a file you already read this run.**`) stays verbatim, and the deleted string is in
  neither `MOVED_RULES['reviewer.md']` nor `PINNED_IN_AGENT_FILE['reviewer.md']` (checked
  against tests/test_agent_prompt_size.py:41-63). Post-state: 12397 - 70 + 13 = **12340 <= 12400**.

## Implementation Steps

### Step 1 — Tier defaults + `_readme` (ops 1-4)
- **File:** `.claude/model-policy.json`
- **Action:** add `"effort"` to each capability tier: most-capable `high`, balanced `medium`,
  fast `low`; document the resolution rule in `_readme`.
- **Done when:** the three tiers carry an effort and `_readme` states "role override else tier
  default" and the allowed set.

### Step 2 — Role overrides (ops 5-8)
- **File:** `.claude/model-policy.json`
- **Action:** `debugger: xhigh` (root-cause work is the one job where under-thinking is
  invisible until production), `planner: high`, `code-reviewer: high`, `reviewer: high`
  (balanced *tier*, but it reviews adversarially — model and effort are chosen separately,
  which is exactly why the override axis exists).
- **Done when:** four roles carry `effort`, and every other role resolves from its tier.

### Step 3 — Projector + gate (op 9)
- **File:** `scripts/gen-model-policy.py`
- **Action:** `ALLOWED_EFFORTS = ("low", "medium", "high", "xhigh", "max")` and
  `EFFORT_LINE_RE`; `load_policy` rejects a tier with a missing/invalid effort and a role with
  an invalid override, raising `ValueError` exactly as an unknown tier does (so it inherits the
  existing fail-closed, nothing-written path); `resolve` returns `(model, effort)` per role;
  the planning loop rewrites a stale `effort:` in place and **inserts** one immediately after
  `model:` when absent, reusing the model line's own line ending so a CRLF file stays CRLF;
  `--check` reports `says <model>/<effort>, policy says <model>/<effort>`.
- **Details:** insertion is computed in the same two-phase planned/defects structure — no write
  happens until every agent has been checked, so a late defect still leaves the tree untouched.
  A missing `effort:` is drift (fixable by a run), never a defect; a missing `model:` stays a
  defect, unchanged.
- **Done when:** `python3 scripts/gen-model-policy.py` writes 22 effort lines and a second run
  reports "in sync"; `--check` exits 1 on an effort-only drift.

### Step 4 — Behavioural tests (op 10)
- **File:** `tests/test_model_policy.py`
- **Action:** new class `EffortIsProjectedPerRole`, using the existing `TempTree` /
  `subset_policy` / `run` harness (script copied into a tmp tree, real policy narrowed):
  (a) effort is written directly under `model:` and equals the tier default for a role with no
  override; (b) a role override beats a deliberately-lowered tier default; (c) `--check` is red
  when only the effort drifted, and names the agent; (d) an invalid effort value and (e) an
  invalid role override are each rejected with nothing written — "nothing written" is proved by
  snapshotting the raw bytes of every agent file before the run and asserting byte-identity
  after, never by asserting the fixture started without an `effort:` line (the fixture copies
  the real repo agents, which carry one after Step 7).
- **Mutants (declared, to be applied and measured at implementation time):**
  1. *Drop the override precedence* — make `resolve` read only the tier default ->
     `test_a_role_override_beats_its_tier_default` goes RED (asserts `max` against a `low` tier).
  2. *Skip effort in `--check`* — compare only the model when `check_only` ->
     `test_check_is_red_when_only_the_effort_drifted` goes RED (exit 0 where 1 is required).
  Each mutant must flip its named test; collateral failures in the repo-level gates are
  expected (measured: mutant 1 also reddens `ModelPolicyIsTheSourceOfTruth::
  test_repo_frontmatter_matches_the_policy_table` and `ChangingAModelIsAOneLineEdit::
  test_check_detects_frontmatter_edited_behind_the_policys_back` — desirable, since a broken
  resolver should redden the repo gates; mutant 2 flipped only its named test). If a mutant
  passes, the test names the wrong mechanism and must be rewritten, not re-anchored.

### Step 5 — Frontmatter contract (op 11)
- **File:** `tests/test_behavior_spec.py` — add `"effort"` to `KNOWN_KEYS` (line 198). Without
  this, `test_frontmatter_is_structurally_valid_yaml` and the key-set assertion at 235 fail on
  all 22 agents the moment the generator runs.

### Step 6 — Reviewer trim (op 12) — see byte arithmetic above.

### Step 7 — CHANGELOG (op 13), then regenerate
- **Post-execution command (NOT an op — `python3` is not in `ALLOWED_RUN_COMMANDS`):**
  ```
  python3 scripts/gen-model-policy.py          # writes 22 `effort:` lines
  python3 scripts/gen-model-policy.py --check  # must print "in sync"
  python3 -m pytest tests/test_model_policy.py tests/test_behavior_spec.py \
      tests/test_agent_frontmatter.py tests/test_agent_prompt_size.py -q
  python3 -m pytest tests/ -q && ruff check scripts/ tests/ && mypy
  ```
- Run them in that order: the suite is expected to be RED between op 13 and the regeneration.

## Testing Strategy

Behavioural throughout: every new test executes `gen-model-policy.py` as a subprocess against a
temp tree and asserts on files and exit codes, never on internals. The two mutants above are
the proof that the new tests can fail. `test_agent_prompt_size.py` is the independent check on
Step 6, and `test_agent_frontmatter.py` on the generated lines.

## Rollback Plan

`git checkout -- .claude/model-policy.json scripts/gen-model-policy.py tests/ CHANGELOG.md
.claude/agents/` restores everything, including the generated frontmatter, since the 22 effort
lines exist only as generator output. No state outside the working tree is touched.

## Risk Assessment

- **The red window is real.** Between op 13 and the regeneration, `gen-model-policy.py --check`
  and the contract tests fail. Do not commit inside that window.
- **Insertion into CRLF files.** `LineEndingsSurviveARewrite` pins byte-identical CRLF
  behaviour; the insert path copies the model line's ending for that reason. If that class goes
  red, the ending detection is wrong — fix it, do not relax the test.
- **ACCEPTED LIMITATION — adjacency is enforced on insertion only.** The "`effort:` rides
  directly under `model:`" invariant binds when the generator *inserts* the key. A hand-placed
  `effort:` elsewhere in the frontmatter is value-normalised in place and `--check` then reports
  "in sync" (measured by review: a first-key `effort: max` became `effort: medium` at that same
  wrong position, rc 0, exactly one `^effort:` line). No corruption, no duplication; cosmetic.
  Repositioning is deliberately NOT in scope here — it would change generator logic that has
  already been executed, mutated and measured, for a case no generated tree produces. If a
  stray-position key is ever observed in practice, fix it then, with its own mutation proof.
- **22 files change outside ops review.** The blast radius is real but mechanical and gated:
  `--check` + `test_agent_frontmatter.py` + `test_agent_prompt_size.py` all bind on the result.
- **Effort semantics are docs-derived.** The inherit-from-session behaviour and the value set
  come from Claude Code docs fetched by the caller today, not from anything in this repo.
  `UNVERIFIED:` the runtime effect of `effort:` is not observable from inside this repo's test
  suite; these tests prove the *projection*, not that Claude Code honours the key.
- **UNVERIFIED:** `.claude/project-graph.json` hub/impact analysis was not run (tool-call
  budget); `scripts/gen-model-policy.py` has no known importers — it is a CLI entry point.
- **Budget note:** discovery used 8 tool calls; no unread file was guessed at — every anchor
  below was copied from grep/sed output.
