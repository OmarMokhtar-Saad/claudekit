---
name: dependency-audit
description: "Use when auditing or upgrading dependencies - CVE assessment, semver analysis, safe upgrade process"
user-invocable: false
---

# Dependency Audit

## Core Principle

**Dependencies are liabilities, not just features.** Every dependency added is code you do not control. Audit regularly, upgrade incrementally, and remove what you do not need.

---

## CVE Assessment Process

### Step 1: Inventory

Identify all dependency manifests and lock files:

| Ecosystem | Manifest | Lock File |
|---|---|---|
| Node.js | package.json | package-lock.json, yarn.lock, pnpm-lock.yaml |
| Python | requirements.txt, pyproject.toml | poetry.lock, pip-compile output |
| Rust | Cargo.toml | Cargo.lock |
| Go | go.mod | go.sum |
| Ruby | Gemfile | Gemfile.lock |
| Java | pom.xml, build.gradle | dependency tree output |

### Step 2: Scan

Run ecosystem-specific audit tools:

- **Node.js**: `npm audit`, `yarn audit`, or `pnpm audit`
- **Python**: `pip-audit`, `safety check`
- **Rust**: `cargo audit`
- **Go**: `govulncheck ./...`
- **Ruby**: `bundle-audit check`

### Step 3: Triage

| Severity | Action Required | Timeline |
|---|---|---|
| Critical | Upgrade immediately | Same day |
| High | Upgrade urgently | Within 1 week |
| Medium | Plan upgrade | Within 1 sprint |
| Low | Track and monitor | Next scheduled audit |

### Step 4: Assess Impact

For each vulnerability:
- Is the vulnerable code path actually reachable in your application?
- Is the vulnerability exploitable given your deployment context?
- Does the fix introduce breaking changes?

---

## Semver Compatibility Analysis

### Version Ranges

| Range | Meaning | Risk |
|---|---|---|
| Patch (1.0.x) | Bug fixes only | Minimal |
| Minor (1.x.0) | New features, backward compatible | Low |
| Major (x.0.0) | Breaking changes possible | High |

### Upgrade Risk Matrix

| Current | Target | Risk Level | Approach |
|---|---|---|---|
| 1.0.0 | 1.0.5 | Low | Batch with other patches |
| 1.0.0 | 1.3.0 | Low-Medium | Review changelog for deprecations |
| 1.0.0 | 2.0.0 | High | Dedicated upgrade, read migration guide |
| 1.0.0 | 3.0.0+ | Very High | Plan multi-step migration (1->2->3) |

### Changelog Review Checklist

Before upgrading any dependency:
- [ ] Read the changelog for breaking changes
- [ ] Check for deprecated APIs you are using
- [ ] Verify peer dependency compatibility
- [ ] Check community reports of upgrade issues
- [ ] Review migration guide (for major versions)

---

## Safe Incremental Upgrade Process

### The Golden Rule

**One dependency at a time. One version bump at a time. Tests after every change.**

### Process

```
1. Create a dedicated branch for the upgrade
2. Apply PATCH updates (all at once is usually safe)
   -> Run tests
   -> Commit if green
3. Apply MINOR updates (one package at a time)
   -> Run tests after each
   -> Commit each successful upgrade
4. Apply MAJOR updates (one package at a time)
   -> Read migration guide first
   -> Make code changes required by the upgrade
   -> Run tests
   -> Commit each successful upgrade
5. Run full verification suite
6. Review total diff before merging
```

### Rollback Strategy

- Each upgrade is a separate commit for easy revert
- If tests fail after an upgrade, revert that single commit
- If multiple upgrades interact badly, use git bisect to find the conflict
- Keep the lock file committed so exact versions are reproducible

---

## Dependency Health Signals

| Signal | Healthy | Concerning |
|---|---|---|
| Last release | Within 6 months | Over 12 months |
| Open issues | Actively triaged | Hundreds unaddressed |
| Maintainers | 2+ active | Single maintainer |
| Downloads | Stable or growing | Declining |
| License | Permissive (MIT, Apache) | Changed recently |
| Security response | Published advisories | No security policy |

---

## When to Replace a Dependency

Consider replacing a dependency when:
- It has unpatched critical CVEs with no fix timeline
- It is unmaintained (no commits in 12+ months, no response to issues)
- Its license changed to something incompatible
- A standard library or platform API now covers the same functionality
- The dependency pulls in an excessive transitive dependency tree

---

## Anti-Patterns

| Anti-Pattern | Why It Is Bad | Alternative |
|---|---|---|
| Upgrading everything at once | Cannot isolate which upgrade caused a failure | Incremental upgrades with tests |
| Ignoring audit warnings | Known vulnerabilities in production | Triage and address by severity |
| Pinning to exact versions forever | Miss security patches | Use ranges, audit regularly |
| No lock file committed | Non-reproducible builds | Always commit lock files |
| Updating without reading changelog | Breaking changes surprise you | Review changelog before every major bump |
