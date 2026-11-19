---
description: "Record, update or look up an owner-agreed rule (global or this project) in the decision ledger"
argument-hint: "[the rule in the owner's words | list | check]"
model: sonnet
---

# Decide Command

Record or look up an agreed rule. Never add a duplicate, never rewrite an accepted rule.

## Task

Handle: $ARGUMENTS

## Mandatory Skills

- **decision-ledger** - the full read/write procedure and hard rules
- **golden-rule** - no code changes without explicit approval

## Procedure

1. If `$ARGUMENTS` is `list` or `check`, run `ck decide list` or `ck decide check` and stop.
2. Otherwise treat `$ARGUMENTS` as the owner's words. Run `ck decide match --text "<words>"`.
3. Overlap with an active rule: **update** it (`ck decide supersede <id> ...` with a reason, or `ck decide note <id> --reason ...` for a wording fix).
4. Contradiction with an active rule: show both, ask replace / narrow both / cancel with AskUserQuestion. Write nothing until answered.
5. New rule: ask the scope with AskUserQuestion ("Global (all projects) or this project only?"). No default.
6. Show the draft (title, one-line rule, guards, the verbatim quote) and wait for approval.
7. `ck decide add --scope <global|project> --title ... --rule ... --quote "<verbatim>" [--paths ...] [--keywords ...]`, then `ck decide index && ck decide check`.
8. Report the rule id and the file written. Commit nothing unless asked.
