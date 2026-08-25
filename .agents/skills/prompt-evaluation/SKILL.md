---
name: prompt-evaluation
description: "Use when iterating on a prompt — isolated judges, one per criterion, over a versioned eval set. Exploratory only; eval-harness stays the CI gate."
user-invocable: true
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
---

# Prompt Evaluation

**Reimplementation, not a port.** The method below is reimplemented from the approach
published by `46ki75/prompt-evaluation-claude-code`, whose license is unstated — so nothing
is copied from it. Analysis: `.Codex/reports/research/behisecc-and-prompt-evaluation.md`.

**Where this sits.** This is the **exploratory** stage: fast, cheap, run while you are still
changing the prompt. It does **not** gate CI and keeps no production baseline. When a change
proves out here, hand it downstream to `eval-harness`, which is the CI-gated regression
baseline. Using this as a merge gate is the mistake it is designed to avoid.

---

## The Rule That Makes It Work

> **One isolated judge per criterion.** A compound rubric produces halo effects — a judge
> scoring "accuracy, tone and completeness" together lets a strong showing on one drag the
> others up, and you can no longer tell which criterion your change actually moved.

Two criteria, two judges, two separate calls, each seeing only its own criterion. Isolation
is what buys you an attributable signal.

**Reasoning before verdict, always.** A judge that emits a verdict first rationalises it
afterwards. Force the order in the output schema so the reasoning is doing work:

```json
{"reasoning": "<why, first>", "verdict": "pass|fail", "confidence": "high|medium|low"}
```

---

## The Loop

### 1. State the criteria, separately

Write each criterion so a judge can answer it without consulting any other. If a criterion
needs another to be interpretable, it is one criterion, not two.

```
C1  factuality  — every claim traceable to the supplied context, no invention
C2  instruction — every explicit constraint in the prompt is obeyed
C3  format      — output parses under the declared schema
```

C3 above should not be a judge at all — see "Do not judge what you can assert" below.

### 2. Build a small, real eval set

**10–30 cases.** Fewer will not separate signal from noise; more slows the loop until you
stop running it.

Source them from **real failures** wherever possible — a case someone actually hit is worth
ten invented ones. Include the boring middle, not only edge cases: a prompt that aces the
adversarial set and fumbles typical input is a worse prompt.

```jsonl
{"id": "fact-01", "input": "...", "context": "...", "note": "from incident 2026-08-02"}
{"id": "instr-04", "input": "...", "constraints": ["cite every source", "under 200 words"]}
```

### 3. Pick the grading method per criterion

| Method | Use when | Watch out for |
|---|---|---|
| **Reference match** | there is one right answer (exact/fuzzy) | brittle to harmless phrasing changes |
| **Binary judge** | open-ended, and "acceptable" is decidable | must emit reasoning first |
| **Pairwise A/B** | comparing two candidate prompts | position bias — see below |

**Pairwise position bias is real and large.** Judges favour whichever candidate they see
first. Run every pair **twice with the positions swapped**, and count a win only when both
orderings agree. Disagreement is a tie, not a coin flip:

```
A-then-B: A wins    B-then-A: A wins   →  A wins
A-then-B: A wins    B-then-A: B wins   →  tie (position bias, not signal)
```

### 4. Run judges in isolation

Each judge gets: one criterion, one candidate output, and the case's context. **Not** the
other judges' verdicts, not the other criteria, not the prompt's own claims about itself,
and not which candidate is the incumbent.

Spawn them as separate subagents with a structured-output schema so verdicts come back
parseable rather than as prose you re-parse later.

### 5. Version the artifacts orthogonally

The eval set and the prompt change independently, so version them independently — otherwise
you cannot tell whether a score moved because the prompt improved or because the set changed.

```
evals/
  eval-set-v3.jsonl              # the data
  prompts/summarize-v7.md        # the candidate
  runs/2026-08-25-v7-vs-v6/
    outputs/                     # candidate outputs per case
    verdicts/                    # one file per (case, criterion) judge
    synthesis.md                 # what moved, what did not, what to try next
```

A run directory that records **which set version** and **which prompt version** produced it
is what makes last month's number comparable to today's.

### 6. Synthesise per criterion, never as one number

Report each criterion separately with its failing case ids. A single blended score is exactly
the halo effect the isolation rule exists to prevent, reassembled at the last step.

```
C1 factuality   14/20   fails: fact-03, fact-09, fact-11, fact-17, fact-19, fact-20
C2 instruction  19/20   fails: instr-08
C3 format       20/20   (asserted, not judged)

→ C1 is the only criterion that moved (was 11/20). C2's single failure is the 200-word
  constraint on long input — a prompt fix, not a judging artifact.
```

---

## Do Not Judge What You Can Assert

An LLM judge is the expensive, noisy option. Anything checkable in code should be checked in
code — schema validity, required fields, length limits, forbidden strings, citation
resolvability, valid JSON. Reserve judges for what genuinely needs semantic reading.

```bash
jq -e '.summary and (.sources | length > 0)' out.json   # assertion, not a judge
```

---

## Anti-Patterns

| Anti-pattern | Why it costs | Instead |
|---|---|---|
| One judge, compound rubric | Halo effect; no attributable signal | One isolated judge per criterion |
| Verdict before reasoning | Rationalisation, not evaluation | Force reasoning first in the schema |
| Single-direction pairwise | Position bias reads as a result | Swap positions; agreement or tie |
| Eval set edited alongside the prompt | Cannot attribute a score change | Version the set and prompt separately |
| Judging format/schema | Pays LLM tokens for what `jq` decides | Assert it |
| Gating CI on this | It is exploratory and unversioned against production | Hand off to `eval-harness` |
| Eval set of only edge cases | Passes the hard set, fails typical input | Include the boring middle |
