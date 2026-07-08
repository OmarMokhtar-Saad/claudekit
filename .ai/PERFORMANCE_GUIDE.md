# Performance Guide

ClaudeKit's scarce resources are **tokens** and **hook latency**, not CPU/memory. (Install is fast and offline; CLI is fine — audit Performance 68/100 with all findings in the two areas below.)

## Token economy

- Routing tax: coordinator boot + skills-registry + frontmatter scanning ≈ 12.4K tokens; full coordinator sessions were measured 28–35K before work starts (audit ai-review §5). Mitigations (task 009 / roadmap §2.4): ≤2 mandatory skill loads per agent with inline 5-line digests; stop double-loading registry + frontmatter (~7K/session); consolidate near-duplicate assets (008).
- File-based handoffs are the core token optimization (~85% claimed reduction vs context passing — **benchmark and publish** per task 010 before repeating the number in marketing).
- Model tiering saves real money: haiku for verifier/gitOps/documenter/model-router; opus only for judgment roles. `/model-route` scores tasks; `/context-budget` audits consumption.
- Skills for users: token-optimization (3 compression levels), token-budget-advisor (25/50/75/100% depth), usage-monitoring, context-keeper.

## Hook latency

- Current: 9–15 process spawns per tool call ≈ 150–300 ms (each settings.json entry = bash -c → script → python3 for JSON). Roadmap: **one dispatcher per event** (~100 ms/call saving) — likely a single Python dispatcher long-term (roadmap §3.5).
- Rules meanwhile: async-background (`&`) anything non-blocking (already done for suggest-compact, cost-tracker, notify, format-typecheck); never add a blocking hook without measuring; `hook-profiling` skill + `harness-optimizer` agent exist for exactly this.

## Ops engine

Atomic writes + per-file backups are I/O-bound and fine at normal plan sizes; MAX_DELETIONS and single-file granularity keep transactions small by design. Don't batch-optimize at the cost of rollback granularity.

## CI

Full matrix (2 OS × 4 Python) is the slowest stage; keep it — it catches the macOS shell class of bugs. Cheap gates (docs-drift, dangling-hooks, shellcheck, permission-gate) run in seconds and should stay separate jobs for clear failure signals.

## When adding anything

Ask: does it add a hook spawn on the hot path? another mandatory skill load? another frontmatter scan? If yes, it needs a measured justification (hook-profiling / context-budget output) in the PR.
