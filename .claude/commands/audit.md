---
description: "Comprehensive codebase audit — runs Explore + Silent Failure Hunter + Security Scanner in parallel"
argument-hint: "[--security|--errors|--performance|--all]"
model: sonnet
---

# Audit Command

Run a comprehensive codebase audit using parallel specialist agents. Each agent is read-only — no changes are made, only a prioritized report of issues.

## Mandatory Skills

- **using-superpowers** - Core capabilities
- **multi-agent-coordination** - Safe parallel agent execution
- **dispatching-parallel-agents** - Parallel investigation

## Task

Run audit: $ARGUMENTS

---

## Audit Modes

### `--all` (default) — Full audit: Security + Errors + Performance

Runs three specialist agents in parallel:

```
[Silent Failure Hunter]    ←── parallel ──→    [Security Scanner]
         ↓                                              ↓
         └──────────── [Synthesized Report] ───────────┘
                                 ↓
                    [Performance Optimizer] (Phase 2)
```

### `--security` — Security scan only
Routes to Security Scanner agent.

### `--errors` — Error handling audit only  
Routes to Silent Failure Hunter agent.

### `--performance` — Performance bottleneck audit only
Routes to Performance Optimizer agent.

---

## Execution Steps

### Phase 1: Scope Assessment

Scope comes from `$ARGUMENTS` when given (e.g. `/audit src/payments/`); otherwise detect the
project's actual source layout first — do not assume `src/` or any fixed language list:

```bash
# Understand the codebase size before running (adjust dir/extensions to the detected stack)
echo "Files to audit:"
find src/ -name "*.ts" -o -name "*.py" -o -name "*.go" 2>/dev/null | wc -l

echo "Test coverage (if available):"
cat coverage/coverage-summary.json 2>/dev/null | python3 -c "
import json,sys
try:
    data = json.load(sys.stdin)
    total = data.get('total', {})
    print(f'  Lines: {total.get(\"lines\", {}).get(\"pct\", \"?\")!s}%')
    print(f'  Branches: {total.get(\"branches\", {}).get(\"pct\", \"?\")!s}%')
except: print('  Not available')
" 2>/dev/null
```

### Phase 2: Parallel Specialist Audit

Spawn ALL specialists in ONE message (they are read-only; spawning one per turn serializes
the audit). Spawn per `.claude/agents/_shared/INVOCATION.md` with each agent's scoped tool
row (`Read,Grep,Glob` for the scanners):

**Agent 1 — Silent Failure Hunter:** Scan for empty catches, swallowed errors, dangerous fallbacks
**Agent 2 — Security Scanner:** Run static analysis, check for OWASP Top 10, dependency CVEs
**Agent 3 — Performance Optimizer** (only with `--all`/`--performance`): hot paths, N+1, allocations

Each specialist must return its own scan counts alongside findings — the commands it ran and
what they covered. Synthesize after all return.

### Phase 3: Synthesized Report

```
## Comprehensive Audit Report

### Executive Summary
Files audited: N | Critical: N | High: N | Medium: N | Low: N

### Critical Issues (Fix Before Merge)
[ranked by impact × exploitability]
1. [CRITICAL] [category] Description — File:Line

### High Priority (Fix This Sprint)
...

### Medium Priority (Fix This Quarter)
...

### Audit Coverage
- Error handling: [count reported by Silent Failure Hunter — never invent this]
- Security checks: [count reported by Security Scanner — never invent this]
- Dependencies: [count reported by Security Scanner — never invent this]

### Coverage Gaps (MANDATORY — especially when zero criticals are found)
- [what was NOT scanned: dirs excluded, languages unsupported, checks skipped]
- A clean audit without a gaps list is an unverified audit

### Top 5 Riskiest Files
1. path/to/file.ts — N issues (N critical)
...

### Recommended Action Plan
Week 1: Fix critical issues
Week 2: Address high priority
Week 3: Code review for medium issues
```

---

## Usage Examples

- `/audit` — Full audit (security + error handling)
- `/audit --security` — Security scan only
- `/audit --errors` — Error handling audit only
- `/audit --performance` — Performance bottleneck analysis
- `/audit src/payments/` — Audit only the payments module

## Notes

- All audit agents are **read-only** — no files are modified
- Findings are ranked by severity × exploitability
- Run monthly or before major releases
- Use `/security` for a pure security scan; `/audit` is broader
