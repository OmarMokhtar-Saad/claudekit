# Implementation Plan: Generators That Cannot Drift (Phase 3, Agent B)

**Status:** QUEUED — awaiting owner approval. Nothing has been executed.
**Ops config:** `.claude/plans/ops-generators-that-cannot-drift.json` (16 operations: 6 `file_create` + 10 `code_edit`; validator: `-> APPROVED` rc=0 `[re-measured after the round-4 corrections]`)
**Addendum (owner-gated, NOT part of the core):** `.claude/plans/ops-mcp-probe.json` (2 operations, both `file_create`; validator: `-> APPROVED` rc=0 `[re-measured after the round-4 corrections]`)
**Tier:** 3 (two new public CLI verbs + a CI gate change)
**Post-approval corrections (round 4, mechanical):** the round-4 adversarial reviewer APPROVED at 90.1/100 conditional on three mechanical fixes, now applied: (D1) every whole-suite figure re-measured in a **real `git worktree`** and the `git archive` export method banned; (L1) the `OVER BUDGET` user-visible string no longer claims every next `ck mcp add` is refused; (D2) the "gate asserted, not re-executed" class logged as a proposed mechanical check in `.ai/BACKLOG.md` (not implemented here, not in the ops), and the two previously-unrun gates now carry the reviewer's real results. Plus two bookkeeping counts corrected (8 `file_create`, 14 step rows covering 16 ops).

**Revision 4** — round 1 REJECTED at 76.4/100 (C1-C4); round 2 REJECTED at 87.6/100
(H1, H2 + M1/M2/L1/L2); round 3 REJECTED at 89.9/100 — 0.1 short, "a REJECT on the gate,
not on the design" — for **[H1-new]** (mypy red, and the round-3 evidence table asserted
it green) plus two mediums. See "Revision 4" below. Rounds 1-3 findings are CLOSED and
verified by execution; they are **not** re-litigated here. The owner authorised this
fourth round past the 3-round ceiling.

**Every figure in this document carries an evidence label** — `[re-measured r4]`,
`[prior round, not re-run]`, or `[not yet executed]` — because the defect that cost
round 3 was a gate asserted from an earlier round's run instead of re-executed against
the delta.
**Lane:** Agent B. Touches no file in Agent A's lane (`.claude/hooks/**`, `src/claudekit/security/**`, the `"hooks"` key of any `profile.json`). `src/claudekit/security/command_validator.py` is read, never edited. **Newly assigned to Agent B for this phase and owned explicitly here:** `scripts/check-context-floor.py`, `tests/test_context_floor.py`, `.github/workflows/ci.yml` — COORDINATION.md's table did not cover them; Agent A is barred from them.

---

## Revision 2 — what the review changed

Every item below was executed in a scratch tree (`git archive HEAD` + the ops applied),
not argued. Output is in "Executed evidence".

| Finding | Change |
| --- | --- |
| **C1** the extraction breaks four tests | The script no longer imports `claudekit` at all. `_load_context_floor()` loads `context_floor.py` from exactly two places **inside this tree** — `src/claudekit/` then beside the script — and `sys.exit`s with a named cause if neither exists. It can no longer silently borrow the installed package. `tests/test_context_floor.py` gains `plant_gate(root)`, which copies the module beside the copied script in all three temp trees; `tests/test_skill_new.py`'s fixture does the same. Proven both ways: 40/40 pass on a bare interpreter with no `claudekit` installed **and** with the editable install. The rejected design fails 7 tests on a bare interpreter. |
| **C2** `--probe` mitigation does not mitigate | `--probe` is **cut from the core**. `--tools N` is required; the core has no execution surface whatsoever. The probe is prepared separately in `.claude/plans/ops-mcp-probe.json` with honest framing (it executes third-party code; the denylist allowlists `npx`/`node`/`docker` and gives no isolation), a typed-out acknowledgement flag, a scrubbed environment (PATH/HOME/LANG only), and `Popen` + `killpg(TERM→KILL)`. Both configs validate independently. **The fork is the owner's; neither branch is chosen here.** |
| **C3** the MCP budget failed open | `check_budget()` counts `set(.mcp.json mcpServers) | set(ledger servers)`. A configured server with no ledger row makes the projected tool total **unknown**, so `max_tools` is refused with that cause named rather than counted as zero. Two regression tests. |
| **C4** `ruff` would fail | Moot: there are no `from claudekit...` imports left in the script, so no I001 and no E402. `ruff check src/ tests/ scripts/` → "All checks passed!" on the patched tree; `mypy` → "Success: no issues found in 23 source files". |
| `.ai/` files missing from the ops | `.ai/CHANGELOG_AI.md` is now op 16 (append before the newest entry — reverse-chronological). `.ai/SESSION_STATE.md` is **deliberately not an op**: its header block is a rewrite, not an append, and COORDINATION.md forbids reflowing a contended file while Agent A holds it. It is a **named post-execution manual step**, listed in the DoD below. |
| `mcp.budget()` could leak `ProfileError` | `resolved.value(...)` moved inside the `try`. |
| ledger written before `.mcp.json` | Disclosed in a comment and in Risk, not claimed away: the failure leaves a ledger row with no config entry, which **over**-counts (refuses one server early). The reverse order would fail open. |
| `ci.yml:170` duplication | Confirmed: the inline `validate-registry` step only checks `agentMapping` → known skill ids, a strict subset. The op now **replaces** it in place (`if: false`, with the reason on the step name) and runs `gen-registry.py --check` there instead of adding a second step to `docs-drift`. **Superseded by revision 3 (L2): the old step is now deleted outright, not disabled.** |

---

## Revision 3 — what the round-2 review changed

Round 2 scored 87.6/100 and named two Highs. Both were design defects, not typos, and both
were fixed and then **executed** in a scratch tree (`git archive HEAD` + both configs
applied); the output is in "Executed evidence (revision 3)".

