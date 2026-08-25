---
name: kotlin-review-checklist
description: "Use when a diff under review contains `.kt` files — nullability, coroutine scope and cancellation, immutability, security, Java interop and idiom."
user-invocable: false
allowed-tools: Read, Grep, Glob, Bash
---

# Kotlin Review Checklist

**Loaded by `code-reviewer` when the diff under review contains `.kt`, `.kts`.**

It is a checklist, not an agent: a separate agent would mean a separate spawn, a
separate context and a separate report to reconcile, for review criteria that belong
to whichever reviewer is already reading the diff.

Its dimensions are numbered independently of `code-reviewer`'s six — they are applied
*within* that agent's Phase 3, not alongside it.

---

You are the **Kotlin Reviewer** — a specialist in Kotlin nullability, structured
concurrency and JVM interop. Kotlin's guarantees are only as strong as the places the
code opts out of them; this checklist is mostly about the opt-outs.

---

## Review Dimensions

### 1. Nullability — Where the Guarantee Is Discarded

```kotlin
// Bad: !! converts a compile-time guarantee into a runtime NPE
val name = user!!.name

// Good: express the null branch
val name = user?.name ?: return DEFAULT_NAME
```

```kotlin
// Bad: platform type from Java crosses into non-null without a check.
//      getHeader() is @Nullable-unannotated Java — this NPEs at the assignment.
val token: String = request.getHeader("Authorization")

// Good: treat unannotated Java as nullable
val token = request.getHeader("Authorization") ?: throw MissingTokenException()
```

```kotlin
// Bad: lateinit read before assignment — UninitializedPropertyAccessException,
//      and lateinit on a nullable-by-nature value hides the real state
lateinit var config: Config

// Good: nullable with an explicit accessor, or a constructor parameter
private var config: Config? = null
fun requireConfig() = config ?: error("configure() was never called")
```

Also check: `!!` on the result of a map lookup (`map[k]!!` — use `getValue` for the
same throw with a better message), and non-null assertions inside `let` chains that
defeat the `?.let` they are nested in.

### 2. Coroutines — Scope, Cancellation, Dispatchers

```kotlin
// Bad: GlobalScope outlives the caller — nothing cancels it, and it leaks
GlobalScope.launch { syncUser(id) }

// Good: a scope tied to the caller's lifecycle
viewModelScope.launch { syncUser(id) }          // or coroutineScope { launch { ... } }
```

```kotlin
// Bad: runBlocking on a request/UI thread blocks it while it waits
fun getUser(id: String): User = runBlocking { repo.fetch(id) }

// Good: suspend all the way up; runBlocking belongs in main() and tests
suspend fun getUser(id: String): User = repo.fetch(id)
```

```kotlin
// Bad: catch(Exception) swallows CancellationException — the coroutine ignores
//      cancellation and keeps running. This is THE Kotlin concurrency bug.
try { doWork() } catch (e: Exception) { log.error("failed", e) }

// Good: let cancellation through
try { doWork() }
catch (e: CancellationException) { throw e }
catch (e: Exception) { log.error("failed", e) }
```

```kotlin
// Bad: dispatcher hardcoded — untestable, and wrong on any other platform
suspend fun load() = withContext(Dispatchers.IO) { file.readText() }

// Good: inject it
class Loader(private val io: CoroutineDispatcher = Dispatchers.IO) {
    suspend fun load() = withContext(io) { file.readText() }
}
```

Also check: `launch` where the result is needed (use `async`/`await`), long CPU work on
`Dispatchers.Main`, blocking JVM calls inside a coroutine without `withContext(IO)`,
`SupervisorJob` missing where one child's failure must not kill its siblings, and
`delay` used as a synchronization primitive.

### 3. Immutability, Data Classes, Exposed State

```kotlin
// Bad: var where val works, and a mutable list handed out by reference
class Cart { var items: MutableList<Item> = mutableListOf() }

// Good: read-only type on the way out
class Cart {
    private val _items = mutableListOf<Item>()
    val items: List<Item> get() = _items.toList()
}
```

```kotlin
// Bad: data class over a mutable property — hashCode changes inside a HashSet
data class Key(var id: String)

// Good
data class Key(val id: String)
```

Also check: `copy()` on a data class with a private constructor (it bypasses the
invariant the constructor enforced), `MutableStateFlow` exposed publicly instead of
`asStateFlow()`, and `val` collections that are still `MutableList` underneath — `val`
freezes the reference, not the contents.

### 4. Exception Handling

```kotlin
// Bad: swallowed, no context, and it eats CancellationException in suspend code
try { parse(raw) } catch (e: Exception) { null }

// Good: narrow, with context preserved
try { parse(raw) }
catch (e: SerializationException) { throw ParseFailure("parsing $id", e) }
```

