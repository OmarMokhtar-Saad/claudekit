# Output Template

Silent mode output standards for all ClaudeKit agents. Controls message length, report format, and structured output.

---

## Token Limits

| Output Type | Max Tokens | When to Use |
|-------------|-----------|-------------|
| Completion message | 100 | Task finished, reporting result |
| Inline error | 50 | Quick error report |
| Handoff block | 200 | Passing work to next agent |
| Escalation | 150 | Requesting human intervention |

For anything beyond these limits, write a report file.

---

## Completion Message Format

The standard completion message. Must be under 100 tokens.

```
<AGENT> COMPLETE
================
Task: <one-line summary>
Status: Complete
Files: <count modified/created>
Deliverables: <list key outputs>
Verified: <one-line evidence>
```

Example:
```
PLANNER COMPLETE
================
Task: Add user authentication
Status: Complete
Files: 6 affected
Deliverables: plan.md, ops.json at .claude/plans/
Verified: ops.json valid, 6 operations match 6 plan steps
```

---

## Report File Format

When detailed output is needed, write to `.claude/reports/`.

**File naming:** `<agent>-<descriptor>-<YYYYMMDD>.md`

**Structure:**
```markdown
# <Agent> Report: <Title>

Date: <YYYY-MM-DD>
Agent: <name>
Task: <description>

## Summary
<2-3 sentence overview>

## Details
<full structured content>

## Evidence
<verification evidence>

## Next Steps
<what happens next in the pipeline>
```

Reference the report in your completion message:
```
Details: .claude/reports/verifier-auth-feature-20250315.md
```

---

## Error Output Format

For inline errors (under 50 tokens):
```
<AGENT> ERROR: <concise description>
File: <path>
Action: <what to do next>
```

For detailed errors, use a report file:
```
<AGENT> ERROR
=============
See: .claude/reports/<agent>-error-<date>.md
Summary: <one-line>
Escalating to: <agent or human>
```

---

## Progress Output (When Permitted)

Some workflows may enable progress output. When permitted, use this format:

```
[<agent>] Step <N>/<M>: <one-line description>
```

Example:
```
[verifier] Step 1/3: Running static analysis...
[verifier] Step 2/3: Executing test suite...
[verifier] Step 3/3: Measuring coverage...
```

Progress output is ONLY permitted when:
- The hook/command explicitly enables it
- The task has a `verbose: true` flag
- The workflow coordinator requests progress tracking

---

## Structured Data Output

When agents produce structured data (scores, checklists, tables), use consistent formatting:

### Score Bars
```
[████████████████████░░░░░] 82/100
```
- Full block: U+2588
- Light shade: U+2591
- Width: 25 characters
- Scale: 4 points per character

### Checklists
```
[x] Completed item
[ ] Pending item
[-] Skipped item
[!] Failed item
```

### Tables
```
| Column 1 | Column 2 | Column 3 |
|----------|----------|----------|
| value    | value    | value    |
```

### Key-Value Pairs
```
Key:     value
Another: value
Long:    value
```
Align values to the longest key.

---

## Forbidden Output Patterns

These patterns violate silent mode and must never appear:

- "Let me start by..." / "First, I'll..." / "I'm going to..."
- "Here's what I found:" (just present the findings)
- "Would you like me to..." / "Shall I..."
- "I think..." / "I believe..." / "In my opinion..."
- "Great!" / "Sure!" / "Absolutely!" (filler acknowledgments)
- Repeating the user's request back to them
- Explaining what a tool does before using it
- Summarizing what you just did in narrative form

**Instead:** Execute the work, produce structured output, done.
