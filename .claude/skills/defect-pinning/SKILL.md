---
name: defect-pinning
description: "Use when a defect is confirmed but not yet fixed — pin it to a quarantined reproducing test so it cannot be re-found, re-argued, or silently fixed."
user-invocable: false
allowed-tools: Read, Grep, Glob, Bash
---

# Defect Pinning

**A confirmed defect you cannot fix today still has to stop costing you.** Without a pin it
gets re-discovered next pass, re-argued from scratch, and — the expensive one — silently
fixed by someone who never learns they fixed it, so nothing guards the fix.

A pin is a **reproducing test that fails today**, quarantined so it does not redden the merge
gate, carrying the whole finding in its own quarantine message.

This is the protocol half of `whitebox-invariant-testing`, but it is deliberately separate:
it applies to **any** confirmed defect regardless of how it was found — a production
incident, a code review, a user report — not only ones an invariant sweep produced.

---

## The Protocol

### 1. Pin it to the exact failure, not to "it's broken"

The test asserts the behaviour the system's **own contract** promises, and fails against
today's code. Not a snapshot of current (wrong) behaviour — that pins the bug in place.

```kotlin
@Ignore("SDK BUG P1 (fail-open provenance): a FAILED read still opens the fabrication gate — " +
        "start() records the executor's ERROR callout via recordRead (AgentTurnEngine.kt:272-277, " +
        "same hole on the detour path :232-236), so hasFetchedRead() claims data arrived when the " +
        "transport failed. See SDK-DEFECTS.md #1.")
@Test
fun d1_a_failed_read_must_not_open_the_provenance_gate() = runTest {
    val h = AgentHarness(failOn = { p -> if ("labs/orders" in p) RuntimeException("5xx") else null })
    h.engine.beginTurn()
    h.engine.start("lab_results")

    assertTrue(h.called("labs/orders"), "fixture drift: the read never reached the endpoint")
    assertFalse(h.engine.hasFetchedRead(setOf("lab_results")))
}
```

Four things that message must carry, because it is what a maintainer sees first:

| Part | Why |
|---|---|
| Severity + one-line class | lets someone triage without opening the report |
| The **file:line** in the SUT | turns "somewhere in the engine" into a diff |
| Every known instance of the hole | the detour path above was a second site; fixing one leaves the bug |
| A pointer to the full analysis | the message is an index, not the report |

Name tests so the quarantine list reads as a defect register: `d<N>_<the invariant, in
words>`. `d1_a_failed_read_must_not_open_the_provenance_gate` says what is wrong; `testBug1`
says nothing.

### 2. Quarantine so the gate stays green

A red merge gate that is *expected* to be red trains everyone to ignore it, and then it stops
catching real regressions. Mark pins as skipped, in the idiom of your runner:

| Stack | Mark |
|---|---|
| Kotlin/JUnit | `@Ignore("...")` |
| Java/JUnit 5 | `@Disabled("...")` |
| pytest | `@pytest.mark.xfail(strict=True, reason="...")` |
| Go | `t.Skip("...")` |
| Jest/Vitest | `test.failing("...")` or `test.skip` |

`xfail(strict=True)` and `test.failing` are the better shape where available: they fail if
the test **passes**, so a fix cannot land unnoticed. With plain skip marks you get that from
step 4 instead.

### 3. One quarantine home

Every pin lives in one dedicated file — `KnownDefectsTest`, `known_defects_test.py`,
whatever your convention names it. Not scattered next to the feature tests.

The reason is that the file becomes the **register**: its length is your outstanding-defect
count, its diff is your progress, and a reviewer can read the whole quarantine in one place
rather than grepping for skip marks. Give the file a header comment that states the protocol
so the next person does not have to infer it:

```kotlin
/**
 * CONFIRMED defects — one RED test per defect. Every test asserts the behaviour the system's
 * own contract (doc comments / spec / recipe data) promises, and fails against today's code.
 *
 * Each is @Ignore'd with a one-line summary so the merge gate stays green; the day a defect
 * is fixed, DROP its @Ignore — the test becomes the regression proof. Full analysis: <report>.
 */
```

