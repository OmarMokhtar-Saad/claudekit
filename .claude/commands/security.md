---
name: security
description: "Run security analysis on codebase or specific files"
model: opus
---

# Security Command

Run an active security analysis on the codebase or specific files to identify vulnerabilities.

## Mandatory Skills

You MUST load and apply the following skills before proceeding:

- **using-superpowers** - Core agent capabilities and tool usage
- **security-checklist** - OWASP Top 10 compliance and security patterns

## Task

Security analysis: $ARGUMENTS

## Scope

If arguments specify files or directories, limit analysis to those paths. If no arguments are provided, run a full codebase scan.

## Workflow

### Phase 1: Reconnaissance
- Identify the project language(s), framework(s), and build system
- Locate dependency manifests (package.json, requirements.txt, Cargo.toml, go.mod, etc.)
- Identify entry points (API routes, command handlers, event listeners)
- Map authentication and authorization boundaries

### Phase 2: OWASP Top 10 Scan
Actively search the codebase for each category:

| # | Category | Search Strategy |
|---|---|---|
| A01 | Broken Access Control | Grep for missing auth checks on routes/endpoints |
| A02 | Cryptographic Failures | Search for weak hashing, hardcoded keys, plain-text storage |
| A03 | Injection | Find user input reaching shell, SQL, or eval without sanitization |
| A04 | Insecure Design | Review for missing rate limiting, CSRF protection, input validation |
| A05 | Security Misconfiguration | Check debug mode, default credentials, verbose errors in config |
| A06 | Vulnerable Components | Cross-reference dependencies against known CVE databases |
| A07 | Auth Failures | Check session management, password policies, token handling |
| A08 | Data Integrity Failures | Look for unsigned deserialization, missing integrity checks |
| A09 | Logging Failures | Verify security events are logged, no sensitive data in logs |
| A10 | SSRF | Find user-controlled URLs passed to HTTP clients |

### Phase 3: Secret Detection
- Search for hardcoded credentials, API keys, tokens, and passwords
- Check for secrets in configuration files, environment files, and test fixtures
- Verify .gitignore covers sensitive files (.env, credentials, key files)
- Check git history for previously committed secrets (git log -p with targeted grep)

### Phase 4: Dependency CVE Analysis
- Read dependency lock files for exact versions
- Identify known vulnerable versions of common packages
- Check for outdated dependencies with known security patches
- Flag dependencies that are unmaintained or deprecated

### Phase 5: Report Generation
Produce a structured security report.

## Output Format

```
## Security Analysis Report

### Summary
- **Scope**: [files/directories analyzed]
- **Risk Level**: CRITICAL / HIGH / MEDIUM / LOW
- **Findings**: N total (X critical, Y high, Z medium, W low)

### Critical Findings
1. [CRITICAL] Description
   - Location: file:line
   - Evidence: [what was found]
   - Impact: [potential damage]
   - Remediation: [how to fix]

### OWASP Top 10 Results
| Category | Status | Findings |
|---|---|---|
| A01 Broken Access Control | PASS/WARN/FAIL | [details] |
| ... | ... | ... |

### Secret Detection
- Hardcoded secrets found: N
- Unprotected config files: N
- .gitignore coverage: ADEQUATE / INCOMPLETE

### Dependency Vulnerabilities
| Package | Version | CVE | Severity | Fix Version |
|---|---|---|---|---|
| ... | ... | ... | ... | ... |

### Recommendations
1. [Priority-ordered list of actions]
```

## Usage Examples

- `/security` -- Full codebase security scan
- `/security src/auth/` -- Scan authentication module
- `/security check for hardcoded secrets`
- `/security audit dependencies for CVEs`
- `/security review API endpoints for injection vulnerabilities`

## Notes

- This is a read-only analysis -- no files are modified
- For dependency CVE checks, rely on lock file versions and known vulnerability patterns
- Always check both source code and configuration files
- Report findings with exact file paths and line numbers when possible
