---
name: property-based-testing
description: Use when writing property-based tests — covers Hypothesis (Python), fast-check (TypeScript), QuickCheck (Haskell/Go), and proptest (Rust) for generating tests from properties.
user-invocable: false
---

# Property-Based Testing

## Core Principle

**Test properties, not examples.** Example-based tests prove your code works for specific inputs. Property-based tests prove your code works for entire categories of inputs by generating hundreds of random cases and automatically shrinking failures to minimal reproductions.

---

## Property Identification Patterns

### Universal Properties

These properties apply to most programs regardless of domain:

| Property | Description | Example |
|---|---|---|
| **Round-trip** | Encode then decode returns original | `decode(encode(x)) == x` |
| **Idempotency** | Applying twice equals applying once | `sort(sort(xs)) == sort(xs)` |
| **Invariant preservation** | Operation maintains a known invariant | `len(filter(xs)) <= len(xs)` |
| **Commutativity** | Order of operations does not matter | `merge(a, b) == merge(b, a)` |
| **Associativity** | Grouping does not matter | `concat(concat(a,b),c) == concat(a,concat(b,c))` |
| **Monotonicity** | Larger input produces larger (or equal) output | `x >= y implies f(x) >= f(y)` |

### Domain-Specific Properties

| Domain | Property | Test Assertion |
|---|---|---|
| Serialization | Round-trip fidelity | `deserialize(serialize(obj)) == obj` |
| Sorting | Output is ordered | `all(result[i] <= result[i+1])` |
| Sorting | Output is a permutation of input | `sorted(result) == sorted(input)` |
| Parsing | Never crashes on any input | `parse(random_string)` does not throw unexpected exceptions |
| Encryption | Ciphertext differs from plaintext | `encrypt(key, msg) != msg` |
| API handlers | Response status is always valid | `status_code in [200, 201, 400, 401, 403, 404, 500]` |
| Data structures | Size invariant | `insert then size == old_size + 1` (if not duplicate) |
| Concurrency | Linearizability | Concurrent operations produce a result consistent with some serial ordering |

### How to Find Properties in Your Code

1. **Look at function signatures.** What must always be true about the return value given the input type?
2. **Look at documentation.** Guarantees stated in docs are properties to verify.
3. **Look at assertions and validation.** Existing runtime checks are properties.
4. **Think about inverses.** Does this function have a reverse operation?
5. **Think about equivalences.** Can you compute the same result a different way?

---

## Framework Reference

### Hypothesis (Python)

```python
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Basic property test
@given(st.lists(st.integers()))
def test_sort_preserves_length(xs):
    assert len(sorted(xs)) == len(xs)

# Composing strategies
@given(
    st.dictionaries(
        keys=st.text(min_size=1, max_size=50),
        values=st.integers(min_value=0, max_value=1000),
        min_size=1
    )
)
def test_serialization_roundtrip(data):
    assert deserialize(serialize(data)) == data

# Filtering invalid inputs
@given(st.integers(min_value=1, max_value=10000))
def test_positive_sqrt(n):
    result = isqrt(n)
    assert result * result <= n < (result + 1) * (result + 1)

# Settings for thorough testing
@settings(max_examples=1000, deadline=None)
@given(st.binary(min_size=0, max_size=10000))
def test_parser_never_crashes(data):
    try:
        parse(data)
    except ParseError:
        pass  # Expected — parser should reject gracefully
```

### fast-check (TypeScript)

```typescript
import fc from "fast-check";

// Basic property test
test("sort preserves length", () => {
  fc.assert(
    fc.property(fc.array(fc.integer()), (arr) => {
      expect(arr.sort().length).toBe(arr.length);
    })
  );
});

// Composing arbitraries
test("JSON roundtrip", () => {
  fc.assert(
    fc.property(fc.jsonValue(), (value) => {
      expect(JSON.parse(JSON.stringify(value))).toEqual(value);
    })
  );
});

// Configuring examples count
test("parser handles arbitrary strings", () => {
  fc.assert(
    fc.property(fc.fullUnicodeString(), (input) => {
      expect(() => parse(input)).not.toThrow(TypeError);
    }),
    { numRuns: 1000 }
  );
});

// Model-based testing
test("stack behaves like array", () => {
  const PushCommand = fc.record({ value: fc.integer() }).map(
    ({ value }) => ({
      check: () => true,
      run: (model: number[], real: Stack) => {
        model.push(value);
        real.push(value);
      },
    })
  );
  // ... define PopCommand similarly
  fc.assert(fc.property(
    fc.commands([PushCommand, PopCommand]),
    (cmds) => fc.modelRun(() => ({ model: [], real: new Stack() }), cmds)
  ));
});
```

### proptest (Rust)

