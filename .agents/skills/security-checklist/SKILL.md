---
name: security-checklist
description: "Use when reviewing plans or code for security issues - OWASP Top 10 compliance"
user-invocable: false
---

# Security Checklist

## Core Principle

**Security is not a feature - it is a constraint on every feature.** Every code change must be reviewed for security implications.

---

## Command Injection Prevention

### Risk: Severity CRITICAL

Any time user input reaches a system command, shell, or process execution.

**Rules:**
- NEVER concatenate user input into shell commands
- NEVER pass unsanitized input to process execution functions
- Use parameterized APIs instead of string interpolation
- Validate and sanitize all input before processing

**What to look for:** Search for any function in the codebase that spawns processes, runs shell commands, or interprets strings as system instructions. These include direct shell execution calls, subprocess invocations with shell=True, and runtime process execution methods.

**Safe alternatives:**
- Use process execution with argument arrays (not shell strings)
- Use parameterized APIs provided by libraries
- Use file-based execution (execFile) instead of shell-based execution
- Whitelist allowed commands rather than blacklisting dangerous ones

---

## Secrets Management

### Risk: Severity CRITICAL

Secrets (API keys, passwords, tokens) must never appear in code or logs.

**Rules:**
- NEVER hardcode secrets in source files
- NEVER commit secrets to version control
- NEVER log secrets or include them in error messages
- Load secrets from environment variables or secure vaults
- Rotate secrets if they are ever exposed

**What to search for:** Look for variable assignments where password, api_key, secret, or token fields are set to string literals.

**Checklist:**
- [ ] No hardcoded credentials in source code
- [ ] Environment files are in .gitignore
- [ ] Secrets are loaded from environment or vault
- [ ] Default/placeholder values do not work as real credentials
- [ ] Error messages do not expose secret values

---

## Logging Security

### Risk: Severity HIGH

Logs can leak sensitive information if not properly managed.

**Rules:**
- NEVER log passwords, tokens, or credentials
- NEVER log full credit card numbers or SSNs
- NEVER log session tokens or auth headers
- Mask sensitive data before logging (show last 4 chars max)
- Control log levels in production (no DEBUG in prod)

**Good practice:** Log the action and the actor, not the credentials. For example, log "User 123 authenticated successfully" instead of logging the password or token used.

---

## Path Traversal Prevention

### Risk: Severity HIGH

User-supplied file paths can escape intended directories.

**Rules:**
- NEVER use user input directly in file paths
- Validate paths are within expected directories
- Normalize paths before validation (resolve relative segments like ../)
- Use allowlists for file types and directories

**Safe approach:** Resolve the full canonical path of any user-supplied path, then verify it starts with the expected base directory prefix. Reject the request if the resolved path escapes the intended directory.

---

## Input Validation

### Risk: Severity HIGH

All input from external sources is untrusted.

**Rules:**
- Validate ALL input at system boundaries
- Use strong typing and schemas for input validation
- Reject invalid input rather than trying to sanitize it
- Validate length, format, range, and type
- Use allowlists over denylists when possible

**Input sources to validate:**

| Source | Examples |
|---|---|
| User input | Forms, query params, request bodies |
| File content | Uploaded files, config files |
| External APIs | Response data, webhook payloads |
| Database reads | Data may have been corrupted |
| Environment | Environment variables, system properties |

---

## SQL Injection Prevention

### Risk: Severity CRITICAL

User input in SQL queries can run arbitrary database commands.

**Rules:**
- ALWAYS use parameterized queries or prepared statements
- NEVER concatenate user input into SQL strings
- Use ORM methods that handle escaping automatically
- Validate and type-check input before query construction

**Safe approach:** Always use placeholder parameters (? or :name) in query strings and pass values as separate arguments. Never build SQL strings by concatenating user-provided values.

---

## Cross-Site Scripting (XSS) Prevention

### Risk: Severity HIGH

User input rendered in HTML can run arbitrary scripts.

**Rules:**
- Escape all user input before rendering in HTML
- Use framework-provided auto-escaping templates
- Sanitize HTML input with allowlisted tags only
- Set Content-Security-Policy headers
- Use HTTPOnly flag on session cookies

---

## Dynamic Code Interpretation Prevention

### Risk: Severity CRITICAL

Functions that interpret strings as executable code are dangerous with user input.

**Rules:**
- NEVER pass user input to functions that interpret strings as code
- NEVER use dynamic code interpretation for data parsing
- Use structured data parsers (JSON parsers, YAML libraries) instead
- If dynamic interpretation is truly needed, sandbox it completely

---

## Authentication and Authorization

### Risk: Severity CRITICAL

Every endpoint and operation must verify identity and permissions.

**Rules:**
- Verify authentication on every protected request
- Check authorization for every resource access
- Use constant-time comparison for tokens and secrets
- Implement rate limiting on authentication endpoints
- Lock accounts after repeated failed attempts

**Checklist:**
- [ ] All endpoints require authentication (unless explicitly public)
- [ ] Authorization checked for resource-level access
- [ ] Session management follows best practices
- [ ] Password storage uses strong hashing (bcrypt, argon2)
- [ ] Multi-factor authentication available for sensitive operations

---

## Severity Ratings Quick Reference

| Severity | Response Required | Examples |
|---|---|---|
| **CRITICAL** | Block release. Fix immediately. | SQL injection, RCE, auth bypass |
| **HIGH** | Fix before next release. | XSS, path traversal, info leak |
| **MEDIUM** | Fix within sprint. | Missing rate limit, verbose errors |
| **LOW** | Track for future fix. | Minor info disclosure, weak cipher |

---

## Security Review Checklist

Before approving any change:

- [ ] No hardcoded secrets
- [ ] No user input in shell commands
- [ ] No user input in SQL without parameterization
- [ ] No user input in file paths without validation
- [ ] No sensitive data in logs
- [ ] Authentication checked on all protected endpoints
- [ ] Authorization checked for resource access
- [ ] Input validated at all boundaries
- [ ] Error messages do not leak internal details
- [ ] Dependencies are up to date (no known CVEs)
