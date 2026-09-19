# planner memory

- [A green check can measure nothing](a-green-check-can-measure-nothing.md) — prove a check fails before trusting that it passes
- [The gate binds in one order](the-gate-binds-in-one-order.md) — stamp the baseline before recording a verdict
- [Installer order decides what survives](installer-order-decides-what-survives.md) — writing a file before preservation runs makes preservation skip the real one
- [Session is not an identity axis](session-is-not-an-identity-axis.md) — one pipeline is one session id; author-vs-reviewer can only be attested by role
- [PostToolUse can rewrite tool output](posttooluse-can-rewrite-output.md) — `updatedToolOutput` exists, and the event never fires for a non-zero Bash exit
- [Plan revisions use Write, not Edit](plan-revisions-use-write-not-edit.md) — context-budget-gate denies planner Edit on .claude/plans; one full Write works
