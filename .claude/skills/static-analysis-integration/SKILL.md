---
name: static-analysis-integration
description: Static analysis toolkit integration with Semgrep, ESLint security plugins, Bandit, and SARIF report parsing. Run and interpret security-focused static analysis tools.
disable-model-invocation: true
allowed-tools: Read, Bash, Grep, Glob
---

# Static Analysis Integration

## Core Principle

**Static analysis finds the bugs humans miss.** Run automated security scanners early and often. Interpret results with context - not every finding is exploitable, but every finding deserves triage.

---

## Tool Selection by Language

| Language | Primary Tool | Secondary Tool | Install Command |
|---|---|---|---|
| All languages | Semgrep | - | `pip install semgrep` or `brew install semgrep` |
| Python | Bandit | Semgrep | `pip install bandit` |
| JavaScript/TypeScript | ESLint + security plugin | Semgrep | `npm install eslint eslint-plugin-security` |
| Go | gosec | Semgrep | `go install github.com/securego/gosec/v2/cmd/gosec@latest` |
| Java | SpotBugs + Find Security Bugs | Semgrep | Maven/Gradle plugin |
| Rust | cargo-audit + clippy | Semgrep | `cargo install cargo-audit` |
| C/C++ | cppcheck + Semgrep | Flawfinder | `brew install cppcheck` |
| Ruby | Brakeman | Semgrep | `gem install brakeman` |

---

## Semgrep (All Languages)

### Running Semgrep

```bash
# Run with the default security ruleset (recommended starting point)
semgrep --config=p/security .

# Run with OWASP Top 10 rules
semgrep --config=p/owasp-top-ten .

# Run language-specific security rules
semgrep --config=p/python .
semgrep --config=p/typescript .
semgrep --config=p/golang .

# Output in SARIF format for downstream parsing
semgrep --config=p/security --sarif -o results.sarif .

# Run with multiple rulesets
semgrep --config=p/security --config=p/secrets .

# Scan only changed files (CI optimization)
semgrep --config=p/security --include='*.py' --include='*.js' .
```

### Key Semgrep Rulesets

| Ruleset | Purpose | Command Flag |
|---|---|---|
| `p/security` | General security issues | `--config=p/security` |
| `p/owasp-top-ten` | OWASP Top 10 coverage | `--config=p/owasp-top-ten` |
| `p/secrets` | Hardcoded secrets | `--config=p/secrets` |
| `p/ci` | CI-optimized ruleset | `--config=p/ci` |
| `p/supply-chain` | Dependency confusion, typosquatting | `--config=p/supply-chain` |

---

## Bandit (Python)

### Running Bandit

```bash
# Scan entire project
bandit -r . -f json -o bandit-results.json

# Scan with severity filter
bandit -r . -ll  # Only medium and higher severity

# Skip test directories
bandit -r . --exclude ./tests,./test

# Output in SARIF format
bandit -r . -f sarif -o bandit-results.sarif

# Show confidence level
bandit -r . -ll -ii  # Medium+ severity, medium+ confidence
```

### Bandit Severity Reference

| Test ID | Name | Severity | What It Finds |
|---|---|---|---|
| B101 | assert_used | Low | `assert` used for security checks (stripped in optimized mode) |
| B102 | exec_used | Medium | Dynamic code interpretation calls |
| B103 | set_bad_file_permissions | Medium | Overly permissive file modes |
| B104 | hardcoded_bind_all | Medium | Binding to `0.0.0.0` |
| B105-B107 | hardcoded_password | Low | Hardcoded credentials |
| B108 | hardcoded_tmp_directory | Medium | Hardcoded `/tmp` paths |
| B301 | pickle | Medium | Unsafe deserialization |
| B303 | md5/sha1 | Medium | Weak hash functions |
| B501 | request_with_no_cert_validation | High | `verify=False` in requests |
| B602 | subprocess_popen_with_shell | High | Shell=True in subprocess |
| B608 | hardcoded_sql_expressions | Medium | SQL string construction |

---

## ESLint Security Plugin (JavaScript/TypeScript)

### Setup

```json
// .eslintrc.json
{
  "plugins": ["security"],
  "extends": ["plugin:security/recommended-legacy"],
  "rules": {
    "security/detect-object-injection": "warn",
    "security/detect-non-literal-regexp": "warn",
    "security/detect-unsafe-regex": "error",
    "security/detect-buffer-noassert": "error",
    "security/detect-eval-with-expression": "error",
    "security/detect-no-csrf-before-method-override": "error",
    "security/detect-possible-timing-attacks": "warn",
    "security/detect-child-process": "warn"
  }
}
```