| Finding | Change |
| --- | --- |
| **H1** `ck skill new` left `gen-docs.py --check` red | Accepted as **unavoidable by design, and therefore pinned rather than hidden.** Component counts are generator-owned (hard rule 8), so creating a skill *must* invalidate them; the only honest remedy is re-running `gen-docs.py`, never a hand-edit, and no design of this verb can avoid that without breaking rule 8. What was wrong was leaving it silent. Three things change: (a) `test_generated_skill_passes_the_repos_own_gates` now runs **all three** gates that apply to a project-shaped tree — `gen-registry.py --check`, `check-context-floor.py --check` **and** `gen-docs.py --check` — after re-running the generator; (b) a new test, `test_a_new_skill_leaves_the_count_gate_red_until_gen_docs_reruns`, watches the gate go **red** immediately after creation and green only after regeneration, so the drift can never pass unnoticed; (c) the CLI's closing hint names `python3 scripts/gen-docs.py` and says it owns the counts — guarded on the script existing, because an installed user project has no `scripts/` tree and a hint to a missing file is a dead end (`test_the_hint_is_omitted_where_the_script_does_not_exist`). The DoD below carries the follow-up `gen-docs.py` run explicitly. |
| **H2** the C3 fix created an inescapable state | Fixed by option **(a)**, the smallest honest fix: `ck mcp add <name> --tools N` **adopts** a server that is already in `.mcp.json` but has no ledger row — it writes the ledger row and touches no configuration. The refusal message already instructed exactly this, so the remedy now works instead of dying on the duplicate-name guard. No new verb, so the public surface and the asset count do not grow (task 008). Failing closed on the unknown count **stays**. Adoption cannot be refused by the budget, because it adds no server and no tool schema — it records a cost already being paid, and refusing it is precisely what made the state inescapable; an over-budget result is reported as a **warning** carrying the numbers, and the next genuine addition is refused normally. `test_a_config_only_server_can_be_adopted_and_unblocks_the_budget` drives the whole escape path end to end: refusal → the printed remedy → success → the previously blocked addition now succeeds. |
| **M1** `ck mcp list` disagreed with the enforcer | Fixed. `list_servers()` returns the **union** of the ledger and `.mcp.json`; config-only rows show `unknown` tools and source `config-only`, and the CLI prints a line naming them and the adoption remedy. That disagreement is what made H2 baffling in the field. The stale claim in Risk ("is visible in `ck mcp list`") is corrected below. |
| **M2** the floor gate blocked on unrelated categories | Fixed. `refuse_new_skill` becomes `check_new_skill`, returning `(refusal, other_overages)`: only an overage in `SKILL_CATEGORY` refuses — that is the only category a new skill charges — and every other over-budget category comes back as a **warning** printed by the CLI. A project with an oversized CLAUDE.md can create a skill again. The remedy string now comes from `floor_remedy(root)`: `python3 scripts/check-context-floor.py` where that script exists, `ck doctor` in an installed project. |
| **L1** `mcp_probe` docstring understated the environment | Fixed in `ops-mcp-probe.json`: the prose now names `SAFE_ENV_KEYS` and lists all six keys plus `NO_COLOR=1`, matching the tuple (hard rule 6 is about the framing being honest, including in a docstring). |
| **L2** ci.yml kept the superseded step under `if: false` | Fixed: the 23-line inline `python3 -c` step is **deleted** and replaced by the single `gen-registry.py --check` step. Subsumption was already proven (the old step only checked `agentMapping` → known skill ids); dead code kept "just in case" is how a disabled gate later looks like a live one. `grep -c "if: false" .github/workflows/ci.yml` → 0 on the patched tree. |
| **M3** the eight gates are **not** green at HEAD | Recorded, **not fixed** — it is not this lane's file. Disclosed in Risk and in the exit criterion below. |

---

## Revision 4 — what the round-3 review changed

Round 3 executed everything and scored 89.9/100. One blocker, two mediums.

| Finding | Change |
| --- | --- |
| **[H1-new]** BLOCKING — `mypy` red at `src/claudekit/mcp.py:253` as emitted by op 5 | Fixed. Revision 3's own H2 adoption code built `config_argv` from `.get()` calls on a hand-written `.mcp.json`, so mypy inferred `Union[list[Optional[Any]], list[str]]` and rejected the assignment into `list[str]` at `argv = config_argv or argv`. `config_argv` is now **annotated and coerced** (final code below). `List` is added to `mcp.py`'s `typing` import (py3.9 target, so `typing.List`, consistent with the rest of the file). Consequence closed twice over: `mypy` is one of the eight DoD gates, **and** `tests/test_gate_scope.py::TestMypyScope::test_gate_is_green_and_actually_reaches_the_ops_scripts` failed on it — a new test failure introduced by this lane, which falsified revision 3's "adds no new failures". |
| **[H1-new] root cause** — a gate asserted, not re-executed | The round-3 evidence table listed ruff, `compile()` and anchor counts but **not mypy**: the delta was never re-typechecked after the H2 fix. That is the exact defect class this repo ratchets against. Two structural remedies, not just a code fix: (a) the **per-revision evidence checklist** below names all eight gates explicitly, so an omission is visible as a blank row rather than as an absence; (b) every figure in this plan is now labelled re-measured / prior-round / not-yet-executed. |
| **[M-new]** `--used-by` manufactured the drift this phase abolishes | **Flag DELETED** (option b). Rationale below. `usedBy` is *derived* by `gen-registry.py` from each agent's `## Skill Loading` section, so an operator-asserted value could only ever disagree with the derivation: `ck skill new probe-skill --used-by planner` produced `DRIFT usedBy probe-skill: registry=['planner'] derived=[]`, the gate went red, and the remedy the CLI printed (`gen-registry.py`) resolved it by **silently discarding the stated intent**. A generator that can put a gate red, whose documented remedy throws the user's input away without a word, is worse than no flag. Deleting it is also the smaller public surface (task 008: consolidate) and it was never documented, never used, and had **zero** test coverage. `new_skill()` loses the `used_by` parameter and writes `"usedBy": []` with the derivation named in a comment; `Sequence` drops out of `skills.py`'s imports (it had no other use — ruff F401 would have caught it). Two new tests, one of them a refusal test. |
| **[M-new]** the MCP budget binds on **deltas only** — complete the disclosure | Fixed by disclosure, not by new enforcement (adding an MCP check to `ck doctor` is explicitly out of scope this revision). `cmd_mcp`'s `list` branch now prints an `OVER BUDGET` warning when `len(servers) > max_servers` or `total_tools > max_tools`, naming the standing overage and that only the **next** `ck mcp add` is refused. `list_servers()`'s docstring says the same. The Risk row (below) is completed to name the consequence: a project can sit permanently at 4/3 servers and 80/40 tools with nothing red anywhere. Exit code stays 0 — `list` is an inspection command, and `.mcp.json` is written by Claude Code, not by us. Hard rule 6 reaches Risk rows and docstrings. |
| **Not a defect, corrected claim** | `tests/test_memory.py`'s self-scan failure (M3) is pre-existing and owned by the memory lane; the owner has now **separately approved fixing it outside this plan**, so the exit criterion is **achievable once that fix lands** — the earlier "not achievable by this lane" framing is corrected below. Round 3's `test_queued_ops_configs_validate_against_head` failure was the reviewer's own unarchived scratch configs, not a plan defect; the archive + README row requirement already in this plan is unchanged. |

### The mypy fix, as emitted by op 5

```python
from typing import Any, Dict, List, Optional, Sequence, Tuple
...
        # Typed explicitly and coerced with str(): `.get()` on a hand-written
        # `.mcp.json` is Any, and mypy (py3.9 target) rejected the untyped form as
        # `Union[list[Optional[Any]], list[str]]` assigned into `list[str]` below.
        config_argv: List[str] = ([str(existing.get("command"))]
                                  + [str(a) for a in (existing.get("args") or [])]
                                  if isinstance(existing, dict) and existing.get("command")
                                  else [])
```

### Why `--used-by` is deleted rather than constrained

Option (a) — refuse `--used-by AGENT` unless that agent file already lists the skill —
was rejected. It keeps a flag whose only legal argument is a value the generator would
derive anyway, on a *brand-new* skill that by definition no agent loads yet: the flag
could then only ever be passed as a no-op or be refused. That is a public flag, a
validation path, a docs paragraph and a test suite defending zero reachable behaviour.
Deleting an unused, undocumented, untested flag is cheaper than defending it, and it
shrinks the surface instead of growing it. The derivation stays the single writer:
add the skill to the agent's `## Skill Loading` section and re-run `gen-registry.py`.

### Per-revision evidence checklist (all eight gates, no omissions)

Every future revision of this plan fills this table in full, from a run **against the
delta**, or writes `not run` in the cell. A blank is a defect.

