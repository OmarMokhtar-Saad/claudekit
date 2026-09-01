# Plan Index

<!-- GENERATED FILE - owned by scripts/gen-plan-index.py; never hand-edit. -->
<!-- Regenerate with: python3 scripts/gen-plan-index.py -->

Every state below is **derived** from evidence on disk -- ops.json presence,
`review-record.py check` verdicts, and `Plan-Id:` git trailers. Nothing here is
hand-maintained, and per CLAUDE.md's evidence-precedence rule this generated
index never outranks the current files.

| State | Means |
|---|---|
| `not_started` | a plan document exists; no ops.json anywhere |
| `planned` | ops.json exists; no review record yet |
| `revise` | a review record exists, but its verdict does not authorise execution |
| `approved` | APPROVED record, and the ops.json still matches the reviewed bytes |
| `drifted` | **the ops.json changed after approval** -- the score does not apply |
| `executed` | a commit carries a `Plan-Id: <slug>` trailer |
| `legacy` | archived with no `Plan-Id:` commit -- pre-convention, state unknowable |

## Summary

| State | Plans |
|---|---:|
| `drifted` | 4 |
| `approved` | 50 |
| `planned` | 12 |
| `executed` | 28 |
| `not_started` | 20 |
| `legacy` | 3 |
| **total** | **117** |

## Plans

