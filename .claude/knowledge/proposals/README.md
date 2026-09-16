# Skill proposals (propose-only)

`knowledge-ledger.py propose` writes one file here when **3 or more `open` findings share
signature tokens**. Each file describes a *candidate* skill.

**Nothing here is a skill, and nothing here is loaded into context.** These files are never
read by an agent automatically, never injected at SessionStart, and never promoted
automatically. Promotion is a human step:

```bash
python3 .claude/operations/scripts/knowledge-ledger.py propose   # look at what it found
ck skill new <name>                                              # then decide
```

`ck skill new` charges the new description against the always-on context floor
(`scripts/check-context-floor.py`), so promoting a proposal has a measurable price — which
is the point. Writing into `.claude/skills/` without explicit user approval would violate
hard rule 5, so the proposer cannot do it.

Delete a proposal you have judged and rejected; it will not be rewritten while the file
exists.

## Patch proposals

`propose --patch <skill> --section Pitfalls|Verification --text "..."` writes
`patch-<skill>-<hash>.md` here: a proposed addition to a skill that already exists, rather
than a whole new one. Same gate, same reason. `/learn --promote patch-<skill>-<hash>`
applies it by building an ops.json that appends the text to the named section and running
the operations engine — after the user confirms in chat. Nothing edits a SKILL.md directly,
and the proposer cannot apply its own proposal.

## Proposals are local until promoted

`.gitignore` ignores `*.md` in this directory (this README excepted). A proposal is a
machine's opinion about a cluster of findings, not a reviewed artifact — it stays on the
machine that generated it. What gets committed is the thing a human decided to make of it:
a skill, a ledger entry, or nothing.
