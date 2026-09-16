---
description: "Review and promote what this session learned: memory candidates and skill proposals, one human decision each"
argument-hint: "[--list|--show <name>|--promote <name>|--reject <name>]"
model: sonnet
---

# Learn Command

Review what this session's machinery already drafted, and promote the parts worth keeping.
Nothing here writes on its own: every write below is one explicit human decision, because a
memory entry is auto-injected into a system prompt and a skill is charged against the
always-on context floor.

## Mandatory Skills

- **continuous-learning** - what the three real triggers are, and what each one writes

## Task

Manage pending learning: $ARGUMENTS

`LEDGER=python3 .claude/operations/scripts/knowledge-ledger.py` in every command below.

---

## What is pending, and who wrote it

| Pending thing | Written by | Lives in |
|---|---|---|
| Memory candidate | `$LEDGER distill --agent <a> --inbox` (demanded at Stop) | `.claude/agent-memory/<agent>/_inbox/<name>.md` |
| Skill proposal | `$LEDGER propose` (3+ open findings share tokens) | `.claude/knowledge/proposals/<name>.md` |
| Skill patch proposal | `$LEDGER propose --patch <skill> --section ... --text ...` | `.claude/knowledge/proposals/patch-<skill>-<hash>.md` |

---

## Workflows

### `/learn --list`

```bash
$LEDGER inbox
```

Prints every pending candidate (with its agent) and every pending proposal. Nothing else.

### `/learn --show <name>`

Read the file for `<name>` from the table above and show it verbatim. Do not summarise it
away: the point of the review is that a human sees the exact text that would be promoted.

### `/learn --promote <name>`

Three cases, decided by what `<name>` is.

**1. A memory candidate.** Run:

```bash
$LEDGER inbox --accept "$NAME"
```

This moves the file out of `_inbox/` into `.claude/agent-memory/<agent>/` and appends its
`index:` line to that agent's `MEMORY.md`. It REFUSES when the result would cross the
200-line truncation cliff - run `$LEDGER consolidate --agent <agent>` and merge first.

**2. A skill proposal** (`.claude/knowledge/proposals/<name>.md`, no `patch-` prefix).
Show the proposal, then ASK the user, in chat, whether to create the skill. Only after an
explicit yes:

```bash
ck skill new "$SKILL_ID" --description "$ONE_LINE"
```

Never run it on your own initiative. Creating a skill spends always-on context budget, and
hard rule 5 puts every write into `.claude/skills/` behind a human.

**3. A skill patch proposal** (`patch-<skill>-<hash>.md`). Never edit the SKILL.md
directly. Show the proposal, ask the user to confirm, then write an ops config that
appends the proposed text to the named section and run the operations engine:

```bash
python3 .claude/operations/scripts/validate-config-json.py ".claude/plans/ops-$NAME.json"
python3 .claude/operations/scripts/execute-json-ops.py ".claude/plans/ops-$NAME.json"
```

The ops config is one `code_edit` with an `add_after` anchored on the section heading the
proposal names. Delete the proposal file once it is applied.

### `/learn --reject <name>`

```bash
$LEDGER inbox --reject "$NAME"                 # memory candidate
rm ".claude/knowledge/proposals/$NAME.md"      # proposal or patch proposal
```

Rejecting is a real outcome, not a failure. A deleted proposal is not rewritten while the
finding cluster is unchanged, and a rejected candidate can always be re-distilled.

---

## Output Format

```
## Pending learning

Memory candidates: N
  - <name> (<agent>) - <one-line index text>
Skill proposals: N
  - <name> - <cluster summary>
Patch proposals: N
  - patch-<skill>-<hash> - section <Section>

Promoted this run: <names, or "none">
Rejected this run: <names, or "none">
```

---

## Notes

- Everything here is project-local. There is no `~/.claude/skills/learned/` tier and never
  was one - the command used to describe a directory that does not exist.
- Candidates and proposals are gitignored. What gets committed is what a human promoted.
- `$LEDGER inbox` with no flags is the honest status check: if it prints nothing, the
  session left nothing worth keeping, which is a valid answer.