| Plan | State | Ops configs | Notes |
|---|---|---:|---|
| `.claude/plans/plan-008-b3c1-simplifier-merge.md` | `executed` | 0 |  |
| `.claude/plans/plan-008-b3c2-silent-failure-merge.md` | `executed` | 0 |  |
| `.claude/plans/plan-008-b3c3-language-checklists.md` | `executed` | 0 |  |
| `.claude/plans/plan-008-b3c4-docs-merge.md` | `executed` | 0 |  |
| `.claude/plans/plan-008-b3c5-tdd-fold.md` | `executed` | 0 |  |
| `.claude/plans/plan-008-b3c6-model-router-fold.md` | `executed` | 0 |  |
| `.claude/plans/plan-008-b3c7-harness-fold.md` | `executed` | 0 |  |
| `.claude/plans/plan-008-batch1-one-tree.md` | `not_started` | 0 |  |
| `.claude/plans/plan-008-paper-trail.md` | `executed` | 5 |  |
| `.claude/plans/plan-adapt-eject-interaction.md` | `not_started` | 0 |  |
| `.claude/plans/plan-agent-tool-grants.md` | `approved` | 1 |  |
| `.claude/plans/plan-approval-machinery.md` | `approved` | 1 |  |
| `.claude/plans/plan-backlog-triage-pass.md` | `executed` | 2 |  |
| `.claude/plans/plan-callsite-audit-line-level.md` | `approved` | 1 |  |
| `.claude/plans/plan-canonical-skill-wins.md` | `approved` | 1 |  |
| `.claude/plans/plan-capability-tiers-audit.md` | `approved` | 1 |  |
| `.claude/plans/plan-capability-tiers-followup.md` | `approved` | 1 |  |
| `.claude/plans/plan-capability-tiers.md` | `drifted` | 1 |  |
| `.claude/plans/plan-ck-adapt.md` | `approved` | 1 |  |
| `.claude/plans/plan-cli-live-findings.md` | `executed` | 4 |  |
| `.claude/plans/plan-close2.md` | `executed` | 2 |  |
| `.claude/plans/plan-code-review-triage.md` | `approved` | 1 |  |
| `.claude/plans/plan-command-bash-parse-gate.md` | `executed` | 1 |  |
| `.claude/plans/plan-command-bash-placeholders.md` | `executed` | 2 |  |
| `.claude/plans/plan-context-budget-lazy-skills.md` | `not_started` | 0 |  |
| `.claude/plans/plan-context-economy-rules.md` | `approved` | 1 |  |
| `.claude/plans/plan-day-one-blockers.md` | `approved` | 1 |  |
| `.claude/plans/plan-dispatcher-payload.md` | `drifted` | 2 |  |
| `.claude/plans/plan-doctor-gate.md` | `approved` | 1 |  |
| `.claude/plans/plan-doctor-score-eject.md` | `approved` | 1 |  |
| `.claude/plans/plan-e2e-lane-a.md` | `approved` | 1 |  |
| `.claude/plans/plan-e2e-pipeline-test-task.md` | `approved` | 1 |  |
| `.claude/plans/plan-enforcement-runtime.md` | `drifted` | 2 |  |
| `.claude/plans/plan-enforcement-trio.md` | `executed` | 21 |  |
| `.claude/plans/plan-eval-replay-engine.md` | `approved` | 1 |  |
| `.claude/plans/plan-fable-behavior-corpus.md` | `not_started` | 0 |  |
| `.claude/plans/plan-findings-and-plan-lifecycle.md` | `not_started` | 0 |  |
| `.claude/plans/plan-fleet-skill-enhancement.md` | `not_started` | 0 |  |
| `.claude/plans/plan-floor-gate-exit-code.md` | `approved` | 1 |  |
| `.claude/plans/plan-floor-json-flag.md` | `planned` | 1 |  |
| `.claude/plans/plan-gate-scope.md` | `approved` | 1 |  |
| `.claude/plans/plan-generators-that-cannot-drift.md` | `approved` | 1 |  |
| `.claude/plans/plan-harness-findings.md` | `approved` | 1 |  |
| `.claude/plans/plan-hook-live-findings.md` | `executed` | 10 |  |
| `.claude/plans/plan-hook-log-dedup.md` | `executed` | 3 |  |
| `.claude/plans/plan-hook-profiles.md` | `approved` | 1 |  |
| `.claude/plans/plan-install-preservation-and-xpipe-policy.md` | `not_started` | 0 |  |
| `.claude/plans/plan-install-receipts.md` | `approved` | 1 |  |
| `.claude/plans/plan-installer-python-hooks.md` | `approved` | 1 |  |
| `.claude/plans/plan-intermittent-sighting.md` | `executed` | 1 |  |
| `.claude/plans/plan-iron-law-enforcement-hook.md` | `approved` | 1 |  |
| `.claude/plans/plan-iron-law-scope-and-hook-count.md` | `approved` | 1 |  |
| `.claude/plans/plan-issue-ledger.md` | `approved` | 1 |  |
| `.claude/plans/plan-legacy-install-lifecycle.md` | `not_started` | 0 |  |
| `.claude/plans/plan-mcp-probe-addendum.md` | `not_started` | 0 |  |
| `.claude/plans/plan-memory-store.md` | `approved` | 1 |  |
| `.claude/plans/plan-model-routing-token-orchestration.md` | `not_started` | 0 |  |
| `.claude/plans/plan-open-issues.md` | `approved` | 1 |  |
| `.claude/plans/plan-ops-approval-gate.md` | `approved` | 1 |  |
| `.claude/plans/plan-ops-engine-file-modes.md` | `approved` | 1 |  |
| `.claude/plans/plan-ops-hardening-implementer-contract.md` | `planned` | 1 |  |
| `.claude/plans/plan-oracle-liveness.md` | `not_started` | 0 |  |
| `.claude/plans/plan-preserve-dir-symlinks.md` | `not_started` | 0 |  |
| `.claude/plans/plan-preserve-fault-tolerance.md` | `drifted` | 6 |  |
| `.claude/plans/plan-protected-docs-scope.md` | `approved` | 1 |  |
| `.claude/plans/plan-queued-ops-gate.md` | `executed` | 3 |  |
| `.claude/plans/plan-receipts-regressions.md` | `approved` | 1 |  |
| `.claude/plans/plan-reflection-ledger-isolation.md` | `approved` | 1 |  |
| `.claude/plans/plan-reflection-lifecycle-gates.md` | `approved` | 1 |  |
| `.claude/plans/plan-reflection-test-isolation.md` | `approved` | 1 |  |
| `.claude/plans/plan-rejection-retro-loop-impl.md` | `not_started` | 0 |  |
| `.claude/plans/plan-rejection-retro-loop.md` | `planned` | 7 |  |
| `.claude/plans/plan-remaining-fixes-2026-07-31.md` | `not_started` | 0 |  |
| `.claude/plans/plan-remove-codex-mirror.md` | `approved` | 1 |  |
| `.claude/plans/plan-request-shaping.md` | `planned` | 5 |  |
| `.claude/plans/plan-residuals.md` | `approved` | 1 |  |
| `.claude/plans/plan-residue-cleanup.md` | `approved` | 1 |  |
| `.claude/plans/plan-retro-completion.md` | `planned` | 9 |  |
| `.claude/plans/plan-review-approval-binding.md` | `planned` | 1 |  |
| `.claude/plans/plan-review-d945278.md` | `executed` | 9 |  |
| `.claude/plans/plan-review-discipline.md` | `approved` | 1 |  |
| `.claude/plans/plan-review-floor-and-iron-law-scope.md` | `approved` | 1 |  |
| `.claude/plans/plan-review-loop-2.md` | `planned` | 1 |  |
| `.claude/plans/plan-review-loop-3.md` | `planned` | 1 |  |
| `.claude/plans/plan-review-loop-tripwire.md` | `approved` | 1 |  |
| `.claude/plans/plan-review-loop.md` | `planned` | 4 |  |
| `.claude/plans/plan-review-round-2.md` | `executed` | 18 |  |
| `.claude/plans/plan-review-round-history.md` | `approved` | 1 |  |
| `.claude/plans/plan-review-truthfulness-batch.md` | `approved` | 1 |  |
| `.claude/plans/plan-round-3-and-gate-residuals.md` | `executed` | 0 |  |
| `.claude/plans/plan-round-4-derived-corpus.md` | `executed` | 0 |  |
| `.claude/plans/plan-round-5-sixth-axis.md` | `executed` | 12 |  |
| `.claude/plans/plan-run-command-op.md` | `not_started` | 0 |  |
| `.claude/plans/plan-scanner-coverage.md` | `executed` | 8 |  |
| `.claude/plans/plan-session-close-fix.md` | `executed` | 2 |  |
| `.claude/plans/plan-session-close.md` | `executed` | 4 |  |
| `.claude/plans/plan-shellcheck-version-drift.md` | `planned` | 1 |  |
| `.claude/plans/plan-silent-failure-lint.md` | `approved` | 1 |  |
| `.claude/plans/plan-skill-loading-contract.md` | `approved` | 1 |  |
| `.claude/plans/plan-task-014-supply-chain-hardening.md` | `planned` | 1 |  |
| `.claude/plans/plan-token-dash.md` | `executed` | 6 |  |
| `.claude/plans/plan-token-efficiency.md` | `not_started` | 0 |  |
| `.claude/plans/plan-token-waste-workflow-fixes.md` | `not_started` | 0 |  |
| `.claude/plans/plan-triage-refresh.md` | `executed` | 10 |  |
| `.claude/plans/plan-uninstall-partial-owned-deadend.md` | `approved` | 1 |  |
| `.claude/plans/plan-validator-base-normalisation.md` | `approved` | 1 |  |
| `.claude/plans/plan-validator-comment-escape.md` | `approved` | 1 |  |
| `.claude/plans/plan-validator-comment-inert.md` | `approved` | 1 |  |
| `.claude/plans/plan-validator-differential-gate.md` | `approved` | 1 |  |
| `.claude/plans/plan-validator-segmentation.md` | `approved` | 1 |  |
| `.claude/plans/plan-work-loss-protection.md` | `not_started` | 0 |  |
| `.claude/plans/plan-workflow-file-templates-ops-schema.md` | `planned` | 1 |  |
| `.claude/plans/plan-worktree-multi-agent.md` | `not_started` | 0 |  |
| `.claude/plans/plan-xpipe-flags.md` | `not_started` | 0 |  |
| `.claude/plans/archive/plan-008-batch2-skill-merges.md` | `legacy` | 0 |  |
| `.claude/plans/archive/plan-008-batch3-agent-merges.md` | `legacy` | 0 |  |
| `.claude/plans/archive/plan-008-batch4-command-diet-and-lint.md` | `legacy` | 0 |  |
