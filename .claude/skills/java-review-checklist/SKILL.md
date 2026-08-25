---
name: java-review-checklist
description: "Use when a diff under review contains `.java` files — null/Optional misuse, equals/hashCode contracts, exceptions, concurrency, security and performance."
user-invocable: false
allowed-tools: Read, Grep, Glob, Bash
---

# Java Review Checklist

**Loaded by `code-reviewer` when the diff under review contains `.java`.**

It is a checklist, not an agent: a separate agent would mean a separate spawn, a
separate context and a separate report to reconcile, for review criteria that belong
to whichever reviewer is already reading the diff.

Its dimensions are numbered independently of `code-reviewer`'s six — they are applied
*within* that agent's Phase 3, not alongside it.

---

You are the **Java Reviewer** — a specialist in Java correctness, concurrency and
security. You review code against the language contracts (equals/hashCode, Comparable,
interruption) and production best practices, not against style preference.

---

## Review Dimensions

### 1. Null Handling and `Optional` Misuse

```java
// Bad: Optional as a field/parameter — it is not Serializable and adds a wrapper
//      per instance; it was designed as a return type.
class User { private Optional<String> nickname; }
void greet(Optional<String> name) { }

// Good: Optional is a return type; fields/params stay nullable with a documented contract
class User { private String nickname; }             // may be null — see getNickname()
Optional<String> getNickname() { return Optional.ofNullable(nickname); }
```

```java
// Bad: Optional.get() without isPresent — a NoSuchElementException in disguise
return find(id).get();

// Good: express the absent branch
return find(id).orElseThrow(() -> new UserNotFoundException(id));
```

```java
// Bad: Optional.of on a value that may be null — throws NPE at construction
return Optional.of(map.get(key));

// Good
return Optional.ofNullable(map.get(key));
```

### 2. `equals` / `hashCode` / `Comparable` Contracts

```java
// Bad: equals overridden without hashCode — the object breaks in every HashMap/HashSet
@Override public boolean equals(Object o) { ... }

// Good: both, from the same fields
@Override public boolean equals(Object o) {
    if (this == o) return true;
    if (!(o instanceof User user)) return false;      // Java 16+ pattern matching
    return Objects.equals(id, user.id);
}
@Override public int hashCode() { return Objects.hash(id); }
```

On Java 8/11 — which several fleet projects still target, so check the `release`/`source`
level before flagging — the same check is `if (!(o instanceof User)) return false;`
followed by an explicit cast. The contract is the point, not the syntax.

```java
// Bad: compareTo inconsistent with equals — TreeSet silently drops "equal" elements
public int compareTo(User o) { return this.name.compareTo(o.name); }   // equals uses id

// Good: compare on the same fields equals uses, or document the inconsistency loudly
public int compareTo(User o) { return this.id.compareTo(o.id); }
```

Also check: `equals` typed as `equals(User o)` (an overload, not an override — require
`@Override`), and mutable fields used in `hashCode` (the object gets lost in its own map).

### 3. Exception Handling

```java
// Bad: swallowed InterruptedException — the thread loses its cancellation signal
try { Thread.sleep(100); } catch (InterruptedException e) { }

// Good: restore the flag (or propagate)
try { Thread.sleep(100); }
catch (InterruptedException e) { Thread.currentThread().interrupt(); return; }
```

```java
// Bad: catch-all plus printStackTrace — no context, no propagation, unmonitorable
try { process(); } catch (Exception e) { e.printStackTrace(); }

// Good: specific type, logged with context, cause preserved
try { process(); }
catch (IOException e) { throw new ProcessingException("processing " + id, e); }
```

```java
// Bad: resource leak when read() throws
InputStream in = new FileInputStream(f);
byte[] b = in.readAllBytes();
in.close();

// Good: try-with-resources
try (InputStream in = new FileInputStream(f)) { return in.readAllBytes(); }
```

Also check: `catch (Throwable)` (swallows `OutOfMemoryError`/`StackOverflowError`),
`return` inside `finally` (discards the in-flight exception), and exceptions used for
ordinary control flow.

### 4. Concurrency

```java
// Bad: check-then-act on shared state is not atomic
if (!map.containsKey(k)) map.put(k, compute(k));

// Good
map.computeIfAbsent(k, this::compute);          // on a ConcurrentHashMap
```

```java
// Bad: SimpleDateFormat is NOT thread-safe — a shared static instance corrupts output
static final SimpleDateFormat FMT = new SimpleDateFormat("yyyy-MM-dd");

// Good: java.time is immutable and thread-safe
static final DateTimeFormatter FMT = DateTimeFormatter.ofPattern("yyyy-MM-dd");
```

```java
// Bad: double-checked locking without volatile — publishes a partly-built object
private static Config instance;
static Config get() {
    if (instance == null) { synchronized (Config.class) {
        if (instance == null) instance = new Config(); } }
    return instance;
}

// Good: volatile (or a holder class / enum singleton)
private static volatile Config instance;
```

Also check: non-atomic compound ops on `volatile` fields (`count++`), synchronizing on
a mutable or interned field (`synchronized (this.lock)` where `lock` is reassigned, or
on a `String`/boxed `Integer`), executors created per call and never shut down, and
mutable state escaping a constructor (`this` published before construction finishes).

### 5. Security

```java
// CRITICAL: SQL injection
String q = "SELECT * FROM users WHERE id = '" + userId + "'";
stmt.executeQuery(q);

// Good: PreparedStatement with bound parameters
try (PreparedStatement ps = conn.prepareStatement("SELECT * FROM users WHERE id = ?")) {
    ps.setString(1, userId);
    ...
}
```

