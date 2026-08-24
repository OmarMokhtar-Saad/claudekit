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

## Dependency Tree Analysis

### Step 1: Map the Full Tree

Generate the complete dependency tree including transitive dependencies:

| Ecosystem | Command | Output |
|---|---|---|
| Node.js | `npm ls --all --json` | Full tree with versions |
| Python | `pip-compile --generate-hashes` or `pipdeptree --json` | Pinned tree with hashes |
| Rust | `cargo tree` | Hierarchical dependency tree |
| Go | `go mod graph` | Module dependency graph |
| Java | `mvn dependency:tree` or `gradle dependencies` | Resolved dependency tree |

### Step 2: Identify Risk Concentration

Flag dependencies that appear as transitive dependencies of many packages. A compromised package deep in the tree can affect the entire application.

**Red flags in the tree:**
- A single maintainer package depended on by 10+ other packages
- Packages with post-install scripts (`scripts.postinstall` in package.json)
- Native binary dependencies pulled from non-registry sources
- Git URLs or tarball URLs instead of registry references

---

## Typosquatting Detection

### Common Typosquatting Patterns

| Pattern | Legitimate | Typosquat Example |
|---|---|---|
| Character swap | `lodash` | `lodahs`, `lodashs` |
| Hyphen manipulation | `cross-env` | `crossenv`, `cross--env` |
| Scope confusion | `@babel/core` | `babel-core` (outdated), `@bable/core` |
| Prefix/suffix | `express` | `express-js`, `node-express` |
| Homoglyph | `request` | `requets` (with zero-width chars) |

### Detection Checklist

- [ ] Compare each dependency name against known legitimate packages
- [ ] Check for packages published within the last 30 days with names similar to popular packages
- [ ] Verify npm scope owners match expected organizations
- [ ] Flag any dependency with fewer than 100 weekly downloads that shares a name pattern with a popular package
- [ ] Check for packages with identical descriptions but different names

---

## Abandoned Package Indicators

| Signal | Threshold | Risk |
|---|---|---|
| Last publish date | > 24 months ago | High - no security patches |
| Open issues without response | > 50 unanswered | Medium - unmaintained |
| Last commit to repository | > 18 months ago | High - likely abandoned |
| Repository archived | Archived flag set | Critical - confirmed abandoned |
| Maintainer account activity | No activity in 12 months | High - account may be hijacked |
| Transfer of ownership | Recent transfer to unknown entity | Critical - investigate immediately |

### What To Do With Abandoned Dependencies

1. Check if a maintained fork exists
2. Evaluate whether the functionality can be replaced with a standard library call
3. If the package is small, consider inlining the code (with license compliance)
4. If no alternative exists, document the risk and monitor for CVEs

---

## CVE Cross-Referencing

### Audit Commands (Run All Applicable)

```
# Node.js
npm audit --json | jq '.vulnerabilities | to_entries[] | {name: .key, severity: .value.severity}'

# Python
pip-audit --format=json --desc

# Rust
cargo audit --json

# Go
govulncheck -json ./...
```

### Cross-Reference Sources

- **NVD (NIST):** https://nvd.nist.gov/ - comprehensive CVE database
- **GitHub Advisory Database:** `gh api /advisories` - GitHub-curated advisories
- **OSV.dev:** https://osv.dev/ - open-source vulnerability database
- **Snyk Vulnerability DB:** package-specific vulnerability data

### Severity Action Matrix

| CVSS Score | Severity | Required Action |
|---|---|---|
| 9.0 - 10.0 | Critical | Stop. Upgrade or remove immediately. |
| 7.0 - 8.9 | High | Upgrade within 48 hours. |
| 4.0 - 6.9 | Medium | Upgrade within current sprint. |
| 0.1 - 3.9 | Low | Track. Upgrade in next dependency sweep. |

---

## Lockfile Integrity Verification

### Lockfile Checks

- [ ] Lockfile exists and is committed to version control
- [ ] Lockfile hashes match registry-published hashes
- [ ] No unexpected registry URL changes (e.g., pointing to a private registry that was not configured)
- [ ] No `resolved` URLs pointing to non-standard registries or git repos
- [ ] Lockfile version is consistent with the package manager version in use
- [ ] Running `install --frozen-lockfile` (or equivalent) succeeds without modifications

### Integrity Hash Verification

| Ecosystem | Hash Format | Verification |
|---|---|---|
| npm | `sha512` in `package-lock.json` | `npm ci` fails on mismatch |
| yarn | `sha512` in `yarn.lock` | `yarn install --frozen-lockfile` |
| pip | `--hash` in `requirements.txt` | `pip install --require-hashes` |
| cargo | `checksum` in `Cargo.lock` | `cargo install --locked` |

---

## Permission Scope Analysis

### Node.js Package Permissions

Flag packages that request or use capabilities beyond their stated purpose:

| Permission | Concern | Example |
|---|---|---|
| Network access | Data exfiltration | A CSS parser making HTTP requests |
| File system write | Arbitrary file modification | A linting tool writing outside project dir |
| Child process spawn | Command execution | A date formatting library spawning shells |
| Environment variable read | Credential harvesting | A color library reading `AWS_SECRET_ACCESS_KEY` |

### Install Script Audit

Review all packages with install lifecycle scripts:

```
# List packages with install scripts (Node.js)
npm query ':attr(scripts, [postinstall])' --json

# Check for preinstall/postinstall in the full tree
grep -r "postinstall\|preinstall" node_modules/*/package.json | head -50
```

---

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

Everything above finds what is wrong with the tree you have. This half is what you
do about it: assessing a CVE's actual reachability, judging semver risk, and moving
versions without losing the ability to say which bump broke the build. Merged from
the `dependency-audit` skill, which is gone; the name resolves here through the
registry `renamed` alias map.

Its core principle stands alongside the one above.
**Dependencies are liabilities, not just features.** Every dependency added is
code you do not control. Audit regularly,
upgrade incrementally, and remove what you do not need.

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

