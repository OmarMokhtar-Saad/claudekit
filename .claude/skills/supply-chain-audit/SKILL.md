---
name: supply-chain-audit
description: Use when auditing or upgrading project dependencies — detects typosquatting, abandoned packages, excessive permissions and known CVEs, and carries the semver risk matrix and the safe incremental upgrade process.
user-invocable: false
allowed-tools: Read, Bash, Grep, Glob
---

# Supply Chain Audit

## Core Principle

**Your dependency tree is your attack surface.** Every transitive dependency is a potential entry point for malicious code. Audit the full tree, not just direct dependencies.

---

## The Audit

1. **Map the full tree** including transitive dependencies; flag risk concentration
   (single-maintainer packages many depend on, install scripts, non-registry sources).
2. **Typosquatting**: compare names against legitimate packages; flag recent,
   low-download look-alikes and unexpected scope owners.
3. **Abandoned packages**: archived repos, ownership transfers, long publish gaps.
4. **CVEs**: run every applicable audit tool and cross-reference.
5. **Lockfile integrity**: committed, hashes match, no unexpected registry URLs,
   frozen install succeeds.
6. **Permission scope**: network, filesystem, child-process or env access beyond a
   package's purpose; audit install scripts.

Read [references/tree-and-typosquatting.md](references/tree-and-typosquatting.md) when you map the tree or check names and maintenance -- per-ecosystem tree commands, typosquatting patterns and checklist, abandoned-package thresholds and what to do.
Read [references/cve-and-lockfile.md](references/cve-and-lockfile.md) when you run CVE, lockfile or permission checks -- audit commands, cross-reference sources, hash verification, install-script audit.

### Severity Action Matrix

| CVSS Score | Severity | Required Action |
|---|---|---|
| 9.0 - 10.0 | Critical | Stop. Upgrade or remove immediately. |
| 7.0 - 8.9 | High | Upgrade within 48 hours. |
| 4.0 - 6.9 | Medium | Upgrade within current sprint. |
| 0.1 - 3.9 | Low | Track. Upgrade in next dependency sweep. |

## Recommended Actions Summary

| Finding | Priority | Action |
|---|---|---|
| Known CVE (Critical/High) | Immediate | Upgrade, patch, or remove |
| Typosquatting candidate | Immediate | Verify legitimacy, remove if fraudulent |
| Abandoned package (critical path) | High | Find maintained alternative |
| Missing lockfile hashes | High | Regenerate lockfile with hashes |
| Post-install scripts (unexpected) | Medium | Audit script contents, consider `--ignore-scripts` |
| Excessive transitive deps | Medium | Evaluate lighter alternatives |
| Single-maintainer critical dep | Low | Monitor, have a contingency plan |

---

# Upgrade Lifecycle (merged from `dependency-audit`)

Its core principle stands alongside the one above.
**Dependencies are liabilities, not just features.** Every dependency added is
code you do not control. Audit regularly,
upgrade incrementally, and remove what you do not need.

Assess each CVE's reachability and exploitability in your deployment before acting,
and whether the fix introduces breaking changes. Semver risk: patch minimal, minor
low, major high (read the migration guide; 3.0.0+ jumps are multi-step).

### The Golden Rule

**One dependency at a time. One version bump at a time. Tests after every change.**


## Anti-Patterns

| Anti-Pattern | Why It Is Bad | Alternative |
|---|---|---|
| Upgrading everything at once | Cannot isolate which upgrade caused a failure | Incremental upgrades with tests |
| Ignoring audit warnings | Known vulnerabilities in production | Triage and address by severity |
| Pinning to exact versions forever | Miss security patches | Use ranges, audit regularly |
| No lock file committed | Non-reproducible builds | Always commit lock files |
| Updating without reading changelog | Breaking changes surprise you | Review changelog before every major bump |

Read [references/upgrade-lifecycle.md](references/upgrade-lifecycle.md) when you upgrade dependencies -- CVE assessment steps and triage timelines, semver and upgrade risk matrices, changelog checklist, the incremental process, rollback strategy, health signals, and when to replace.
