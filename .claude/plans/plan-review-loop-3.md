# Plan — review-loop, amendment 3: the artifact check matches by name, not by prefix

**Tier:** 1. **Ops config:** `.claude/plans/ops-review-loop-3.json`

Run against the real corpus, `scripts/check-plan-artifacts.py` flagged
`plan-dispatcher-payload.md` for three hook files the plan names twelve times — by basename,
without the `.claude/hooks/` prefix. That is a false positive, and the expensive kind: it trains
authors to paste path prefixes instead of describing the artifact, and it makes the gate ignorable.

The class being mechanised is *the artifact goes unmentioned*, so the basename is the correct
token. `scripts/check-plan-artifacts.py` now passes when either the full path or the basename
appears; `tests/test_check_plan_artifacts.py` gains both directions — a basename-only plan passes,
an unmentioned artifact still fails.
