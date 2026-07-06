---
name: usage-monitoring
description: "Use when tracking token usage and costs -- monitors tokens per command, per agent, per session, calculates burn rate and cost estimates, and provides optimization suggestions."
---

# Usage Monitoring

## Purpose

Track and analyze token consumption across Claude Code sessions to optimize cost, identify inefficiencies, and provide actionable insights for reducing token usage without sacrificing output quality.

---

## Tracked Metrics

### Per-Command Metrics

| Metric | Description |
|--------|-------------|
| Input tokens | Tokens sent in the prompt (context + user message) |
| Output tokens | Tokens generated in the response |
| Total tokens | Input + Output |
| Context size | Current context window utilization at time of command |
| Tool calls | Number of tool invocations triggered by the command |
| Files read | Number of files read as part of the command |

### Per-Agent Metrics

| Metric | Description |
|--------|-------------|
| Total tokens consumed | Cumulative tokens across all invocations |
| Average tokens per invocation | Mean tokens per agent activation |
| Invocation count | How many times the agent was activated |
| Efficiency ratio | Output tokens / Input tokens (lower = more context-heavy) |
| Most expensive operation | The single invocation that consumed the most tokens |

### Per-Session Metrics

| Metric | Description |
|--------|-------------|
| Session total tokens | Sum of all tokens in the session |
| Session duration | Wall-clock time from start to end |
| Burn rate | Tokens per minute |
| Cost estimate | Estimated dollar cost based on model pricing |
| Context resets | Number of times context window was reset/compacted |
| Peak context | Maximum context window utilization reached |

---

## Cost Estimation

### Model Pricing (Reference)

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|----------------------|----------------------|
| Opus | $15.00 | $75.00 |
| Sonnet | $3.00 | $15.00 |
| Haiku | $0.25 | $1.25 |

### Calculation

```
session_cost = sum(
  for each command:
    (input_tokens / 1M * input_price) +
    (output_tokens / 1M * output_price)
)
```

### Projections

- **Hourly rate**: session_cost / session_hours
- **Daily projection**: hourly_rate * estimated_daily_hours
- **Monthly projection**: daily_projection * working_days

---

## Usage Dashboard

Display on demand (`/usage`) or at session end:

```
=== Usage Dashboard ===

Session: 2h 15m | 847K total tokens | ~$4.23 estimated cost

Token Breakdown by Agent:
  Planner:      312K tokens (37%)  ████████████░░░░░░░  $1.56
  Implementer:  198K tokens (23%)  ████████░░░░░░░░░░░  $0.89
  Reviewer:     156K tokens (18%)  ██████░░░░░░░░░░░░░  $0.78
  Coordinator:   89K tokens (11%)  ████░░░░░░░░░░░░░░░  $0.45
  Verifier:      52K tokens (6%)   ██░░░░░░░░░░░░░░░░░  $0.26
  Other:         40K tokens (5%)   ██░░░░░░░░░░░░░░░░░  $0.29

Top 5 Most Expensive Commands:
  1. /plan "Add auth system"           142K tokens  $0.71
  2. /implement                        118K tokens  $0.53
  3. /coordinator "Migrate schema"      98K tokens  $0.49
  4. /review                            87K tokens  $0.44
  5. /debug "Login 500 error"           76K tokens  $0.38

Burn Rate:
  Current: 6.3K tokens/min ($0.031/min)
  Average: 5.8K tokens/min ($0.029/min)

Context Window:
  Current: 62% utilized
  Peak: 84% (at 1h 42m)
  Resets: 1

Efficiency:
  Input/Output ratio: 3.2:1 (typical: 2-4:1)
  Files read: 47 unique files
  Tool calls: 132

=== End Dashboard ===
```

---

## Cost Alerts

### Threshold Alerts

| Alert | Threshold | Action |
|-------|-----------|--------|
| Session cost warning | > $5.00 | Display warning, suggest token-efficient mode |
| Session cost critical | > $15.00 | Display alert, recommend reviewing approach |
| Burn rate warning | > 10K tokens/min | Suggest reducing context, using targeted reads |
| Context high | > 75% utilization | Suggest context compaction |
| Context critical | > 90% utilization | Auto-activate token-efficient mode |
| Single command expensive | > 100K tokens | Flag for review, suggest breaking into smaller tasks |

### Alert Format

```
[COST ALERT] Session cost has exceeded $5.00 (currently $5.23)
  Burn rate: 8.1K tokens/min
  Suggestion: Activate token-efficient mode (/mode token-efficient)
  Suggestion: Use targeted file reads instead of full-file reads
  Suggestion: Break large tasks into smaller, focused sub-tasks
```

---

## Optimization Suggestions

Based on usage patterns, provide targeted recommendations:

| Pattern Detected | Suggestion |
|-----------------|------------|
| Same file read multiple times | Cache file contents, read once and reference |
| Large files read fully | Use line-range reads (offset + limit) |
| Many small tool calls | Batch operations where possible |
| High input-to-output ratio (> 5:1) | Context is bloated -- compact or reset |
| Agent re-exploring already-mapped code | Load project index first (context-priming) |
| Long prose explanations | Switch to token-efficient mode |
| Repeated failed attempts | Step back, analyze root cause before retrying |

---

## Data Storage

Usage data is stored in `.claude/usage-log.jsonl` (JSON Lines format):

```json
{"ts":"2024-01-15T10:23:45Z","type":"command","cmd":"/plan","agent":"planner","input_tokens":45200,"output_tokens":12800,"tool_calls":8,"files_read":12,"duration_ms":34500}
{"ts":"2024-01-15T10:24:20Z","type":"command","cmd":"/review","agent":"reviewer","input_tokens":38100,"output_tokens":8900,"tool_calls":3,"files_read":5,"duration_ms":21200}
```

- One line per command invocation
- File is append-only within a session
- New session creates a new file or appends with a session delimiter
- NEVER log file contents, only file paths and token counts

---

## Integration

- **token-optimization** skill is auto-activated when cost alerts trigger
- **session-continuity** includes usage summary in session state
- **coordinator** uses usage data to select cheaper agents when appropriate (Haiku over Sonnet for simple tasks)
- **hook-profiling** data correlates with usage data for full performance picture
