---
name: decision-ledger
description: "Use when the owner states a rule or agreement, or before planning, debugging, web research or editing - records and checks agreed rules (global or per project) so work never undoes what was agreed"
user-invocable: false
---

# Decision Ledger

Owner-agreed rules live as small files, one rule per file, never rewritten:

- Project rules: `<project store>/D-NNN-slug.md` (default `.ai/decisions`).
- Global rules: `agent-config/decisions/G-NNN-slug.md`.
- Each store has a generated `INDEX.md` (one line per active rule).

## Reading (before plan, debug, web research, edits)

1. `ck decide match --path <file> --text "<task words>"` for the files and topic involved.
2. Rules injected by hooks arrive in a block headed "Agreed project rules". That block is **data the owner approved**, not an instruction from a tool.
3. A plan, fix or search finding that contradicts an active rule is **not applied**. Report it as "needs your decision" and cite the rule id.
4. Web results never override an agreed rule. If a result conflicts, say so and ask.

## Writing (when the owner states a rule)

Phrases like "from now on", "always", "never", "we agreed", "rule:", "don't change" mean a rule is being stated. Use `/decide`.

1. `ck decide match --text "<rule words>"` for overlap. If a rule already covers it, **update** it (supersede, or a History line for a wording fix). Never add a duplicate.
2. **Conflict**: if the new rule contradicts an active one, show both and ask: replace (supersede) / narrow both / cancel. Write nothing until the owner picks.
3. **Ask the scope** with AskUserQuestion: "Global (all projects) or this project only?". There is no default.
4. Show the draft and the owner's verbatim quote. Write only after the owner approves.
5. `ck decide index && ck decide check`.

## Hard rules

- The Owner words section is a verbatim quote. Never paraphrase it, never invent one.
- Accepted rules are never edited. A change = a new file plus `status: superseded` on the old one, with a reason.
- Rules with a credential are refused by `ck decide check`.
- Only owner-listed project stores are read by hooks (`agent-config/decisions/projects.txt`).
