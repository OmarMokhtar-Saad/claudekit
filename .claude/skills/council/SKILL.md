---
name: council
description: "Use when facing hard decisions with multiple credible paths — runs 4 adversarial perspectives (Architect, Skeptic, Pragmatist, Critic) in parallel to surface real tradeoffs"
disable-model-invocation: true
---

# Council

## Purpose

Structure multi-perspective decision-making under ambiguity. When you have multiple credible options and no obvious winner, the Council forces each option to be challenged from four distinct angles simultaneously.

**Use when:**
- Multiple viable approaches with real tradeoffs (monolith vs. microservices, feature flag vs. full rollout, ship now vs. hold)
- Go/no-go calls that benefit from adversarial challenge
- You want a second opinion that doesn't just mirror your existing reasoning
- Architecture decisions with long-term implications

**Do NOT use for:**
- Code review (use `differential-security-review` or a language reviewer)
- Implementation planning (use `blueprint` or `/plan`)
- Architecture design (use planner + reviewer pipeline)
- Factual questions with a clear answer
- Obvious execution tasks

---

## The Four Roles

Each role has a fixed mandate — they CANNOT switch perspectives mid-discussion:

| Role | Mandate | Primary Lens |
|------|---------|-------------|
| **Architect** | Correctness, maintainability, long-term implications | "Will this hold up at 10x scale?" |
| **Skeptic** | Challenge premises, find simplifications, break assumptions | "Do we actually need this?" |
| **Pragmatist** | Shipping speed, user impact, operational reality | "What ships value fastest?" |
| **Critic** | Edge cases, downside risk, failure modes | "How does this break?" |

---

## 6-Step Workflow

### Step 1: Extract the Real Question

Don't accept the question as stated. Clarify:

```
Decision: [What are we actually choosing between?]
Constraints: [Non-negotiable limits: time, budget, team size, existing contracts]
Success criteria: [How will we know the right choice was made in 6 months?]
Context: [Why is this decision hard? What makes the options comparable?]
```

### Step 2: Gather Compact Context

Read only what's necessary — relevant files, snippets, architecture docs. Do NOT load the full conversation history into each subagent (anti-anchoring rule).

### Step 3: Form Architect Position First

Before launching parallel subagents, establish the Architect's position. This prevents the synthesis from just mirroring external inputs:

```
Architect initial position:
- Position: [one sentence]
- Top 3 reasons: [bullets]
- Main risk: [one sentence]
```

### Step 4: Launch 3 Parallel Subagents

Spawn Skeptic, Pragmatist, and Critic simultaneously. Each gets:
- The decision question (from Step 1)
- Compact context (from Step 2)
- Their role instructions (below)
- NO conversation history

**Subagent prompt shape:**

```
You are the [ROLE] in a council decision review.
Your mandate: [role mandate]

Decision: [extracted question]
Context: [compact context]

Respond with ONLY:
**Position:** [1-2 sentences — your recommendation]
**Reasoning:** [3 bullets — strongest reasons]
**Risk:** [biggest risk if your position is ignored]
**Surprise:** [1 thing others may have missed]

Under 300 words total. No preamble.
```

### Step 5: Synthesize with Bias Guardrails

Combine all four positions into a verdict. Apply these guardrails:

1. **Don't dismiss external views without explanation** — if you disagree with a role, say why explicitly
2. **Call out when an external view changed your recommendation** — intellectual honesty builds trust
3. **Always include the strongest dissent** — even if you're going with the majority view
4. **Check if the premise was challenged** — the Skeptic may have revealed the question was wrong

### Step 6: Present Compact Verdict

Format for scanning on a small screen:

```markdown
## Council: [Short Decision Title]

**Architect:** [position] — [reason in one sentence]
**Skeptic:** [position] — [reason in one sentence]
**Pragmatist:** [position] — [reason in one sentence]
**Critic:** [position] — [reason in one sentence]

### Verdict
- **Consensus:** [where 3+ roles agree, or "No consensus"]
- **Strongest dissent:** [which role disagrees and why]
- **Premise check:** [did the Skeptic reveal a false assumption?]
- **Recommendation:** [final recommendation + confidence: HIGH/MEDIUM/LOW]
- **Open questions:** [what you'd need to increase confidence]
```

---

## Anti-Patterns

| Anti-Pattern | Why It Fails |
|-------------|-------------|
| Feeding subagents full conversation history | Anchors them to the existing framing — defeats the purpose |
| Using Council for code review | Too heavyweight; use specialized reviewers |
| Hiding disagreement in the verdict | The point is to surface the hard tradeoffs, not smooth them over |
| Auto-writing notes for every decision | Only persist when the decision changes something real |
| Running roles sequentially | They MUST be parallel to avoid anchoring |

---

## When Consensus Doesn't Exist

If roles are split 2-2 or all different:

1. **Identify the core disagreement** — usually one axis (e.g., speed vs. maintainability)
2. **Reframe as a values question** — "This decision is really about whether we prioritize X or Y"
3. **Propose a time-bounded experiment** — "Ship option A for 30 days, measure [metric], revisit"
4. **Escalate to human decision** — present the split clearly: "The council is deadlocked on [issue]. Here are the two camps..."

---

## Example Application

**Decision:** "Should we add Redis caching before launch or ship without it?"

**Architect:** Ship without it — premature optimization. Complexity before we know our bottlenecks.
**Skeptic:** Do we even have a performance problem? What does profiling show?
**Pragmatist:** Ship without it, add after first traffic spike — maximum shipping velocity now.
**Critic:** Risk: If launch goes viral, we have no quick cache option. Redis setup in prod under pressure is dangerous.

**Verdict:**
- Consensus: Ship without caching (3/4)
- Strongest dissent: Critic — deployment under pressure is the real risk
- Recommendation: Ship without Redis, but have a documented runbook for adding it within 2 hours if needed. **HIGH confidence.**