### 4. Re-run every pin live on every SUT change — and restore verbatim

This is the step that makes pinning pay, and the one that gets skipped.

```bash
# Un-quarantine everything, run it, put it back EXACTLY as it was.
# `find`, not `src/test/**/...`: bash 3.2 (the macOS default) has no globstar, so `**`
# collapses to one level and silently matches nothing at a deeper path.
test -z "$(git status --porcelain)" || { echo "dirty tree — commit or stash first"; exit 1; }
# -print0/xargs -0, not $(find ...): an unquoted expansion word-splits on a path
# containing a space, and the restore would then miss the file it just rewrote.
find src/test -name 'KnownDefectsTest.kt' -print0 \
  | xargs -0 sed -i.bak -E 's|^([[:space:]]*)@Ignore\(|\1// PIN-CHECK @Ignore(|'
./gradlew test --tests '*KnownDefectsTest*' || true      # failures are EXPECTED here
find src/test -name 'KnownDefectsTest.kt.bak' -print0 \
  | while IFS= read -r -d '' b; do mv "$b" "${b%.bak}"; done   # verbatim restore
git diff --exit-code -- src/test/   # MUST be empty; if not, the restore was not verbatim
```

Read the result three ways:

- **Still fails, same message** — the defect is alive. Nothing to do.
- **Now passes** — someone fixed it. **Drop the quarantine mark permanently**: the pin is now
  the regression proof, and it belongs in the green suite. Record which SUT change fixed it.
- **Fails differently** — the defect changed shape, or your repro drifted. Re-triage before
  touching the mark; a pin asserting a stale mechanism is worse than none.

That last case is why the restore must be **verbatim**. A "cleanup" that rewrites the
quarantine messages loses the file:line evidence that made the pin actionable.

---

## The Companion Coverage Map

A defect register tells you what is broken. It does not tell you **what you have not looked
at** — and that is what decides where the next pass starts.

Keep a companion map of every attack surface you can name, each with one of five states:

| Mark | Meaning |
|---|---|
| ✅ | covered by a green test — a regression here fails the gate |
| 🔴 | covered by a RED pin — a confirmed defect, quarantined |
| ⬜ | **gap** — reachable from this harness today, simply not written yet |
| 🔧 | gap, but needs a harness affordance first (name the affordance in the row) |
| ⛔ | not reachable from this harness — device, non-determinism, or visibility |

The two middle states are the ones that earn the map. ⬜ is a worklist you can start on
this afternoon. 🔧 is a *different* job — build the seam first — and separating them stops
the next pass from repeatedly rediscovering that a surface needs tooling before it needs
tests.

⛔ is equally load-bearing: it is how the map avoids implying coverage it can never have.
A row reading `RTL/bidi control characters in a label | ⬜ | display spoofing; the label
rides into the confirm card` is a complete handoff — someone can pick it up cold.

State the totals where they cannot be missed, and date them:

```
Current state: 148 tests, 0 failures, 38 quarantined pins, ~30s including compile.
```

"38 quarantined pins" is the number a stakeholder actually wants, and the one that makes
"0 failures" honest rather than misleading.

---

## Anti-Patterns

| Anti-pattern | Why it costs | Instead |
|---|---|---|
| Asserting current wrong behaviour "so the suite is green" | Pins the bug in; the fix now breaks the test | Assert the contract; quarantine the failure |
| Deleting the pin when the defect is fixed | Throws away the only regression guard, at the moment it becomes valuable | Drop the mark, keep the test |
| Pins scattered across feature test files | No register, no count, no reviewable diff | One quarantine file |
| A skip message reading "known issue" | The next reader re-does the whole investigation | Severity, file:line, every instance, report pointer |
| Never re-running the pins | Silent fixes go unnoticed; pins rot against a moved API | Step 4 on every SUT change |
| A coverage map with only ✅ and ⬜ | Hides that some gaps need tooling first | Five states, including ⛔ |
