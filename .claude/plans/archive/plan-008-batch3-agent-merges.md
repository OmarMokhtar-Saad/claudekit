# Implementation Plan: task 008 batch 3 — the blocker first

**Status:** phase 0 only (the alias mechanism). The seven merge clusters are NOT in
this plan — one cluster per plan, one plan per PR, per the owner's compensating
controls.

## Why this plan contains no merges

The sign-off approved batch 3 **over a recommendation to hold**, because its designed
gate — the eval suite — is blocked on cassettes. The owner's compensating controls
therefore replace that gate, and one of them is a hard prerequisite:

> the registry `renamed` alias map must serve every removed agent name for one release,
> so consumers see a rename and not a deletion

**That mechanism did not exist.** Measured before writing anything:

    renamed: 'python-reviewer' -> 'code-reviewer', which does not exist

`gen-registry.py` resolves every `renamed` target against `.claude/skills/`, so an
agent name could not be aliased at all. This is the same shape as batch 1's blocker —
the protected-file `*.md` glob had to be narrowed before batch 1 could run — and it
gets the same treatment: land the mechanism, prove it, **then** delete an agent.

## Why a separate map and not a flag on `renamed`

`renamedAgents` maps an old agent id to `{"to": <name>, "kind": "agent"|"skill"}`. The
object-valued target is not ceremony; it is forced by batch 3's own content:

- **Three of the seven clusters move an agent INTO the skill namespace.**
  `python-reviewer` and `typescript-reviewer` become per-language checklist skills;
  `tdd-guide` folds into the existing `test-driven-development` skill. A bare-name alias
  cannot say which directory to validate the target against, so `kind` carries it.
- **The namespaces can collide.** `comm -12` over the two name sets is empty today, so
  a flat map would work *now* — and batch 3 is precisely the change that creates the
  pressure, since it puts former agent names into `.claude/skills/`. A flat map would
  then resolve an agent name to a same-named skill silently.

## Scope — 2 configs, no deletions

| # | Config | Effect |
| --- | --- | --- |
| 00 | `agent-alias-mechanism` | `renamed_agents_map()` + `resolve_agent_id()` in `src/claudekit/skills.py`; `renamedAgents` validation in `scripts/gen-registry.py`; `ck doctor` reads it |
| 01 | `agent-alias-tests` | `tests/test_agent_aliases.py` — every validator rule proven by a registry that violates it |

`MAX_DELETIONS` is not exercised: this plan deletes nothing. The map ships **empty**,
and the first merge cluster is what fills it.

## Must be proven, not asserted

| # | Claim | Proof |
| --- | --- | --- |
| 1 | An agent name can now be aliased at all | A project fixture whose registry aliases a removed agent passes `gen-registry.py --check`; the same alias was a hard error before. |
| 2 | The cross-namespace case actually works | `kind: skill` pointing at a real skill is accepted; **`kind: agent` pointing at that same real skill is refused.** Without the second half, `kind` is decoration. |
| 3 | A dishonest alias is refused | Missing target, wrong namespace, empty key, malformed spec, and an alias shadowing an agent that still exists — five fixtures, five non-zero exits with the message asserted. |
| 4 | Resolution is single-hop | `a -> b -> c` resolves `a` to `b`, never `c`. A chain means two releases of aliases outliving a one-release window. |
| 5 | The resolver and the generator disagree ON PURPOSE | Junk degrades to "no alias" in the resolver (a lookup must never crash a caller) and is a hard error in the generator (junk must never ship). Both asserted, so a future "consistency" cleanup cannot quietly collapse them. |
| 6 | `ck doctor` tells a consumer which files still name the removed agent | The same one-file exemption as the skill map: the asset that REPLACED the agent may name what it absorbed. |
| 7 | Nothing ships aliased yet | `renamed_agents_map()` on the shipped registry is empty — the mechanism lands before the merges that need it. |

## Risk

Low. Additive: a registry with no `renamedAgents` key behaves exactly as before, and
the validation only fires on a key that does not exist yet. The risk this plan REMOVES
is the one that matters — deleting an agent with no way for a consumer to resolve its
name.

## What comes next, and what is still unsolved

Seven clusters remain, each its own plan and PR:

| From | Into |
| --- | --- |
| `python-reviewer`, `typescript-reviewer` | per-language checklist **skills**, loaded by `code-reviewer` on matching extensions |
| `silent-failure-hunter` | a `code-reviewer` dimension |
| `documenter` + `doc-updater` | one `docs` agent, `mode: create\|update` |
| `code-simplifier` | `refactor-cleaner` |
| `tdd-guide` | the existing `test-driven-development` skill |
| `model-router` | inline table in `coordinator.md` + a thin `/model-route` |
| `harness-optimizer` | `context-budget` skill/command |

29 → ~20 agents. **The accepted risk is unchanged by this plan:** routing behaviour
still cannot be demonstrated unchanged, because the eval cassettes do not exist. Every
cluster PR must say so plainly rather than implying the eval suite covered it.

Note for the `documenter` + `doc-updater` cluster: batch 4 just made the coordinator
routing table distinguish **Docs (new)** from **Docs (update)**, which is the
`mode: create|update` split that cluster implements. The table is already shaped for it.

## Definition of Done

    python3 -m pytest tests/ -q
    ruff check src/ tests/ scripts/
    mypy
    python3 scripts/gen-docs.py --check
    python3 scripts/gen-registry.py --check
    python3 scripts/gen-model-policy.py --check
    python3 scripts/check-context-floor.py
    shellcheck install.sh .claude/hooks/*.sh
    python3 scripts/check-protected-differential.py --baseline main --require-baseline
    ck lint
