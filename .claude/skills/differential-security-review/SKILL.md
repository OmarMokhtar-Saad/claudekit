---
name: differential-security-review
description: Use when reviewing code changes for security regressions — detects removed security controls and newly introduced vulnerabilities via git diff analysis.
user-invocable: false
allowed-tools: Read, Bash, Grep, Glob
---

# Differential Security Review

## Core Principle

**Security regressions hide in diffs.** A change that removes a single authorization check can undo months of security work. Review every diff through the lens of what security properties may have been weakened.

---

## Git Diff Security Analysis

### Generating the Diff

```
# Compare against the base branch
git diff main...HEAD

# Show only files with security-relevant changes
git diff main...HEAD -- '*.py' '*.js' '*.ts' '*.go' '*.rs' '*.java' '*.yml' '*.yaml' '*.toml' '*.json'

# Show diff with function context for better understanding
git diff main...HEAD -U10 -W

# List changed files by category
git diff main...HEAD --stat
```

### Triage Changed Files by Risk

| File Pattern | Risk Level | Why |
|---|---|---|
| `auth/`, `login/`, `session/` | Critical | Authentication boundary |
| `middleware/`, `interceptor/` | Critical | Cross-cutting security controls |
| `*.yml`, `*.yaml`, `*.toml` (CI/config) | High | Infrastructure and permission changes |
| `Dockerfile`, `docker-compose.*` | High | Container security posture |
| `routes/`, `controllers/`, `handlers/` | High | New endpoints = new attack surface |
| `models/`, `schema/`, `migrations/` | Medium | Data model changes may affect access control |
| `test/`, `spec/` | Low | Tests rarely introduce vulnerabilities (but removing security tests is a red flag) |

---

## Removed Security Control Detection

### What to Search For in Deleted Lines

Scan all removed lines (lines starting with `-` in the diff) for security-relevant patterns:

| Category | Patterns to Flag |
|---|---|
| Authentication | `authenticate`, `requireAuth`, `isAuthenticated`, `verifyToken`, `jwt.verify` |
| Authorization | `authorize`, `checkPermission`, `hasRole`, `canAccess`, `isAllowed`, `rbac` |
| Input validation | `validate`, `sanitize`, `escape`, `zod.`, `joi.`, `yup.`, `class-validator` |
| Rate limiting | `rateLimit`, `throttle`, `slowDown`, `rateLimiter` |
| CSRF protection | `csrf`, `csrfToken`, `xsrf`, `_token` |
| Security headers | `helmet`, `Content-Security-Policy`, `X-Frame-Options`, `Strict-Transport-Security` |
| Encryption | `encrypt`, `hash`, `bcrypt`, `argon2`, `crypto.`, `scrypt` |
| Logging/audit | `audit`, `auditLog`, `securityLog`, `logAccess` |

### Removal Severity Matrix

| What Was Removed | Severity | Justification Required |
|---|---|---|
| Authentication middleware from a route | Critical | Must have written justification in PR description |
| Authorization check on resource access | Critical | Must have replacement or explicit reason |
| Input validation on user-facing endpoint | High | Must explain why validation is no longer needed |
| Rate limiting on authentication endpoint | High | Must have alternative protection |
| Security header configuration | Medium | Must explain the risk trade-off |
| Security-related test case | Medium | Must explain why the tested behavior is no longer relevant |

---

## New Attack Surface Identification

### New Endpoints

For every new route or endpoint added, verify:

- [ ] Authentication middleware is attached
- [ ] Authorization checks are present for resource access
- [ ] Input validation exists for all parameters (path, query, body, headers)
- [ ] Rate limiting is configured
- [ ] Response does not leak internal details on error

### New Dependencies

For every new dependency added to a manifest file:

- [ ] Package is from a known, trusted publisher
- [ ] Package has significant download count and community adoption
- [ ] No known CVEs at the added version
- [ ] License is compatible with the project
- [ ] Package does not introduce unnecessary transitive dependencies

### New Configuration

For every new configuration file or value:

- [ ] No secrets hardcoded in configuration
- [ ] Default values follow the principle of least privilege
- [ ] Debug/development settings are not enabled by default
- [ ] Network exposure (ports, hosts) is minimized

---

## Regression Patterns

### Common Security Regressions in Diffs

| Pattern | What It Looks Like | Risk |
|---|---|---|
| Broadened access | `role === 'admin'` changed to `role === 'admin' \|\| role === 'user'` | Privilege escalation |
| Weakened validation | Regex pattern simplified or length check removed | Input injection |
| Error detail exposure | `catch(e) { res.status(500) }` changed to `catch(e) { res.status(500).json(e) }` | Information leakage |
| Protocol downgrade | `https://` changed to `http://` or TLS version lowered | Man-in-the-middle |
| Algorithm downgrade | `sha256` changed to `md5` or `sha1` | Cryptographic weakness |
| Timeout increase | Connection or session timeouts significantly increased | Resource exhaustion |
| Disabled security feature | `secure: true` changed to `secure: false` | Protection bypass |

### Git History Analysis for Regressions

```
# Find commits that removed security-related code
git log --all -p -S "authenticate" -- '*.py' '*.js' '*.ts'

# Find reverts of security-related commits
git log --all --grep="revert" --grep="security\|auth\|fix\|vuln" --all-match

# Check for force-pushes that may have removed security commits
git reflog --all | grep "forced-update"
```

---

## Input Validation Changes

### Validation Weakening Indicators

Flag any diff that:
- Removes a `required` constraint from a schema
- Widens a numeric range (e.g., `max: 100` to `max: 10000`)
- Removes a string format check (email, URL, UUID)
- Changes a whitelist to a blacklist approach
- Removes or loosens a regular expression pattern
- Removes length constraints on string fields
- Changes `strict` mode to `loose` or permissive parsing

### Before/After Comparison Table

For each validation change found, document:

| Field | Before | After | Risk Assessment |
|---|---|---|---|
| (field name) | (previous constraint) | (new constraint) | (impact analysis) |

---

## Auth/Authz Boundary Modifications

### Authentication Boundary Checks

When authentication code changes, verify:

- [ ] Token validation logic is not weakened
- [ ] Session expiry is not extended without justification
- [ ] Password requirements are not reduced
- [ ] Multi-factor authentication is not made optional where it was required
- [ ] Login attempt limits are not increased or removed
- [ ] Account lockout policies are still enforced

### Authorization Boundary Checks

When authorization code changes, verify:

- [ ] No endpoint changed from authenticated to unauthenticated
- [ ] No resource changed from restricted to public
- [ ] Role hierarchy is not flattened (fewer roles with more permissions)
- [ ] Object-level authorization is still enforced (not just endpoint-level)
- [ ] Ownership checks on resources are not removed
- [ ] Default-deny is still the fallback behavior

### Cross-Cutting Concern Checklist

| Concern | What to Verify |
|---|---|
| Middleware ordering | Security middleware still executes before route handlers |
| Error handling | Security checks are not bypassed when exceptions occur |
| Async boundaries | Authorization is checked after async operations complete (no TOCTOU) |
| Caching | Authenticated responses are not cached and served to unauthenticated users |
| Logging | Security events (login, permission denied, input rejected) are still logged |

---

## Review Output Template

For each finding, report:

```
## [SEVERITY] Finding Title

**File:** path/to/file.ext (lines X-Y)
**Change Type:** Removed control | Weakened validation | New attack surface | Regression
**Diff Context:** (relevant diff snippet)
**Security Impact:** (what can an attacker now do that they could not before)
**Recommendation:** (specific fix or mitigation)
```
