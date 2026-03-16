---
name: deps
description: "Audit and manage project dependencies for vulnerabilities and updates"
model: sonnet
---

# Deps Command

Audit project dependencies for vulnerabilities, outdated packages, and upgrade opportunities.

## Mandatory Skills

You MUST load and apply the following skills before proceeding:

- **using-superpowers** - Core agent capabilities and tool usage
- **security-checklist** - Dependency security validation

## Task

Dependency audit: $ARGUMENTS

## Workflow

### Phase 1: Discovery
- Identify all dependency manifests in the project (package.json, requirements.txt, Cargo.toml, go.mod, pom.xml, Gemfile, etc.)
- Read lock files for pinned versions (package-lock.json, yarn.lock, poetry.lock, Cargo.lock, etc.)
- Categorize dependencies: runtime, development, optional, peer

### Phase 2: CVE Scanning
- Cross-reference installed versions against known vulnerability patterns
- Run available audit tools for the detected ecosystem:
  - Node.js: `npm audit` or `yarn audit`
  - Python: `pip audit` or `safety check`
  - Rust: `cargo audit`
  - Go: `govulncheck`
  - Ruby: `bundle audit`
- Flag any dependencies with known critical or high severity CVEs

### Phase 3: Outdated Package Detection
- Run ecosystem-specific outdated checks:
  - Node.js: `npm outdated`
  - Python: `pip list --outdated`
  - Rust: `cargo outdated`
  - Go: `go list -m -u all`
- Categorize updates by semver impact: patch, minor, major
- Identify packages that are multiple major versions behind

### Phase 4: Risk Assessment
- Flag unmaintained packages (no updates in 12+ months)
- Identify packages with known deprecation notices
- Check for packages with very few maintainers (bus factor risk)
- Note any packages with restrictive license changes

### Phase 5: Report
Produce upgrade recommendations with risk assessment.

## Output Format

```
## Dependency Audit Report

### Summary
- **Ecosystems**: [detected package managers]
- **Total Dependencies**: N (runtime: X, dev: Y)
- **Vulnerabilities Found**: N (critical: X, high: Y, medium: Z)
- **Outdated Packages**: N (major: X, minor: Y, patch: Z)

### Vulnerabilities
| Package | Current | CVE | Severity | Fixed In | Action |
|---|---|---|---|---|---|
| ... | ... | ... | ... | ... | Upgrade/Replace/Monitor |

### Outdated Packages
| Package | Current | Latest | Update Type | Breaking Changes | Priority |
|---|---|---|---|---|---|
| ... | ... | ... | major/minor/patch | Yes/No/Unknown | HIGH/MEDIUM/LOW |

### Upgrade Recommendations
1. **Immediate** (security fixes):
   - [package]: upgrade from X to Y (fixes CVE-XXXX)
2. **Soon** (minor/patch updates with no breaking changes):
   - [package]: upgrade from X to Y
3. **Planned** (major updates requiring migration):
   - [package]: upgrade from X to Y (see migration guide)

### Risk Flags
- [unmaintained, deprecated, or problematic packages]

### Safe Upgrade Process
1. Create a feature branch
2. Apply patch updates first, run tests
3. Apply minor updates, run tests
4. Apply major updates one at a time, run tests after each
5. Run full verification suite before merging
```

## Usage Examples

- `/deps` -- Full dependency audit for all ecosystems
- `/deps audit` -- Focus on vulnerability scanning
- `/deps outdated` -- Show only outdated packages
- `/deps upgrade recommendations` -- Prioritized upgrade plan
- `/deps check package-name` -- Audit a specific package

## Notes

- This is a read-only audit -- no packages are installed or upgraded
- If audit tools are not available, fall back to manual version analysis
- Always recommend incremental upgrades over bulk updates
- Flag any dependency that requires a major version jump with migration notes