| Gate | r4 status |
| --- | --- |
| `python3 -m pytest tests/ -q` | `[re-measured r4 by the round-4 adversarial reviewer, real `git worktree` @ 5f3e322 + uncommitted tracked diff]` baseline `1 failed, 1766 passed, 1 xfailed` -> patched `2 failed, 1809 passed, 1 xfailed`; **+43 passing, zero new failures** (the one added failure is the unarchived queued configs, remedied by the archive step) |
| `ruff check src/ tests/ scripts/` | `[re-measured r4]` `All checks passed!` |
| `mypy` | `[re-measured r4]` — the omission that caused H1-new; see the table |
| `python3 scripts/gen-docs.py --check` | `[re-measured r4]` exit 0 |
| `python3 scripts/gen-registry.py --check` | `[re-measured r4]` exit 0 |
| `python3 scripts/gen-model-policy.py --check` | `[re-measured by the round-4 adversarial reviewer, real tree]` `Model policy in sync: 29 agent roles.` rc=0 |
| `python3 scripts/check-context-floor.py` | `[re-measured r4]` exit 0, numbers unchanged |
| `shellcheck install.sh .claude/hooks/*.sh` | `[re-measured by the round-4 adversarial reviewer, real tree]` rc=0, no output |

## Overview

Layered profiles gave us somewhere to *declare* budgets. Nothing enforces them at the
moment an asset is created. This phase makes three creation paths refuse to produce
drift: `ck skill new` (creation and registration become one act), `ck mcp add`
(a server is registered against the profile's `mcp` budget or refused with numbers),
and `scripts/gen-registry.py --check` (which now sees the filesystem, so a
hand-created asset fails the gate instead of passing in silence).

## Verified ground truth (re-derived 2026-08-21, not taken from the brief)

| Claim | Command | Result |
| --- | --- | --- |
| `ck` verb list | `python3 -m claudekit.cli.main --help` | `init doctor validate execute rollback agents diff update uninstall eval check-command check-path config profile` — no `skill`, no `mcp` |
| Layered profiles landed in `f5eb927` | `git log --oneline -3` | `f5eb927 feat(profiles): layered, inspectable hook profiles and \`ck profile\`` |
| `mcp` budget keys exist and are already declared | `cat .claude/profiles/python/profile.json` | `"mcp": {"max_servers": 3, "max_tools": 40}`. `minimal`/`standard`/`strict` declare `"mcp": {}`; the base layer supplies `None` = unlimited (`profiles.base_layer`) |
| `gen-registry.py --check` misses a hand-created asset | copied the corpus + script to a temp tree, added `skills/hand-made-drift/SKILL.md` **and** `agents/hand-made-agent.md`, ran `--check` | `OK: agentMapping + usedBy match agent files (18 agents).` **exit 0** — both mutants invisible |
| Why it is blind | read `scripts/gen-registry.py` | it enumerates `.claude/agents/*.md` only; it never globs `.claude/skills/*/SKILL.md`, and an agent with no `## Skill Loading` section hits `continue` |
| The gate is not even in CI | `grep -rn gen-registry .github/workflows/*.yml` | **no matches** — CLAUDE.md lists it as a gate that CI does not run |
| "Breaching the floor" concretely | `python3 scripts/check-context-floor.py` | `skill descriptions 7719 / 9000` → **1281 chars of headroom**; over budget ⇒ `--check` exits 1 with `FAIL: context floor over budget: <category>` |
| Registry ↔ filesystem currently agree | script over `.claude/skills` vs registry | 76 skills both sides, 0 fs-only, 0 registry-only — in sync **by luck, not by gate** |
| 11 agents declare no skills | derived from the agent files | `code-simplifier, doc-updater, harness-optimizer, model-router, performance-optimizer, python-reviewer, refactor-cleaner, silent-failure-hunter, tdd-guide, typescript-reviewer, web-researcher` (18 mapped + 11 unmapped = 29 agent files with frontmatter) |
| `python3` is **not** run_command-allowlisted | `sed -n 38,50p .claude/operations/scripts/shared.py` | `pip-compile black isort ruff prettier gofmt goimports rustfmt` — so the registry edit is a hand-written `code_edit`, not a regeneration step |

Two constraints discovered by reading, which shaped the design:

1. `tests/test_context_floor.py` copies `scripts/check-context-floor.py` into a temp tree and
   runs it there; `tests/test_skill_loading_contract.py` loads it by path and calls
   `module.measure()`, `module.frontmatter`, `module.model_invisible`, `module.description_span`.
   The extraction therefore keeps `measure()` zero-arg and re-exports those three names.
2. `argparse` cannot express `mcp add NAME --tools 5 -- npx …`: a trailing `nargs="*"`
   positional reports `unrecognized arguments: -- npx …`, and `argparse.REMAINDER` swallows the
   flags into the argv (both verified before writing the ops). Hence `_split_server_command`,
   which splits `sys.argv` on the first `--` **for the `mcp` verb only**. A positional named
   `command` would also have collided with the subparser's own `dest="command"`.

## Scope

**In scope:** `ck skill new`, `ck mcp add` / `ck mcp list`, filesystem↔registry reconciliation in
`gen-registry.py` (+ its missing CI step), the extraction of the context-floor measurement into
the installable package, one `ck doctor` check, docs/CHANGELOG/RESEARCH entries, three
behavioural test files.

**Out of scope:** the memory store and `ck adapt` (Phases 4–5); anything in Agent A's lane;
adding any MCP server to this repo; changing `ECC_HOOK_PROFILE` semantics; re-implementing
profile resolution (`profiles.resolve` is consumed, not duplicated); deleting or merging assets
(task 008 is owner-gated).

## Prerequisites

- Branch `perf/token-efficiency`, clean, `git pull --rebase` first (Agent A is committing).
- `.claude/settings.local.json` with `ECC_HOOK_PROFILE=minimal` present (session gotcha).

## Implementation Steps

| # | File | Action | What |
| --- | --- | --- | --- |
| 1 | `src/claudekit/context_floor.py` | Create | The one measurement: `BUDGETS`, `measure(root)`, `floor_remedy(root)`, `check_new_skill(root, description, invisible)` -> `(refusal, other_overages)`. Only a `skill descriptions` overage refuses; other categories warn (M2). Refusal quotes current / added / projected / budget and names the three ways out (shorten, `--invisible`, owner-signed budget raise), with a remedy command the reader actually has. |
| 2 | `scripts/check-context-floor.py` | Modify | Becomes a CLI over that module. `sys.path.insert(0, ROOT/"src")` so a bare CI checkout can import it; re-exports `frontmatter`/`model_invisible`/`description_span` for the two tests that load it by path; `measure()` stays zero-arg. |
| 3 | `src/claudekit/skills.py` | Create | **No `--used-by` parameter (M-new):** `usedBy` is always written `[]`, because `gen-registry.py` derives it from agent files and is its only writer. `new_skill()`: validate name/description → load registry → floor check → write `SKILL.md` → append registry entry atomically; on any failure after the scaffold, `rmtree` it. Registry entries are **appended, never re-sorted** (the shipped list is not sorted; re-sorting would bury a one-line addition in a 700-line diff). |
| 4 | `src/claudekit/mcp.py` | Create | `add_server()`: validate → require `--tools N` → `check_budget()` → write `.mcp.json` + `.claude/state/mcp-servers.json`. **Executes nothing.** `check_budget()` counts the union of `.mcp.json` and the ledger, and refuses to evaluate `max_tools` when a configured server has no recorded count. A name already in `.mcp.json` but absent from the ledger is **adopted**: ledger row written, no configuration touched, budget reports rather than refuses (H2). `list_servers()` returns that same union, so the view matches the enforcer (M1). `config_argv` is annotated `List[str]` and `str()`-coerced so the module typechecks under mypy/py3.9 (H1-new). |
| 5 | `src/claudekit/cli/main.py` | Modify (6 edits) | `cmd_skill`, `cmd_mcp`, `_split_server_command`, two subparsers, dispatch rows, and a `ck doctor` warning for skills on disk that are not registered. `cmd_skill` prints the floor warnings and, where `scripts/gen-docs.py` exists, names it as the required next step (H1); `cmd_mcp` distinguishes an adoption from an addition, surfaces the budget warning, and lists config-only servers as `unknown`; its `list` branch also prints `OVER BUDGET` with the numbers when the *standing* state exceeds `max_servers`/`max_tools`, naming that only the next addition is refused (M-new). There is no `--used-by` argparse row — a comment in its place records why (M-new). |
| 6 | `scripts/gen-registry.py` | Modify (3 edits) | `derive_skill_ids()`, `derive_agent_ids()`, `skill_entry_from_disk()`, and a rewritten `main()` tail that reconciles both directions. |
| 7 | `.claude/skills/skills-registry.json` | Modify | Add `agentsWithoutSkills` (the 11 agents above). Existing consumers read the registry with `.get()`, so an added key is inert for `ck doctor` and `run-evals.py`. |
| 2a | `tests/test_context_floor.py` | Modify | `plant_gate(root)` copies the gate CLI **and** `context_floor.py` into each isolated temp tree (C1). |
| 8 | `.github/workflows/ci.yml` | Modify | Replace the inline `validate-registry` step with `python3 scripts/gen-registry.py --check`, which strictly subsumes it. The old 23-line `python3 -c` block is **deleted**, not disabled (L2). |
| 16 | `.ai/CHANGELOG_AI.md` | Modify | Append the session entry, newest-first. |
| 9–11 | `tests/test_skill_new.py`, `tests/test_registry_drift.py`, `tests/test_mcp_add.py` | Create | The four mutation proofs (below), driven through the real CLI/script. |
| 12 | `docs/cli.md` | Modify | Document `skill new`, `mcp add`/`list` — and `profile`, undocumented since `f5eb927`. No `--used-by` to document: it is deleted (M-new), which is why this step needed no change in revision 4. |
| 13 | `CHANGELOG.md` | Modify | Append under `[Unreleased] / Added`. |
| 14 | `.ai/RESEARCH.md` | Modify | Append the CLI-vs-MCP-server rule and the ChaosEngine precedent; state explicitly that this repo adds no MCP servers. |

### The three refusal rules, stated precisely

- **Floor:** `projected = current_skill_description_chars + len(description)`. Refuse if
  `projected > 9000`, or if any category is *already* over budget. A skill created with
  `--invisible` (`disable-model-invocation: true`) is admitted uncharged — that is the same rule
  `measure()` already applies, not an exception to it.
- **`max_servers`:** refuse when `len(servers) + 1 > max_servers`; message quotes
  `max_servers=<limit> (current <n>)`.
- **`max_tools`:** refuse when `sum(declared) + tools > max_tools`; message quotes
  `current total is <n>`, `projected <n+t>`, `max_tools=<limit>` and the overage.
  `None` (the base-layer value, i.e. any profile that declares no `mcp` keys) means unlimited.

`--tools` is required, with deliberately no default: a default of zero would make the `max_tools`
budget pass for free, which is the silent-pass failure mode this whole phase exists to remove.
The core plan does **not** measure the count by running the server. Doing so means downloading and
executing third-party code from a `ck` verb, and ClaudeKit's validator allowlists `npx`, `node`,
`npm`, `python3` and `docker` by name — `npx -y @vendor/mcp-server` passes it. Calling that a
mitigation would be exactly the framing hard rule 6 forbids: it is a denylist speed bump, not a
sandbox. See `ops-mcp-probe.json` if the owner wants the probe anyway.

- **Unknown is not zero:** a server present in `.mcp.json` with no ledger row counts towards
  `max_servers` but makes the projected tool total unknowable, so `max_tools` is refused with that
  cause named. Counting only our own ledger made the budget fail **open**.
- **Adoption is not an addition.** `.mcp.json` is Claude Code's file and `claude mcp add` is
  its primary writer, so "configured but unrecorded" is a normal state. `ck mcp add <that name>
  --tools N` therefore *adopts* it: the ledger row is written, no configuration is touched, and
  the budget **cannot refuse** it — it adds no server and no tool schema, it records a cost
  already being paid. Refusing there is what made the fail-closed refusal inescapable (there is
  no `ck mcp remove`, so the only exit was hand-editing the ledger — the drift this phase
  abolishes). An over-budget adoption is reported as a warning with the numbers; the next
  genuine addition is refused normally, which the test asserts. An adopting call that supplies a
  `--` argv disagreeing with the configured one is refused, because adoption changes nothing.

## Testing Strategy — the four mutation proofs

Each proof mutates a real artifact and reads the failure. None is a structural assertion.

1. **Floor refusal** — `tests/test_skill_new.py::test_description_that_would_breach_the_floor_is_refused`.
   Plants a skill with an 8 900-char description in a temp project (headroom 100), then runs the
   real `ck skill new` with a 200-char description. Asserts exit 1, `"context floor"`,
   `"skill descriptions"` and `"9000"` in stderr, **and that neither the directory nor the
   registry entry was created**. Mutating the artifact back (shortening the description, or
   `--invisible`) makes it pass — pinned by `test_invisible_skill_is_not_charged_to_the_floor`.
2. **Hand-created asset fails the registry gate** — `tests/test_registry_drift.py`. Copies the
   real corpus, drops in `skills/hand-made-drift/SKILL.md` and `agents/hand-made-agent.md`, runs
   the real script: expects exit 1 and `UNREGISTERED skill 'hand-made-drift'`.
   `test_the_check_would_have_passed_the_mutants_before` asserts the failure is **not** an
   `agentMapping` drift line — i.e. it is the new check firing, not the old one.
   `test_regenerating_fixes_both_mutants` proves the generator is the remedy.
3. **MCP budget refusal** — `tests/test_mcp_add.py::test_max_servers_is_refused_with_numbers`
   (4th server under `python`: expects `max_servers=3`, `current 3`) and
   `::test_max_tools_is_refused_with_numbers` (35 + 10 against 40: expects `max_tools=40`,
   `current total is 35`, `projected 45`). `test_refusal_writes_nothing` byte-compares both JSON
   files across the refused call. `test_unlimited_when_the_profile_declares_no_budget` proves the
   gate does not fire where no budget is declared — a gate that always fires proves nothing.
4. **Generator output survives our own gates** —
   `tests/test_skill_new.py::test_generated_skill_passes_the_repos_own_gates` runs the real
   `gen-registry.py --check`, `check-context-floor.py --check` **and `gen-docs.py --check`**
   against the tree the generator just wrote (H1). Those are the three of the eight gates that
   apply to a project-shaped tree; the other five gate Python, shell and model policy that a
   generated `SKILL.md` does not contain. A generator whose output fails our lint manufactures
   drift at scale.
   `::test_a_new_skill_leaves_the_count_gate_red_until_gen_docs_reruns` pins the one drift that
   **cannot** be designed away: component counts are generator-owned (hard rule 8), so a new
   skill invalidates them and the only legal remedy is re-running `gen-docs.py`. The test
   baselines the generated blocks, creates a skill, asserts `--check` exits 1 with
   `"out of date"`, re-runs the generator, and asserts it exits 0 — so the red gate is a
   *pinned, named* consequence rather than a surprise in someone's CI run.
   `::test_the_cli_names_gen_docs_as_the_next_step` and
   `::test_the_hint_is_omitted_where_the_script_does_not_exist` pin both halves of the hint.

5. **The MCP escape path, end to end** (H2) —
   `tests/test_mcp_add.py::test_a_config_only_server_can_be_adopted_and_unblocks_the_budget`
   plants a config-only server, asserts the fail-closed refusal *and that it prints
   `ck mcp add`*, runs exactly that remedy, asserts the ledger row is `source: adopted` and
   `.mcp.json` is byte-unchanged, then asserts the addition that was blocked now succeeds.
   `::test_adopting_an_over_budget_server_is_recorded_with_a_warning` proves adoption is not a
   silent pass (numbers printed, exit 0) and that the budget still binds afterwards
   (`projected 100` refused). `::test_list_shows_the_config_only_servers_the_budget_counts`
   pins M1. `::test_an_unrelated_over_budget_category_warns_but_does_not_block` and
   `::test_the_floor_remedy_names_a_command_the_project_actually_has` (in
   `tests/test_skill_new.py`) pin M2.

6. **The generator cannot put the registry gate red** (M-new) —
   `tests/test_skill_new.py::test_there_is_no_way_to_hand_set_used_by` passes
   `--used-by planner` and asserts the CLI **rejects** it (argparse exit 2, `used-by`
   named in stderr) and that no skill directory is left behind.
   `::test_creation_leaves_the_registry_gate_green` then creates a skill and runs the real
   `gen-registry.py --check` in the temp project, asserting exit 0 and `usedBy == []` — the
   value the derivation produces. Zero tests covered this flag before; it was the one flag
   in the new surface that could put a DoD gate red.
7. **A standing MCP overage is disclosed, not implied away** (M-new) —
   `tests/test_mcp_add.py::test_list_names_the_standing_overage_the_budget_will_not_block`
   plants four config-only servers, adopts each at 20 tools (all exit 0, because adoption
   adds no schema), then asserts `ck mcp list` prints `servers 4/3`, `tools 80/40`,
   `OVER BUDGET`, and the sentence naming that only the next `ck mcp add` is refused.

**Mutation-proved, not asserted** (revision 4, run in the patched scratch tree — see the
revision-4 evidence table): reverting `config_argv` to revision 3's untyped form makes
`mypy` report `mcp.py:256 Incompatible types in assignment` again and fails
`tests/test_gate_scope.py::TestMypyScope`; deleting the `OVER BUDGET` block from
`cmd_mcp` fails `test_list_names_the_standing_overage_the_budget_will_not_block`;
restoring the `--used-by` flag and the `used_by` parameter fails
`test_there_is_no_way_to_hand_set_used_by`.

**Mutation-proved, not asserted** (revision 3, run in the patched scratch tree):
`adopting = name in config["mcpServers"]` → `adopting = False` fails 3 tests; removing
`scripts/gen-docs.py` from the CLI hint fails `test_the_cli_names_gen_docs_as_the_next_step`;
restoring the old "refuse on any overage" rule fails
`test_an_unrelated_over_budget_category_warns_but_does_not_block`.

Plus: `test_a_failed_registry_write_leaves_no_orphan_directory` monkeypatches the registry write
to raise and asserts no scaffold survives — the atomicity claim, exercised rather than asserted.

**Post-execution manual step (not an op):** update `.ai/SESSION_STATE.md` by hand — its header
and Resume point are a rewrite, not an append, and COORDINATION.md forbids reflowing a contended
file another agent may be holding.

**Definition of Done (all eight gates):** `pytest tests/ -q` · `ruff check src/ tests/ scripts/`
· `mypy` · `gen-docs.py --check` · `gen-registry.py --check` · `gen-model-policy.py --check`
· `check-context-floor.py` · `shellcheck install.sh .claude/hooks/*.sh`.

**Two disclosures on that gate list, so neither failure is misattributed:**

1. **`gen-docs.py` must be RE-RUN, not just checked** (H1). This change adds no counted asset,
   so `gen-docs.py --check` passes on the repo as delivered — but the moment anybody *uses*
   `ck skill new`, the skill count changes and the gate goes red until `python3
   scripts/gen-docs.py` is run. That is generator-owned behaviour (hard rule 8), not a defect,
   and it is pinned by a test rather than left to be discovered. Sequence after execution:
   `python3 scripts/gen-docs.py` → `git diff` (expect **no** change) → `--check`.
2. **`pytest tests/ -q` is RED at HEAD for a reason outside this lane** (M3).
   `tests/test_day_one_blockers.py::TestSelfScanIsClean::test_no_committed_file_matches_a_live_pattern[api_key...]`
   fails against `tests/test_memory.py` (lines 240, 257, 438 — literal `api_key = "sk-live-..."`
   fixtures committed by the memory lane). Re-verified at HEAD `5f3e322`:
   `1 failed, 14 passed` `[prior round, superseded]`. **Since fixed outside this plan:** the
   real tree's self-scan is now GREEN — `tests/test_day_one_blockers.py` +
   `tests/test_delivery_contract_smoke.py` -> `81 passed, 1 xfailed`
   `[re-measured by the round-4 adversarial reviewer, real tree]`.
   The owner has **separately approved fixing that failure outside this plan**, in the
   memory lane that owns `tests/test_memory.py`. So the exit criterion "all eight gates
   pass" (COORDINATION.md:81-82) is **achievable once the separately-approved memory-lane
   fix lands** — it is not achievable *by this lane*, whose ops deliberately do not touch
   that file, and this failure must not be read as a regression from this change.

Two extra post-execution checks specific to this change:
`python3 scripts/gen-registry.py` must be a **no-op** on the repo afterwards, and
`python3 scripts/check-context-floor.py --json` must report the **same numbers** as before the
extraction (`skill descriptions 7719`, `CLAUDE.md 30508`, total `89880`) — the extraction is a
move, and any change in those numbers means it was not.

## Net asset-count delta

**Zero** `[re-measured r4: `Counts: agents=29 commands=42 skills=76 hooks=21` / `OK: docs
counts are current.` on the patched scratch tree, exit 0]`. Revision 4 makes the public
surface **smaller**, not larger: one flag (`--used-by`) deleted, no verb, no counted asset,
no runtime dependency. `scripts/gen-docs.py` counts agents / commands / skills / hooks; this phase adds none
of the four. It adds 3 Python modules, 3 test files, 1 registry key and 2 CLI verbs — none of
which are counted assets, and none of which is a near-duplicate of an existing asset. The two
skills the brief names (`writing-skills`, `mcp-integration`) are **kept**: they teach judgement,
the generators enforce mechanics. Deleting them is a task-008 decision, not this one. The H2 fix
adds **no verb** (adoption is a mode of `ck mcp add`, chosen precisely so the surface does not
grow), and the `--probe` addendum adds 1 module + 1 test file, still no counted asset.

Verified, not asserted: on the patched scratch tree `python3 scripts/gen-docs.py --check` →
`Counts: agents=29 commands=42 skills=76 hooks=21` / `OK: docs counts are current.` (exit 0),
i.e. the delivered change moves no count. The *use* of `ck skill new` does move the skill count
— by construction, see the DoD note — which is why the follow-up generator run is named there
instead of the gate being left red.

## Rollback Plan

- Pre-execution: nothing to roll back; the ops config is queued, not applied.
- Post-execution, before commit: `ck rollback` (the operations engine backs up every touched
  file), or `git checkout -- <paths>`; the four created modules/tests are new files and can be
  deleted outright.
- Post-commit: `git revert` the single commit. Nothing here changes on-disk state in a user
  project until they run the new verbs; `.mcp.json` and `.claude/state/mcp-servers.json` are only
  written by an explicit `ck mcp add`.

## Risk Assessment

**Medium**
- *The context-floor extraction touches a shipped gate.* Two existing test files consume the
  script by path (one copies it into a temp tree, one imports it as a module). The design
  preserves both call shapes, and the DoD requires the measured numbers to be byte-identical.
  This is the single most likely place for the change to break something.
- *`ruff` on the deliberate late import.* `sys.path.insert` before `from claudekit.context_floor
  import …` is `E402`, marked `# noqa: E402`; the isort rule (`I`) may still want a word. Caught
  by the DoD lint run; remedy is a `# noqa: I001` on the block.
- *Registry schema addition.* `agentsWithoutSkills` is new. Verified that both consumers
  (`ck doctor`, `scripts/run-evals.py`) read the registry with `.get()` and ignore unknown keys.

**Low**
- `ck mcp add` executes nothing at all: it reads two JSON files, decides, and writes two JSON
  files. There is no third-party execution surface in the core plan.
- *Ledger before config, no transaction.* A hard kill between the two writes leaves a ledger row
  with no `.mcp.json` entry. That over-counts (one server refused too early); the opposite order
  would fail open. Both `ck mcp list` and `check_budget` now see the union of the two files, so
  such a row is visible rather than silent. (The earlier draft of this row claimed visibility in
  `ck mcp list` while `list_servers` read only the ledger — that claim was false when written and
  is what M1 fixed.) Disclosed, not claimed atomic.
- The registry `code_edit` is a hand-written insertion of 11 names; if it is ever wrong,
  `gen-registry.py --check` fails immediately and loudly.

**Watch (not a blocker)**
- *The budget binds on **deltas only**, so a standing overage is possible and nothing goes
  red.* `[re-measured r4]` Four config-only servers adopted at 20 tools each leave a project
  at **servers 4/3, tools 80/40** with every command exiting 0: adoption cannot be refused
  (it adds no schema — that is the H2 fix), `.mcp.json` is written by Claude Code rather
  than by us, and `ck doctor` has **no MCP check**. Only the *next addition* is refused.
  This is not a regression — nothing enforced the budget before this phase — but it is
  materially weaker than "the budget is enforced", so `ck mcp list` now prints
  `OVER BUDGET` with the numbers and says only the next add is refused, and
  `list_servers()`'s docstring says the same (hard rule 6 reaches Risk rows and
  docstrings). An MCP check in `ck doctor` is the obvious next step and is **deliberately
  out of scope for this revision**; it belongs in a backlog row.
