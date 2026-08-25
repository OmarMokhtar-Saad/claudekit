---
name: whitebox-invariant-testing
description: "Use when testing an SDK or dependency you cannot modify — build an invariant table from its source, then attack each promise through harness knobs."
user-invocable: false
allowed-tools: Read, Grep, Glob, Bash
---

# White-box Invariant Testing

**The method: read the source to learn what it PROMISES, then attack each promise from
outside it.** Not "does the happy path work" — that is what the authors already tested.
This finds the cases where the code's own documented contract and its behaviour disagree.

Harvested from a live pass against a production agent SDK: 148 tests, 38 confirmed defects,
zero lines changed in the system under test. The worked examples below are that pass.

**Load `defect-pinning` next** — this skill finds defects; that one is the protocol for
keeping them found. For agent/LLM systems specifically, the invariant catalog is in
`ai-agent-testing`.

---

## The Precondition: You Do Not Own the SUT

This method assumes you **cannot** change the system under test — it is a vendor SDK, another
team's library, or a repo you have read access to and no merge rights on. That constraint is
a feature: it forces every attack through the seams the SUT actually exposes, which is the
same surface a real caller has.

Set the harness up as a **read-only composite build** — your test project consumes the SUT's
*source*, not a published artifact:

```kotlin
// settings.gradle.kts — the SUT is a sibling checkout, never edited
includeBuild(providers.gradleProperty("sdkPath").getOrElse("../the-sdk"))
```

```bash
# point at any branch/checkout without publishing or version-bumping anything
./gradlew test -PsdkPath=/abs/path/to/the-sdk
```

Why source and not a jar: **you find out at compile time** when the SUT changes under you.
A stale published artifact silently tests a version nobody runs any more.

---

## Step 1 — Build the Invariant Table FROM the Source

Do not invent invariants. Extract them. Every row is **a promise the SUT makes about itself**
plus **the location it makes it**. Five places promises hide:

| Source | What to extract | Example found this way |
|---|---|---|
| Doc comments | Explicit contracts, especially quoted definitions | `fetchedReads` = "capability ids whose READ **actually returned data**" |
| Guard clauses | What the code refuses, and what it claims about state when it refuses | repeat-breaker message: "you already did exactly this — the state is unchanged" |
| Emitted events | The state machine's own vocabulary; what each event asserts happened | `FlowCancelled(STALE)`, `WriteOk`, `CardShown` |
| Fail-closed claims | Anywhere the code says it degrades safely | "returns an EMPTY catalog on schema mismatch" |
| Spec/recipe data | Declarative config that encodes rules the code must honour | step arg templates declaring `{stepKey.field}` dependencies |

```bash
# Harvest candidate promises. Read the hits -- do not trust the grep as the table.
grep -rnE '^\s*\*.*(must|never|always|guarantee|actually|exactly once)' --include='*.kt' src/
grep -rnE 'require\(|check\(|error\(|return\s+(Guard|Refused|Denied)' --include='*.kt' src/
grep -rnE 'sealed (class|interface) \w*Event' -A 20 --include='*.kt' src/
```

Write the table down before writing any test. A row looks like:

```
INVARIANT: a failed read must not open the anti-fabrication gate
PROMISED AT: AgentTurnEngine.kt:272-277 (KDoc on fetchedReads)
ENFORCED BY: recordRead() — called on the executor's result
ATTACK: make the transport fail, then ask hasFetchedRead()
```

The table is the deliverable of Step 1. It outlives the pass — the gaps in it are the
next pass's worklist (see `defect-pinning`'s coverage map).

---

## Step 2 — Attack Through Harness Knobs, Never by Editing the SUT

Every attack is expressed as **harness configuration**. If an attack requires changing the
SUT, it is not a test — it is a different program. Build the harness with one knob per
hostile condition:

```kotlin
class AgentHarness(
    val locale: String = "ar",
    /** Per-path canned response, on top of the fixtures. Return null to fall through. */
    val overrides: (String) -> String? = { null },
    /** Throw from here to simulate a transport failure for a given path. */
    val failOn: (String) -> Throwable? = { null },
    /** HTTP-level: answer with a real status/body/headers, not just a 200. */
    val respondWith: (String) -> StubResponse? = { null },
    /** Seam: classify a write failure as OUTCOME-UNKNOWN (it may have landed server-side). */
    val classifyUnknown: (Throwable) -> Boolean = { false },
) {
    /** Ordered log of every path called. Assert on THIS. */
    val calls = mutableListOf<String>()
    /** Injected clock -- no test ever sleeps. */
    var now: Long = 1_700_000_000_000L
}
```

The four attack shapes that find the most, in order:

1. **Make a dependency fail** (`failOn`) — the error path is the one nobody exercised.
2. **Move the clock** (`now += 61 * 60_000`) — timeouts, staleness, expiry.
3. **Call out of order, and call twice** — guards that register state before validating it.
4. **Answer with the wrong shape** (`respondWith`) — a 200 whose body is not what the
   contract says.

