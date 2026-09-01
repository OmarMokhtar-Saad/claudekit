---
description: "Shape a raw request into the six dimensions the pipeline routes on, then name the next step"
argument-hint: "<raw request>"
---

# Ask Command

Normalize a raw request into a Shaped Request block before any tier is chosen or agent
spawned. Emits the block, names the next command, and **never runs it** -- `/ask` is not
a code change and never triggers one.

## Task

Shape this request: $ARGUMENTS

## Mandatory Skills

- **request-shaping** - the six dimensions, the severity ladder, the block format
- **clarify** - Blocking / Risky / Minor definitions
- **context-first-workflow** - what must be read before anything is written

## Workflow

1. **Extract** the six dimensions; derive the tier from scope and constraints.
   Never ask the user for a tier -- they need not know this kit's routing table.
   Explore only as far as extraction requires; auditing is the next command's job.
2. **Triage** every gap you could not extract per the **clarify** ladder. Blocking ->
   ask. Risky/Minor -> resolve with your best reading and record it under `ASSUMED:`.
3. **Ask once.** At most three questions, all in a single `AskUserQuestion` round. A
   second round means step 2 under-triaged; a fourth question means this needed a
   specification -- say so and point at `/specify`.
4. **Emit** the Shaped Request block exactly as **request-shaping** defines it. Every
   field present; `none` or `nothing` where there is nothing to say.
5. **Name** the next step and stop: Tier 1 -> `ops.json` -> `validate-config-json.py`
   -> `/implement`; Tier 2 -> `/plan`; Tier 3 -> `/plan` then `/review`. Do not run it.

## Flags

Honours **command-flags**: `--depth=1` (no exploration), `--format=json` (the block as
JSON keyed by its seven field names).
