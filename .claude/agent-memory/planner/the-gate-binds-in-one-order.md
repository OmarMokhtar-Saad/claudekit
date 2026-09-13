---
name: the-gate-binds-in-one-order
description: In claudekit, stamp the ops baseline before recording a verdict, and record from the reviewer's verbatim reply
metadata:
  type: feedback
---

Order is **stamp baseline → record verdict → execute**. Never stamp after.

**Why:** `validate-config-json.py --stamp-baseline` rewrites the config, which changes the hash the verdict binds to. Recording first therefore deadlocks execution and looks like a gate bug rather than an ordering mistake.

Two adjacent traps confirmed the same session:
- A reviewer is never asked for the anchored `=== REVIEW ===` block unless you ask explicitly. Without it `review-record.py --from-review` parses nothing and no verdict binds. Ask for it **in the reply**, not only in a file.
- An executed ops.json left in `.claude/plans/` fails `test_queued_ops_configs_validate_against_head`, because its anchors are consumed. Archive it under `archive/` with a README row as part of finishing, not later.

**How to apply:** never compose the verdict block yourself — that is a gate bypass, not a shortcut. Re-ask.

Related: [[a-green-check-can-measure-nothing]].
