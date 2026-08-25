---
name: ai-agent-testing
description: "Use when testing an LLM-agent system — the two-suite doctrine that keeps the merge gate deterministic, plus the agent invariants worth asserting."
user-invocable: false
allowed-tools: Read, Grep, Glob, Bash
---

# Testing AI Agent Systems

**An agent system is not untestable — it is testable everywhere except the model call.**
The mistake is concluding that because the model is non-deterministic, the system around it
must be tested non-deterministically too. Almost none of what actually breaks is the model's
wording. It is the governance around the tool calls: writes without confirmation, provenance
gates that open on failures, state cleared by a harmless duplicate.

Method and examples come from a real pass against a production health-assistant agent:
148 offline tests, 38 confirmed defects, no SUT modified. The method for producing them is
`whitebox-invariant-testing`; the protocol for keeping them is `defect-pinning`.

---

## The Two-Suite Doctrine

Two suites, and **only one of them may ever gate a merge**.

| | Offline suite | Live driver |
|---|---|---|
| Backend | stubbed, canned fixtures | real |
| Model | stubbed / scripted tool calls | real LLM |
| Clock | injected | real |
| Runtime | seconds | minutes |
| Cost | zero | per-token |
| **Gates a merge** | **yes — put every assertion you care about here** | **never** |
| Purpose | correctness of everything around the model | exploration, routing quality, prompt work |

**Why the live suite must never gate.** Providers return transient 5xx often enough that a
red build stops meaning "you broke something". One flaky gate trains a team to re-run until
green, and at that point every gate is decorative. A live failure is a *lead*, not a verdict.

```bash
./gradlew test                                  # offline: the gate. no key, no network.

AGENT_SAY='show my appointments;book me a dentist' \
  ./gradlew test --tests '*LiveConsoleTest*'    # exploratory. skips entirely with no key.
```

Make the live driver **skip, not fail**, when its key is absent — otherwise it fails for
everyone who does not have one, and someone eventually deletes it.

What genuinely belongs to the live suite: whether the model picks the right tool for a real
utterance, prompt-change comparisons, and multi-turn conversational coherence. For running
those as a disciplined evaluation rather than eyeballing transcripts, see `prompt-evaluation`
(exploratory) and `eval-harness` (the CI-gated baseline).

---

## Making the Offline Suite Deterministic

Three seams, all injected at construction:

```kotlin
val h = AgentHarness(
    overrides   = { path -> if ("serviceList" in path) SERVICES_JSON else null },
    failOn      = { path -> if ("labs/orders" in path) IOException("5xx") else null },
    respondWith = { path -> if ("auth" in path) StubResponse(401, "") else null },
)
h.now += 61 * 60_000L        // injected clock: no test ever sleeps
```

**Assert on events and the call log, never on the model's prose.** The wording is generated;
the tool calls and emitted events are not.

```kotlin
assertIs<FlowEvent.FlowStarted>(r.event)        // events: yes
assertTrue(h.called("serviceList"))             // call log: yes
assertFalse(h.called("appointments/book"))      // and what must NOT have been called
// assertTrue(r.text.contains("booked"))        // NEVER -- prose is non-deterministic
```

Note the third line. Half the value of agent testing is asserting the **absence** of a call.

---

## The Agent Invariant Catalog

These are the promises agent systems make and break. Each one below was a real defect. Work
the list against your own system — the mechanisms differ, the classes do not.

### 1. Tool-call governance

- No write executes without an explicit ready state **and** a user confirmation.
- Side effects happen **exactly once** — a retry after an ambiguous failure must not double-book.
- **A refused call does not consume state.** Real defect: a guard registered the call
  signature *before* the method's own guards ran, so a call refused downstream still consumed
  it — and the legitimate retry was then refused with "you already did exactly this, the
  state is unchanged", which was false on both counts.

```kotlin
@Test fun no_write_without_ready_and_confirm() = runTest {
    val h = AgentHarness(); h.engine.beginTurn()
    h.engine.start("book_appointment")
    fillEveryStep(h)
    assertFalse(h.called("appointments/book"), "wrote before confirmation")
    h.engine.confirm()
    assertEquals(1, h.calls.count { "appointments/book" in it }, "not exactly-once")
}
```

### 2. Provenance and anti-fabrication

- A **failed** read must not mark data as fetched. Real defect (P1): a transport failure
  produced an error callout, the engine recorded the read anyway, and the anti-fabrication
  gate — whose own doc said "capability ids whose READ *actually returned data*" — opened,
  admitting the error payload into the data ledger.
- Render only ledger-backed values. Any number on screen traces to a recorded read.

### 3. Staleness semantics

- Staleness is **idle** time, so every user-driven action resets the clock. Real defect: no
  `confirm()` path updated the activity timestamp, so a user who confirmed at T+59min, hit a
  transient failure, and retried at T+61min lost the entire filled flow to a staleness cancel
  — two minutes after acting.

### 4. Model-echo resilience

- A duplicate or same-value re-fill is a **no-op**. Real defect: a cross-turn re-send of an
  already-filled value (a classic model echo — a per-turn seen-set cannot catch it) triggered
  the implicit-revise branch and cleared every downstream pick, silently re-fetching and
  re-auto-picking one of them.

### 5. Multi-entry verdict completeness

- When the model submits several fills at once, **every** entry gets an explicit verdict —
  matched, stashed, or no-match. An entry that falls through the switch is data loss with no
  error.

### 6. Dependent scoping

- Revising a step invalidates its **transitive** dependents. Real defect: the dependency scan
  read the primary arg templates but not a secondary set (`nearestArgs`), so a step that
  depended on another through that path survived un-revalidated and rode into the write.
- The general shape: **dependency detection that scans some reference sites but not all.**
  Enumerate every place a reference can be declared, then assert the scan covers each.

### 7. Locale and RTL contract

- Wire headers follow the session locale (`Accept-Language`, and any vendor equivalent) on
  **every** call, and no other language's strings leak into rendered labels.
- A string localized on only one side must fall back to the **present** side — never to an
  internal identifier. Real defect (P3): a step title with a blank English side rendered the
  raw step id `specialty_step` on screen.
- RTL/bidi control characters in a label are a **display-spoofing** surface: they ride
  through into the confirmation card, where they can reorder what the user thinks they are
  approving. Assert labels are free of bidi overrides before they reach a confirm surface.

```bash
# Labels carrying bidi control characters (U+202A-U+202E, U+2066-U+2069).
# NOT `grep -P` -- PCRE mode is GNU-only and errors out on BSD/macOS grep.
python3 - <<'EOF'
import pathlib, re
BIDI = re.compile('[\u202a-\u202e\u2066-\u2069]')
for f in pathlib.Path('fixtures').rglob('*.json'):
    for n, line in enumerate(f.read_text(encoding='utf-8').splitlines(), 1):
        if BIDI.search(line):
            print(f'{f}:{n}: bidi control character in a label')
EOF
```

---

## Coverage and Reporting

Agent surfaces are wide and partly unreachable, so track them explicitly rather than by
percentage — a line-coverage number over an agent system is close to meaningless. Use
`defect-pinning`'s five-state map (✅ / 🔴 / ⬜ / 🔧 / ⛔), and be honest about ⛔: voice,
real rendering, on-device behaviour and true model-routing quality are not reachable from a
headless suite, and saying so is what keeps the map from implying false confidence.

To judge whether a given test would actually catch the regression it claims to, use
`verification-gap-lens`.
