---
name: request-shaping
description: "Use when a raw request must be normalized before routing - extracts the six dimensions the pipeline routes on"
disable-model-invocation: true
argument-hint: "<raw-request>"
---

# Request Shaping

## Core Principle

**Every other prompt asset in this kit is output-side.** `writing-plans`, `writing-skills`,
`prompt-evaluation` and `token-optimization` all improve text *we* emit. This one is
input-side: it normalizes the request *before* a tier is chosen or an agent is spawned.

An unshaped request forces every downstream consumer to re-derive the same facts. The
planner re-greps for scope, the tier gets guessed from a sentence, and the verifier has no
stated pass condition. Shaping once removes that repeated work.

---

## The Six Dimensions

Extract exactly these. They are the fields the pipeline actually consumes -- not a generic
prompt-quality checklist.

| # | Dimension | Question it answers | Feeds |
|---|---|---|---|
| 1 | **Task verb** | add / fix / refactor / explain / audit / release? | agent selection |
| 2 | **Scope** | which concrete files, dirs, globs? | `ops.json` targets |
| 3 | **Constraints** | stdlib-only, bash 3.2, no new deps, protected files? | planner guardrails |
| 4 | **Success criteria** | which command proves it worked? | DoD gate, verifier |
| 5 | **Blast-radius tier** | 1, 2 or 3 per CLAUDE.md? | pipeline routing |
| 6 | **Evidence needed** | what must be read before anything is written? | `context-first-workflow` |

### Dimension 5 is derived, never asked

Never ask the user for a tier. Derive it from dimensions 2 and 3:

- **Tier 1** -- single file, no public API / security / schema / architecture surface.
- **Tier 2** -- multiple files, no security or schema surface.
- **Tier 3** -- security-relevant, DB migrations, >15 ops, or >2 phases.

State the tier with its reason. If dimensions 2 and 3 are too thin to derive a tier, that
is a Blocking gap in *those* dimensions -- ask about scope, not about tiers.

---

## Missing-Dimension Protocol

Reuse the severity ladder from the **clarify** skill verbatim. Do not invent a second one.

| Severity | Meaning | Action here |
|---|---|---|
| **Blocking** | Cannot derive the dimension at all; any guess could be wrong in a way that wastes the work | Ask |
| **Risky** | Derivable, but a wrong reading costs real effort | State as an assumption |
| **Minor** | Several readings, all reasonable | State as an assumption |

**Only Blocking gaps earn a question. Maximum three questions, asked in one round via
`AskUserQuestion`.** A fourth question means the request needed a spec, not shaping --
say so and point at `/specify`.

Everything Risky or Minor goes in the `ASSUMED:` line. An assumption stated out loud is
cheaper than a question, and it stays visible for the user to correct.

---

## Output: the Shaped Request Block

Emit exactly this block. The fixed shape is the contract -- a planner reads it without
re-parsing prose, and the field names are asserted by `tests/test_request_shaping.py`.

```
TASK: <verb> <object>
SCOPE: <paths>
TIER: <1|2|3> (<reason>)
CONSTRAINTS: <list, or "none beyond repo defaults">
DONE WHEN: <command that must pass>
READ FIRST: <paths>
ASSUMED: <Risky/Minor calls made without asking, or "nothing">
```

Every field is mandatory. A field with nothing to say carries an explicit `none` or
`nothing` -- never an empty value, which reads as an oversight rather than a decision.

---

## Where Shaping Stops

Shaping produces the block and **names** the next step. It never takes it.

| Tier | Next step to name |
|---|---|
| 1 | minimal `ops.json` -> validate -> execute -> compile-verify |
| 2 | `/plan` (planner + `ops.json`) |
| 3 | `/plan` then `/review` -- full pipeline |

Stopping here is what keeps the Golden Rule intact: shaping a request is never itself a
code change, so it needs no approval, and the approval gate stays exactly where it was.

---

## Anti-Patterns

| Anti-pattern | Why it fails |
|---|---|
| Asking about all six dimensions | Six questions for a request that needed zero; the ladder exists to prevent this |
| Asking for the tier | The user should not have to know this kit's routing table |
| Emitting prose instead of the block | Downstream consumers re-parse, which is the cost shaping exists to remove |
| Shaping, then immediately implementing | Skips the approval gate that the stop point protects |
| Inventing dimensions seven and eight | Nothing downstream reads them; they are pure token cost |