```java
// CRITICAL: command injection — the shell parses the concatenated string
Runtime.getRuntime().exec("sh -c 'convert " + userFile + " out.png'");

// Good: argument array, no shell
new ProcessBuilder("convert", userFile, "out.png").start();
```

```java
// CRITICAL: XXE — the default factory resolves external entities
DocumentBuilderFactory f = DocumentBuilderFactory.newInstance();

// Good: disable DTDs entirely
f.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
f.setXIncludeAware(false);
f.setExpandEntityReferences(false);
```

```java
// CRITICAL: Java deserialization of untrusted bytes is remote code execution
Object o = new ObjectInputStream(socket.getInputStream()).readObject();

// Good: a data format with no code semantics
Payload p = objectMapper.readValue(socket.getInputStream(), Payload.class);
```

Also check: path traversal (`new File(base, userPath)` without
`toPath().normalize().startsWith(base)`), `MessageDigest.isEqual` vs `String.equals` for
token comparison (timing), `Random` where `SecureRandom` is required, hardcoded
credentials, and secrets reaching logs or exception messages.

### 6. Performance

```java
// Bad: O(n²) — a new String per iteration
String out = "";
for (String s : items) out += s;

// Good
String out = String.join("", items);            // or a StringBuilder in a loop
```

```java
// Bad: two lookups, and an NPE on the first increment — get(k) returns null
Map<String, Integer> counts = new HashMap<>();
counts.put(k, counts.get(k) + 1);

// Good: one lookup instead of two, and no NPE when the key is absent
// (this still boxes -- Integer::sum returns an Integer; the win is correctness,
//  not allocation. For a genuinely hot counter, use a primitive-specialised map.)
counts.merge(k, 1, Integer::sum);
```

Also check: streams where a plain loop is clearer *and* the stream is in a hot path,
`parallelStream()` on small or IO-bound work (it borrows the common ForkJoinPool),
collection resizing in known-size loops, string concatenation inside log calls that a
level guard would skip, and N+1 queries inside a loop.

### 7. API Design and Idiom

```java
// Bad: mutable public field, and a collection handed out by reference
public List<String> tags = new ArrayList<>();

// Good: encapsulated, defensive on the way out
private final List<String> tags = new ArrayList<>();
public List<String> getTags() { return Collections.unmodifiableList(tags); }
```

Also check: raw types (`List` instead of `List<String>`), fields that should be `final`,
`public` methods that should be package-private, arrays returned from getters without a
copy, `Optional`/collection getters returning `null` instead of empty, and interfaces
declaring `throws Exception`.

---

## Automated Checks

Detect the build before invoking it — do not assume Maven, and do not assume a plugin is
configured.

```bash
# Which build system?
ls pom.xml build.gradle build.gradle.kts 2>/dev/null

# Maven: compile and test
mvn -q compile 2>&1 | tail -40
mvn -q test 2>&1 | tail -60

# Static analysis — ONLY if the plugin is declared in the pom
grep -q spotbugs pom.xml && mvn -q com.github.spotbugs:spotbugs-maven-plugin:check 2>&1 | tail -40
grep -q '<artifactId>pmd' pom.xml && mvn -q pmd:check 2>&1 | tail -40
grep -q checkstyle pom.xml && mvn -q checkstyle:check 2>&1 | tail -40

# SQL built by concatenation
grep -rnE '(execute(Query|Update)?|prepareStatement)\s*\(\s*"[^"]*"\s*\+' --include='*.java' .

# Command execution
grep -rnE 'Runtime\.getRuntime\(\)\.exec\(|new ProcessBuilder\(\s*"(sh|bash|cmd)' --include='*.java' .

# Swallowed / printed exceptions
grep -rn 'printStackTrace()' --include='*.java' .
grep -rnE 'catch \((Exception|Throwable|InterruptedException) ' --include='*.java' .

# Unsafe deserialization and XXE
grep -rn 'new ObjectInputStream' --include='*.java' .
grep -rnE '(DocumentBuilderFactory|SAXParserFactory|XMLInputFactory)\.newInstance\(\)' --include='*.java' .

# equals without hashCode (per file)
for f in $(grep -rl 'boolean equals(Object' --include='*.java' .); do
  grep -q 'int hashCode()' "$f" || echo "no hashCode: $f"
done

# Thread-unsafe formatters held statically
grep -rnE 'static .*(SimpleDateFormat|Calendar) ' --include='*.java' .
```

---

## Report Format

```
## Java Code Review

### Blocking findings: N Critical, M High
*(The gate is the blocking-finding count, not a score -- see `code-reviewer`'s Exit
Rule. A number invites another round over findings that do not block.)*
### Java Version: [detected from pom/gradle release|source level]
### Build: [maven|gradle] — compile [PASS|FAIL], tests [N passed / M failed | not run]

### Critical Security Issues
[Must fix immediately]

### Code Quality Findings

FINDING #N — [CRITICAL|HIGH|MEDIUM|LOW]
File: <path>:<line>
Pattern: <anti-pattern name>
Issue: <description>
Fix: <recommended fix>

Code:
[problematic snippet]

Fix:
[corrected snippet]

### Contract Compliance
- equals/hashCode pairs: N checked, M incomplete
- Resources closed via try-with-resources: N of M
- InterruptedException handled correctly: N of M

### Verdict: [APPROVE | REQUEST_CHANGES | BLOCK]
```
