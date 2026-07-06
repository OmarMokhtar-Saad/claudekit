---
name: hook-profiling
description: "Use when diagnosing slow hooks or optimizing hook performance -- measures execution time, output size, failure rates, and provides color-coded performance alerts."
---

# Hook Profiling

## Purpose

Profile the performance of Claude Code hooks (PreToolUse, PostToolUse, Notification) to identify bottlenecks, excessive output, and reliability issues. Provides actionable metrics and optimization recommendations.

---

## Profiling Metrics

### Per-Hook Metrics

| Metric | Description | Unit |
|--------|-------------|------|
| Execution time | Wall-clock time from hook start to exit | ms |
| Output size | Number of characters in hook stdout | chars |
| Exit code | Return code (0 = success) | int |
| Failure rate | Percentage of runs that return non-zero | % |
| Invocation count | How many times the hook fired in the session | count |
| Mean time | Average execution time across invocations | ms |
| P95 time | 95th percentile execution time | ms |
| Max time | Slowest single invocation | ms |

### Aggregate Metrics

| Metric | Description |
|--------|-------------|
| Total hook time | Sum of all hook execution times in the session |
| Hook overhead % | Total hook time / total session time |
| Slowest hook | Which hook has the highest mean execution time |
| Most frequent hook | Which hook fires most often |
| Most failing hook | Which hook has the highest failure rate |

---

## Performance Thresholds

| Level | Execution Time | Output Size | Failure Rate | Indicator |
|-------|---------------|-------------|-------------|-----------|
| Good | < 500ms | < 5,000 chars | < 2% | GREEN |
| Warning | 500ms - 1s | 5,000 - 20,000 chars | 2% - 10% | YELLOW |
| Slow | 1s - 5s | 20,000 - 100,000 chars | 10% - 25% | ORANGE |
| Critical | > 5s | > 100,000 chars | > 25% | RED |

---

## Profiling Commands

### Profile a Single Hook

```
/hook-profile <hook-name>
```

1. Run the hook 5 times with representative inputs
2. Measure execution time, output size, and exit code for each run
3. Calculate mean, median, P95, and max
4. Display results with color-coded threshold indicators

**Output:**

```
--- Hook Profile: PreToolUse/lint-check ---
Runs: 5

  Run 1: 342ms  | 1.2K chars | exit 0  [GREEN]
  Run 2: 389ms  | 1.3K chars | exit 0  [GREEN]
  Run 3: 1204ms | 1.1K chars | exit 0  [ORANGE]
  Run 4: 356ms  | 1.2K chars | exit 0  [GREEN]
  Run 5: 371ms  | 1.2K chars | exit 0  [GREEN]

Summary:
  Mean:    532ms  [WARNING]
  Median:  371ms  [GREEN]
  P95:     1204ms [ORANGE]
  Max:     1204ms [ORANGE]
  Output:  ~1.2K chars avg  [GREEN]
  Failures: 0/5 (0%)  [GREEN]

Recommendation: P95 exceeds 1s threshold. Run 3 was an outlier --
investigate if it was caused by cold cache or disk I/O contention.
---
```

### Batch Profile All Hooks

```
/hook-profile all
```

1. Discover all configured hooks from `.claude/settings.json` and `.claude/settings.local.json`
2. Profile each hook sequentially (5 runs each)
3. Display a summary table sorted by mean execution time (slowest first)

**Output:**

```
--- Hook Profile: All Hooks ---

| Hook                        | Mean    | P95     | Max     | Failures | Status   |
|-----------------------------|---------|---------|---------|----------|----------|
| PreToolUse/security-scan    | 3.2s    | 4.8s    | 5.1s    | 0%       | CRITICAL |
| PreToolUse/lint-check       | 532ms   | 1.2s    | 1.2s    | 0%       | WARNING  |
| PostToolUse/format          | 245ms   | 312ms   | 320ms   | 4%       | WARNING  |
| Notification/log            | 12ms    | 18ms    | 22ms    | 0%       | GREEN    |

Total hook overhead: ~4.0s per tool invocation
Recommendation: security-scan is CRITICAL -- consider caching results
or running asynchronously.
---
```

### Statistical Profile

```
/hook-profile <hook-name> --runs 20
```

Run the hook 20 times to get statistically significant data. Useful for hooks with variable performance.

---

## Optimization Recommendations

Based on profiling results, provide specific advice:

| Issue | Recommendation |
|-------|---------------|
| Execution time > 5s | Move heavy computation to async/background. Cache results. Consider skip conditions. |
| Execution time > 1s | Add skip conditions for irrelevant tool invocations. Cache intermediate results. |
| Output > 20K chars | Truncate output. Summarize instead of listing. Write details to a log file instead. |
| Failure rate > 10% | Check for missing dependencies, permissions issues, or flaky external calls. Add error handling. |
| Hook runs on every tool | Add tool-type filtering (e.g., only run lint on Write operations). |
| Same result repeated | Add caching with TTL. Skip if input hasn't changed since last run. |

---

## Hook Skip Conditions

Common patterns to reduce unnecessary hook invocations:

```bash
# Only run on file write operations
if [ "$TOOL_NAME" != "Write" ] && [ "$TOOL_NAME" != "Edit" ]; then
  exit 0
fi

# Only run on specific file types
case "$FILE_PATH" in
  *.py|*.js|*.ts) ;; # continue
  *) exit 0 ;;        # skip
esac

# Skip if file hasn't changed since last check
HASH=$(md5sum "$FILE_PATH" | cut -d' ' -f1)
if [ "$HASH" = "$(cat .claude/cache/last-lint-hash 2>/dev/null)" ]; then
  exit 0
fi
```

---

## Integration

- Run automatically when a session feels slow
- Results feed into **usage-monitoring** for cost/performance correlation
- **coordinator** uses profiling data to decide whether to disable slow hooks temporarily
