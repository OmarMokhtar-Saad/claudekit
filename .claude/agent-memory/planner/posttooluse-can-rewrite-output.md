---
name: posttooluse-can-rewrite-output
description: PostToolUse can replace tool output via hookSpecificOutput.updatedToolOutput, and never fires for a Bash call that exits non-zero
metadata:
  type: project
---

A `PostToolUse` hook may return `hookSpecificOutput.updatedToolOutput`, which "Replaces the
tool output before it is sent to the model" (works for all tools; `updatedMCPToolOutput` is
the MCP-only legacy field). The host validates the value against the tool's output schema and
logs "using original output" on a mismatch — host-level fail-soft. Hooks run **in parallel on
the ORIGINAL output** and rewrites resolve **last-write-wins**, so only one rewriter may
exist and nobody may return an identity rewrite.

`PostToolUseFailure` has exactly one field, `additionalContext` — no rewrite field. And
PostToolUse does not fire at all for a Bash call that exits non-zero (verified 2026-09-16: a
deliberate `false; exit 3` left no `[post-tool-use]` line in `.claude/hooks/hooks.log` while
neighbouring successful calls did).

Also: `bashOutputMaxChars` defaults to 30,000 chars for **successful** Bash output; past that
the output goes to a file and Claude gets a **head**-biased preview plus the path.

**Why:** established while planning adoption item B1 (`.claude/plans/plan-output-filters.md`).
Item A1 died because its host mechanism did not exist; this one was verified against the
2.1.273 binary before a line of the plan was written.

**How to apply:** any plan that proposes filtering, redacting or summarising tool output
hangs off this field — and gets requirement "never strip stderr on failure" for free, because
the host never offers the hook a failed command. Re-verify against the installed binary
before relying on it; these are undocumented internals.

Related: [[a-green-check-can-measure-nothing]].