```kotlin
// Attacking the row from Step 1. The assertion quotes the promise it is testing.
@Test
fun a_failed_read_must_not_open_the_provenance_gate() = runTest {
    val h = AgentHarness(failOn = { p -> if ("labs/orders" in p) RuntimeException("5xx") else null })
    h.engine.beginTurn()
    h.engine.start("lab_results")

    assertTrue(h.called("labs/orders"), "fixture drift: the read never reached the endpoint")
    assertFalse(
        h.engine.hasFetchedRead(setOf("lab_results")),
        "the fabrication gate (KDoc: ids \"whose READ actually returned data\") opened on an error",
    )
}
```

### Two rules that decide whether a test means anything

**Assert on events and call logs, never on generated prose.** Wording is
non-deterministic — especially from an LLM — and a test bound to it fails for the wrong
reason or passes while the behaviour rots.

**A wrong fixture looks exactly like an honest empty backend.** If your route key or
response shape is stale, the SUT sees `[]`, correctly reports "nothing available", and your
test passes *having tested nothing*. Every fixture-dependent test carries a
`assertTrue(h.called(path))` line proving the wire was reached. Keep one contract test whose
only job is to prove the fixtures still map.

---

## Step 3 — Hostile-Environment Sweeps as a Standing Battery

Run every read surface through the same hostile backends, and collect failures per surface so
one run reports every broken one at once rather than stopping at the first.

| Leg | Backend behaviour | Catches |
|---|---|---|
| Total outage | HTTP 500 on every endpoint | unhandled exceptions, retry storms |
| Expired session | HTTP 401 on every endpoint | auth-refresh loops, silent data loss |
| Captive portal | HTTP 200 whose body is an HTML login page | "success" parsing of non-data |
| Timeout | connection never answers | unbounded waits, missing deadlines |

Four assertions per surface per leg:

```kotlin
for (cap in readSurfaces) {
    val h = harness(hostileStub)
    val result = runCatching { h.engine.start(cap) }

    assertNull(result.exceptionOrNull(), "$cap: a raw exception escaped the engine")
    for (w in writePaths)
        assertFalse(h.called(w), "$cap: a WRITE was called during a failing READ")
    for ((path, n) in h.calls.groupingBy { it }.eachCount())
        assertTrue(n <= allowed(path), "$cap: $path called ${n}x — retry loop")
    // and, for surfaces that MUST use the network, prove the leg was not vacuous:
    if (cap in httpBacked) assertTrue(h.calls.isNotEmpty(), "$cap: never reached the wire")
}
```

That last line is the one people skip. Without it a sweep "passes" for a surface that never
made a call at all.

**Document the exceptions in the code, with evidence.** A surface legitimately absent from
`httpBacked` needs a comment saying why and when it was checked — otherwise the next reader
deletes the exception or, worse, adds more:

```kotlin
// vital_trends is deliberately ABSENT: its read is prefill-gated, so a bare start honestly
// asks which vital and makes no HTTP call. Triaged 2026-08-23: expectation wrong, SDK right.
```

Same for documented fan-outs: if one capability legitimately calls one path five times, the
retry-loop assertion needs an allowance naming the source line that makes it five.

---

## Step 4 — The Finding Shape

A finding that cannot be acted on is a complaint. Every one carries five parts:

```
INVARIANT BROKEN: <the promise, quoted from the SUT's own words>
SUT LOCATION:     <file:line where the promise is made AND where it is broken>
REPRO:            <the test name that fails today>
OBSERVED:         <what actually happens>
EXPECTED:         <what the quoted promise requires>
FIX SKETCH:       <the smallest diff that would satisfy it>
```

Worked example:

```
INVARIANT BROKEN: a refused call must not consume its repeat signature — the breaker's own
                  message claims "the state is unchanged"
SUT LOCATION:     AgentTurnEngine.kt:152-161 — entryGuard registers the signature BEFORE the
                  method's own guards run
REPRO:            d2_a_call_refused_by_a_downstream_guard_must_not_consume_the_signature
OBSERVED:         start(B) refused by a downstream guard; caller complies, retries start(B);
                  refused with "you already did exactly this — the state is unchanged",
                  which is false on both counts
EXPECTED:         the retry proceeds; only the guard's OWN refusals consume a signature
FIX SKETCH:       move the registerSignature() call below the guard block at :161
```

Quote the SUT's promise verbatim. A finding phrased as your opinion invites a debate about
taste; a finding phrased as *the code does not do what its own doc comment says* does not.

---

## What This Method Does Not Cover

Say so explicitly, in the report. A headless white-box harness cannot reach:

- anything requiring a device, real rendering, or audio/input timing;
- `internal`/module-private members — you are a different module (do not hardcode around
  this; read the value from the artifact the SUT itself parses);
- the quality of a non-deterministic component's output (see `ai-agent-testing`'s two-suite
  doctrine for where that belongs instead).

Naming the unreachable set is what stops the coverage map from implying false confidence.
