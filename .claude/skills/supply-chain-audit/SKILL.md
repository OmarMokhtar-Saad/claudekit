---
name: supply-chain-audit
description: Audit supply-chain threat landscape of project dependencies. Detect typosquatting, abandoned packages, excessive permissions, and known CVEs in the dependency tree.
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
