# Plan — review-loop, amendment 2: keep the policy under the context floor

**Tier:** 1-2 follow-up to `plan-review-loop.md`. **Ops config:** `.claude/plans/ops-review-loop-2.json`

Amendment 1's two `CLAUDE.md` bullets broke `scripts/check-context-floor.py`: CLAUDE.md is
delivery-weighted ×4 (main context + 3 pipeline subagent injections, `src/claudekit/context_floor.py:47`),
so 729 added bytes cost 2916 against a 492-byte headroom. Adding policy to CLAUDE.md is expensive
by design; the fix is to put the policy where the agent that must obey it already reads.

Changes:
- `CLAUDE.md` — the two bullets collapse to one pointer line.
- `.ai/REVIEW_GUIDE.md` — gains the full reviewer-routing rule, the code-review exit rule, the
  rounds-2+ ledger contract, and the pre-ops design precheck.
- `.claude/agents/planner.md` — gains **Phase 0: Design Precheck (Tier 2/3)**, so the precheck
  reaches the agent that authors configs rather than only the orchestrator.

Proof: `python3 scripts/check-context-floor.py` returns to OK, and the full DoD gate stays green.
