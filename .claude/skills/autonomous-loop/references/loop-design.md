# Autonomous Loop -- loop design (merged from `autonomous-loops`)

Moved verbatim from SKILL.md, which keeps the use/do-not-use rules and the binding
iteration budget.

# Loop Design (merged from `autonomous-loops`)

The six phases above are one *instance* of an autonomous loop. This half is the
general contract every loop in the kit must satisfy, whatever its phases: when it
is allowed to run at all, how convergence is defined, which guards are mandatory,
and what it must report. Merged from the `autonomous-loops` skill, which is gone;
the name resolves here through the registry `renamed` alias map.

## Loop Architecture

```
[Start]
  |
  v
[Execute Iteration N]
  |
  v
[Evaluate: Convergence Criteria Met?]
  |
  +--YES--> [Report Success] --> [Stop]
  |
  +--NO, max_iterations not reached--> [Log Progress] --> [Execute Iteration N+1]
  |
  +--NO, max_iterations reached--> [Report Partial Results + Escalate]
```

---

## Convergence Criteria

Every loop MUST have at least one of:

### Hard Convergence
A deterministic check that is either true or false:
- All tests pass: `npm test` exits 0
- No lint errors: `flake8 src/` exits 0
- File exists and matches pattern
- API returns expected response

### Soft Convergence
A quality threshold:
- Coverage >= 80%
- Security score <= 2 high severity issues
- Performance benchmark within 10% of target

### Iteration Budget
A maximum number of attempts:
- `max_iterations: 5` (hard limit)
- After which: report progress and escalate

---

## Loop Design Patterns

### Pattern 1: Test-Fix Loop

Run tests → fix failures → repeat until all pass:

```
Loop:
  Run: npm test
  If all pass → DONE
  If failures:
    Analyze: Which tests failed?
    Fix: Apply targeted fix for first failure
    Continue loop

Max iterations: 5
On budget exceeded: Report remaining failures, ask for human input
```

### Pattern 2: Quality-Improve Loop

Measure quality → improve → repeat until threshold met:

```
Loop:
  Measure: Current quality score (lint, coverage, complexity)
  If score >= target → DONE
  If score < target:
    Identify: Lowest-scoring dimension
    Improve: Apply one targeted improvement
    Verify: Re-measure that dimension
    Continue loop

Max iterations: 10
On budget exceeded: Report current score vs. target, list remaining issues
```

### Pattern 3: Search-Refine Loop

Search for information → refine query based on results → repeat until answer found:

```
Loop:
  Search: Current query
  Evaluate: Did results answer the question?
  If yes → Synthesize and DONE
  If no:
    Analyze: What's missing from results?
    Refine: Narrow or pivot query
    Continue loop

Max iterations: 5
On budget exceeded: Provide best answer from collected data
```

---