- `.mcp.json` is Claude Code's file. `ck mcp add` merges into `mcpServers` and never rewrites
  keys it did not add — an adoption writes **only** the ledger — but it is a file the user may
  also edit by hand.
- *Adoption is exit-0 even when the resulting state is over budget.* Deliberate: adoption adds
  no schema, and the only alternative is the trap H2 identified. It is loud (the numbers are
  printed as a warning) and the next genuine addition is refused, which a test asserts. If the
  owner would rather adoption also exit non-zero while remaining *effective*, that is a one-line
  change in `cmd_mcp` and the test's expected exit code — say so.

**Pre-existing, not caused by this change (M3, out of lane)**
- `tests/test_day_one_blockers.py::TestSelfScanIsClean::test_no_committed_file_matches_a_live_pattern[api_key...]`
  fails at HEAD `5f3e322` against `tests/test_memory.py:240,257,438`, which commits literal
  `api_key = "sk-live-abcdefghijklmnop"` secret-shaped fixtures. Owned by the **memory lane**;
  this plan does not touch that file. Any post-execution suite run will show this failure, and
  it must not be attributed to Phase 3. Fixing it (a split literal, or a `gen-docs:ignore`-style
  allowance in the self-scan) belongs to whoever owns `tests/test_memory.py`, and the owner has
  now **separately approved that fix outside this plan** — so the eight-gate exit criterion is
  achievable once it lands, rather than blocked indefinitely. It is deliberately **not** in
  this plan's ops: `tests/test_memory.py` is not this lane's file.

