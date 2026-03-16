---
name: performance-guidelines
description: "Use when implementing features that affect response times or resource usage - performance targets and patterns"
user-invocable: false
---

# Performance Guidelines

## Core Principle

**Performance is a feature, not an afterthought.** Every implementation choice has performance implications. Consider them during design, not after users complain.

---

## Generic Performance Targets

### Response Time Targets

| Operation Type | Target | Maximum |
|---|---|---|
| In-memory computation | < 10ms | 50ms |
| Local I/O (file, cache) | < 50ms | 200ms |
| Database query (simple) | < 100ms | 500ms |
| Database query (complex) | < 500ms | 2s |
| External API call | < 1s | 5s |
| Batch processing (per item) | < 10ms | 100ms |
| UI interaction response | < 100ms | 300ms |
| Page/screen load | < 1s | 3s |

### Resource Targets

| Resource | Guideline |
|---|---|
| Memory per request | Minimize allocations, avoid unbounded growth |
| CPU per request | Avoid blocking computations on request threads |
| Database connections | Use connection pooling, release promptly |
| File handles | Close after use, use context managers |
| Network connections | Reuse connections, use connection pools |

---

## Main Thread Safety

### Rules

- **NEVER** perform long-running operations on the main/UI thread
- **NEVER** block on network I/O on the main thread
- **NEVER** perform database queries on the main thread (in UI applications)
- **ALWAYS** offload heavy work to background threads/workers

### Pattern: Async Offloading

```
Main Thread                    Background Worker
    |                               |
    |-- dispatch(work) ------------>|
    |                               |-- process()
    |   (remains responsive)        |-- complete
    |<-- notify(result) ------------|
    |
    |-- update UI/respond
```

### Common Violations

| Violation | Fix |
|---|---|
| Network call on UI thread | Use async/await or background task |
| File read blocking main thread | Use async I/O or worker thread |
| Heavy computation in request handler | Offload to task queue |
| Database query in UI callback | Use repository pattern with async |

---

## Memory Management Patterns

### Avoid Unbounded Growth

- Set maximum sizes on caches and buffers
- Use LRU eviction for in-memory caches
- Stream large data instead of loading entirely into memory
- Paginate large query results

### Common Memory Issues

| Issue | Pattern | Fix |
|---|---|---|
| Loading entire file into memory | `read_all()` | Stream line by line |
| Unbounded list growth | `results.append()` in loop | Use generators or pagination |
| Large object retention | Holding references after use | Nullify references, use weak refs |
| String concatenation in loops | `result += string` | Use string builder / join |
| Duplicate data structures | Multiple copies of same data | Share references, use flyweight |

### Caching Strategy

```
[REQUEST] --> [CHECK CACHE] --> HIT --> [RETURN CACHED]
                    |
                    v
                   MISS
                    |
                    v
              [COMPUTE/FETCH]
                    |
                    v
              [STORE IN CACHE]
                    |
                    v
              [RETURN RESULT]
```

**Cache rules:**
- Always set a maximum cache size
- Always set a TTL (time-to-live) for cache entries
- Choose eviction policy (LRU, LFU, FIFO)
- Consider cache invalidation strategy
- Monitor cache hit rates

---

## Resource Disposal

### The Rule

**Every resource that is opened must be closed.** Use language-provided mechanisms to ensure disposal:

- Python: `with` statements (context managers)
- JavaScript: `try/finally` or `using` declarations
- Go: `defer` statements
- C#: `using` statements
- Rust: RAII (automatic via Drop trait)
- General: try/finally blocks

### Resources That Must Be Disposed

| Resource | Consequence of Leak |
|---|---|
| Database connections | Connection pool exhaustion |
| File handles | OS file descriptor limit reached |
| Network sockets | Port exhaustion |
| Thread pool executors | Thread leak, OOM |
| Locks/mutexes | Deadlock |
| Temporary files | Disk space exhaustion |
| Event listeners | Memory leak, phantom behavior |

---

## Database Performance

### Query Optimization

- Use indexes for frequently queried columns
- Avoid SELECT * (select only needed columns)
- Use LIMIT for paginated results
- Avoid N+1 queries (use joins or batch loading)
- Use EXPLAIN to analyze query plans

### N+1 Query Prevention

```
# BAD: N+1 queries
users = get_all_users()           # 1 query
for user in users:
    orders = get_orders(user.id)  # N queries

# GOOD: Batch loading
users = get_all_users()                            # 1 query
orders = get_orders_for_users([u.id for u in users])  # 1 query
```

### Connection Management

- Use connection pooling (never create per-request connections)
- Set appropriate pool size (typically 5-20 connections)
- Configure connection timeout
- Release connections back to pool ASAP
- Monitor pool usage and wait times

---

## Network Performance

### Minimize Round Trips

- Batch API calls when possible
- Use bulk operations instead of individual ones
- Consider GraphQL or similar for flexible data fetching
- Cache responses when appropriate

### Handle Failures Gracefully

- Set timeouts on all network calls
- Implement retry with exponential backoff
- Use circuit breakers for unreliable services
- Have fallback behavior for degraded dependencies

---

## Performance Testing

### What to Measure

| Metric | Tool/Approach |
|---|---|
| Response time (p50, p95, p99) | Load testing, APM |
| Throughput (requests/second) | Load testing |
| Memory usage over time | Profiler, monitoring |
| CPU utilization | Profiler, monitoring |
| Database query time | Slow query log, APM |
| Error rate under load | Load testing |

### When to Performance Test

- Before releasing a new feature
- After significant refactoring
- When adding new database queries
- When changing data structures
- When integrating new external services

---

## Anti-Patterns

| Anti-Pattern | Why It Is Bad | Alternative |
|---|---|---|
| Premature optimization | Wastes time, adds complexity | Profile first, then optimize |
| Ignoring algorithmic complexity | O(n^2) in disguise | Analyze big-O before implementing |
| Synchronous everything | Blocks threads, poor scalability | Use async for I/O operations |
| No connection pooling | Resource exhaustion under load | Always pool database/HTTP connections |
| Logging in tight loops | I/O overhead destroys performance | Log summaries, use sampling |
| Unbounded queues | Memory exhaustion | Set max sizes with backpressure |
