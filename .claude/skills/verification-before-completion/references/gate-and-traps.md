# Verification Before Completion -- gate diagram, traps, report template

Moved verbatim from SKILL.md; the rules they illustrate stay there.

## The Gate Function

Every completion claim must pass through this gate:

```
[IDENTIFY] What needs to be verified?
    |
    v
[RUN] Execute verification commands
    |
    v
[READ] Read the FULL output (not just exit code)
    |
    v
[VERIFY] Confirm the output matches expectations
    |
    v
[CLAIM] Only now may you claim success
```

## Rationalization Prevention

### The "Obviously Works" Trap

You see simple code and think: "This clearly works, no need to test."

**Reality:** The most confident claims of correctness are the most likely to be wrong. Confidence is not evidence.

### The "Same as Before" Trap

You think: "I made the same kind of change earlier and it worked."

**Reality:** Context matters. The same pattern in a different file may have different dependencies, edge cases, or interactions.

### The "Tests Are Slow" Trap

You think: "Running the full suite takes too long, I'll skip it."

**Reality:** Run at minimum the targeted tests. A partial verification is better than none. But note in your report that you ran a subset.

### The "I Checked the Diff" Trap

You think: "The diff looks correct, so it works."

**Reality:** Diffs show what changed, not whether the change is correct. Only execution reveals runtime behavior.

---

## Verification Report Format

When reporting verification results:

```
## Verification Results

### Command Run
[exact command]

### Output Summary
- Tests: [X passed, Y failed, Z skipped]
- Build: [SUCCESS / FAILED]
- Warnings: [count]

### Full Output
[include relevant output, not just summary]

### Verdict
[PASS / FAIL with explanation]
```