## Executed evidence (revision 2 — method DISCREDITED: `git archive HEAD` export)

> **`git archive` is BANNED as a baseline/measurement method in this repo.** An export has no `.git` and no editable install, so it manufactures failures that exist only in the export and hides real regressions in the noise (it hid a genuine +1 regression in round 2 and was used again in round 4). The only admissible method is a **real `git worktree`** of the commit under test with the uncommitted tracked diff applied, measured against the same worktree without the delta.

All whole-suite figures in this revision-2 table are `[prior round, discredited method — not facts about this delta]` and are **superseded** by the revision-4 worktree re-derivation below. Per-command results (gates, single-file test runs) stand.

| Proof | Command | Result |
| --- | --- | --- |
| **C1, bare interpreter** (no `claudekit` installed — the `python3 -m pytest tests/ -q` DoD case) | `bare/bin/python -m pytest tests/test_context_floor.py tests/test_skill_loading_contract.py -q` | `40 passed` |
| **C1, editable install** (CI's case) | same, system `python3` | `40 passed` |
| **C1, the rejected design** | same two files, old header, HEAD's tests | `7 failed, 29 passed` — `ModuleNotFoundError: No module named 'claudekit'` |
| Extraction is a move | `check-context-floor.py --check` patched vs HEAD | identical: `skill descriptions 7719`, `CLAUDE.md 30508`, `TOTAL 89880` |
| **Proof 1** floor refusal | `ck skill new one-too-many --description <200 chars>` with 8 900 planted | exit 1 — `'skill descriptions' is 8900 chars of 9000; this description adds 200, projecting 9100 — 100 over`; skill dir absent, registry `[]`; `--invisible` admitted |
| **Proof 2** hand-created assets | two mutants in the real corpus | HEAD's script: `OK: agentMapping + usedBy match agent files (18 agents).` **exit 0**. New script: `UNREGISTERED skill 'hand-made-drift'` + `UNREGISTERED agent(s) ['hand-made-agent']`, **exit 1** |
| **Proof 3** MCP budget | 4th server / 35+10 tools | `max_servers=3 (current 3)` exit 1; `current total is 35, projected 45 … max_tools=40 — 5 over` exit 1 |
| **C3 regression** | 3 servers hand-added to `.mcp.json`, ledger empty | refused: `would be server 4 … max_servers=3 (current 3)` (old code: admitted) |
| **C3 unknown count** | 1 hand-added server | `MCP budget cannot be evaluated: 'hand-a' is in .mcp.json with no tool count …` |
| **Proof 4** generator output vs our gates | `ck skill new` then both gates | `OK: registry matches the filesystem (…1 skills).` exit 0; floor exit 0 |
| New tests | `pytest test_skill_new test_registry_drift test_mcp_add test_mcp_probe -q` | `32 passed` |
| ~~Full suite (export)~~ | ~~`python3 -m pytest tests/ -q` in a `git archive` export~~ | **STRUCK — discredited method.** Superseded by the revision-4 worktree row below. `[prior round, discredited method]` |
| Gates | gen-docs / gen-registry / gen-model-policy / context-floor / ruff / mypy | all exit 0; `ruff … All checks passed!`; `mypy … Success: no issues found in 23 source files` |
| Both configs | `validate-config-json.py` | `-> APPROVED` (16 ops) and `-> APPROVED` (2 ops) |

## Executed evidence (revision 3 — method DISCREDITED for whole-suite figures: `git archive HEAD` export)

This table contains no whole-suite count, so nothing in it is struck; the export method is nonetheless banned (see the note above) and its per-command results are labelled `[prior round, not re-run]` unless repeated in revision 4.

| Proof | Command | Result |
| --- | --- | --- |
| Every anchor still matches exactly once at HEAD `5f3e322` | counted `find` occurrences for all 16 + 2 operations | every `code_edit` anchor: **1**; every `file_create` path: absent |
| Both configs validate independently | `validate-config-json.py <each>` | `-> APPROVED` (16 ops) and `-> APPROVED` (2 ops), exit 0 |
| New + touched tests | `pytest tests/test_skill_new.py tests/test_mcp_add.py tests/test_registry_drift.py tests/test_context_floor.py -q` | **72 passed** |
| Lint of everything the configs emit | `ruff check --line-length 100` over the applied tree | `All checks passed!` |
| Every emitted Python file parses | `compile()` on all 12 produced modules/tests | OK |
| **H1** the count gate is pinned | `gen-docs.py --check` before/after `ck skill new`, then after regeneration | exit 0 → exit 1 (`... is out of date`) → exit 0 |
| **H1** mutation | dropped `scripts/gen-docs.py` from the CLI hint | `test_the_cli_names_gen_docs_as_the_next_step` **fails** |
| **H2** the escape path | refusal → `ck mcp add hand-a --tools 4` → previously blocked add | refusal names `ck mcp add`; adoption exit 0, `source: adopted`, `.mcp.json` unchanged; blocked add now exit 0 |
| **H2** mutation | `adopting = False` | 3 adoption tests **fail** |
| **M2** mutation | restored "refuse on any over-budget category" | `test_an_unrelated_over_budget_category_warns_but_does_not_block` **fails** |
| **L2** no dead CI step | `grep -c "if: false" .github/workflows/ci.yml` | `0`; `grep -n gen-registry` → `171: run: python3 scripts/gen-registry.py --check` |
| Repo gates on the patched tree | `gen-registry.py --check` / `gen-docs.py --check` / `check-context-floor.py --check` | `OK: registry matches the filesystem (18 mapped agents, 11 agents without skills, 76 skills).` / `OK: docs counts are current.` / `OK: context floor within budget.` |
| **M3** pre-existing failure at HEAD | `pytest tests/test_day_one_blockers.py::TestSelfScanIsClean -q` | `1 failed, 14 passed` — `'api_key...' matches committed files: ['tests/test_memory.py']`, **not** caused by this change |

## Executed evidence (revision 4, **real `git worktree` @ `5f3e322` + the uncommitted tracked diff** + the core config applied, then the probe config on top)

Revision 4 originally measured this in a `git archive` export. That method is banned (see the note above) and every whole-suite figure it produced has been struck. The whole-suite numbers below were **re-measured by the round-4 adversarial reviewer** in a real `git worktree` of `5f3e322` with the uncommitted tracked diff applied — the only admissible method.

Every row here was **run in this revision** unless the label says otherwise. Labels:
`[re-measured r4]` = executed against this delta; `[prior round, not re-run]` = last
executed in an earlier revision and unchanged by this delta; `[not yet executed]` = not run.

| Proof | Command | Result | Label |
| --- | --- | --- | --- |
| **H1-new** the delta typechecks | `python3 -m mypy src/claudekit/mcp.py src/claudekit/skills.py src/claudekit/context_floor.py src/claudekit/mcp_probe.py` in the patched tree | `Success: no issues found in 4 source files` | `[re-measured r4]` |
| **H1-new** the delta adds no mypy error | `python3 -m mypy` in the real tree | `Success: no issues found in 20 source files` at HEAD, and no new error from the delta (per-module run above is `Success: no issues found in 4 source files`). The earlier `Found 2 errors …` pair was an export artifact of the banned `git archive` method — the `[[tool.mypy.overrides]]` block only suppresses them when the package is importable — and is **STRUCK** | `[re-measured r4]` |
| **H1-new** the fix binds by mutation | reverted `config_argv` to revision 3's untyped form | `src/claudekit/mcp.py:256: error: Incompatible types in assignment (expression has type "Union[list[Optional[Any]], list[str]]", variable has type "list[str]")` returns, and `tests/test_gate_scope.py::TestMypyScope::test_gate_is_green_and_actually_reaches_the_ops_scripts` **fails** | `[re-measured r4]` |
| **M-new** `--used-by` is gone and the gate stays green | `pytest tests/test_skill_new.py -k "used_by or registry_gate_green"` | `2 passed` | `[re-measured r4]` |
| **M-new** mutation: restore the flag | re-added the argparse row + `used_by` parameter | `test_there_is_no_way_to_hand_set_used_by` **fails** (`[✓] Created .claude/skills/widget-forge/SKILL.md` — the flag was accepted) | `[re-measured r4]` |
| **M-new** the drift the flag produced | `ck skill new probe-skill --used-by planner` then `gen-registry.py --check` | `DRIFT usedBy probe-skill: registry=['planner'] derived=[]` / `FAIL`, and plain `gen-registry.py` resets `usedBy` to `[]` without a word | `[prior round, not re-run]` — executed by the round-3 reviewer; reproduced here only as far as the flag being accepted (mutation row above) |
| **M-new** the standing MCP overage is named | `pytest tests/test_mcp_add.py -k standing_overage` | `1 passed` — `servers 4/3`, `tools 80/40`, `OVER BUDGET`, "the next `ck mcp add` is refused" | `[re-measured r4]` |
| **M-new** mutation: delete the warning block | removed the `over_servers`/`over_tools` block from `cmd_mcp` | `test_list_names_the_standing_overage_the_budget_will_not_block` **fails** | `[re-measured r4]` |
| Every anchor matches exactly once at `5f3e322` | counted `find` occurrences for all 16 + 2 operations | every `code_edit` anchor: **1** — 20 `find` anchors across 10 modified files, counted with `str.count` (not grep, so leading whitespace is exact); every `file_create` path — **8** in total (**6** core + **2** addendum), corrected from the "7"/"5 core" miscount the round-4 reviewer re-derived: **all 8 absent at HEAD** | `[re-measured r4]` |
| Both configs validate **independently** | `python3 .claude/operations/scripts/validate-config-json.py <each>` | `-> APPROVED` exit 0 (16 ops) and `-> APPROVED` exit 0 (2 ops) | `[re-measured r4]` |
| Every emitted Python file parses | `compile()` over all 14 produced modules/tests | OK | `[re-measured r4]` |
| Lint | `python3 -m ruff check src/ tests/ scripts/` on the patched tree | `All checks passed!` (E501 is ignored repo-wide; `line-length = 100` still respected in the emitted code) | `[re-measured r4]` |
| Lane tests | `pytest tests/test_skill_new.py tests/test_mcp_add.py tests/test_registry_drift.py tests/test_context_floor.py -q` | **75 passed** (72 in revision 3, +3 new) | `[re-measured r4]` |
| Probe addendum tests | `pytest tests/test_mcp_probe.py -q` | `5 passed` | `[re-measured r4]` |
| Repo gates on the patched tree | `gen-registry.py --check` / `gen-docs.py --check` / `check-context-floor.py --check` | `OK: registry matches the filesystem (18 mapped agents, 11 agents without skills, 76 skills).` / `Counts: agents=29 commands=42 skills=76 hooks=21` + `OK: docs counts are current.` / `OK: context floor within budget.` with `skill descriptions 7719`, `CLAUDE.md 30508`, `TOTAL 89880` — **identical to HEAD**, so the extraction is still a move | `[re-measured r4]` |
| Full suite, real worktree: baseline vs patched | `pytest tests/ -q -p no:randomly` in a **real `git worktree` @ `5f3e322` + the uncommitted tracked diff**, once without and once with both ops applied | baseline worktree: `1 failed, 1766 passed, 1 xfailed`; patched worktree (both ops): `2 failed, 1809 passed, 1 xfailed`. **True net effect: +43 passing tests, ZERO new failures.** The one added failure is `tests/test_delivery_contract_smoke.py::test_queued_ops_configs_validate_against_head` — the spent configs sitting unarchived in `.claude/plans/`, already anticipated and attributed by this plan (see the archive requirement above); the reviewer proved the documented remedy closes it (`1 passed` after moving the configs and appending the archive README rows). The baseline's own `1 failed` was an unrelated archive-README self-scan failure present at measurement time and **since fixed** — the real tree's self-scan is now green (`81 passed, 1 xfailed` across `tests/test_day_one_blockers.py` + `tests/test_delivery_contract_smoke.py`). The queued-configs failure is the **only** failure attributable to applying this plan. **STRUCK from this row:** the former `35 failed, 1776 passed` / `35 failed, 1732 passed` export figures and the `37 vs 35 order-dependent flakes under the random-ordering plugin` claim — both were artifacts of the banned `git archive` method, not facts about this delta | `[re-measured r4 by the round-4 adversarial reviewer, real `git worktree` @ 5f3e322 + uncommitted tracked diff]`; baseline self-scan figure `[re-measured, and since fixed]` |
| `gen-model-policy.py --check` | `python3 scripts/gen-model-policy.py --check` | `Model policy in sync: 29 agent roles.` rc=0 | `[re-measured by the round-4 adversarial reviewer, real tree]` |
| `shellcheck` | `shellcheck install.sh .claude/hooks/*.sh` | rc=0, no output | `[re-measured by the round-4 adversarial reviewer, real tree]` |
| ~~`tests/test_gate_scope.py::TestMypyScope` fails when its whole file runs~~ | `pytest tests/test_gate_scope.py::TestMypyScope -q` | **STRUCK — the claim was FALSE.** The round-4 reviewer executed it: `3 passed` on the patched tree with the whole file running, and `1 failed, 2 passed` only under the deliberate mutant. There is no order-dependent failure here | `[re-measured r4 by the round-4 adversarial reviewer, real worktree]` |

## Open decisions for the owner

1. **`--probe`: take it or leave it.** The core plan is probe-free and complete without it. The
   addendum `.claude/plans/ops-mcp-probe.json` is ready if you want it, and says plainly what it
   costs: it executes third-party code as you, and nothing in ClaudeKit isolates it. **Not chosen
   here.** Its CLI wiring (three lines: import `mcp_probe`, a `--probe` flag, an ack flag) is not
   in that config because `validate-config-json.py` requires `find` anchors to exist at HEAD and
   `mcp.py` does not exist yet — it is a follow-up ops config authored after the core lands.
2. **Lane change accepted:** `scripts/check-context-floor.py`, `tests/test_context_floor.py` and
   `.github/workflows/ci.yml` are Agent B's for this phase. Agent A should be told, and
   COORDINATION.md's table should gain the three rows.
3. **Where should `.mcp.json` be written** — project root (Claude Code's project scope, chosen
   here) or `.claude/`? Root is what Claude Code reads; confirm that is the intended surface.
4. **`agentsWithoutSkills` is a registry schema addition.** It is what makes a hand-created agent
   fail the gate. If you would rather the gate stayed skills-only, say so and mutation proof 2
   drops its agent half.
5. **Version bump.** Two new public verbs are a minor-version surface. Hard rule 7 says three
   files bump together; not included here because releases are owner-gated.
6. **Adoption semantics (H2).** Chosen: option (a) — `ck mcp add` adopts a config-only server,
   because the refusal already prescribed that exact command and it adds no verb (task 008).
   Options (b) `ck mcp adopt` / `ck mcp remove` and (c) "accept `--tools N` on the refusing
   call" were rejected: (b) grows the public surface and the asset count for a state that is
   already expressible, and (c) would have `ck mcp add second` silently record facts about a
   *different* server, which is a worse surprise than the refusal. A `ck mcp remove` is still
   the obvious missing verb — deliberately **out of scope** here and worth a backlog row.
7. **`--used-by` is deleted (M-new), and that is a public-surface deletion.** No release has
   shipped it — it exists only inside this queued plan — so nothing downstream can depend on
   it, and no user-visible removal notice is needed. Recorded here rather than assumed:
   if you would rather have option (a) (refuse the flag unless the agent file already lists
   the skill), say so and it comes back with the refusal test attached; the argument against
   it is in "Why `--used-by` is deleted rather than constrained" above.
8. **An MCP check in `ck doctor` is not in this revision.** The budget binds on deltas only,
   so a project can sit permanently over it with nothing red. Disclosed in Risk and printed
   by `ck mcp list`; enforcing it in `ck doctor` is a scope decision for you, and a backlog
   row either way.
9. **M3 blocks the phase exit criterion, and it is not this lane's file.** COORDINATION.md:81-82
   asserts all eight gates pass; they do not, because of `tests/test_memory.py`. Please route
   that to the memory lane, or tell Agent B to treat that single named failure as a known-bad
   baseline for this phase's sign-off.

---

HANDOFF TO: reviewer
---
Plan File: `.claude/plans/plan-generators-that-cannot-drift.md`
Ops Config: `.claude/plans/ops-generators-that-cannot-drift.json`
Complexity: Complex
Files Affected: 16 core ops (6 `file_create`, 10 `code_edit` across 10 modified files) + 2 `file_create` in the owner-gated addendum = **8 `file_create` paths total**, all absent at HEAD `[re-measured by the round-4 adversarial reviewer]`
Steps: **14 step rows covering the 16 core operations** (rows such as `2a` and `9–11` cover several ops each, so it is not literally 1:1); **zero step paths orphaned from ops** and zero ops without a step row `[re-measured by the round-4 adversarial reviewer]`
Revision: 4 (round 3 = 89.9/100; [H1-new] blocker + 2 mediums closed; fourth round owner-authorised)
Net asset-count delta: ZERO (and one public flag deleted)
Risk Level: Medium