### Running

```bash
# Run security rules only
npx eslint --plugin security --rule 'security/detect-eval-with-expression: error' .

# Run with full config
npx eslint --ext .js,.ts,.jsx,.tsx . -f json -o eslint-results.json

# Output in SARIF (requires formatter)
npx eslint . -f @microsoft/eslint-formatter-sarif -o eslint-results.sarif
```

---

## SpotBugs + Find Security Bugs (Java)

### Maven Setup

```xml
<plugin>
  <groupId>com.github.spotbugs</groupId>
  <artifactId>spotbugs-maven-plugin</artifactId>
  <version>4.8.3.1</version>
  <configuration>
    <plugins>
      <plugin>
        <groupId>com.h3xstream.findsecbugs</groupId>
        <artifactId>findsecbugs-plugin</artifactId>
        <version>1.13.0</version>
      </plugin>
    </plugins>
    <effort>Max</effort>
    <threshold>Low</threshold>
  </configuration>
</plugin>
```

### Running

```bash
# Maven
mvn spotbugs:check
mvn spotbugs:gui  # Visual report

# Gradle
gradle spotbugsMain
```

---

## Cargo Audit and Clippy (Rust)

```bash
# Check dependencies for known vulnerabilities
cargo audit

# Run clippy with security-related lints
cargo clippy -- -W clippy::unwrap_used -W clippy::expect_used \
  -W clippy::panic -W clippy::indexing_slicing

# Generate advisory report as JSON
cargo audit --json
```

---

## SARIF Report Parsing

### SARIF Structure

SARIF (Static Analysis Results Interchange Format) is the standard output format. Key fields:

```
results.sarif
  -> runs[]
    -> tool.driver.name          # Tool that produced the result
    -> results[]
      -> ruleId                  # Rule identifier (e.g., "B602")
      -> level                   # "error", "warning", "note"
      -> message.text            # Human-readable description
      -> locations[]
        -> physicalLocation
          -> artifactLocation.uri    # File path
          -> region.startLine        # Line number
```

### Parsing SARIF with jq

```bash
# List all findings with severity
jq '.runs[].results[] | {rule: .ruleId, level: .level, file: .locations[0].physicalLocation.artifactLocation.uri, line: .locations[0].physicalLocation.region.startLine, message: .message.text}' results.sarif

# Count findings by severity
jq '[.runs[].results[] | .level] | group_by(.) | map({level: .[0], count: length})' results.sarif

# Filter to errors only
jq '.runs[].results[] | select(.level == "error")' results.sarif

# Get unique rules triggered
jq '[.runs[].results[] | .ruleId] | unique' results.sarif
```

---

## Severity Classification

### Unified Severity Mapping

| Tool Native | Normalized Severity | Action |
|---|---|---|
| Semgrep ERROR | Critical/High | Fix before merge |
| Semgrep WARNING | Medium | Fix in current sprint |
| Semgrep INFO | Low | Track for future fix |
| Bandit High/High | Critical | Fix before merge |
| Bandit Medium/Medium | Medium | Fix in current sprint |
| Bandit Low/Low | Low | Track for future fix |
| ESLint error | High | Fix before merge |
| ESLint warn | Medium | Evaluate and address |
| SpotBugs High | High | Fix before merge |
| Cargo audit (CVSS 7+) | High | Fix before merge |

---

## False Positive Assessment

### When to Suppress a Finding

A finding may be a false positive if:

| Criterion | Example | Action |
|---|---|---|
| Unreachable code path | Dead code flagged for injection | Suppress with comment explaining why |
| Test code only | Test fixture uses dynamic evaluation for testing | Suppress in test config |
| Intentional design | Crypto library implementing MD5 for compatibility | Suppress with security review approval |
| Already mitigated | Input is validated upstream before reaching flagged function | Suppress with comment referencing the validation |

### Suppression Best Practices

- Always add a comment explaining WHY the finding is suppressed
- Use tool-specific inline suppression (e.g., `# nosec B602` for Bandit, `// nosemgrep: rule-id`)
- Track all suppressions and review them periodically
- Never suppress an entire category of findings globally
- Require security team approval for suppressing Critical/High findings

---

## CI Integration Checklist

- [ ] Static analysis runs on every pull request
- [ ] Findings at High/Critical severity block merge
- [ ] SARIF results are uploaded to GitHub Security tab (if using GitHub)
- [ ] Baseline is established so only new findings are flagged
- [ ] Tool versions are pinned for reproducible results
- [ ] Custom rules are version-controlled alongside the codebase
- [ ] Suppression inventory is reviewed quarterly