```rust
use proptest::prelude::*;

// Basic property test
proptest! {
    #[test]
    fn sort_preserves_length(ref v in prop::collection::vec(any::<i32>(), 0..100)) {
        let mut sorted = v.clone();
        sorted.sort();
        prop_assert_eq!(sorted.len(), v.len());
    }
}

// Custom strategy
fn valid_email() -> impl Strategy<Value = String> {
    (
        "[a-z]{1,20}",
        "[a-z]{1,10}",
        prop_oneof!["com", "org", "net"],
    )
        .prop_map(|(user, domain, tld)| format!("{user}@{domain}.{tld}"))
}

proptest! {
    #[test]
    fn parse_valid_email(ref email in valid_email()) {
        let result = parse_email(email);
        prop_assert!(result.is_ok());
    }

    #[test]
    fn roundtrip_serialization(ref data in any::<Vec<u8>>()) {
        let encoded = encode(data);
        let decoded = decode(&encoded).unwrap();
        prop_assert_eq!(data, &decoded);
    }
}
```

### rapid (Go - QuickCheck-style)

```go
import "pgregory.net/rapid"

func TestSortPreservesLength(t *testing.T) {
    rapid.Check(t, func(t *rapid.T) {
        xs := rapid.SliceOf(rapid.Int()).Draw(t, "xs")
        sort.Ints(xs)
        if len(xs) != len(xs) {
            t.Fatal("length changed")
        }
    })
}

func TestMapRoundtrip(t *testing.T) {
    rapid.Check(t, func(t *rapid.T) {
        key := rapid.String().Draw(t, "key")
        val := rapid.Int().Draw(t, "val")
        m := NewMap()
        m.Set(key, val)
        got, ok := m.Get(key)
        if !ok || got != val {
            t.Fatalf("roundtrip failed: set %q=%d, got %d (ok=%v)", key, val, got, ok)
        }
    })
}
```

---

## Generator Composition

### Building Complex Generators from Simple Ones

| Technique | Purpose | Example |
|---|---|---|
| `map` / `prop_map` | Transform generated values | `integers().map(abs)` for non-negative ints |
| `filter` / `assume` | Reject invalid values | `integers().filter(lambda x: x != 0)` |
| `flatMap` / `bind` | Generate dependent values | Generate list, then generate valid index into it |
| `oneOf` / `prop_oneof` | Choose among alternatives | `oneOf(validInput(), edgeCaseInput())` |
| `tuple` / `record` | Combine independent generators | `(name_gen, age_gen, email_gen)` |
| `recursive` | Build recursive data structures | Trees, nested JSON, ASTs |

### Edge Case Injection

Good frameworks automatically test boundary values. Ensure your generators include:

- Empty collections (`[]`, `""`, `{}`)
- Single-element collections
- Maximum-length inputs
- Zero, negative, and maximum integers
- Unicode, null bytes, newlines in strings
- `NaN`, `Infinity`, `-0` for floating point

---

## Shrinking Strategies

### How Shrinking Works

When a property test fails, the framework automatically **shrinks** the failing input to find the smallest input that still triggers the failure. This transforms a failing input like `[483, -29, 0, 7812, -3]` into `[0, -1]`.

### Shrinking Guidance

| Situation | Guidance |
|---|---|
| Custom generators | Use `map` over built-in generators (preserves shrinking) rather than generating from scratch |
| Filtered generators | Prefer `assume()` over `filter()` when rejection rate is low |
| Slow tests | Set a deadline/timeout so shrinking does not take forever |
| Non-deterministic code | Seed the random source for reproducibility during shrinking |
| Complex structures | Decompose into smaller properties that shrink faster |

---

## Stateful Testing

### What It Tests

Stateful (model-based) testing generates random **sequences of operations** and checks that the system under test behaves identically to a simplified model.

### When to Use It

- Testing data structures (maps, queues, caches)
- Testing stateful APIs (REST endpoints with CRUD)
- Testing concurrent systems (database operations, message queues)
- Testing state machines (workflow engines, UI state)

### Pattern

```
1. Define a simplified MODEL (e.g., a Python dict for a database)
2. Define COMMANDS (create, read, update, delete)
3. Each command:
   a. Has a PRECONDITION (when is this command valid?)
   b. Runs against both the MODEL and the REAL system
   c. Asserts the MODEL and REAL system agree
4. The framework generates random command sequences and shrinks failures
```

---

## When to Use Property-Based Testing

| Situation | Use PBT? | Reasoning |
|---|---|---|
| Serialization/parsing | Yes | Round-trip properties are natural and powerful |
| Pure functions | Yes | Easy to state properties, no setup needed |
| Data structure operations | Yes | Invariants and model-based testing are ideal |
| Security-sensitive code | Yes | Find edge cases that bypass validation |
| Concurrency code | Yes | Random interleavings find race conditions |
| UI rendering | Rarely | Hard to state properties, visual regression is better |
| Integration tests | Sometimes | Useful for API contract testing, expensive to run |

---

## Anti-Patterns

| Anti-Pattern | Problem | Fix |
|---|---|---|
| Reimplementing the function in the test | Test passes trivially | Test a property, not the implementation |
| Overly broad generators | Tests are slow, findings hard to interpret | Constrain generators to realistic inputs |
| Ignoring shrunk output | Missing the minimal reproduction | Always examine the shrunk failing case |
| Too few examples | Misses rare edge cases | Run 1000+ examples for critical code |
| Not seeding for CI | Failures are non-reproducible | Use fixed seeds in CI, random locally |
