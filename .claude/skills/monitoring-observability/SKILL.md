---
name: monitoring-observability
description: "Use when implementing monitoring or debugging production systems - logging, tracing, metrics, alerting"
user-invocable: false
---

# Monitoring and Observability

## Core Principle

**You cannot fix what you cannot see.** Observability is the ability to understand the internal state of a system from its external outputs. Invest in logging, metrics, and tracing before you need them.

---

## The Three Pillars

| Pillar | What It Captures | Use When |
|---|---|---|
| **Logs** | Discrete events with context | Debugging specific requests, audit trails |
| **Metrics** | Aggregated numerical measurements | Dashboards, alerting, capacity planning |
| **Traces** | Request flow across services | Debugging latency, understanding dependencies |

---

## Structured Logging

### Log Format

Always use structured (JSON) logging, never unstructured strings:

```
# BAD: Unstructured
"User 123 failed to login from 10.0.0.1"

# GOOD: Structured
{
  "level": "warn",
  "message": "Login failed",
  "user_id": "123",
  "source_ip": "10.0.0.1",
  "reason": "invalid_password",
  "attempt": 3,
  "timestamp": "2026-03-16T10:30:00Z",
  "request_id": "req_abc123"
}
```

### Log Levels

| Level | When to Use | Production Default |
|---|---|---|
| ERROR | Operation failed, needs attention | Enabled |
| WARN | Degraded operation, handled gracefully | Enabled |
| INFO | Normal operation milestones | Enabled |
| DEBUG | Detailed diagnostic information | Disabled |
| TRACE | Very fine-grained execution details | Disabled |

### Logging Rules

- ALWAYS include a request/correlation ID for tracing across services
- ALWAYS use structured key-value pairs, not string interpolation
- NEVER log secrets, passwords, tokens, or PII
- NEVER log at ERROR level for expected conditions (use WARN)
- Keep log messages concise but include enough context to diagnose without reading code

---

## Distributed Tracing

### Trace Propagation

```
[Client] --trace_id--> [API Gateway] --trace_id--> [Service A] --trace_id--> [Database]
                                      --trace_id--> [Service B] --trace_id--> [Cache]
```

Every request gets a unique trace ID. Every service propagates the trace ID to downstream calls. This creates a complete picture of the request lifecycle.

### Span Design

| Span Level | What to Instrument |
|---|---|
| **Service entry** | HTTP handler, message consumer, job processor |
| **External call** | Database query, HTTP client call, cache operation |
| **Significant logic** | Business rule evaluation, data transformation |

### Rules

- Propagate trace context through all service-to-service calls
- Include span attributes: operation name, status, duration, error details
- Sample traces in production (100% is expensive; 1-10% is typical)
- Always capture 100% of error traces regardless of sampling rate

---

## Metric Naming and Design

### Naming Convention

Use a consistent hierarchy:

```
<namespace>.<subsystem>.<metric_name>.<unit>

Examples:
  app.http.request_duration.seconds
  app.http.requests_total.count
  app.db.query_duration.seconds
  app.db.connection_pool.active.count
  app.queue.messages_pending.count
```

### Metric Types

| Type | Use For | Example |
|---|---|---|
| **Counter** | Cumulative totals (only increases) | Total requests, total errors |
| **Gauge** | Current value (increases and decreases) | Active connections, queue depth |
| **Histogram** | Distribution of values | Request duration, response size |

### The Four Golden Signals

| Signal | What to Measure | Why It Matters |
|---|---|---|
| **Latency** | Request duration (p50, p95, p99) | User experience |
| **Traffic** | Requests per second | Load awareness |
| **Errors** | Error rate (percentage) | Reliability |
| **Saturation** | Resource utilization (CPU, memory, connections) | Capacity limits |

---

## Alerting Thresholds

### Alert Design Rules

- Alert on symptoms (high error rate), not causes (CPU spike)
- Every alert MUST have a runbook or action plan
- Alerts MUST be actionable -- if no one needs to respond, it is not an alert
- Use multiple severity levels to avoid alert fatigue

### Threshold Guidelines

| Metric | Warning | Critical |
|---|---|---|
| Error rate | > 1% for 5 min | > 5% for 2 min |
| Latency (p99) | > 2x baseline for 5 min | > 5x baseline for 2 min |
| CPU utilization | > 70% for 10 min | > 90% for 5 min |
| Memory utilization | > 80% for 10 min | > 95% for 5 min |
| Disk usage | > 80% | > 90% |
| Queue depth | > 2x normal for 10 min | > 10x normal for 5 min |

### Alert Anti-Patterns

| Anti-Pattern | Problem | Fix |
|---|---|---|
| Too many alerts | Alert fatigue, responders ignore them | Reduce to actionable alerts only |
| No runbook | Responder does not know what to do | Write runbook for every alert |
| Alerting on causes | Fires without user impact | Alert on symptoms instead |
| Static thresholds only | Does not adapt to traffic patterns | Use anomaly detection for variable metrics |

---

## SLO and SLA Definition

### Terminology

| Term | Definition |
|---|---|
| **SLI** (Service Level Indicator) | The metric being measured (e.g., request success rate) |
| **SLO** (Service Level Objective) | The target for the SLI (e.g., 99.9% success rate) |
| **SLA** (Service Level Agreement) | The contractual commitment with consequences for breach |
| **Error Budget** | The allowed failure rate (100% - SLO) |

### SLO Examples

| Service | SLI | SLO | Error Budget (30 days) |
|---|---|---|---|
| API | Successful responses | 99.9% | 43 minutes of downtime |
| API | Latency p99 < 500ms | 99.0% | 7.2 hours of slow responses |
| Data pipeline | Successful processing | 99.5% | 3.6 hours of failures |

### Error Budget Policy

```
Budget remaining > 50%  -> Ship features normally
Budget remaining 25-50% -> Slow down, prioritize reliability
Budget remaining < 25%  -> Feature freeze, focus on reliability
Budget exhausted        -> All hands on reliability until budget resets
```

---

## Observability Checklist

- [ ] Structured logging with correlation IDs on all services
- [ ] The four golden signals are measured (latency, traffic, errors, saturation)
- [ ] Distributed tracing propagates across service boundaries
- [ ] Metric names follow a consistent naming convention
- [ ] Alerts are actionable with linked runbooks
- [ ] SLOs are defined for critical services
- [ ] Dashboards exist for each service showing key metrics
- [ ] Sensitive data is excluded from logs and traces
- [ ] Log retention policies are configured and compliant
- [ ] Alerting thresholds are reviewed quarterly
