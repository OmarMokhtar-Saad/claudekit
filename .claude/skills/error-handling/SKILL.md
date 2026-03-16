---
name: error-handling
description: "Use when implementing error handling - structured exceptions, logging, recovery patterns"
user-invocable: false
---

# Error Handling

## Core Principle

**Errors are not exceptional - they are expected.** Design your error handling strategy before writing the happy path. Every function that can fail should communicate failure clearly.

---

## Exception Hierarchy Principles

### Design a Clear Hierarchy

Organize exceptions/errors by domain meaning, not by technical mechanism:

```
ApplicationError (base)
├── ValidationError
│   ├── InvalidInputError
│   └── MissingRequiredFieldError
├── BusinessRuleError
│   ├── InsufficientFundsError
│   └── OrderLimitExceededError
├── ResourceError
│   ├── NotFoundError
│   └── ConflictError
└── InfrastructureError
    ├── DatabaseConnectionError
    ├── ExternalServiceError
    └── TimeoutError
```

### Hierarchy Rules

| Rule | Rationale |
|---|---|
| Use specific exception types | Callers can handle specific errors differently |
| Include context in exceptions | Error messages should contain diagnosis information |
| Never use generic exceptions for flow control | Exceptions are for errors, not for normal branching |
| Keep hierarchy shallow (max 3 levels) | Deep hierarchies are hard to remember and maintain |

---

## Catch vs Propagate Rules

### When to CATCH an Exception

| Situation | Action |
|---|---|
| You can fully recover from the error | Catch and recover |
| You need to translate to a domain exception | Catch, wrap, and rethrow |
| You need to add context | Catch, add context, and rethrow |
| You need to clean up resources | Catch in finally/cleanup block |
| You are at a system boundary (API, UI) | Catch and convert to user response |

### When to PROPAGATE an Exception

| Situation | Action |
|---|---|
| You cannot meaningfully handle it | Let it propagate |
| It is a programming error (null ref, index out of bounds) | Let it propagate and crash |
| The caller is better positioned to decide | Let it propagate |
| You are in a utility/helper function | Let it propagate |

### The Decision Flow

```
Can I fully recover from this error?
  YES --> Catch and handle
  NO  --> Can I add useful context?
            YES --> Catch, wrap with context, rethrow
            NO  --> Let it propagate
```

### Anti-Patterns

```
# BAD: Swallowing exceptions silently
try:
    do_something()
except Exception:
    pass  # NEVER DO THIS

# BAD: Catching too broadly
try:
    result = calculate(x, y)
except Exception as e:
    return default_value  # Hides bugs

# BAD: Logging and rethrowing without adding value
try:
    do_something()
except SomeError as e:
    log.error(e)  # Just noise - the caller will log it too
    raise

# GOOD: Catching specific errors with recovery
try:
    result = cache.get(key)
except CacheMissError:
    result = database.get(key)
    cache.set(key, result)

# GOOD: Wrapping with context
try:
    user = repository.find(user_id)
except DatabaseError as e:
    raise UserLookupError(f"Failed to find user {user_id}") from e
```

---

## Logging Levels

### Level Definitions

| Level | When to Use | Example |
|---|---|---|
| **ERROR** | Something failed and needs attention | Database connection lost, API call failed |
| **WARN** | Something unexpected but handled | Retry succeeded, using fallback value |
| **INFO** | Normal operations worth recording | Request received, job completed |
| **DEBUG** | Detailed diagnostic information | Variable values, decision points |
| **TRACE** | Very detailed execution flow | Method entry/exit, loop iterations |

### Logging Rules

1. **ERROR** logs should be actionable - someone reading them should know what to do
2. **WARN** logs indicate degraded operation - the system is working but not ideally
3. **INFO** logs tell the story of normal operation
4. **DEBUG/TRACE** should never appear in production logs by default

### What to Include in Error Logs

```
# Good error log
log.error(
    "Failed to process order",
    order_id=order.id,
    customer_id=order.customer_id,
    error_type=type(e).__name__,
    error_message=str(e),
    retry_count=retry_count
)

# Bad error log
log.error("Error occurred")  # Useless
log.error(str(e))           # No context
```

---

## User vs Internal Error Messages

### The Two-Message Rule

Every error needs TWO messages:

1. **User-facing message:** Safe, helpful, non-technical
2. **Internal log message:** Detailed, technical, includes context

| Error Type | User Message | Internal Log |
|---|---|---|
| Validation | "Please enter a valid email address" | "Validation failed: email field did not match regex pattern" |
| Not Found | "The requested item could not be found" | "Entity not found: type=Order, id=12345" |
| Permission | "You don't have permission to perform this action" | "Authorization failed: user=456, action=DELETE, resource=Order/123" |
| Infrastructure | "Service is temporarily unavailable. Please try again." | "Database connection pool exhausted: active=20, max=20, wait_time=30s" |
| Unknown | "An unexpected error occurred. Please try again." | Full stack trace with all context |

### Rules

- NEVER expose stack traces to users
- NEVER expose database details to users
- NEVER expose internal IDs or paths to users
- ALWAYS provide a correlation/request ID so users can report issues
- ALWAYS log the full details internally

---

## Recovery Strategies

### Retry Pattern

```
Attempt 1 --> FAIL --> Wait 1s
Attempt 2 --> FAIL --> Wait 2s
Attempt 3 --> FAIL --> Wait 4s
Attempt 4 --> FAIL --> Give up, report error
```

**When to retry:**
- Transient network errors
- Temporary resource unavailability
- Rate limit responses (with appropriate backoff)

**When NOT to retry:**
- Validation errors (will fail every time)
- Authentication errors (credentials are wrong)
- Not-found errors (resource does not exist)

### Fallback Pattern

```
Primary --> FAIL --> Fallback --> FAIL --> Default
```

**Examples:**
- Primary cache fails -> fall back to database
- Primary API fails -> fall back to cached response
- Configuration file missing -> use default values

### Circuit Breaker Pattern

```
CLOSED (normal) --> too many failures --> OPEN (failing fast)
                                             |
                                        timeout elapsed
                                             |
                                         HALF-OPEN (testing)
                                        /            \
                                    success          failure
                                      |                |
                                   CLOSED            OPEN
```

**When to use:**
- External service calls that may be down
- Database connections that may be unavailable
- Any dependency that can fail for extended periods

---

## Error Handling Checklist

Before considering error handling complete:

- [ ] All external calls have error handling (network, file I/O, database)
- [ ] User-facing errors are clear and non-technical
- [ ] Internal errors are logged with sufficient context
- [ ] No exceptions are silently swallowed
- [ ] Recovery strategies are implemented where appropriate
- [ ] Error paths are tested (not just happy paths)
- [ ] Resources are properly cleaned up on error
- [ ] Error responses include correlation IDs for support
