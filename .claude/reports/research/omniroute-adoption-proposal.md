# OmniRoute → ClaudeKit fleet: adoption proposal

Date: 2026-09-06 · Status: PROPOSAL, owner-gated · No code changed
Source research: `.claude/reports/research/omniroute-2026-09-06.md`

## What OmniRoute is

`diegosouzapw/OmniRoute` — MIT, TypeScript, an OpenAI-compatible **AI gateway** that
routes requests across 352+ LLM providers. 19 selection strategies, an "Auto-Combo"
scorer over ~16 factors (health, quota, cost, latency, task fit, model quality),
user-defined fallback **combo chains** stored in SQLite and reordered from a dashboard,
and a 3-layer resilience stack (provider circuit breaker → per-account connection
cooldown with exponential backoff → per-model 429 lockout, honouring `Retry-After`).

## The honest fit assessment

Its *core* — multi-vendor provider arbitrage — **does not transfer**. ClaudeKit routes
one vendor's capability tiers (`model-policy.json`: most-capable/balanced/fast) and
does not own the request path at all; Claude Code does. Adopting a gateway would mean
building an inference proxy, which is a different product and would break hard rule 8
(zero runtime dependencies) and the "no vendor model names in policy" rule.

What *does* transfer is the **shape of its escalation and degradation model**, and
three of its repo practices. Ranked by value-to-risk:

### A. Fallback chains as data, not prose  — HIGH value, Tier 2
Our degradation rule lives as one English sentence in CLAUDE.md ("On limits, degrade
one tier, never stop"). OmniRoute's combo chain is an ordered, inspectable list.
Proposal: extend `model-policy.json` with an explicit `degrade_to` per tier, making the
chain a checked artifact `gen-model-policy.py --check` can assert, symmetric to the
`escalate_to`/`escalate_when` pair roles already carry. Today escalation is data and
degradation is folklore; this makes them the same kind of thing.

### B. Health/cooldown state instead of blind retry — MEDIUM value, Tier 3
Their per-model 429 lockout + `Retry-After` is the disciplined version of what our
agents do ad hoc when they hit limits. A bounded version for us: record a tier's
limit-hit in session state so the next spawn starts degraded rather than re-hitting.
Real risk: this is new stateful machinery in the spawn path, security-adjacent, and the
concurrency-guard experience (27 review rounds, never converged) is the warning. Only
worth it if limit-thrash is an observed pain, not a theoretical one. **Recommend: defer.**

### C. `changelog.d/` fragments instead of a hand-edited CHANGELOG — HIGH value, Tier 2
Directly relevant to the fleet: 16 repos each hand-editing `[Unreleased]` is a merge-
conflict generator. Fragment files per change, assembled at release, removes the
conflict class entirely. This is the single cleanest steal.

### D. Schema validation on config inputs — MEDIUM, already partly ours
They use Zod on every input. Our analogue is ops.json validation, which exists. The gap
worth noting is the one already recorded in memory: the validator never compiles the
post-state (`ops add_after` is literal concat). That is our real validation hole, and
OmniRoute doesn't help with it. Listed only so it isn't mistaken for a new idea.

### E. Build integrity sentinel (BUILD_SHA) — MEDIUM value for the fleet, Tier 2
They stamp a build SHA to detect a stale deploy. Fleet analogue: stamp the kit version +
source commit into installed trees so `ck doctor` can report "this project is 3 versions
behind" instead of the owner tracking 16 sync states by hand. Fits the existing
`ck doctor --strict` surface rather than adding a new one.

### Rejected outright
- **Zero-config free-provider preconnection** — we ship no credentials; nothing to preconnect.
- **19 pluggable strategies** — routing 20-odd roles across 3 tiers does not need a strategy
  library. Would be pure ceremony.
- **Dashboard-driven reordering** — a UI is not in scope for a prompt corpus + CLI.
- **Compression pipeline (RTK/Caveman/LLMLingua-2)** — lossy prompt compression in front of
  a review agent trades away exactly the fidelity reviews depend on.

## Fleet constraints that bound any of this

- Fleet is currently **HELD** (concurrency-guard decision #23, PR #28 open).
- Sync must stay surgical — never overwrite downstream project-specific files.
- Downstream changes stay uncommitted for the owner; never merge downstream back.

So even the approved items ship to ClaudeKit first and reach the fleet only on the next
deliberate sync, after the hold lifts.

## Recommendation

Take **A + C + E**. Defer **B**. Drop the rest.
That is two Tier-2 changes to this repo (policy schema + changelog fragments) and one
`ck doctor` extension — each independently revertable, none touching the security surface.

## Open decisions for the owner
1. Approve A/C/E, or a subset?
2. Does `changelog.d/` go to the fleet template too, or ClaudeKit only?
3. Is limit-thrash (B) an actually observed problem worth Tier-3 machinery?
