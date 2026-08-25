---
name: verification-gap-lens
description: Use when judging whether tests would actually catch a regression in a code change — four verification-gap shapes, the Demonstration technique, and proving a check binds by mutating the shipped artifact and reading the failure.
user-invocable: false
allowed-tools: Read, Grep, Glob, Bash
---

# Verification-Gap Lens

Adapted from SHAFT_ENGINE `chaos-engine/references/verification-gap-lens.md` (MIT), itself
adapted from bmad-method `src/core-skills/bmad-review/references/lens-verification-gap.md`
(MIT). Trimmed and reworded to ClaudeKit's scale; the attribution chain is preserved
deliberately — do not strip it.

## Core Principle

**One question, and only this one:** if the behavior this change is supposed to produce broke
where it is actually used, would a test fail?

This is not a general correctness hunt — the review dimensions cover that. This lens measures
verification coverage only. Its output is a list of places where behavior could break and
nothing would go red. An empty list is a valid, complete result; say so plainly rather than
padding with low-confidence noise.

---

## The four gap shapes

1. **Regression gap.** The changed code regresses where it is used, and no test covering that
   use would fail.
2. **Missing-adoption gap.** A site that should now use the new behavior does not — it handles
   the same case its own way, or not at all — and no test flags the omission. This qualifies
   ONLY when there is a real supersession signal (the change's stated intent, a replaced
   sibling site, a deleted duplicate) **and** the local site shares the same observable
   contract. Without both, it is a refactor suggestion, not a gap. Say which it is.
3. **Broken-verification gap.** A test appears to cover the changed behavior but would not
   catch a regression: skipped, flaky, not run in the normal path (wrong marker, excluded
   directory, opt-in job), or too weak to observe the change — mock-only, snapshot-only, or a
   success/no-throw assertion.
4. **Unbound-check gap.** The change adds or edits a check, guard, pin, gate or metric that
   would still pass with the thing it protects removed. Three ways it happens:
   - the test declares its own copy of a pattern, threshold or clause that the shipped artifact
     owns, so it verifies the copy and not the artifact;
   - a metric whose input is absent reports that absence as a value (zero findings because
     nothing ran looks identical to zero findings because nothing is wrong);
   - the fix's own mechanism is unguarded, so reverting the fix leaves the suite green.

   In this repo these land as: a hook test that re-declares the deny pattern instead of
   invoking the hook; a gate whose budget table is duplicated in the test; a coverage number
   computed over a file set that silently became empty.

---

## The Demonstration technique

For each candidate site, name the **smallest realistic regression a real consumer would
observe**: invert the branch, drop the default, omit the field, return the old error code,
skip the call, let the guard fall through.

- If you cannot name one, drop the path. Untested downstream code that nothing would actually
  break is not a finding.
- If you can, find the relevant test and ask: would the Demonstration make an assertion fail?
  Yes -> verified, no finding. No -> that is the gap; report it with the shape.

---

## Proving a check binds (your own diff)

Imagining the Demonstration is correct for code you are *reviewing*. For a check in your **own
diff** it is not, because the mutation is free and revertible:

```
apply the mutation to the SHIPPED artifact -> run the check -> read the failure -> revert
```

Mutate the shipped artifact, never a fixture. A green run after mutating the fixture proves
only that the fixture moved.

**Weakening counts as a mutation.** A rule survives deletion and dies by addition: appending
"unless time is short" leaves every pinned word in place while gutting the rule, so mutate by
qualifying as well as by removing. Make the metric move; a metric that cannot report failure is
reporting its own absence.

---

## Evidence rules (non-negotiable)

- Read a test before claiming what it covers, runs, asserts, or misses — and re-open it before
  writing the finding rather than reporting from memory of a glance earlier in the review.
- Before claiming no test exists, search the repository by symbol and by import reference.
  Expected file locations alone are not enough.
- A green build banner proves nothing when the runner writes structured reports. Read the
  report counts before calling anything green.
- State what you actually checked and how far you looked ("none of the tests I read cover
  this"). An ungrounded finding is dropped, not softened.
- Do not assign severity or priority here — the reviewing agent's severity table owns that.

---

## Trimmed review sequence

1. **Screen for behavioral change.** Formatting, renames, type-only, pure docs -> zero
   findings, stop and say so.
2. **Name what changed:** output, side effect, branch, error path, schema shape, default,
   contract.
3. **Trace consumers:** direct callers, registered entry points, contract consumers. Stop at
   the nearest boundary where a test would fail, or where the next hop is guesswork.
4. **Qualify each consumer with the Demonstration, then read its test.**

---

## Finding shape

```
location:             <path>:<line>
trigger_condition:    <the gap, one line>
potential_consequence:<what ships wrong, and why the tests you read would not catch it>
gap_shape:            regression | missing-adoption | broken-verification | unbound-check | other
evidence:             <what you actually read or ran, with file:line>
```

`other` is only for a genuine problem noticed in passing — it is not a bucket for hunches.
When the consuming agent uses recurrence classes, this lens' `gap_shape` maps onto the
`Class` field (see `.ai/REVIEW_GUIDE.md`).

---

## Anti-Patterns (NEVER DO THESE)

- NEVER claim a test covers something you did not open.
- NEVER report a gap you cannot attach a Demonstration to.
- NEVER call a self-written check verified without mutating the shipped artifact and reading
  the failure.
- NEVER treat "the build was green" as evidence when the runner writes a report file.
- NEVER promote a refactor suggestion to a missing-adoption gap without a supersession signal
  AND a shared observable contract.