Also check: `runCatching` in suspend functions (it catches `CancellationException` —
rethrow it, or don't use it there), `Result` swallowed with `getOrNull()` and no branch,
`require`/`check`/`error` used for user-facing validation that should return a typed
failure, and `@Throws` missing on functions Java callers must catch.

### 5. Security

```kotlin
// CRITICAL: SQL injection — a string template is still concatenation
val q = "SELECT * FROM users WHERE id = '$userId'"
stmt.executeQuery(q)

// Good
conn.prepareStatement("SELECT * FROM users WHERE id = ?").use {
    it.setString(1, userId); it.executeQuery()
}
```

```kotlin
// CRITICAL: command injection — the template interpolates straight into the shell
Runtime.getRuntime().exec("sh -c 'convert $userFile out.png'")

// Good: argument array, no shell
ProcessBuilder("convert", userFile, "out.png").start()
```

```kotlin
// CRITICAL: deserializing untrusted bytes into arbitrary types is RCE
val o = ObjectInputStream(socket.getInputStream()).readObject()

// Good: a data format with no code semantics, into a declared type
val p = Json.decodeFromStream<Payload>(socket.getInputStream())
```

Also check: string templates reaching file paths (`File("$base/$userPath")` — normalize
and verify the prefix), unannotated `@Serializable` classes accepting unknown fields,
`SecureRandom` vs `Random`, hardcoded keys in `companion object` constants, and secrets
appearing in `toString()` of a data class (data classes print every property).

### 6. Java Interop

```kotlin
// Bad: Java callers must write Utils.INSTANCE.parse(...)
object Utils { fun parse(s: String) = ... }

// Good: a plain static for Java
object Utils { @JvmStatic fun parse(s: String) = ... }
```

Also check: default arguments invisible to Java without `@JvmOverloads`, Kotlin
exceptions being unchecked (a Java caller cannot `catch` what is not declared — add
`@Throws`), `Nothing?`/`Unit` leaking into a Java-facing API, nullability annotations
missing on Kotlin types Java consumes, and properties named `isX` colliding with a Java
getter convention.

### 7. Idiom

```kotlin
// Bad: nested scope functions — which `it` is which?
user?.let { u -> u.address?.let { a -> a.city?.let { c -> send(u, a, c) } } }

// Good: flatten with early returns
val u = user ?: return
val a = u.address ?: return
send(u, a, a.city ?: return)
```

```kotlin
// Bad: non-exhaustive `when` on a sealed type with a catch-all — a new subclass
//      compiles silently and falls into `else`
when (state) { is Loading -> ...; else -> Unit }

// Good: exhaust every branch; the compiler then flags the new subclass
when (state) { is Loading -> ...; is Ready -> ...; is Failed -> ... }
```

Also check: `apply` used where `also` is meant (and vice versa), `!!` inside `run`/`with`
blocks, extension functions on types you do not own that shadow members, `companion
object` used as a namespace for what should be top-level functions, and `==` vs `===`
where reference identity was intended.

---

## Automated Checks

Detect the build and the linters before invoking them — do not assume detekt or ktlint
is configured.

```bash
# Which build files exist?
ls build.gradle.kts build.gradle settings.gradle.kts 2>/dev/null

# Compile and test (Gradle wrapper)
./gradlew -q compileKotlin 2>&1 | tail -40
./gradlew -q test 2>&1 | tail -60

# Static analysis — ONLY if the plugin is declared
grep -rq detekt build.gradle.kts build.gradle 2>/dev/null && ./gradlew -q detekt 2>&1 | tail -40
grep -rqE 'ktlint|spotless' build.gradle.kts build.gradle 2>/dev/null && ./gradlew -q ktlintCheck 2>&1 | tail -40

# Non-null assertions
grep -rn '!!' --include='*.kt' --include='*.kts' .

# Unscoped / blocking coroutines
grep -rnE 'GlobalScope\.(launch|async)' --include='*.kt' .
grep -rn 'runBlocking' --include='*.kt' .

# Cancellation-swallowing catches (check each for a CancellationException rethrow)
grep -rnE 'catch \(\w+: (Exception|Throwable)\)|runCatching' --include='*.kt' .

# Hardcoded dispatchers
grep -rnE 'Dispatchers\.(IO|Default|Main)' --include='*.kt' .

# SQL and command execution built from string templates
grep -rnE '"(SELECT|INSERT|UPDATE|DELETE)[^"]*\$' --include='*.kt' .
grep -rnE 'Runtime\.getRuntime\(\)\.exec\(|ProcessBuilder\(\s*"(sh|bash|cmd)' --include='*.kt' .

# Unsafe deserialization
grep -rn 'ObjectInputStream' --include='*.kt' .

# Mutable state exposed publicly
grep -rnE '^\s*(public )?(var|val) \w+: Mutable(List|Map|Set|StateFlow)' --include='*.kt' .
```

---

## Report Format

```
## Kotlin Code Review

### Blocking findings: N Critical, M High
*(The gate is the blocking-finding count, not a score -- see `code-reviewer`'s Exit
Rule. A number invites another round over findings that do not block.)*
### Kotlin Version: [detected from build file / gradle.properties]
### Build: gradle — compileKotlin [PASS|FAIL], tests [N passed / M failed | not run]
### Linters: [detekt configured? ktlint configured? or "none declared"]

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

### Safety Audit
- `!!` occurrences in the diff: N (each justified? Y/N)
- Coroutines launched outside a lifecycle scope: N
- catch blocks that swallow CancellationException: N

### Verdict: [APPROVE | REQUEST_CHANGES | BLOCK]
```
